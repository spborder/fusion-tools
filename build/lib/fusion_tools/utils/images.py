"""
Utility functions relating to images
"""
import os
import sys
from typing_extensions import Union
import numpy as np

from shapely.geometry import shape
from skimage.draw import polygon2mask

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
    :param tile_source: A large-image tile source object (or custom object with "getRegion" method)
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
    
    feature_image, mime_type = tile_source.getRegion(
            region = {
                'left': feature_bounds[0],
                'top': feature_bounds[1],
                'right': feature_bounds[2],
                'bottom': feature_bounds[3]
            },
            format = large_image.constants.TILE_FORMAT_NUMPY
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









































