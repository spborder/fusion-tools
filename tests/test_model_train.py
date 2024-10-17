# %%

# Importing packages
import os
import sys
import json
sys.path.append('../src/')
#!{sys.executable} -m pip install segmentation-models-pytorch plotly kaleido==0.1.0 albumentations
#!{sys.executable} -m pip install nbformat
import numpy as np
from tqdm import tqdm
import pandas as pd

import torch
import torchvision
import segmentation_models_pytorch as smp
from torch.utils.data import DataLoader
from torchvision.transforms import ToTensor, Normalize
from torchvision.transforms.v2 import RandomHorizontalFlip, RandomVerticalFlip, ElasticTransform, ColorJitter, Compose
import albumentations as A

from typing import Callable, List
from fusion_tools.dataset import ClassificationDataset
from fusion_tools.utils.shapes import load_histomics
from math import floor

import plotly.express as px
import plotly.graph_objects as go

# %%
class CellClassificationModel(torch.nn.Module):
    def __init__(self,
                 output_size: int = 2,
                 simple: bool = True):
        super().__init__()
        self.output_size = output_size
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.simple = simple
        self.fc1 = torch.nn.LazyLinear(120)
        self.fc2 = torch.nn.Linear(120,84)
        self.fc3 = torch.nn.Linear(84,self.output_size)
        
        if self.simple:
            self.conv1 = torch.nn.Conv2d(3,6,5)
            self.pool = torch.nn.MaxPool2d(2,2)
            self.conv2 = torch.nn.Conv2d(6,16,5)

            self.conv_layers = torch.nn.Sequential(
                self.conv1,
                torch.nn.ReLU(inplace=True),
                self.pool,
                self.conv2,
                torch.nn.ReLU(inplace=True),
                self.pool
            )

        else:
            model_weights = torchvision.models.EfficientNet_V2_S_Weights
            self.conv_layers = torchvision.models.efficientnet_v2_s(weights = model_weights.DEFAULT)

        self.linear_layers = torch.nn.Sequential(
            self.fc1,
            torch.nn.ReLU(inplace=True),
            self.fc2,
            torch.nn.ReLU(inplace=True),
            self.fc3
        )

    def forward(self, input):
        
        output = self.conv_layers(input)
        output = torch.flatten(output,1)
        output = torch.nn.Sigmoid()(self.linear_layers(output))        
        return output


def cell_percentages(inp:list):
    if len(inp)>0:
        return torch.from_numpy(np.array([sum([-1*(i-1) for i in inp])/len(inp), sum(inp)/len(inp)]))
    else:
        return torch.from_numpy(np.array([1.0, 0.0]))

def train(train_data, val_data, model, optimizer, loss, output_dir):
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)
    loss.to(device)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    epoch_num = 5
    train_loss = 0
    val_loss = 0
    losses = []
    train_step_count = 0
    with tqdm(total = epoch_num, position = 0, leave = True, file = sys.stdout) as pbar:
        for i in range(0,epoch_num):
            for step, (train_imgs,train_labels) in enumerate(train_data):
                model.train()
                optimizer.zero_grad()

                pbar.set_description(f'Epoch: {i}/{epoch_num}, Train Step: {step}, Train/Val Loss: {round(train_loss,4)}/{round(val_loss,4)}')

                train_imgs = train_imgs.to(device)
                train_labels = train_labels.to(device)

                train_pred = model(train_imgs)

                train_loss = loss(train_pred, train_labels)
                train_loss.backward()
                train_loss = train_loss.item()

                optimizer.step()
                losses.append({
                    'step': train_step_count+step, 'loss': train_loss, 'Train/Val': 'train'
                })

                # Performing validation
                with torch.no_grad():
                    model.eval()
                    val_imgs, val_labels = next(iter(val_data))

                    val_imgs = val_imgs.to(device)
                    val_labels = val_labels.to(device)

                    val_pred = model(val_imgs)
                    val_loss = loss(val_pred, val_labels)
                    val_loss = val_loss.item()

                    losses.append(
                        {'step': train_step_count+step, 'loss': val_loss, 'Train/Val': 'val'}
                    )

            train_step_count+=step
            torch.save(model.state_dict(), output_dir+'Classification_Model.pth')
            loss_df = pd.DataFrame.from_records(losses)
            loss_df.to_csv(output_dir+'Loss.csv')
            vis_loss(loss_df,output_dir)

            pbar.update(1)


        pbar.update(1)
        torch.save(model.state_dict(), output_dir+'Classification_Model.pth')
        loss_df = pd.DataFrame.from_records(losses)
        loss_df.to_csv(output_dir+'Loss.csv')
        vis_loss(loss_df,output_dir)
        pbar.close()

def vis_loss(loss_df, output_dir):
    
    plot = px.line(
        data_frame=loss_df,
        x = 'step',
        y = 'loss',
        color = 'Train/Val'
    )

    plot.write_image(output_dir+'Loss_Plot.png')

def test(model_path, output_size, holdout_data, n):

    model = CellClassificationModel(
        output_size = output_size,
        simple=False
    )

    if torch.cuda.is_available():
        device = torch.device('cuda')
        model.load_state_dict(torch.load(model_path,weights_only=True))
    else:
        device = torch.device('cpu')
        model.load_state_dict(torch.load(model_path,weights_only=True,map_location = torch.device('cpu')))

    model.to(device)
    model.eval()

    test_dataloader = iter(DataLoader(holdout_data,batch_size=1,shuffle=False))

    with torch.no_grad():
        for idx in range(n):
            image,gt = next(test_dataloader)
            pred = model(image.to(device)).detach().cpu().numpy()

            image = np.moveaxis(np.squeeze(image.detach().cpu().numpy()),source=0,destination=-1)

            plot = go.Figure(
                px.imshow(image)
            )

            print(f'Predicted: {pred}, GT: {gt.cpu().numpy()}')



# %%
slides = [
    "40775.tif"
]
annotations = load_histomics('Cells.json')[0]

# Splitting the data into training and validation sets:
total_anns = len(annotations['features'])
train_test_split = 0.75
train_annotations = [{
    'type': 'FeatureCollection',
    'features': annotations['features'][:floor(train_test_split*total_anns)][0:15000],
    'properties': {'name': 'Train Cells'}
}]

val_annotations = [{
    'type': 'FeatureCollection',
    'features': annotations['features'][floor(train_test_split*total_anns):][0:8000],
    'properties': {'name': 'Validation Cells'}
}]

batch_size = 16

# Image augmentations (Normalization means and std are optimized for ImageNet pre-trained models)
train_transforms = Compose([
    RandomHorizontalFlip(p=0.5),
    RandomVerticalFlip(p=0.5),
    ColorJitter(),
    ToTensor(),
    Normalize(mean = [0.485, 0.456, 0.406], std = [0.229,0.224,0.225])
])

val_transforms = Compose([
    ToTensor(),
    Normalize(mean = [0.485,0.456, 0.406], std = [0.229, 0.224, 0.225])
])

# Converts list of labels per cell to proportions of each cell type
label_transform = lambda imm_list: cell_percentages(imm_list)

print('Starting dataset construction')
train_data = ClassificationDataset(
    slides = slides,
    annotations = train_annotations,
    label_property = 'Main_Cell_Types --> IMM',
    transforms = train_transforms,
    label_transforms = label_transform,
    use_cache = False,
    use_parallel=False,
    patch_mode = 'centered_bbox',
    verbose = True
)

val_data = ClassificationDataset(
    slides = slides,
    annotations = val_annotations,
    label_property = 'Main_Cell_Types --> IMM',
    transforms = val_transforms,
    label_transforms = label_transform,
    use_cache = False,
    use_parallel=False,
    patch_mode = 'centered_bbox',
    verbose = True
)

print(f'size of train_data: {sys.getsizeof(train_data.data)}, size of val_data: {sys.getsizeof(val_data.data)}')
print('Datasets prepared!')

train_dataloader = DataLoader(train_data, batch_size = batch_size, shuffle = True)
val_dataloader = DataLoader(val_data, batch_size = batch_size, shuffle = True)


# %%

model = CellClassificationModel(
    output_size = 2,
    simple = False
)

optimizer = torch.optim.Adam([
    dict(params = model.parameters(), lr = 5e-5, weight_decay = 0.00001)
])

loss = torch.nn.CrossEntropyLoss()


# %%
print('Starting Training!')
print(f'Number of steps per epoch: {round(len(train_data)/batch_size)}')
train(
    train_data = train_dataloader,
    val_data = val_dataloader,
    model = model,
    optimizer = optimizer,
    loss = loss,
    output_dir = './outputs/'
)


# %%
print('Starting Testing!')
test(
    model_path = './outputs/Classification_Model.pth',
    output_size = 2,
    holdout_data = val_data,
    n = 10
)



