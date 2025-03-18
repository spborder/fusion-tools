"""
Utility functions relating to images
"""
import os
import sys
from typing_extensions import Union
import numpy as np
import requests
import json

import geojson
import geopandas as gpd

from rasterio.features import rasterize

from shapely.geometry import shape, box
from skimage.draw import polygon2mask
from PIL import Image
from io import BytesIO

import tifffile
from skimage.measure import block_reduce, label

import large_image


def get_style_dict(channel_colors:list, tile_source = None, tile_metadata = None):
    """Generate style dictionary that can be used in association with large_image.open("/path/to/file.ext",style={}) to view different channels as different colors

    :param channel_colors: List of dictionaries where each key is a channel name found in "tile_source" and each value is an rgba() CSS color string
    :type channel_colors: list
    :param tile_source: Large-image tile source object used to open image
    :type tile_source: None
    """
    assert any([not i is None for i in [tile_source,tile_metadata]])

    if not tile_source is None and tile_metadata is None:
        assert hasattr(tile_source,"getMetadata")
        tile_metadata = tile_source.getMetadata()

    if 'frames' in tile_metadata:
        if all(['Channel' in i for i in tile_metadata['frames']]):
            frame_names = [i['Channel'] if 'Channel' in i else idx for idx,i in enumerate(tile_metadata['frames'])]
        elif 'channels' in tile_metadata:
            frame_names = tile_metadata['channels']

        frame_color_dict = {
            frame_names.index(list(c.keys())[0]): list(c.values())[0]
            for c in channel_colors
        }
        style_dict = get_bands(frame_color_dict)

        return style_dict
    else:
        raise TypeError('tile_source is not a multi-frame image')
    
def get_bands(channel_dict:dict):

    style_dict = {'bands':[]}
    for frame_index, color in channel_dict.items():
        if not type(color)==str:
            if type(color)==list:
                style_dict['bands'].append(
                    {
                        'palette': ['rgba(0,0,0,255)',f'rgba({",".join(color[0:3])},255)'],
                        'framedelta': frame_index
                    }
                )
            else:
                raise TypeError(f'Color of type: {type(color)} is not accepted. {color} was provided')
        else:
            style_dict['bands'].append(
                {
                    'palette': ['rgba(0,0,0,255)',color],
                    'framedelta': frame_index
                }
            )

    return style_dict

def get_feature_image(feature:dict, tile_source:None, return_mask: bool=False, return_image:bool= True, frame_index: Union[None,list,int] = None, frame_colors: Union[None,list] = None):
    """Extract image region associated with a given feature from tile_source (a large-image object)

    :param feature: GeoJSON Feature with "geometry" field containing coordinates
    :type feature: dict
    :param tile_source: A large-image tile source object or URL that accepts region inputs
    :type tile_source: None
    :param return_mask: Whether or not to return both the image region (bounding box) as well as a binary mask of the boundaries of that feature, defaults to False
    :type return_mask: bool, optional
    :param return_image: Whether or not to grab the image
    :type return_image: bool, optional
    :param frame_index: If this is a multi-frame image, specify one or multiple frames to grab data from (only grabs the mask once)
    :type frame_index: Union[None, list, int], optional
    """

    # Getting bounding box of feature:
    if not 'geometry' in feature:
        raise ValueError(f"Feature does not contain 'geometry' key: {list(feature.keys())}")
    
    feature_shape = shape(feature['geometry'])
    # This will only work with geometries that have an "exterior", so not Point
    if not feature_shape.geom_type=='Point':
        feature_bounds = list(feature_shape.exterior.bounds)
    else:
        raise TypeError("Feature geometries of type: 'Point' are not implemented, try again using .buffer(1) or other to extract a valid bounding box")
    
    # Just making sure that the boundaries are int
    feature_bounds = [round(i) for i in feature_bounds]

    if return_image:
        if not type(tile_source)==str:
            # Used for extracting a region from a locally stored image
            if frame_index is None:
                feature_image, mime_type = tile_source.getRegion(
                        region = {
                            'left': feature_bounds[0],
                            'top': feature_bounds[1],
                            'right': feature_bounds[2],
                            'bottom': feature_bounds[3]
                        },
                        format = large_image.constants.TILE_FORMAT_NUMPY
                    )
            else:
                if type(frame_index)==int:
                    frame_index = [frame_index]

                height = feature_bounds[3] - feature_bounds[1]
                width = feature_bounds[2] - feature_bounds[0]

                if frame_colors is None:
                    feature_image = np.zeros((height,width,len(frame_index)))
                else:
                    feature_image = np.zeros((height,width,3),dtype=np.uint8)

                for f_idx,f in enumerate(frame_index):
                    frame_image, mime_type = tile_source.getRegion(
                        region = {
                            'left': feature_bounds[0],
                            'top': feature_bounds[1],
                            'right': feature_bounds[2],
                            'bottom': feature_bounds[3]
                        },
                        frame = f,
                        format = large_image.constants.TILE_FORMAT_NUMPY
                    )

                    if frame_colors is None:
                        feature_image[:,:,f] += frame_image
                    else:
                        feature_image += np.uint8(np.repeat(frame_image[:,:,None],repeats=3,axis=-1) * np.array(frame_colors[f_idx])[None,:])
                
        else:
            if '?' in tile_source:
                start_str = '&'
            else:
                start_str = '?'

            if frame_index is None:
                feature_image = np.array(
                    Image.open(
                        BytesIO(
                            requests.get(
                                tile_source+f'{start_str}left={feature_bounds[0]}&top={feature_bounds[1]}&right={feature_bounds[2]}&bottom={feature_bounds[3]}'
                                ).content
                        )
                    )
                )
            else:
                height = int(feature_bounds[3] - feature_bounds[1])
                width = int(feature_bounds[2] - feature_bounds[0])

                if frame_colors is None:
                    feature_image = np.zeros((height,width,len(frame_index)))
                else:
                    feature_image = np.zeros((height,width,3),dtype=np.uint8)

                    style_dict = get_bands({
                        f_idx: [str(i) for i in color]
                        for f_idx,color in zip(frame_index,frame_colors)
                    })

                if type(frame_index)==int:
                    frame_index = [frame_index]

                if frame_colors is None:
                    for f_idx,f in enumerate(frame_index):
                        frame_image = np.array(
                            Image.open(
                                BytesIO(
                                    requests.get(
                                        tile_source+f'{start_str}left={feature_bounds[0]}&top={feature_bounds[1]}&right={feature_bounds[2]}&bottom={feature_bounds[3]}&frame={f}'
                                        ).content
                                )
                            )
                        )
                        feature_image[:,:,f] += frame_image
                else:
                    styled_url = tile_source+f'{start_str}left={feature_bounds[0]}&top={feature_bounds[1]}&right={feature_bounds[2]}&bottom={feature_bounds[3]}&style={json.dumps(style_dict)}'
                    feature_image = np.array(
                        Image.open(
                            BytesIO(
                                requests.get(styled_url).content
                            )
                        )
                    )

    if return_mask:

        height = feature_image.shape[0]
        width = feature_image.shape[1]

        # Scaling exterior coordinates to fit within bounding box
        top_left = feature_bounds[0:2]
        scaled_coords = np.squeeze(feature_shape.exterior.coords) - np.array([top_left[0], top_left[1]])

        # polygon2mask expects coordinates to be y,x and scaled_coords is x,y
        feature_mask = polygon2mask(
            image_shape = (height,width),
            polygon = np.flip(scaled_coords,axis=1)
        )

    if return_image and return_mask:
        return feature_image, feature_mask
    elif return_image and not return_mask:
        return feature_image
    elif return_mask and not return_image:
        return feature_mask

def write_ome_tiff(data: np.ndarray, output_path:str, channel_names:list, pixel_size:list, physical_size_z:float, compression:str='zlib', create_pyramid:bool = True, imagej:bool = False, unit:str='pixel', downsample_count:int=4):
    """Write an ome-tiff file from a numpy array (from: https://github.com/TristanWhitmarsh/numpy2ometiff/blob/main/numpy2ometiff/writer.py)

    :param data: numpy array containing image data to save as OME-TIFF
    :type data: np.ndarray
    :param output_path: path to save output file to  
    :type output_path: str
    :param channel_names: list of names for each channel
    :type channel_names: list
    :param pixel_size: list of x,y pixel dimensions
    :type pixel_size: list
    :param physical_size_z: physical length in the z-dimension
    :type physical_size_z: float
    :param create_pyramid: Whether or not to create a pyramid from the assembled data
    :type create_pyramid: bool
    :param imagej: Whether or not to modify microns to um
    :type imagej: bool
    :param unit: what units the dimensions are in
    :type unit: str
    :param downsample_count: How many downsample levels for pyramidal saving
    :type downsample_count: int
    """
    
    # Doesn't make sense to include this part as the data could be not-3D
    # Ensure the data is in ZCYX format (4D array: Z-slices, Channels, Y, X)
    #if len(data.shape) != 4:
    #    raise ValueError(f"Input data must have 4 dimensions (ZCYX). Found {len(data.shape)} dimensions.")
    
    #if channel_names and data.shape[1] != len(channel_names):
    #    raise ValueError(f"Number of channels in the data ({data.shape[1]}) does not match the length of 'channel_names' ({len(channel_names)}).")
    
    data = data[None,...]

    # Provide default channel names if none are provided
    if not channel_names:
        channel_names = [f"Channel {i+1}" for i in range(data.shape[1])]

    # Handle unit conversion for ImageJ compatibility (ImageJ expects 'um' instead of 'µm')
    if unit == 'µm' and imagej:
        unit = 'um'
        
    # Validate compression options
    valid_compressions = [None, 'zlib', 'lzma', 'jpeg']
    if compression not in valid_compressions:
        raise ValueError(f"Invalid compression option '{compression}'. Valid options are: {valid_compressions}.")

    # Handle 3D data (ZCYX format)
    if data.shape[0] > 1:
        
        if data.shape[1] == 3 and data.dtype == np.uint8:
            data = np.transpose(data, (0, 2, 3, 1))
            metadata = {
                'axes': 'ZYXC',
                'PhysicalSizeX': pixel_size[0],
                'PhysicalSizeXUnit': unit,
                'PhysicalSizeY': pixel_size[1],
                'PhysicalSizeYUnit': unit,
                'PhysicalSizeZ': physical_size_z,
                'PhysicalSizeZUnit': unit,
                'Photometric': 'RGB',
                'Planarconfig': 'contig',
            }
            
            # Handle pyramid creation
            if create_pyramid:
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=downsample_count, metadata=metadata, compression=compression)
                    for level in range(1, downsample_count + 1):
                        data = block_reduce(data, block_size=(1, 2, 2, 1), func=np.mean).astype(data.dtype)  # Average pooling
                        metadata['PhysicalSizeX'] *= 2  # Update pixel size for each level
                        metadata['PhysicalSizeY'] *= 2
                        tif.write(data, subfiletype=1, metadata=metadata, compression=compression)
            else:
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=0, metadata=metadata, compression=compression)
        else:
            metadata = {
                'axes': 'ZCYX',
                'Channel': [{'Name': name, 'SamplesPerPixel': 1} for name in channel_names],
                'PhysicalSizeX': pixel_size[0],
                'PhysicalSizeXUnit': unit,
                'PhysicalSizeY': pixel_size[1],
                'PhysicalSizeYUnit': unit,
                'PhysicalSizeZ': physical_size_z,
                'PhysicalSizeZUnit': unit,
                'Photometric': 'minisblack',
            }
        
            # Handle pyramid creation
            if create_pyramid:
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=downsample_count, metadata=metadata, compression=compression)
                    for level in range(1, downsample_count + 1):
                        data = block_reduce(data, block_size=(1, 1, 2, 2), func=np.mean).astype(data.dtype)  # Average pooling
                        metadata['PhysicalSizeX'] *= 2  # Update pixel size for each level
                        metadata['PhysicalSizeY'] *= 2
                        tif.write(data, subfiletype=1, metadata=metadata, compression=compression)
            else:
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=0, metadata=metadata, compression=compression)

    # Handle 2D data (CYX format)
    else:
        # Remove the z-dimension (since it's a single z-slice)
        data = data[0, ...]  # Now data has shape (C, Y, X)
            
        # Check if data is RGB (3 channels and uint8 type)
        if data.shape[0] == 3 and data.dtype == np.uint8:
            data = np.transpose(data, (1, 2, 0))
            metadata = {
                'axes': 'YXC',
                'PhysicalSizeX': pixel_size[0],
                'PhysicalSizeXUnit': unit,
                'PhysicalSizeY': pixel_size[1],
                'PhysicalSizeYUnit': unit,
                'Photometric': 'RGB',
                'Planarconfig': 'contig',
            }
            
            # Handle pyramid creation
            if create_pyramid:
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=downsample_count, metadata=metadata, compression=compression)
                    for level in range(1, downsample_count + 1):
                        data = block_reduce(data, block_size=(2, 2, 1), func=np.mean).astype(data.dtype)  # Average pooling
                        metadata['PhysicalSizeX'] *= 2  # Update pixel size for each level
                        metadata['PhysicalSizeY'] *= 2
                        tif.write(data, subfiletype=1, metadata=metadata, compression=compression)
            else:
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=0, metadata=metadata, compression=compression)
        else:
            metadata = {
                'axes': 'CYX',
                'Channel': [{'Name': name, 'SamplesPerPixel': 1} for name in channel_names],
                'PhysicalSizeX': pixel_size[0],
                'PhysicalSizeXUnit': unit,
                'PhysicalSizeY': pixel_size[1],
                'PhysicalSizeYUnit': unit,
                'Photometric': 'minisblack',
                'Planarconfig': 'separate',
            }

            # Handle pyramid creation
            if create_pyramid:
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=downsample_count, metadata=metadata, compression=compression)
                    for level in range(1, downsample_count + 1):
                        data = block_reduce(data, block_size=(1, 2, 2), func=np.mean).astype(data.dtype)  # Average pooling
                        metadata['PhysicalSizeX'] *= 2  # Update pixel size for each level
                        metadata['PhysicalSizeY'] *= 2
                        tif.write(data, subfiletype=1, metadata=metadata, compression=compression)
            else:
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=0, metadata=metadata, compression=compression)

def format_intersecting_masks(base_geojson, other_geojsons, mask_format='one-hot-labels'):
    """Creating a mask which includes intersecting structures with the "base_geojson"

    :param base_geojson: FeatureCollection containing structures to use as a basis for finding intersections with other structures.
    :type base_geojson: dict
    :param other_geojsons: List of other FeatureCollections to search for intersection with base_geojson
    :type other_geojsons: list
    """

    other_geos_gdf = [gpd.GeoDataFrame.from_features(i['features']) for i in other_geojsons]

    mask_colors = []
    if mask_format=='rgb':
        mask_colors = [
            [
                np.random.randint(0,255)
                for i in range(3)
            ]
            for j in range(len(other_geojsons))
        ]

    intersecting_masks = []
    for f in base_geojson['features']:
        # Bounds in the form minx, miny, maxx, maxy
        f_bounds = list(shape(f['geometry']).bounds)
        f_box = box(*f_bounds)
        f_height = int(f_bounds[3]-f_bounds[1])
        f_width = int(f_bounds[2]-f_bounds[0])
        
        if 'one-hot' in mask_format:
            f_mask = np.zeros((f_height,f_width,len(other_geos_gdf)),dtype=np.int16)
        elif 'rgb' in mask_format:
            f_mask = np.zeros((f_height,f_width,3),dtype=np.uint8)

        for s_idx,s in enumerate(other_geos_gdf):
            s_intersection = s.intersection(f_box)
            s_intersection = s_intersection[~s_intersection.is_empty]
            if not all(s_intersection.is_empty.tolist()):
                # This can be used for GeoSeries, but removes all "properties". Just geometries in this one
                s_intersection_geo = s_intersection.__geo_interface__
                s_scaled_intersection = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]-f_bounds[0],c[1]-f_bounds[1]),g),s_intersection_geo)
                
                s_mask = rasterize([i['geometry'] for i in s_scaled_intersection['features']],out_shape=(f_height,f_width))
                
                if mask_format=='one-hot-labels':
                    s_labeled_mask = label(s_mask)
                    f_mask[:,:,s_idx]+=s_labeled_mask
                elif mask_format=='one-hot':
                    f_mask[:,:,s_idx]+=s_mask
                elif mask_format=='rgb':
                    f_mask += np.array(mask_colors[s_idx],dtype=np.uint8) * s_mask.astype(np.uint8)[:,:,None]

        intersecting_masks.append(f_mask)       

    return intersecting_masks



