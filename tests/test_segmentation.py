"""

Using the SegmentationDataset for segmenting cells using cellpose

"""

import os
import sys
sys.path.append('./src/')
import numpy as np
import pandas as pd
import geopandas as gpd
import json

from fusion_tools.dataset import SegmentationDataset
from wsi_annotations_kit import wsi_annotations_kit as wak

import large_image
from tqdm import tqdm
from cellpose import io, models, utils

import rasterio
import rasterio.features

from fusion_tools import Visualization
from fusion_tools.tileserver import LocalTileServer
from fusion_tools.components import SlideMap, OverlayOptions
import threading


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
    ]

    seg_dataset = SegmentationDataset(
        slides = slides,
        annotations = None,
        use_parallel=False,
        verbose = True,
        patch_mode = 'all',
        patch_region = 'all',
        patch_size = [2*224,2*224]
    )

    print(f'Number of patches = {len(seg_dataset)}')
    
    cell_model = models.CellposeModel(model_type='tissuenet_cp3',gpu=False)

    all_cells_gdf = gpd.GeoDataFrame()
    with tqdm(seg_dataset, total = len(seg_dataset)) as pbar:
        pbar.set_description('Predicting on patches in SegmentationDataset')
        for idx, (patch,_) in enumerate(seg_dataset):
            
            masks, _, _ = cell_model.eval(patch, diameter=10, cellprob_threshold = 0.0, channels=[0,0])

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
                    'name': 'Bounding Boxes'
                }
            }
            for i in seg_dataset.data
        ],
        'properties': {
            'name': 'Bounding Boxes'
        }
    }

    all_cells_geo = all_cells_gdf.to_geo_dict(show_bbox=False)
    all_cells_geo['properties'] = {'name': 'Segmented Cells'}
    with open(slides[0].replace('tiff','json'),'w') as f:
        json.dump(all_cells_geo,f)

        f.close()


    tile_server = LocalTileServer(
        local_image_path=slides[0]
    )

    new_thread = threading.Thread(
        target = tile_server.start,
        name = 'tile_server',
    )
    new_thread.daemon = True
    new_thread.start()

    vis = Visualization(
        components = [
            SlideMap(
                tile_server = tile_server,
                annotations = [all_cells_geo,bbox_geos]
            ),
            [
                OverlayOptions(
                    geojson_anns= [all_cells_geo,bbox_geos]
                )
            ]
        ]
    )
    vis.start()

if __name__=='__main__':
    main()
