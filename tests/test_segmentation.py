"""

Using the SegmentationDataset for segmenting cells using cellpose

"""
# This is for running with pipx environment, $ pipx run test_segmentation.py
# /// script
# dependencies = ["numpy","cellpose==3.1.0","fusion-tools[interactive]"]
# ///

with_predictions = True

import os
import sys
sys.path.append('./src/')
import numpy as np
import pandas as pd
import geopandas as gpd
import json

from fusion_tools.dataset import SegmentationDataset
#from wsi_annotations_kit import wsi_annotations_kit as wak

#import large_image
from tqdm import tqdm
if with_predictions:
    from cellpose import io, models, utils

import rasterio
import rasterio.features

from fusion_tools.visualization import Visualization
from fusion_tools.components import SlideMap, OverlayOptions

import uuid


def mask_to_shape(mask: np.ndarray, bbox: list)->list:

    mask_features = []
    for geo, val in rasterio.features.shapes(mask, mask = mask>0):
        mask_features.append({
            'type': 'Feature',
            'geometry': {
                'type': geo['type'],
                'coordinates': [[
                    [float(i[0]+bbox[0]),float(i[1]+bbox[1])]
                    for i in geo['coordinates'][0]
                ]]
            },
            'properties': {
                'name': 'Segmented Cell'
            }
        })
    
    return mask_features


def main():

    slides = [
        'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\Cropped_15-1 new merged.tiff'
        #'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\XY01_IU-21-015F.svs'
    ]

    seg_dataset = SegmentationDataset(
        slides = slides,
        annotations = None,
        use_parallel=False,
        verbose = True,
        patch_mode = 'all',
        patch_region = 'all',
        patch_size = [224,224]
    )

    print(seg_dataset.slide_data[0]['metadata'])
    print(f'Number of patches = {len(seg_dataset)}')
    
    if with_predictions:
        cell_model = models.CellposeModel(model_type='cyto3',gpu=False)

    all_cells_gdf = gpd.GeoDataFrame()
    if with_predictions:
        #import matplotlib.pyplot as plt
        with tqdm(seg_dataset, total = len(seg_dataset)) as pbar:
            for idx, (patch,_) in enumerate(seg_dataset):
                pbar.set_description(f'Predicting on patches in SegmentationDataset ({all_cells_gdf.shape[0]})')
                masks, _, _ = cell_model.eval([patch[:,:,0:2]], channel_axis = 2)
                masks = masks[0]
                if max(np.unique(masks))>0:
                    # Converting masks to annotations
                    mask_bbox = seg_dataset.data[idx]['bbox']
                    mask_geos = mask_to_shape(masks,mask_bbox)
                    if all_cells_gdf.empty:
                        all_cells_gdf = gpd.GeoDataFrame.from_features(mask_geos)

                    else:
                        new_cells = gpd.GeoDataFrame.from_features(mask_geos)
                        all_cells_gdf = pd.concat([all_cells_gdf,new_cells],axis=0,ignore_index=True)
                        merged_geoms = all_cells_gdf.union_all().geoms
                        all_cells_gdf = gpd.GeoDataFrame({'geometry': merged_geoms, 'name': ["Segmented Cells"]*len(merged_geoms)})

                pbar.update(1)

        pbar.close()
    
    # Adding the bounding boxes for patches:
    bbox_geos = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [i['bbox'][0],i['bbox'][1]],
                        [i['bbox'][2],i['bbox'][1]],
                        [i['bbox'][2],i['bbox'][3]],
                        [i['bbox'][0],i['bbox'][3]],
                        [i['bbox'][0],i['bbox'][1]]
                    ]],
                },
                'properties': {
                    'name': 'Bounding Boxes',
                    '_id': uuid.uuid4().hex[:24]
                }
            }
            for i in seg_dataset.data
        ],
        'properties': {
            'name': 'Bounding Boxes',
            '_id': uuid.uuid4().hex[:24]
        }
    }

    
    if with_predictions:
        all_cells_geo = all_cells_gdf.to_geo_dict(show_bbox=False)
        all_cells_geo['properties'] = {'name': 'Segmented Cells','_id': uuid.uuid4().hex[:24]}
        with open(slides[0].replace('tiff','json'),'w') as f:
            json.dump(all_cells_geo,f)

            f.close()

        local_annotations = [[bbox_geos,all_cells_geo]]
    else:
        local_annotations = [[bbox_geos]]

    local_slides = slides

    vis = Visualization(
        local_slides=local_slides,
        local_annotations=local_annotations,
        components = [
            SlideMap(),
            [
                OverlayOptions()
            ]
        ]
    )
    vis.start()

if __name__=='__main__':
    main()
