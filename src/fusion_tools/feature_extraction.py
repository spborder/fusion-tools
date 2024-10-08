"""
Feature extraction functions
"""

import os
import sys

import numpy as np
import pandas as pd
import geopandas as gpd

import large_image
from skimage.exposure import equalize_hist
from skimage.feature import graycomatrix, graycoprops, peak_local_max
from skimage.measure import regionprops_table, label
from skimage.color import rgb2gray, rgb2hsv
from skimage.morphology import remove_small_holes, remove_small_objects
from skimage.segmentation import watershed
from skimage.draw import polygon2mask
from skimage.filters import threshold_otsu

from scipy.ndimage import distance_transform_edt

from shapely.geometry import shape

from joblib import Parallel, delayed

from PIL import Image, UnidentifiedImageError
from typing import Callable
from typing_extensions import Union

from fusion_tools.tileserver import TileServer
from io import BytesIO
import requests

from tqdm import tqdm

class ParallelFeatureExtractor:
    """This class is for extracting multiple types of features at the same time using joblib
    """
    def __init__(self,
                 image_source: Union[str, TileServer] = None,
                 feature_list: list = [],
                 preprocess: Union[Callable,None] = None,
                 n_jobs: None = None,
                 verbose: bool = False):
        """Constructor method

        :param feature_list: List of feature extraction functions to apply to images/structures, defaults to []
        :type feature_list: list, optional
        :param preprocess: Function to apply to images/structures prior to calculating features, defaults to None
        :type preprocess: Union[Callable,None], optional
        :param n_jobs: Number of jobs to use for parallelization, defaults to None
        :type n_jobs: None, optional
        :param verbose: Whether or not to show progress, defaults to False
        :type verbose: bool, optional
        """
        
        self.image_source = image_source
        if type(self.image_source)==str:
            self.image_source = large_image.open(self.image_source)
            self.image_metadata = self.image_source.getMetadata()

        else:
            if hasattr(self.image_source,"tiles_metadata"):
                self.image_metadata = self.image_source.tiles_metadata
            else:
                raise AttributeError(f"Missing metadata for image source: {self.image_source}")

        self.feature_list = feature_list
        self.preprocess = preprocess
        self.n_jobs = n_jobs
        self.verbose = verbose

    def merge_dict(self, a:dict, b:dict, path = []):

        # https://stackoverflow.com/questions/7204805/deep-merge-dictionaries-of-dictionaries-in-python
        for key in b:
            if key in a:
                if isinstance(a[key],dict) and isinstance(b[key],dict):
                    self.merge_dict(a[key],b[key],path+[str(key)])
                elif a[key] != b[key]:
                    raise Exception(f'Conflict at {".".join(path+[str(key)])}')
            else:
                a[key] = b[key]
        return a
    
    def get_bbox(self, coords:list)->list:

        coords_array = np.squeeze(np.array(coords))
        min_x = np.min(coords_array[:,0])
        min_y = np.min(coords_array[:,1])
        max_x = np.max(coords_array[:,0])
        max_y = np.max(coords_array[:,1])

        return [min_x, min_y, max_x, max_y]

    def read_image_region(self, coords:list)->np.ndarray:
        
        bbox = self.get_bbox(coords)

        if isinstance(self.image_source,TileServer):
            if 'frames' in self.image_metadata:
                image_region = np.zeros((int(bbox[3]-bbox[1]),int(bbox[2]-bbox[0]),len(self.image_metadata['frames'])))
                for i in range(0,len(self.image_metadata['frames'])):
                    image_region[:,:,i] = np.array(Image.open(
                        BytesIO(
                            requests.get(
                                self.image_source.regions_url+f'?left={bbox[0]}&top={bbox[1]}&right={bbox[2]}&bottom={bbox[3]}&frame={i}'
                            ).content
                        )
                    ))
            else:
                image_region = np.array(Image.open(
                    BytesIO(
                        requests.get(
                            self.image_source.regions_url+f'?left={bbox[0]}&top={bbox[1]}&right={bbox[2]}&bottom={bbox[3]}'
                        ).content
                    )
                ))

        else:
            if 'frames' in self.image_metadata:
                image_region = np.zeros((int(bbox[3]-bbox[1]),int(bbox[2]-bbox[0]),len(self.image_metadata['frames'])))
                for i in range(0,len(self.image_metadata['frames'])):
                    image_region[:,:,i], _ = self.image_source.getRegion(
                        format = large_image.constants.TILE_FORMAT_NUMPY,
                        region = {
                            'left': bbox[0],
                            'top': bbox[1],
                            'right': bbox[2],
                            'bottom': bbox[3]
                        },
                        frame = i
                    )
            else:
                image_region, _ = self.image_source.getRegion(
                    format = large_image.constants.TILE_FORMAT_NUMPY,
                    region = {
                        'left': bbox[0],
                        'top': bbox[1],
                        'right': bbox[2],
                        'bottom': bbox[3]
                    }
                )

        return image_region

    def make_mask(self, coords:list)->np.ndarray:
        
        # Finding minimum and maximum for coords:
        coords_array = np.array(coords)
        bbox = self.get_bbox(coords)

        height = int(bbox[3] - bbox[1])
        width = int(bbox[2] - bbox[0])

        # polygon2mask expects y,x coordinates, scaled to within shape bounding box
        scaled_coords = np.flip(np.squeeze(coords_array)-np.array([bbox[0], bbox[1], 0]),axis=1)
        if np.shape(scaled_coords)[-1]==3:
            scaled_coords = scaled_coords[:,1:]

        mask = polygon2mask(
            image_shape = (height,width),
            polygon = scaled_coords
        ).astype(int)

        return mask

    def extract_features(self, region: dict)->dict:
        
        # Extracting region coordinates (original image CRS)
        coords = region['geometry']['coordinates']
        # Mask returned using bounding box of coordinates
        image_region = self.read_image_region(coords)

        # Applying preprocessing function if provided
        if not self.preprocess is None:
            image_region = self.preprocess(image_region)

        # Making mask of just the original shape's pixels within the image_region bounding box
        mask = self.make_mask(coords)

        bbox = self.get_bbox(coords)

        return_dict = {
            'min_x': bbox[0],
            'min_y': bbox[1],
            'max_x': bbox[2],
            'max_y': bbox[3]
        }
        for f in self.feature_list:
            # Each feature extraction function should accept three inputs, whether they are used or not
            return_dict = self.merge_dict(return_dict,f(image_region, mask, coords))
            
        return return_dict

    def start(self, region_list:list)->pd.DataFrame:
        
        # Returns a dictionary for each region containing feature names and values (key,value)
        feature_list = Parallel(n_jobs=self.n_jobs,verbose=100 if self.verbose else 0)(delayed(self.extract_features)(i) for i in region_list)
        
        return pd.DataFrame.from_records(feature_list).fillna(0)




def distance_transform_features(image:np.ndarray, mask:np.ndarray, coords:list)->dict:
    """Function to calculate distance transform features for each label in "mask"

    :param image: Input image region (not used)
    :type image: np.ndarray
    :param mask: Mask of regions to include in the feature calculation (0=background)
    :type mask: np.ndarray
    :param coords: Coordinates of this specific image (not used)
    :type coords: list
    :return: Dictionary containing key/value pairs for each feature extracted (Mean, Median, Maximum, Sum)
    :rtype: dict
    """

    feature_values = {}
    mask_labels = [i for i in np.unique(mask).tolist() if not i==0]

    for m_idx, m in enumerate(mask_labels):
        mask_regions = (mask==m).astype(np.uint8)

        distance_transform = distance_transform_edt(mask_regions)
        distance_transform[distance_transform==0] = np.nan
        
        feature_values[f'Mask {m}'] = {
            'Distance Transform': {
                "Mean": np.nanmean(distance_transform),
                "Median": np.nanmedian(distance_transform),
                "Max": np.nanmax(distance_transform),
                "Sum": np.nansum(distance_transform)
            }
        }

    return feature_values

def color_features(image:np.ndarray, mask: np.ndarray, coords:list)->dict:
    """Calculate "color" features for each label in mask within image (color defined as channel statistics)

    :param image: Input image region
    :type image: np.ndarray
    :param mask: Mask of regions to include in the feature calculation (0=background)
    :type mask: np.ndarray
    :param coords: Coordinates of this specific image (not used)
    :type coords: list
    :return: Dictionary containing key/value pairs for each feature extracted (Mean, Median, Maximum, Std)
    :rtype: dict
    """

    feature_values = {}

    mask_labels = [i for i in np.unique(mask).tolist() if not i==0]
    for m_idx, m in enumerate(mask_labels):
        mask_regions = (mask==m)
        masked_channels = image[mask_regions>0]

        mean_vals = np.nanmean(masked_channels,axis=0).tolist()
        median_vals = np.nanmedian(masked_channels,axis=0).tolist()
        max_vals = np.nanmedian(masked_channels,axis=0).tolist()
        std_vals = np.nanstd(masked_channels,axis=0).tolist()
        
        feature_values[f'Mask {m}'] = {}
        for c_idx,(m1,m2,m3,s) in enumerate(zip(mean_vals, median_vals, max_vals, std_vals)):
            
            feature_values[f'Mask {m}'] = feature_values[f'Mask {m}'] | {f'Channel {c_idx}': {'Mean': m1, 'Median': m2, 'Max': m3, 'Std': s}}

    return feature_values

def texture_features(image:np.ndarray, mask:np.ndarray, coords: list)->dict:
    """Calculate texture features for each label in mask within image.

    :param image: Input image region
    :type image: np.ndarray
    :param mask: Mask of regions to include in the feature calculation (0=background)
    :type mask: np.ndarray
    :param coords: Coordinates of this specific image (not used)
    :type coords: list
    :return: Dictionary containing key/value pairs for each feature extracted (Contrast, Homogeneity, Correlation, Energy)
    :rtype: dict
    """

    feature_values = {}
    texture_features = ['Contrast','Homogeneity','Correlation','Energy']
    mask_labels = [i for i in np.unique(mask).tolist() if not i==0]
    channels = np.shape(image)[-1]

    for m_idx, m in enumerate(mask_labels):
        masked_pixels = (1/255)*(mask==m).astype(np.uint8)

        feature_values[f'Mask {m}'] = {}
        for c in range(0,channels):
            masked_channel = np.uint8(image[:,:,c] * masked_pixels)
            texture_matrix = graycomatrix(masked_channel, [1],[0],levels=256,symmetric=True, normed=True)
            
            feature_values[f'Mask {m}'][f'Channel {c}'] = {}
            for t in texture_features:
                t_value = graycoprops(texture_matrix,t.lower())[0][0]
                
                feature_values[f'Mask {m}'][f'Channel {c}'][t] = t_value

    return feature_values

def morphological_features(image:np.ndarray,mask:np.ndarray,coords:list)->dict:
    """Calculate morphological features for each label in mask within image.

    :param image: Input image region (not used)
    :type image: np.ndarray
    :param mask: Mask of regions to include in the feature calculation (0=background)
    :type mask: np.ndarray
    :param coords: Coordinates of this specific image (not used)
    :type coords: list
    :return: Dictionary containing key/value pairs for each feature extracted (Contrast, Homogeneity, Correlation, Energy)
    :rtype: dict
    """

    feature_values = {}

    mask_labels = [i for i in np.unique(mask).tolist() if not i==0]

    for m_idx, m in enumerate(mask_labels):
        props = pd.DataFrame(
                    regionprops_table(
                        label(mask==m),
                        image,
                        properties = ('area','centroid','eccentricity','equivalent_diameter_area','extent','euler_number')
                    )
                ).select_dtypes(exclude='object')

        feature_values[f'Mask {m}'] = {'Count': props.shape[0]}
        for p in props.columns.tolist():
            feature_values[f'Mask {m}'][p] = {
                'Mean': props[p].mean(),
                'Median': props[p].median(),
                'Max': props[p].max(),
                'Min': props[p].min()
            }

    return feature_values

def relative_distance(input_shapes:dict, other_shapes:Union[dict,list])->list:
    """Calculate relative distance statistics between each Feature in "input_shapes" (GeoJSON FeatureCollection) and each Feature in each FeatureCollection in "other_shapes"

    :param input_shapes: FeatureCollection containing Features to calculate relative distance statistics for each FeatureCollection in other_shapes
    :type input_shapes: dict
    :param other_shapes: List of multiple FeatureCollections or single FeatureCollection where relative distance statistics are calculated off of for input_shapes
    :type other_shapes: Union[dict,list]
    """
    
    if type(other_shapes)==dict:
        other_shapes = [other_shapes]
    
    other_shapes_gdf = [gpd.GeoDataFrame(i) for i in other_shapes]

    # Calculating min, max, mean, median
    distance_stats = []
    for other_fc in other_shapes_gdf:
        all_dist = []
        for f in input_shapes['features']:
            all_dist.extend(other_fc.distance(shape(f['geometry'])))

        distance_stats.append({
            'Min': np.min(all_dist),
            'Max': np.max(all_dist),
            'Mean': np.mean(all_dist),
            'Median': np.median(all_dist),
            'Std': np.std(all_dist)
        })

    return distance_stats

def threshold_channels(input_image:np.ndarray,threshold_method: Union[str,None] = None)->np.ndarray:
    """Example preprocessing function that thresholds each channel in the input image according to some method

    :param input_image: Input image region (Y,X,C)
    :type input_image: np.ndarray
    :param threshold_method: Method to use for thresholding (None is set to Otsu's), defaults to None
    :type threshold_method: Union[str,None], optional
    :return: Returns image with each channel thresholded independently
    :rtype: np.ndarray
    """

    assert threshold_method in [None, 'otsu','average','median']

    threshed_image = np.zeros_like(input_image)
    for c in np.shape(input_image)[-1]:
        if threshold_method in [None, 'otsu']:
            threshed_image[:,:,c] = input_image[:,:,c] > threshold_otsu(input_image[:,:,c])
        elif threshold_method=='average': 
            threshed_image[:,:,c] = input_image[:,:,c] > np.mean(input_image[:,:,c])
        elif threshold_method=='median':
            threshed_image[:,:,c] = input_image[:,:,c] > np.median(input_image)

    return threshed_image





