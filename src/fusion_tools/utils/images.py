"""
Utility functions relating to images
"""
import os
import sys
from typing_extensions import Union
import numpy as np

from shapely.geometry import shape
from skimage.draw import polygon2mask
from PIL import Image
from io import BytesIO

import tifffile
import skimage.measure

import large_image


def get_style_dict(channel_colors:list, tile_source):
    """Generate style dictionary that can be used in association with large_image.open("/path/to/file.ext",style={}) to view different channels as different colors

    :param channel_colors: List of dictionaries where each key is a channel name found in "tile_source" and each value is an rgba() CSS color string
    :type channel_colors: list
    :param tile_source: Large-image tile source object used to open image
    :type tile_source: None
    """

    assert hasattr(tile_source,"getMetadata")

    tile_metadata = tile_source.getMetadata()

    if 'frames' in tile_metadata:
        frame_names = [i['Channel'] if 'Channel' in i else idx for idx,i in enumerate(tile_metadata['frames'])]
        style_dict = {"bands": []}
        for c in channel_colors:
            style_dict["bands"].append(
                {
                    'palette': ['rgba(0,0,0,255)',list(c.values())[0]],
                    'framedelta': frame_names.index(list(c.keys())[0])
                }
            )

        return style_dict
    else:
        raise TypeError('tile_source is not a multi-frame image')

def get_feature_image(feature:dict, tile_source:None, return_mask: bool=False):
    """Extract image region associated with a given feature from tile_source (a large-image object)

    :param feature: GeoJSON Feature with "geometry" field containing coordinates
    :type feature: dict
    :param tile_source: A large-image tile source object or URL that accepts region inputs
    :type tile_source: None
    :param return_mask: Whether or not to return both the image region (bounding box) as well as a binary mask of the boundaries of that feature, defaults to False
    :type return_mask: bool, optional
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
    
    if not type(tile_source)==str:
        # Used for extracting a region from a locally stored image
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
        if '?' in tile_source:
            start_str = '&'
        else:
            start_str = '?'

        feature_image = np.array(
            Image.open(
                BytesIO(
                    requests.get(
                        tile_source+f'{start_str}left={feature_bounds[0]}&top={feature_bounds[1]}&right={feature_bounds[2]}&bottom={feature_bounds[3]}'
                        ).content
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

        return feature_image, feature_mask
    else:
        return feature_image

def write_ome_tiff(data: np.ndarray, output_path:str, channel_names:list, pixel_size:list, physical_size_z:float, compression:str='zlib', create_pyramid:bool = True, imagej:bool = False, unit:str='µm', downsample_count:int=4):
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
    
    if channel_names and data.shape[1] != len(channel_names):
        raise ValueError(f"Number of channels in the data ({data.shape[1]}) does not match the length of 'channel_names' ({len(channel_names)}).")
    
    # Provide default channel names if none are provided
    if not channel_names:
        channel_names = [f"Channel {i+1}" for i in range(data.shape[1])]

    # Handle unit conversion for ImageJ compatibility (ImageJ expects 'um' instead of 'µm')
    if Unit == 'µm' and imagej:
        Unit = 'um'
        
    # Validate compression options
    valid_compressions = [None, 'zlib', 'lzma', 'jpeg']
    if compression not in valid_compressions:
        raise ValueError(f"Invalid compression option '{compression}'. Valid options are: {valid_compressions}.")

    # Handle 3D data (ZCYX format)
    if data.shape[0] > 1:
        
        if data.shape[1] == 3 and data.dtype == np.uint8:
            print("Detected 3D color data")
            data = np.transpose(data, (0, 2, 3, 1))
            metadata = {
                'axes': 'ZYXC',
                'PhysicalSizeX': pixel_size[0],
                'PhysicalSizeXUnit': Unit,
                'PhysicalSizeY': pixel_size[1],
                'PhysicalSizeYUnit': Unit,
                'PhysicalSizeZ': physical_size_z,
                'PhysicalSizeZUnit': Unit,
                'Photometric': 'RGB',
                'Planarconfig': 'contig',
            }
            
            # Handle pyramid creation
            if create_pyramid:
                print(f"Writing with pyramid, {downsample_count} downsample levels")
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=downsample_count, metadata=metadata, compression=compression)
                    for level in range(1, downsample_count + 1):
                        data = skimage.measure.block_reduce(data, block_size=(1, 2, 2, 1), func=np.mean).astype(data.dtype)  # Average pooling
                        metadata['PhysicalSizeX'] *= 2  # Update pixel size for each level
                        metadata['PhysicalSizeY'] *= 2
                        tif.write(data, subfiletype=1, metadata=metadata, compression=compression)
            else:
                print("Writing without pyramid")
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=0, metadata=metadata, compression=compression)
        else:
            print("Detected 3D data")
            metadata = {
                'axes': 'ZCYX',
                'Channel': [{'Name': name, 'SamplesPerPixel': 1} for name in channel_names],
                'PhysicalSizeX': pixel_size[0],
                'PhysicalSizeXUnit': Unit,
                'PhysicalSizeY': pixel_size[1],
                'PhysicalSizeYUnit': Unit,
                'PhysicalSizeZ': physical_size_z,
                'PhysicalSizeZUnit': Unit,
                'Photometric': 'minisblack',
            }
        
            # Handle pyramid creation
            if create_pyramid:
                print(f"Writing with pyramid, {downsample_count} downsample levels")
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=downsample_count, metadata=metadata, compression=compression)
                    for level in range(1, downsample_count + 1):
                        data = skimage.measure.block_reduce(data, block_size=(1, 1, 2, 2), func=np.mean).astype(data.dtype)  # Average pooling
                        metadata['PhysicalSizeX'] *= 2  # Update pixel size for each level
                        metadata['PhysicalSizeY'] *= 2
                        tif.write(data, subfiletype=1, metadata=metadata, compression=compression)
            else:
                print("Writing without pyramid")
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=0, metadata=metadata, compression=compression)

    # Handle 2D data (CYX format)
    else:
        # Remove the z-dimension (since it's a single z-slice)
        data = data[0, ...]  # Now data has shape (C, Y, X)
            
        # Check if data is RGB (3 channels and uint8 type)
        if data.shape[0] == 3 and data.dtype == np.uint8:
            print("Detected 2D color data")
            data = np.transpose(data, (1, 2, 0))
            metadata = {
                'axes': 'YXC',
                'PhysicalSizeX': pixel_size[0],
                'PhysicalSizeXUnit': Unit,
                'PhysicalSizeY': pixel_size[1],
                'PhysicalSizeYUnit': Unit,
                'Photometric': 'RGB',
                'Planarconfig': 'contig',
            }
            
            # Handle pyramid creation
            if create_pyramid:
                print(f"Writing with pyramid, {downsample_count} downsample levels")
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=downsample_count, metadata=metadata, compression=compression)
                    for level in range(1, downsample_count + 1):
                        data = skimage.measure.block_reduce(data, block_size=(2, 2, 1), func=np.mean).astype(data.dtype)  # Average pooling
                        metadata['PhysicalSizeX'] *= 2  # Update pixel size for each level
                        metadata['PhysicalSizeY'] *= 2
                        tif.write(data, subfiletype=1, metadata=metadata, compression=compression)
            else:
                print("Writing without pyramid")
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=0, metadata=metadata, compression=compression)
        else:
            print("Detected 2D data")
            metadata = {
                'axes': 'CYX',
                'Channel': [{'Name': name, 'SamplesPerPixel': 1} for name in channel_names],
                'PhysicalSizeX': pixel_size[0],
                'PhysicalSizeXUnit': Unit,
                'PhysicalSizeY': pixel_size[1],
                'PhysicalSizeYUnit': Unit,
                'Photometric': 'minisblack',
                'Planarconfig': 'separate',
            }

            # Handle pyramid creation
            if create_pyramid:
                print(f"Writing with pyramid, {downsample_count} downsample levels")
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=downsample_count, metadata=metadata, compression=compression)
                    for level in range(1, downsample_count + 1):
                        data = skimage.measure.block_reduce(data, block_size=(1, 2, 2), func=np.mean).astype(data.dtype)  # Average pooling
                        metadata['PhysicalSizeX'] *= 2  # Update pixel size for each level
                        metadata['PhysicalSizeY'] *= 2
                        tif.write(data, subfiletype=1, metadata=metadata, compression=compression)
            else:
                print("Writing without pyramid")
                with tifffile.TiffWriter(output_path, bigtiff=True, imagej=imagej) as tif:
                    tif.write(data, subifds=0, metadata=metadata, compression=compression)









































