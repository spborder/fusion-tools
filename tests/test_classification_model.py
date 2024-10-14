"""

Testing out segmentation model using the SegmentationDataset class

"""

import os
import sys
import json
sys.path.append('./src/')

import numpy as np
from tqdm import tqdm
import pandas as pd

import torch
import segmentation_models_pytorch as smp
from torch.utils.data import DataLoader
from torchvision.transforms import ToTensor
import albumentations as A

from typing import Callable, List
from fusion_tools.dataset import ClassificationDataset
from fusion_tools.utils.shapes import load_histomics
from math import floor

import plotly.express as px

# Bonus stuff for augmentations
class Repr:
    def __repr__(self):
        return f'{self.__class__.__name__}: {self.__dict__}'
    
class FunctionWrapperSingle(Repr):
    def __init__(self,
                 function: Callable,
                 *args,**kwargs):
        from functools import partial
        self.function = partial(function,*args,**kwargs)
        
    def __call__(self, inp:np.ndarray):
        return self.function(inp)

class FunctionWrapperDouble(Repr):
    def __init__(self, 
                 function: Callable, 
                 input: bool = True, 
                 target: bool = False, 
                 *args, **kwargs):

        from functools import partial
        self.function = partial(function,*args,**kwargs)
        self.input = input
        self.target = target

    def __call__(self, inp: np.ndarray, tar:dict):
        if self.input: inp = self.function(inp)
        if self.target: tar = self.function(tar)

        return inp, tar
    
class Compose:
    def __init__(self,
                 transforms: List[Callable]):
        
        self.transforms = transforms
    
    def __repr__(self):
        return str([transform for transform in self.transforms])

class ComposeSingle(Compose):
    def __call__(self, inp:np.ndarray):
        for t in self.transforms:
            inp = t(inp)

        return inp

class ComposeDouble(Compose):
    def __call__(self, inp: np.ndarray,target:dict):
        for t in self.transforms:
            inp, target = t(inp,target)
        
        return inp, target

class AlbuSeg1d(Repr):
    def __init__(self, albumentation: Callable):
        self.albumentation = albumentation

    def __call__(self, inp:np.ndarray):
        out_dict = self.albumentation(image = inp, mask = None)

        input_out = out_dict['image']

        return input_out

class AlbuSeg2d(Repr):
    def __init__(self, albumentation:Callable):
        self.albumentation = albumentation
    
    def __call__(self, inp:np.ndarray, tar: np.ndarray):
        out_dict = self.albumentation(image = inp, mask = tar)

        input_out = out_dict['image']
        target_out = out_dict['mask']

        return input_out, target_out


class CellClassificationModel(torch.nn.Module):
    def __init__(self,
                 output_size: int = 2):
        super().__init__()
        self.output_size = output_size
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        self.conv1 = torch.nn.Conv2d(3,6,5)
        self.pool = torch.nn.MaxPool2d(2,2)
        self.conv2 = torch.nn.Conv2d(6,16,5)
        self.fc1 = torch.nn.LazyLinear(120)
        self.fc2 = torch.nn.Linear(120,84)
        self.fc3 = torch.nn.Linear(84,self.output_size)
        
        self.conv_layers = torch.nn.Sequential(
            self.conv1,
            torch.nn.ReLU(inplace=True),
            self.pool,
            self.conv2,
            torch.nn.ReLU(inplace=True),
            self.pool
        )

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
        output = torch.nn.Softmax(dim=1)(self.linear_layers(output))        
        return output


def cell_percentages(inp:list):

    if len(inp)>0:
        return torch.from_numpy(np.array([inp.count(0.0)/len(inp), inp.count(1.0)/len(inp)]))
    else:
        return torch.from_numpy(np.array([1.0, 0.0]))

def normalize_01(inp:np.ndarray):
    out = (inp - np.min(inp))/ np.ptp(inp)
    return out

def train(train_data, val_data, model, optimizer, loss, output_dir):
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)
    loss.to(device)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    step_num = 1000
    save_step = 50
    train_loss = 0
    val_loss = 0
    losses = []
    with tqdm(total = step_num, position = 0, leave = True, file = sys.stdout) as pbar:
        for i in range(0,step_num):
            model.train()
            optimizer.zero_grad()

            pbar.set_description(f'Step: {i}/{step_num}, Train/Val Loss: {round(train_loss,4)}/{round(val_loss,4)}')
            pbar.update(1)

            train_imgs, train_labels = next(iter(train_data))
            train_imgs = train_imgs.to(device)
            train_labels = train_labels.to(device)

            train_pred = model(train_imgs)

            train_loss = loss(train_pred, train_labels)
            train_loss.backward()
            train_loss = train_loss.item()

            optimizer.step()
            losses.append({
                'step': i, 'loss': train_loss, 'Train/Val': 'train'
            })


            if i%save_step==0:
                with torch.no_grad():
                    model.eval()

                    val_imgs, val_labels = next(iter(val_data))
                    val_pred = model(val_imgs)
                    val_loss = loss(val_pred, val_labels)
                    val_loss = val_loss.item()

                    losses.append(
                        {'step': i, 'loss': val_loss, 'Train/Val': 'val'}
                    )

                    torch.save(model.state_dict(), output_dir+'Segmentation_Model.pth')
                    loss_df = pd.DataFrame.from_records(losses)
                    loss_df.to_csv(output_dir+'Loss.csv')
                    vis(losses,output_dir)



        pbar.set_description(f'Step: {i}/{step_num}, Train/Val Loss: {round(train_loss,4)}/{round(val_loss,4)}')
        pbar.update(1)

        torch.save(model.state_dict(), output_dir+'Segmentation_Model.pth')
        loss_df = pd.DataFrame.from_records(losses)
        loss_df.to_csv(output_dir+'Loss.csv')
        vis(losses,output_dir)
        pbar.close()

def test():
    pass

def vis(loss_df, output_dir):
    
    plot = px.line(
        data_frame=loss_df,
        x = 'step',
        y = 'loss',
        color = 'Train/Val'
    )

    plot.write_image(output_dir+'Loss_Plot.png')




def main():
    
    slides = [
        "C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\Xenium_Data\\40775.tif"
    ]
    annotations = load_histomics('C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\Xenium_Data\\Cells.json')[0]

    # Splitting the data into training and validation sets:
    total_anns = len(annotations['features'])
    train_test_split = 0.75
    train_annotations = [{
        'type': 'FeatureCollection',
        'features': annotations['features'][:floor(train_test_split*total_anns)],
        'properties': {'name': 'Train Cells'}
    }]

    val_annotations = [{
        'type': 'FeatureCollection',
        'features': annotations['features'][floor(train_test_split*total_anns):],
        'properties': {'name': 'Validation Cells'}
    }]

    batch_size = 16

    # Image augmentations
    train_transforms = ComposeSingle([
        AlbuSeg1d(A.HorizontalFlip(p=0.2)),
        AlbuSeg1d(A.VerticalFlip(p=0.2)),
        FunctionWrapperSingle(normalize_01),
        FunctionWrapperSingle(np.moveaxis, source = -1, destination = 0),
        FunctionWrapperSingle(np.float32),
        FunctionWrapperSingle(torch.from_numpy)
    ])

    val_transforms = ComposeSingle([
        FunctionWrapperSingle(normalize_01),
        FunctionWrapperSingle(np.moveaxis, source = -1, destination = 0),
        FunctionWrapperSingle(np.float32),
        FunctionWrapperSingle(torch.from_numpy)
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

    print('Datasets prepared!')

    train_dataloader = DataLoader(train_data, batch_size = batch_size, shuffle=True)
    val_dataloader = DataLoader(val_data, batch_size = batch_size, shuffle = True)

    model = CellClassificationModel(
        output_size = 2
    )

    optimizer = torch.optim.Adam([
        dict(params = model.parameters(), lr = 5e-7, weight_decay = 0.00001)
    ])

    loss = torch.nn.CrossEntropyLoss()

    print('Starting Training!')
    train(
        train_data = train_dataloader,
        val_data = val_dataloader,
        model = model,
        optimizer = optimizer,
        loss = loss,
        output_dir = './outputs/'
    )



if __name__=='__main__':
    main()

