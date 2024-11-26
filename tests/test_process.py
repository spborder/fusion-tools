# %% [markdown]
# ### Making annotations for *10x Visium* data
# 
# #### Step 1: (*external*) Convert *.RDS* file (SpaceRanger output) to *.h5ad*
# - This can be done using Seurat and SeuratDisk to go from *SeuratObject* -> *.h5Seurat* -> *.h5ad* see [this page](https://mojaveazure.github.io/seurat-disk/articles/convert-anndata.html) although the spot coordinates have to be added to the `seuratObject` manually in order to be added to the *.h5ad* file.
#     - Do this using:
#     
#         `seuratObject@meta.data[["spot_coordinates"]] <- cbind(seuratObject@meta.data, seuratObject@images[["slice1"]]@coordinates)`
# 
#     - **Important**:
#         - `Convert` will only save the *DefaultAssay* to the *X* matrix and will ignore all other assays. You can get around this by resetting the *DefaultAssay*:
# 
#             `DefaultAssay(seuratObject) <- "predsubclassl2"`
#     

# %% [markdown]
# #### Step 2: Create annotation files using *fusion-tools*

# %%
#%pip install fusion-tools[interactive]==2.3.3

# %%
import os
import sys
import json
sys.path.append('./src/')

import numpy as np
import pandas as pd

import anndata as ad
from tqdm import tqdm
import uuid

from shapely.geometry import Point, shape, Polygon
from shapely.ops import unary_union

from fusion_tools.utils.shapes import load_visium, spatially_aggregate
from fusion_tools.utils.omics import group_subtypes, selective_aggregation

visium_path = "..\\..\\Test Upload\\new Visium\\V12U21-010_XY02_21-0069.h5ad"

# This function will be in the next released version
spot_annotations = load_visium(visium_path)
anndata_object = ad.read_h5ad(visium_path)


# %% [markdown]
# ## Creating Cell Hierarchical labels

# %%
cell_groups_path = "..\\..\\Test Upload\\new Visium\\Supplementary Tables Version 1 05-2024.xlsx"
cell_groups = pd.read_excel(cell_groups_path,engine='openpyxl',sheet_name='Table S - sn annot',skiprows=range(4),index_col=0)
cell_groups = cell_groups[cell_groups["v2.subclass.l1"].notna()]

l1_types = cell_groups["v2.subclass.l1"].dropna(how='all').unique()
main_cell_grouping = {}
for l1 in l1_types:
    l2_types = cell_groups[cell_groups["v2.subclass.l1"].str.contains(l1)]["v2.subclass.l2"].tolist()
    main_cell_grouping[l1] = l2_types

print(json.dumps(main_cell_grouping,indent=4))


# %% [markdown]
# ## Adding Seurat Clusters as a sub-property for each spot

# %%
# Aligning annotations with cell subtype values and Seurat clusters (stored in obs):
pred_l2 = anndata_object.to_df().round(decimals = 5)
clusters = anndata_object.obs['seurat_clusters'].values
for row in range(pred_l2.shape[0]):
    row_data = pred_l2.iloc[row,:].to_dict()
    del row_data['max']

    spot_annotations['features'][row]['properties'] = spot_annotations['features'][row]['properties'] | {'L2 Cell Types': row_data, 'Seurat Cluster': str(clusters[row])}
    spot_annotations['features'][row]['properties'] = spot_annotations['features'][row]['properties'] | {"L1 Cell Types": group_subtypes({"L2": row_data},"L2",main_cell_grouping,keep_zeros=True)}
       


# %% [markdown]
# ## Extracting simple morphometrics for spots

# %%
from PIL import Image
from io import BytesIO
import large_image
from skimage.filters import threshold_otsu
from skimage.segmentation import watershed
from skimage import exposure
from skimage.color import rgb2hsv
import scipy.ndimage as ndi
from skimage.morphology import remove_small_holes, remove_small_objects
from skimage.measure import label, find_contours
from skimage.feature import peak_local_max
import matplotlib.pyplot as plt

from fusion_tools.feature_extraction import (
    ParallelFeatureExtractor, distance_transform_features, color_features,
    texture_features, morphological_features
)

if False:
    # define sub-compartment segmentation function
    def stain_mask(image,mask):

        seg_params = [
            {
                'name': 'Nuclei',
                'threshold': 150,
                'min_size': 40
            },
            {
                'name': 'Eosinophilic',
                'threshold': 30,
                'min_size': 20
            },
            {
                'name': 'Luminal Space',
                'threshold': 0,
                'min_size': 0
            }
        ]

        image_shape = np.shape(image)

        sub_comp_image = np.zeros((image_shape[0],image_shape[1],3))
        remainder_mask = np.ones((image_shape[0],image_shape[1]))

        hsv_image = np.uint8(255*rgb2hsv(image))
        hsv_image = hsv_image[:,:,1]

        for idx,param in enumerate(seg_params):

            # Check for if the current sub-compartment is nuclei
            if param['name'].lower()=='nuclei':
                # Using the inverse of the value channel for nuclei
                h_image = 255-np.uint8(255*rgb2hsv(image)[:,:,2])
                h_image = np.uint8(255*exposure.equalize_hist(h_image))

                remaining_pixels = np.multiply(h_image,remainder_mask)
                masked_remaining_pixels = np.multiply(remaining_pixels,mask)
                #masked_remaining_pixels = remaining_pixels

                # Applying manual threshold
                masked_remaining_pixels[masked_remaining_pixels<=param['threshold']] = 0
                masked_remaining_pixels[masked_remaining_pixels>0] = 1

                # Area threshold for holes is controllable for this
                sub_mask = remove_small_holes(masked_remaining_pixels>0,area_threshold=10)
                sub_mask = sub_mask>0
                # Watershed implementation from: https://scikit-image.org/docs/stable/auto_examples/segmentation/plot_watershed.html
                distance = ndi.distance_transform_edt(sub_mask)
                labeled_mask, _ = ndi.label(sub_mask)
                coords = peak_local_max(distance,footprint=np.ones((3,3)),labels = labeled_mask)
                watershed_mask = np.zeros(distance.shape,dtype=bool)
                watershed_mask[tuple(coords.T)] = True
                markers, _ = ndi.label(watershed_mask)
                sub_mask = watershed(-distance,markers,mask=sub_mask)
                sub_mask = sub_mask>0

                # Filtering out small objects again
                sub_mask = remove_small_objects(sub_mask,param['min_size'])

            else:

                remaining_pixels = np.multiply(hsv_image,remainder_mask)
                masked_remaining_pixels = np.multiply(remaining_pixels,mask)
                #masked_remaining_pixels = remaining_pixels

                # Applying manual threshold
                masked_remaining_pixels[masked_remaining_pixels<=param['threshold']] = 0
                masked_remaining_pixels[masked_remaining_pixels>0] = 1

                # Filtering by minimum size
                small_object_filtered = (1/255)*np.uint8(remove_small_objects(masked_remaining_pixels>0,param['min_size']))

                sub_mask = small_object_filtered

            sub_comp_image[sub_mask>0,idx] = 1
            remainder_mask -= sub_mask>0

        # Assigning remaining pixels within the boundary mask to the last sub-compartment
        #remaining_pixels = np.multiply(mask,remainder_mask)
        remaining_pixels = remainder_mask
        sub_comp_image[remaining_pixels>0,idx] = 1

        final_mask = np.zeros_like(remainder_mask)
        final_mask += sub_comp_image[:,:,0]
        final_mask += 2*sub_comp_image[:,:,1]
        final_mask += 3*sub_comp_image[:,:,2]

        return final_mask


    # Define feature extractor class
    feature_extractor = ParallelFeatureExtractor(
        image_source = "..\\..\\Test Upload\\new Visium\\V12U21-010_XY02_21-0069.tif",
        feature_list = [
                lambda image,mask,coords: distance_transform_features(image,mask,coords),
                lambda image,mask,coords: color_features(image,mask,coords),
                lambda image,mask,coords: texture_features(image,mask,coords),
                lambda image,mask,coords: morphological_features(image,mask,coords)
        ],
        preprocess = None,
        sub_mask = lambda image,mask: stain_mask(image,mask),
        mask_names = ['Nuclei','Eosinophilic','Luminal Space'],
        channel_names = ['Red','Green','Blue'],
        n_jobs = 4,
        verbose = True
    )
    # Execute feature extraction
    feature_df = feature_extractor.start(spot_annotations['features'])




    # %%
    # Add properties to spot annotations
    spot_features = feature_df.to_dict('records')
    for f,s in zip(spot_features,spot_annotations['features']):
        s['properties'] = s['properties'] | {"Pathomics": f}

    print(json.dumps(spot_annotations['features'][0]['properties'],indent=4))

# %% [markdown]
# ## Merging adjacent spots from the same cluster

# %%
# Merging adjacent spots based on Seurat cluster
poly_list = []
for f in spot_annotations['features']:
    poly_list.append(Point(shape(f['geometry']).centroid))

# Making the tissue mask
def find_tissue(slide_tile_source):

    # Grabbing the thumbnail of the image (RGB)
    slide_metadata = slide_tile_source.getMetadata()
    thumbnail_img,_ = slide_tile_source.getThumbnail()
    thumb_array = np.array(Image.open(BytesIO(thumbnail_img)))

    # Getting scale factors for thumbnail image to full-size image
    thumbX, thumbY = np.shape(thumb_array)[1],np.shape(thumb_array)[0]
    scale_x = slide_metadata['sizeX']/thumbX
    scale_y = slide_metadata['sizeY']/thumbY

    # Mean of all channels/frames to make grayscale mask
    gray_mask = np.squeeze(np.mean(thumb_array,axis=-1))

    threshold_val = 1.15*threshold_otsu(gray_mask)
    tissue_mask = gray_mask <= threshold_val

    tissue_mask = remove_small_holes(tissue_mask,area_threshold=150)
    tissue_mask = remove_small_objects(tissue_mask,min_size=64)

    #plt.imshow(tissue_mask)
    #plt.show()
    labeled_mask = label(tissue_mask)
    tissue_pieces = np.unique(labeled_mask).tolist()
    tissue_areas = [np.sum(labeled_mask==j) for j in tissue_pieces[1:]]
    largest_2 = [tissue_pieces[1:][tissue_areas.index(m)] for m in tissue_areas if m in sorted(tissue_areas)[-2:]]

    tissue_shape_list = []
    for piece in largest_2:
        if np.sum(labeled_mask==piece)>100:
            tissue_contours = find_contours(labeled_mask==piece)
            for contour in tissue_contours:
                poly_list = [(i[1]*scale_x,i[0]*scale_y) for i in contour]
                if len(poly_list)>2:
                    obj_polygon = Polygon(poly_list)
                    if obj_polygon.is_valid:
                        tissue_shape_list.append(obj_polygon)

    # Merging shapes together to remove holes
    merged_tissue = unary_union(tissue_shape_list)
    if merged_tissue.geom_type=='Polygon':
        merged_tissue = [merged_tissue]
    elif merged_tissue.geom_type in ['MultiPolygon','GeometryCollection']:
        merged_tissue = merged_tissue.geoms

    thumbnail_geojson = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type':'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [list(i.exterior.coords)]
                },
                'properties': {
                    'name': 'Tissue Mask',
                    '_id': uuid.uuid4().hex[:24],
                    '_index': idx
                }
            }
            for idx,i in enumerate(merged_tissue) if i.geom_type=='Polygon'
        ],
        'properties': {
            'name': 'Tissue Mask',
            '_id': uuid.uuid4().hex[:24]
        }
    }

    return thumbnail_geojson


tissue_mask = find_tissue(
    large_image.open('..\\..\\Test Upload\\new Visium\\V12U21-010_XY02_21-0069.tif')
)

unique_clusters = np.unique(clusters).tolist()
merged_geojson = []
for c in unique_clusters:
    c_idx = np.where(clusters==c)[0].tolist()

    cluster_spots = [poly_list[i] for i in c_idx]
    cluster_merges = {
        'type': 'FeatureCollection',
        'features': [],
        'properties': {
            'name': f'Cluster {c}',
            '_id': uuid.uuid4().hex[:24]
        }
    }
    for t in tissue_mask['features']:
        tissue_shape = shape(t['geometry'])
        within_tissue_spots = [i for i in cluster_spots if i.within(tissue_shape)]
        if len(within_tissue_spots)>0:
            # Buffering spots to a size that they start to intersect
            # (for Visium spots this is a little easier to define since all of the spots are separated 
            # by the same distance, for other structures this might have to be some kind of Voronoi diagram)
            buffered_spots = [i.buffer(100) for i in within_tissue_spots]

            # Merging buffered spots
            merged_spots = unary_union(buffered_spots)
            cluster_geojson = [
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [list(g.exterior.coords)]
                    },
                    'properties': {
                        'name': f'Cluster {c}',
                        '_id': uuid.uuid4().hex[:24],
                        '_index': g_idx
                    }
                }
                for g_idx,g in enumerate(merged_spots.geoms)
            ]

            cluster_merges['features'].extend(cluster_geojson)
            
    merged_geojson.append(cluster_merges)

spatially_agged = []
for m in merged_geojson:
    spatially_agged.append(spatially_aggregate(m,[spot_annotations]))


# %% [markdown]
# ## Visualization in *fusion-tools*

# %%
# Visualizing spots in fusion-tools
from fusion_tools.components import SlideMap,OverlayOptions,PropertyPlotter,HRAViewer, BulkLabels
from fusion_tools import Visualization

local_image_path = "..\\..\\Test Upload\\new Visium\\V12U21-010_XY02_21-0069.tif"

vis_session = Visualization(
    local_slides = [local_image_path],
    local_annotations = [spot_annotations],
    components = [
        [
            SlideMap(),
            [
                OverlayOptions(),
                PropertyPlotter(),
                BulkLabels(),
                HRAViewer()
            ]
        ]
    ],
    app_options = {
        'jupyter': False,
        'port': 8080
    }
)

vis_session.start()



