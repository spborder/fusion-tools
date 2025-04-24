"""

Dataset sub-module for fusion-tools

"""


import os
import sys
import random
import json
from math import floor

import large_image.constants
import numpy as np
import pandas as pd
import geopandas as gpd
import large_image
from tqdm import tqdm

from fusion_tools.utils.shapes import process_filters_queries

from shapely.geometry import shape, box, Polygon
from shapely.validation import make_valid
from shapely.ops import unary_union
from skimage.filters import threshold_otsu
from skimage.morphology import remove_small_holes, remove_small_objects
from skimage.measure import label, find_contours
from skimage.draw import polygon2mask
from PIL import Image
from io import BytesIO

from typing import Callable
from typing_extensions import Union

from joblib import Parallel, delayed


class FUSIONDataset:
    def __init__(self,
                 slides: list = [],
                 annotations: Union[list,dict,None] = None,
                 image_transforms: Union[Callable, None] = None,
                 target_transforms: Union[Callable, None] = None,
                 patch_size: list = [256,256],
                 patch_mode: str = 'bbox',
                 patch_region: Union[str,list,dict] = 'all',
                 overlap: Union[float,None] = None,
                 spatial_filters: Union[list,None] = None,
                 property_filters: Union[list,None] = None,
                 use_cache: bool = False,
                 shuffle: bool = True,
                 seed_val: int = 1701,
                 verbose: bool = False,
                 use_parallel: bool = True,
                 n_jobs: int = 1):
        
        self.slides = slides
        self.pre_annotations = annotations
        self.image_transforms = image_transforms
        self.target_transforms = target_transforms
        self.patch_size = patch_size
        self.patch_mode = patch_mode
        self.patch_region = patch_region
        self.overlap = overlap
        self.spatial_filters = spatial_filters
        self.property_filters = property_filters
        self.use_cache = use_cache
        self.shuffle = shuffle
        self.seed_val = seed_val
        self.verbose = verbose
        self.use_parallel = use_parallel
        self.n_jobs = n_jobs

        # Checking inputs
        assert self.patch_mode in ['all','even','overlap','bbox','centered_bbox','random_bbox']
        if self.pre_annotations is None:
            if 'bbox' in self.patch_mode:
                raise AssertionError('If no annotations are passed, patch_mode must be "all"')
        if type(self.patch_region)==str:
            assert self.patch_region in ['all','tissue']
        elif type(self.patch_region)==list:
            assert all([any([i==j for j in ['all','tissue']]) if type(i)==str else type(i)==dict for i in self.patch_region])
        
        # Setting seed for reproducibility (🖖)
        self.seed_val = seed_val
        self.plant_seed(seed_val)
        self.verbose = verbose
        self.use_parallel = use_parallel
        self.n_jobs = n_jobs

    def plant_seed(self, seed_val):

        random.seed(seed_val)
        os.environ["PYTHONHASHSEED"] = str(seed_val)
        np.random.seed(seed_val)
        #torch.manual_seed(seed_val)
        #torch.cuda.manual_seed(seed_val)

    def process_annotations(self):
        pass

    def gen_slide_patches(self):
        pass

    def find_tissue(self):
        pass

    def __len__(self):
        pass

    def __getitem__(self, idx:int):
        pass

    def __str__(self):
        pass




class SegmentationDataset:
    def __init__(self,
                 slides: list = [],
                 annotations: Union[list,dict,None] = None,
                 transforms: Union[None, Callable] = None,
                 target_transforms: Union[None, Callable] = None,
                 mask_key: Union[dict,None] = None,
                 patch_size: list = [256,256],
                 patch_mode: str = 'bbox',
                 patch_region: Union[str,list,dict] = 'all',
                 spatial_filters: Union[list,None] = None,
                 property_filters: Union[list,None] = None,
                 use_structures: Union[str,list] = 'all',
                 use_cache: bool = True,
                 shuffle: bool = True,
                 seed_val: int = 1701,
                 verbose: bool = False,
                 use_parallel: bool = True,
                 n_jobs: int = 1
                 ):
        
        self.slides = slides
        self.pre_annotations = annotations
        self.transforms = transforms
        self.target_transforms = target_transforms
        self.mask_key = mask_key
        self.patch_size = patch_size
        self.patch_mode = patch_mode
        self.patch_region = patch_region
        assert self.patch_mode in ['all','even','overlap','bbox','centered_bbox','random_bbox']
        if self.pre_annotations is None:
            if 'bbox' in self.patch_mode:
                raise AssertionError('If no annotations are passed, patch_mode must be "all"')
        if type(self.patch_region)==str:
            assert self.patch_region in ['all','tissue']
        elif type(self.patch_region)==list:
            assert all([any([i==j for j in ['all','tissue']]) if type(i)==str else type(i)==dict for i in self.patch_region])

        # These two (if not None) should both be lists of either dicts containing filters to apply
        # to all slides or lists of lists of filters to apply to each slide, can also be mixed with some 
        # filters applied to some slides and then None applied to others 
        # (see fusion_tools.shapes.process_filters_queries for specifications)
        self.spatial_filters = spatial_filters if not spatial_filters is None else []
        self.property_filters = property_filters if not property_filters is None else []
        
        self.use_structures = use_structures
        self.use_cache = use_cache
        self.shuffle = shuffle

        # Setting seed for reproducibility (🖖)
        self.seed_val = seed_val
        self.plant_seed(seed_val)
        self.verbose = verbose
        self.use_parallel = use_parallel
        self.n_jobs = n_jobs

        self.process_annotations()
        self.gen_slide_patches()

    def plant_seed(self, seed_val):

        random.seed(seed_val)
        os.environ["PYTHONHASHSEED"] = str(seed_val)
        np.random.seed(seed_val)
        #torch.manual_seed(seed_val)
        #torch.cuda.manual_seed(seed_val)
        
    def process_annotations(self):

        # Starting out with assuming all GeoJSON type
        all_names = []
        self.slide_annotation_names = []
        if not self.pre_annotations is None:
            if type(self.pre_annotations)==dict:
                self.annotations = [gpd.GeoDataFrame.from_features(self.pre_annotations['features'])]
                all_names.append(self.pre_annotations['properties']['name'])
                self.slide_annotation_names.extend(all_names)
            else:
                self.annotations = []
                for a in self.pre_annotations:
                    if type(a)==dict:
                        self.annotations.append(gpd.GeoDataFrame.from_features(a['features']))
                        all_names.append(a['properties']['name'])
                        self.slide_annotation_names.append([a['properties']['name']])
                    elif type(a)==list:
                        self.annotations.append([gpd.GeoDataFrame.from_features(b['features']) for b in a if type(b)==dict])
                        all_names.extend([b['properties']['name'] for b in a if type(b)==dict])        
                        self.slide_annotation_names.append([b['properties']['name'] for b in a if type(b)==dict])
            
            if self.mask_key is None:
                self.mask_key = {
                    name:idx
                    for idx,name in enumerate(list(set(all_names)))
                }
        else:
            self.annotations = [None for s in self.slides]
            self.slide_annotation_names = [None for s in self.slides]

    def gen_slide_patches(self):
         
        # Records-style list of bbox, feature or just bbox if no annotations are passed
        self.data = []
        self.slide_data = []
        # Iterating through
        for s_idx, (slide, pre_slide_annotations, annotation_names) in enumerate(zip(self.slides,self.annotations,self.slide_annotation_names)):
            single_slide_data = {}
            if type(slide)==str:
                slide_tile_source = large_image.open(slide)
            else:
                slide_tile_source = slide

            single_slide_data['image_source'] = slide_tile_source

            slide_metadata = slide_tile_source.getMetadata()
            single_slide_data['metadata'] = slide_metadata
            
            # Find available regions to extract patches from
            if type(self.patch_region)==str:
                if self.patch_region=='tissue':
                    available_regions = self.find_tissue(slide_tile_source, slide_metadata)
                elif self.patch_region=='all':
                    available_regions = {
                        'type': 'FeatureCollection',
                        'features': [{
                            'type': 'Feature',
                            'geometry': {
                                'type': 'Polygon',
                                'coordinates': [[
                                    [0,0],
                                    [0,slide_metadata['sizeY']],
                                    [slide_metadata['sizeX'],slide_metadata['sizeY']],
                                    [slide_metadata['sizeX'],0],
                                    [0,0]
                                ]]
                            },
                            'properties': {}
                        }]
                    }

            elif type(self.patch_region)==list:
                if type(self.patch_region[s_idx])==str:
                    if self.patch_region[s_idx]=='tissue':
                        available_regions = self.find_tissue(slide_tile_source,slide_metadata)
                    elif self.patch_region[s_idx]=='all':
                        available_regions = {
                            'type': 'FeatureCollection',
                            'features': [{
                                'type': 'Feature',
                                'geometry': {
                                    'type': 'Polygon',
                                    'coordinates': [[
                                        [0,0],
                                        [0,slide_metadata['sizeY']],
                                        [slide_metadata['sizeX'],slide_metadata['sizeY']],
                                        [slide_metadata['sizeX'],0],
                                        [0,0]
                                    ]]
                                },
                                'properties': {}
                            }]
                        }
                elif type(self.patch_region[s_idx])==dict:
                    available_regions = self.patch_region[s_idx]

            elif type(self.patch_region)==dict:
                available_regions = self.patch_region

            single_slide_data['available_regions'] = available_regions

            # Finding current annotations
            if not pre_slide_annotations is None:

                # Filtering annotations by available_regions
                if type(pre_slide_annotations)==dict:
                    available_slide_annotations = gpd.sjoin(
                        left_df = pre_slide_annotations,
                        right_df = gpd.GeoDataFrame.from_features(available_regions['features']),
                        how = 'inner',
                        predicate = 'intersects'
                    )

                    available_geo_dict = available_slide_annotations.to_geo_dict(show_bbox=True)
                    available_geo_dict['properties'] = {'name': annotation_names}
                    available_slide_annotations = [available_geo_dict]

                elif type(pre_slide_annotations)==list:
                    available_regions_gdf = gpd.GeoDataFrame.from_features(available_regions['features'])
                    available_slide_annotations = []
                    for s,a in zip(pre_slide_annotations,annotation_names):
                        filtered_s = gpd.sjoin(
                            left_df = s,
                            right_df = available_regions_gdf,
                            how = 'inner',
                            predicate = 'intersects'
                        )

                        filtered_geo_dict = filtered_s.to_geo_dict(show_bbox=True)
                        filtered_geo_dict['properties'] = {'name':a}
                        available_slide_annotations.append(
                            filtered_geo_dict
                        )

                # If spatial or property filters applied
                filtered_slide_annotations, filter_reference_list = process_filters_queries(self.property_filters, self.spatial_filters, [self.use_structures], available_slide_annotations)

                single_slide_data['filtered_annotations'] = filter_reference_list
            else:
                filtered_slide_annotations = {'features': []}
                single_slide_data['filtered_annotations'] = []

            self.slide_data.append(single_slide_data)
            slide_annotations_gdf = gpd.GeoDataFrame.from_features(filtered_slide_annotations['features'])
            # Finding patch coordinates
            if self.patch_mode=='all':
                available_regions_gdf = gpd.GeoDataFrame.from_features(available_regions['features'])
                available_bbox = available_regions_gdf.total_bounds

                x_start = np.maximum(int(self.patch_size[0]/2),int(available_bbox[0]+(self.patch_size[0]/2)))
                y_start = np.maximum(int(self.patch_size[1]/2),int(available_bbox[1]+(self.patch_size[1]/2)))
                n_x = floor((available_bbox[2]-available_bbox[0])/self.patch_size[0])
                n_y = floor((available_bbox[3]-available_bbox[1])/self.patch_size[1])

                bbox_list = []
                for x in range(0,n_x):
                    for y in range(0,n_y):

                        # Adding column of bboxes
                        bbox = [
                            int(x_start-(self.patch_size[0]/2)),
                            int(y_start-(self.patch_size[1]/2)),
                            int(x_start+(self.patch_size[0]/2)),
                            int(y_start+(self.patch_size[1]/2))
                        ]

                        if any(available_regions_gdf.intersects(box(*bbox)).tolist()):
                            bbox_list.append(bbox)

                        y_start+=self.patch_size[1]

                    bottom_row_bbox = [
                        int(x_start - (self.patch_size[0]/2)),
                        int(available_bbox[3]-self.patch_size[1]),
                        int(x_start + (self.patch_size[0]/2)),
                        int(available_bbox[3])
                    ]

                    if any(available_regions_gdf.intersects(box(*bottom_row_bbox)).tolist()):
                        bbox_list.append(bottom_row_bbox)
                    x_start += self.patch_size[0]
                    y_start = np.maximum(self.patch_size[1]/2,available_bbox[1]-(self.patch_size[1]/2))

                # Adding right-side column
                for y in range(0,n_y):
                    right_column_bbox = [
                        int(available_bbox[2] - self.patch_size[0]),
                        int(y_start - (self.patch_size[1]/2)),
                        int(available_bbox[2]),
                        int(y_start + (self.patch_size[1]/2))
                    ]

                    if any(available_regions_gdf.intersects(box(*right_column_bbox)).tolist()):
                        bbox_list.append(right_column_bbox)
                    y_start+=self.patch_size[1]

                # Adding bottom-right corner
                bottom_right_bbox = [
                    int(available_bbox[2]-self.patch_size[0]),
                    int(available_bbox[3]-self.patch_size[1]),
                    int(available_bbox[2]),
                    int(available_bbox[3])
                ]

                if any(available_regions_gdf.intersects(box(*bottom_right_bbox)).tolist()):
                    bbox_list.append(bottom_right_bbox)

            if self.patch_mode=='overlap':
                #TODO: add overlap patch_mode
                raise NotImplementedError

            if self.patch_mode== 'even':
                # 'even' means all patches within available_regions (with and without intersection with features)
                # Starting out with the bounding box of available regions
                available_bbox = gpd.GeoDataFrame.from_features(available_regions['features']).total_bounds

                # Assuming non-overlapping patches equally dispersed within this box (excludes bottom and right edge)
                x_coords = np.linspace(
                    start = int(available_bbox[0]+(self.patch_size[0]/2)),
                    stop = int(available_bbox[2]-(self.patch_size[0]/2)),
                    num = floor((available_bbox[2]-available_bbox[0])/self.patch_size[0])
                ).tolist()
                y_coords = np.linspace(
                    start = int(available_bbox[1]+(self.patch_size[1]/2)),
                    stop = int(available_bbox[3]-(self.patch_size[1]/2)),
                    num = floor((available_bbox[3]-available_bbox[1])/self.patch_size[1])
                ).tolist()
                # Adding last coordinate
                x_coords.append(np.maximum(int(available_bbox[0]-(self.patch_size[0]/2)),0+(self.patch_size[0]/2)))
                y_coords.append(np.maximum(int(available_bbox[1]-(self.patch_size[1]/2)),0+(self.patch_size[1]/2)))

                # Iterating through both and adding to self.data
                bbox_list = []
                for x in x_coords:
                    for y in y_coords:
                        bbox = [
                            int(x-(self.patch_size[0]/2)),
                            int(y-(self.patch_size[1]/2)),
                            int(x+(self.patch_size[0]/2)),
                            int(y+(self.patch_size[1]/2))
                        ]
                        bbox = [np.maximum(i,0) for i in bbox]
                        bbox_list.append(bbox)

            elif self.patch_mode=='bbox':
                # 'bbox' means each patch will be formed from the bbox of each feature (structure) (patches will initially be different sizes)
                bbox_list = []
                for i in filtered_slide_annotations['features']:
                    bbox = i['bbox']
                    bbox_list.append(bbox)

            elif self.patch_mode=='centered_bbox':
                # 'centered_bbox' means each patch uses the center of the bbox of each feature and expands out to "patch_size"
                centroids = [[(i['bbox'][0]+i['bbox'][2])/2, (i['bbox'][1]+i['bbox'][3])/2] for i in filtered_slide_annotations['features']]
                bbox_list = []
                for c in centroids:
                    bbox = [int(c[0]-(self.patch_size[0]/2)),int(c[1]-(self.patch_size[1]/2)),int(c[0]+(self.patch_size[0]/2)), int(c[1]+(self.patch_size[1]/2))]
                    bbox = [np.maximum(i,0) for i in bbox]
                    bbox_list.append(bbox)

            elif self.patch_mode=='random_bbox':
                # 'random_bbox' means each patch uses the center of the bbox of each feature and expands out to a random amount +/- 0.25 patch_size (patches will initially be different sizes)
                centroids = [[(i['bbox'][0]+i['bbox'][2])/2, (i['bbox'][1]+i['bbox'][3])/2] for i in filtered_slide_annotations['features']]
                width_list = [np.random.randint(int(self.patch_size[0]-(0.25*self.patch_size[0])),int(self.patch_size[0]+(0.25*self.patch_size[0]))) for i in range(len(centroids))]
                height_list = [np.random.randint(int(self.patch_size[1]-(0.25*self.patch_size[1])),int(self.patch_size[1]+(0.25*self.patch_size[1]))) for i in range(len(centroids))]

                bbox_list = []
                for c,w,h in zip(centroids,width_list,height_list):
                    bbox = [int(c[0]-(w/2)),int(c[1]-(h/2)),int(c[0]+(w/2)),int(c[1]+(h/2))]
                    bbox = [np.maximum(i,0) for i in bbox]
                    
                    bbox_list.append(bbox)

            if self.use_parallel:
                self.data.extend(Parallel(
                    n_jobs = self.n_jobs,
                    verbose = 50 if self.verbose else 0,
                    backend = 'threading',
                    return_as = 'list'
                )(
                    delayed(
                        self.make_patch
                    )(i,s_idx,slide_annotations_gdf)
                    for i in bbox_list
                ))
            else:
                if not self.verbose:
                    for i in bbox_list:
                        self.data.append(
                            self.make_patch(i,s_idx,slide_annotations_gdf)
                        )
                else:
                    for i in tqdm(bbox_list):
                        self.data.append(
                            self.make_patch(i,s_idx,slide_annotations_gdf)
                        )

        if self.shuffle:
            random.shuffle(self.data)

    def make_patch(self, bbox:list, slide_idx:int, annotations:gpd.GeoDataFrame):
        
        if not annotations.empty:
            features = annotations[annotations.intersects(box(*bbox))].to_geo_dict(show_bbox=True)['features']
        else:
            features = []

        if not self.use_cache:
            return_dict = {
                'bbox': bbox,
                'features': features,
                'slide_idx': slide_idx
            }
        else:
            image, mask = self.make_image_and_mask(bbox,slide_idx,features)

            return_dict = {
                'bbox': bbox,
                'features': features,
                'slide_idx': slide_idx,
                'image': image,
                'mask': mask
            }

        return return_dict

    def find_tissue(self, slide_tile_source, slide_metadata):
        
        # This process has variable success and most likely will not work the same for all tissues
        if not 'frames' in slide_metadata:
                # Grabbing the thumbnail of the image (RGB)
                thumbnail_img,_ = slide_tile_source.getThumbnail()
                thumb_array = np.array(Image.open(BytesIO(thumbnail_img)))

        else:
            # Getting the max projection of the thumbnail
            thumb_frame_list = []
            for f in range(len(slide_metadata['frames'])):
                thumb,_ = slide_tile_source.getThumbnail()
                thumb = np.array(Image.open(BytesIO(thumb)))
                thumb_frame_list.append(np.max(thumb,axis=-1)[:,:,None])

            thumb_array = np.concatenate(tuple(thumb_frame_list),axis=-1)

        print(f'shape of thumbnail array: {np.shape(thumb_array)}')
        # Getting scale factors for thumbnail image to full-size image
        thumbX, thumbY = np.shape(thumb_array)[1],np.shape(thumb_array)[0]
        scale_x = slide_metadata['sizeX']/thumbX
        scale_y = slide_metadata['sizeY']/thumbY

        #thumb_array = 255-thumb_array

        # Mean of all channels/frames to make grayscale mask
        gray_mask = np.squeeze(np.mean(thumb_array,axis=-1))

        threshold_val = threshold_otsu(gray_mask)
        tissue_mask = gray_mask <= threshold_val

        print(f'threshold: {threshold_val}')
        tissue_mask = remove_small_holes(tissue_mask,area_threshold=150)
        tissue_mask = remove_small_objects(tissue_mask)

        labeled_mask = label(tissue_mask)
        tissue_pieces = np.unique(labeled_mask).tolist()
        print(f'Found: {len(tissue_pieces)-1} tissue pieces!')
        tissue_shape_list = []
        for piece in tissue_pieces[1:]:
            tissue_contours = find_contours(labeled_mask==piece)

            for contour in tissue_contours:

                poly_list = [(i[1]*scale_x,i[0]*scale_y) for i in contour]
                if len(poly_list)>2:
                    obj_polygon = Polygon(poly_list)

                    if not obj_polygon.is_valid:
                        made_valid = make_valid(obj_polygon)

                        if made_valid.geom_type=='Polygon':
                            tissue_shape_list.append(made_valid)
                        elif made_valid.geom_type in ['MultiPolygon','GeometryCollection']:
                            for g in made_valid.geoms:
                                if g.geom_type=='Polygon':
                                    tissue_shape_list.append(g)
                    else:
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
                {'type':'Feature','properties': {}, 'geometry': {'type': 'Polygon','coordinates': [list(i.exterior.coords)]}}
                for i in merged_tissue if i.geom_type=='Polygon'
            ]
        }

        return thumbnail_geojson

    def make_image_and_mask(self, bbox:list, slide_idx:int, features: list):
        
        image_source = self.slide_data[slide_idx]['image_source']
        if not 'frames' in self.slide_data[slide_idx]['metadata']:
            image,_ = image_source.getRegion(
                format = large_image.constants.TILE_FORMAT_NUMPY,
                region = {
                    'left': bbox[0],
                    'top': bbox[1],
                    'right': bbox[2],
                    'bottom': bbox[3]
                }
            )
        else:
            image = np.zeros((int(bbox[3]-bbox[1]),int(bbox[2]-bbox[0]),len(self.slide_data[slide_idx]['metadata']['frames'])))
            
            for f in range(len(self.slide_data[slide_idx]['metadata']['frames'])):
                image_frame,_ = image_source.getRegion(
                    format = large_image.constants.TILE_FORMAT_NUMPY,
                    region = {
                        'left': bbox[0],
                        'top': bbox[1],
                        'right': bbox[2],
                        'bottom': bbox[3]
                    },
                    frame = f
                )
                image[:,:,f] += np.squeeze(image_frame)


        if len(features)>0:
            mask = np.zeros((int(bbox[3]-bbox[1]),int(bbox[2]-bbox[0]),len(list(self.mask_key.keys()))))
            bbox_box = box(*bbox)
            height = int(bbox[3]-bbox[1])
            width = int(bbox[2]-bbox[0])
            for f in features:
                feature_shape = shape(f['geometry'])
                bbox_intersection = feature_shape.intersection(bbox_box)

                if bbox_intersection.area>0 and bbox_intersection.geom_type=='Polygon':
                    int_coords = np.array(list(bbox_intersection.exterior.coords))
                    min_x = bbox[0]
                    min_y = bbox[1]

                    scaled_coords = np.flip(np.squeeze(int_coords) - np.array([min_x, min_y]),axis=1)
                    f_mask = polygon2mask(
                        image_shape = (height,width),
                        polygon = scaled_coords
                    ).astype(int)

                    mask[:,:,self.mask_key[f['properties']['name']]] += f_mask
                
                elif bbox_intersection.area>0 and bbox_intersection.geom_type=='GeometryCollection':
                    for g in bbox_intersection.geoms:
                        if g.geom_type=='Polygon':
                            int_coords = np.array(list(g.exterior.coords))
                            min_x = bbox[0]
                            min_y = bbox[1]

                            scaled_coords = np.flip(np.squeeze(int_coords) - np.array([min_x, min_y]),axis=1)
                            f_mask = polygon2mask(
                                image_shape = (height,width),
                                polygon = scaled_coords
                            ).astype(int)

                            mask[:,:,self.mask_key[f['properties']['name']]] += f_mask

        else:
            mask = np.zeros((int(bbox[3]-bbox[1]),int(bbox[2]-bbox[0])))


        return image, mask

    def get_next_image(self, idx:int):
        
        next_data = self.data[idx]

        if self.use_cache:
            image = next_data['image']
            mask = next_data['mask']

        else:
            image, mask = self.make_image_and_mask(next_data['bbox'], next_data['slide_idx'], next_data['features'])
        
        return image, mask

    def __len__(self):
        return len(self.data)

    def __getitem__(self,idx):
        
        image, mask = self.get_next_image(idx)

        if self.transforms:
            image = self.transforms(image)

        if self.target_transforms:
            mask = self.target_transforms(mask)

        return image, mask

    def __str__(self):
        
        key_configs = {
            'slide_data': [
                {i:j for i,j in k.items() if not i=='image_source'}
                for k in self.slide_data
            ],
            'patches': {
                'region': self.patch_region,
                'mode': self.patch_mode,
                'size': self.patch_size
            },
            'property_filters': self.property_filters,
            'spatial_filters': self.spatial_filters,
            'mask_key': self.mask_key,
            'use_structures': self.use_structures,
            'use_cache': self.use_cache,
            'shuffle': self.shuffle,
            'seed_val': self.seed_val
        }

        return json.dumps(key_configs)

    def export_configs(self, save_path: str):
        
        # mask_key, patch_size, patch_mode, patch_region
        # spatial filters, property_filters, use_structures, use_cache, shuffle, seed_val
        key_configs = {
            'slide_data': [
                {i:j for i,j in k.items() if not i=='image_source'}
                for k in self.slide_data
            ],
            'patches': {
                'region': self.patch_region,
                'mode': self.patch_mode,
                'size': self.patch_size
            },
            'property_filters': self.property_filters,
            'spatial_filters': self.spatial_filters,
            'mask_key': self.mask_key,
            'use_structures': self.use_structures,
            'use_cache': self.use_cache,
            'shuffle': self.shuffle,
            'seed_val': self.seed_val
        }

        with open(save_path,'w') as f:
            json.dump(key_configs, f, indent=4)


class ClassificationDataset:
    def __init__(self,
                 slides: list = [],
                 annotations: Union[list,dict,None] = None,
                 label_property: Union[list,str,None] = None,
                 transforms: Union[None, Callable] = None,
                 label_transforms: Union[None, Callable] = None,
                 patch_size: list = [256,256],
                 patch_mode: str = 'bbox',
                 patch_region: Union[str,list,dict] = 'all',
                 spatial_filters: Union[list,None] = None,
                 property_filters: Union[list,None] = None,
                 use_structures: Union[str,list] = 'all',
                 use_cache: bool = True,
                 shuffle: bool = True,
                 seed_val: int = 1701,
                 verbose: bool = False,
                 use_parallel: bool = True,
                 n_jobs: int = 1
                 ):
        
        self.slides = slides
        self.pre_annotations = annotations
        self.label_property = label_property
        self.transforms = transforms
        self.label_transforms = label_transforms

        self.patch_size = patch_size
        self.patch_mode = patch_mode
        if self.pre_annotations is None:
            if 'bbox' in self.patch_mode:
                raise AssertionError('If no annotations are passed, patch_mode must be "all"')
        self.patch_region = patch_region
        if type(self.patch_region)==str:
            assert self.patch_region in ['all','tissue']
        elif type(self.patch_region)==list:
            assert all([any([i==j for j in ['all','tissue']]) if type(i)==str else type(i)==dict for i in self.patch_region])
        self.spatial_filters = spatial_filters if not spatial_filters is None else []
        self.property_filters = property_filters if not property_filters is None else []
        
        self.use_structures = use_structures
        self.use_cache = use_cache
        self.shuffle = shuffle
        self.seed_val = seed_val

        # Setting seed for reproducibility (🖖)
        self.seed_val = seed_val
        self.plant_seed(seed_val)
        self.verbose = verbose
        self.use_parallel = use_parallel
        self.n_jobs = n_jobs
        self.process_annotations()
        self.gen_slide_patches()

    def plant_seed(self, seed_val):

        random.seed(seed_val)
        os.environ["PYTHONHASHSEED"] = str(seed_val)
        np.random.seed(seed_val)
        #torch.manual_seed(seed_val)
        #torch.cuda.manual_seed(seed_val)
        
    def process_annotations(self):

        # Starting out with assuming all GeoJSON type
        self.slide_annotation_names = []
        if not self.pre_annotations is None:
            if type(self.pre_annotations)==dict:
                self.annotations = [gpd.GeoDataFrame.from_features(self.pre_annotations['features'])]
                self.slide_annotation_names.append(self.pre_annotations['properties']['name'])
            else:
                self.annotations = []
                for a in self.pre_annotations:
                    if type(a)==dict:
                        self.annotations.append([gpd.GeoDataFrame.from_features(a['features'])])
                        self.slide_annotation_names.append([a['properties']['name']])
                    elif type(a)==list:
                        self.annotations.append([gpd.GeoDataFrame.from_features(b['features']) for b in a if type(b)==dict])
                        self.slide_annotation_names.append([b['properties']['name'] for b in a if type(b)==dict])
        else:       
            self.annotations = None

    def gen_slide_patches(self):
        
        # Records-style list of bbox, feature or just bbox if no annotations are passed
        self.data = []
        self.slide_data = []

        # Iterating through
        for s_idx, (slide,pre_slide_annotations,annotation_names) in enumerate(zip(self.slides, self.annotations, self.slide_annotation_names)):
            single_slide_data = {}
            if type(slide)==str:
                slide_tile_source = large_image.open(slide)
            else:
                slide_tile_source = slide

            single_slide_data['image_source'] = slide_tile_source

            slide_metadata = slide_tile_source.getMetadata()
            single_slide_data['metadata'] = slide_metadata
            
            # Find available regions to extract patches from
            if type(self.patch_region)==str:
                if self.patch_region=='tissue':
                    available_regions = self.find_tissue(slide_tile_source,slide_metadata)
                elif self.patch_region=='all':
                    available_regions = {
                        'type': 'FeatureCollection',
                        'features': [{
                            'type': 'Feature',
                            'geometry': {
                                'type': 'Polygon',
                                'coordinates': [[
                                    [0,0],
                                    [0,slide_metadata['sizeY']],
                                    [slide_metadata['sizeX'],slide_metadata['sizeY']],
                                    [slide_metadata['sizeX'],0],
                                    [0,0]
                                ]]
                            },
                            'properties': {}
                        }]
                    }

            elif type(self.patch_region)==list:
                if type(self.patch_region[s_idx])==str:
                    if self.patch_region[s_idx]=='tissue':
                        available_regions = self.find_tissue(slide_tile_source,slide_metadata)
                    elif self.patch_region[s_idx]=='all':
                        available_regions = {
                            'type': 'FeatureCollection',
                            'features': [{
                                'type': 'Feature',
                                'geometry': {
                                    'type': 'Polygon',
                                    'coordinates': [[
                                        [0,0],
                                        [0,slide_metadata['sizeY']],
                                        [slide_metadata['sizeX'],slide_metadata['sizeY']],
                                        [slide_metadata['sizeX'],0],
                                        [0,0]
                                    ]]
                                },
                                'properties': {}
                            }]
                        }
                elif type(self.patch_region[s_idx])==dict:
                    available_regions = self.patch_region[s_idx]

            elif type(self.patch_region)==dict:
                available_regions = self.patch_region

            single_slide_data['available_regions'] = available_regions

            # Finding current annotations
            if not self.annotations is None:

                # Filtering annotations by available_regions
                if type(pre_slide_annotations)==gpd.GeoDataFrame:
                    available_slide_annotations = gpd.sjoin(
                        left_df = pre_slide_annotations,
                        right_df = gpd.GeoDataFrame.from_features(available_regions['features']),
                        how = 'inner',
                        predicate = 'intersects'
                    )

                    available_geo_dict = available_slide_annotations.to_geo_dict(show_bbox=True)
                    available_geo_dict['properties'] = {'name': annotation_names}
                    available_slide_annotations = [available_geo_dict]

                elif type(pre_slide_annotations)==list:
                    available_regions_gdf = gpd.GeoDataFrame.from_features(available_regions['features'])
                    available_slide_annotations = []
                    for s,a in zip(pre_slide_annotations,annotation_names):
                        filtered_s = gpd.sjoin(
                            left_df = s,
                            right_df = available_regions_gdf,
                            how = 'inner',
                            predicate = 'intersects'
                        )

                        filtered_geo_dict = filtered_s.to_geo_dict(show_bbox=True)
                        filtered_geo_dict['properties'] = {'name': a}
                        available_slide_annotations.append(
                            filtered_geo_dict
                        )


                # If spatial or property filters applied
                filtered_slide_annotations, filter_reference_list = process_filters_queries(self.property_filters, self.spatial_filters, [self.use_structures], available_slide_annotations)

                single_slide_data['filtered_annotations'] = filter_reference_list
            else:
                filtered_slide_annotations = {'features': []}
                single_slide_data['filtered_annotations'] = []

            self.slide_data.append(single_slide_data)      
            slide_annotations_gdf = gpd.GeoDataFrame.from_features(filtered_slide_annotations['features'])
            # Finding patch coordinates
            if self.patch_mode== 'all':
                # 'all' means all patches within available_regions (with and without intersection with features)
                # Starting out with the bounding box of available regions
                available_bbox = gpd.GeoDataFrame.from_features(available_regions['features']).total_bounds

                # Assuming non-overlapping patches equally dispersed within this box (excludes bottom and right edge)
                x_coords = np.linspace(
                    start = int(available_bbox[0]+(self.patch_size[0]/2)),
                    stop = int(available_bbox[2]-(self.patch_size[0]/2)),
                    num = floor((available_bbox[2]-available_bbox[0])/self.patch_size[0])
                ).tolist()
                y_coords = np.linspace(
                    start = int(available_bbox[1]+(self.patch_size[1]/2)),
                    stop = int(available_bbox[3]-(self.patch_size[1]/2)),
                    num = floor((available_bbox[3]-available_bbox[1])/self.patch_size[1])
                ).tolist()
                # Adding last coordinate
                x_coords.append(np.maximum(int(available_bbox[0]-(self.patch_size[0]/2)),0+(self.patch_size[0]/2)))
                y_coords.append(np.maximum(int(available_bbox[1]-(self.patch_size[1]/2)),0+(self.patch_size[1]/2)))

                # Iterating through both and adding to self.data
                bbox_list = []
                for x in x_coords:
                    for y in y_coords:
                        bbox = [
                            int(x-(self.patch_size[0]/2)),
                            int(y-(self.patch_size[1]/2)),
                            int(x+(self.patch_size[0]/2)),
                            int(y+(self.patch_size[1]/2))
                        ]
                        bbox = [np.maximum(i,0) for i in bbox]
                        bbox_list.append(bbox)

            elif self.patch_mode=='bbox':
                # 'bbox' means each patch will be formed from the bbox of each feature (structure) (patches will initially be different sizes)
                bbox_list = []
                for i in filtered_slide_annotations['features']:
                    bbox = i['bbox']
                    bbox_list.append(bbox)

            elif self.patch_mode=='centered_bbox':
                # 'centered_bbox' means each patch uses the center of the bbox of each feature and expands out to "patch_size"
                centroids = [[(i['bbox'][0]+i['bbox'][2])/2, (i['bbox'][1]+i['bbox'][3])/2] for i in filtered_slide_annotations['features']]

                bbox_list = []
                for c in centroids:
                    bbox = [int(c[0]-(self.patch_size[0]/2)),int(c[1]-(self.patch_size[1]/2)),int(c[0]+(self.patch_size[0]/2)), int(c[1]+(self.patch_size[1]/2))]
                    bbox = [np.maximum(i,0) for i in bbox]

                    bbox_list.append(bbox)

            elif self.patch_mode=='random_bbox':
                # 'random_bbox' means each patch uses the center of the bbox of each feature and expands out to a random amount +/- 0.25 patch_size (patches will initially be different sizes)
                centroids = [[(i['bbox'][0]+i['bbox'][2])/2, (i['bbox'][1]+i['bbox'][3])/2] for i in filtered_slide_annotations['features']]
                width_list = [np.random.randint(int(self.patch_size[0]-(0.25*self.patch_size[0])),int(self.patch_size[0]+(0.25*self.patch_size[0]))) for i in range(len(centroids))]
                height_list = [np.random.randint(int(self.patch_size[1]-(0.25*self.patch_size[1])),int(self.patch_size[1]+(0.25*self.patch_size[1]))) for i in range(len(centroids))]

                bbox_list = []
                for c,w,h in zip(centroids,width_list,height_list):
                    bbox = [int(c[0]-(w/2)),int(c[1]-(h/2)),int(c[0]+(w/2)),int(c[1]+(h/2))]
                    bbox = [np.maximum(i,0) for i in bbox]

                    bbox_list.append(bbox)

            if self.use_parallel:
                self.data.extend(Parallel(
                    n_jobs = self.n_jobs,
                    verbose = 50 if self.verbose else 0,
                    backend = 'threading',
                    return_as = 'list'
                )(
                    delayed(
                        self.make_patch
                    )(i,s_idx,slide_annotations_gdf)
                    for i in bbox_list
                ))
            else:
                if not self.verbose:
                    for i in bbox_list:
                        self.data.append(
                            self.make_patch(i,s_idx,slide_annotations_gdf)
                        )
                else:
                    for i in tqdm(bbox_list):
                        self.data.append(
                            self.make_patch(i,s_idx,slide_annotations_gdf)
                        )

        if self.shuffle:
            random.shuffle(self.data)

    def make_patch(self,bbox:list, slide_idx: int, annotations:gpd.GeoDataFrame):

        features = annotations[annotations.intersects(box(*bbox))].to_geo_dict(show_bbox=True)['features']

        if not self.use_cache:
            return_dict = {
                'bbox': bbox,
                'features': features,
                'slide_idx': slide_idx
            }
        else:
            image, label = self.make_image_and_label(bbox,slide_idx,features)

            return_dict = {
                'bbox': bbox,
                'features': features,
                'slide_idx': slide_idx,
                'image': image,
                'label': label
            }

        return return_dict

    def make_image_and_label(self, bbox:list, slide_idx:int, features: list):

        image_source = self.slide_data[slide_idx]['image_source']
        if not 'frames' in self.slide_data[slide_idx]['metadata']:
            image,_ = image_source.getRegion(
                format = large_image.constants.TILE_FORMAT_NUMPY,
                region = {
                    'left': bbox[0],
                    'top': bbox[1],
                    'right': bbox[2],
                    'bottom': bbox[3]
                }
            )
        else:
            image = np.zeros((int(bbox[3]-bbox[1]),int(bbox[2]-bbox[0]),len(self.slide_data[slide_idx]['metadata']['frames'])))
            for f in range(len(self.slide_data[slide_idx]['metadata']['frames'])):
                image_frame,_ = image_source.getRegion(
                    format = large_image.constants.TILE_FORMAT_NUMPY,
                    region = {
                        'left': bbox[0],
                        'top': bbox[1],
                        'right': bbox[2],
                        'bottom': bbox[3]
                    },
                    frame = f
                )
                image[:,:,f] += image_frame

        # For now this will return multiple "labels" depending on the number of structures that intersect with this bbox, label_transforms can prune this if needed
        label = []
        for f in features:
            if type(self.label_property)==str:
                label_list = [self.label_property]
            elif type(self.label_property)==list:
                label_list = self.label_property

            for l_p in label_list:
                if not '-->' in l_p:
                    if l_p in f['properties']:
                        try:
                            label.append(float(f['properties'][l_p]))
                        except ValueError:
                            label.append(f['properties'][l_p])
                else:
                    l_parts = l_p.split(' --> ')
                    f_props_copy = f['properties'].copy()
                    for l in l_parts:
                        if not f_props_copy is None:
                            if l in f_props_copy:
                                f_props_copy = f_props_copy[l]
                            else:
                                f_props_copy = None
                    
                    if not f_props_copy is None:
                        try:
                            label.append(float(f_props_copy))
                        except ValueError:
                            label.append(f_props_copy)
                    else:
                        label.append(float(0))
        
        return image, label

    def get_next_image(self, idx:int):
        
        next_data = self.data[idx]

        if self.use_cache:
            image = next_data['image']
            label = next_data['label']

        else:
            image, label = self.make_image_and_label(next_data['bbox'], next_data['slide_idx'], next_data['features'])
        
        return image, label

    def __len__(self):
        return len(self.data)

    def __getitem__(self,idx):
        image, label = self.get_next_image(idx)

        if self.transforms:
            image = self.transforms(image)

        if self.label_transforms:
            label = self.label_transforms(label)

        return image, label

    def __str__(self):
        
        key_configs = {
            'slide_data': [
                {i:j for i,j in k.items() if not i=='image_source'}
                for k in self.slide_data
            ],
            'patches': {
                'region': self.patch_region,
                'mode': self.patch_mode,
                'size': self.patch_size
            },
            'property_filters': self.property_filters,
            'spatial_filters': self.spatial_filters,
            'label_property': self.label_property,
            'use_structures': self.use_structures,
            'use_cache': self.use_cache,
            'shuffle': self.shuffle,
            'seed_val': self.seed_val
        }

        return json.dumps(key_configs)

    def export_configs(self, save_path:str):
        
        # patch_size, patch_mode, patch_region, label_property
        # spatial filters, property_filters, use_structures, use_cache, shuffle, seed_val
        key_configs = {
            'slide_data': [
                {i:j for i,j in k.items() if not i=='image_source'}
                for k in self.slide_data
            ],
            'patches': {
                'region': self.patch_region,
                'mode': self.patch_mode,
                'size': self.patch_size
            },
            'property_filters': self.property_filters,
            'spatial_filters': self.spatial_filters,
            'label_property': self.label_property,
            'use_structures': self.use_structures,
            'use_cache': self.use_cache,
            'shuffle': self.shuffle,
            'seed_val': self.seed_val
        }

        with open(save_path,'w') as f:
            json.dump(key_configs, f, indent=4)


