"""Testing CustomFunction component
"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import SlideMap, CustomFunction

from shapely.geometry import shape
from typing_extensions import Union
import numpy as np
from skimage.segmentation import watershed
from skimage.color import rgb2hsv
import scipy.ndimage as ndi
from skimage.morphology import remove_small_holes, remove_small_objects
from skimage import exposure
from skimage.feature import peak_local_max

# function that just expands geometry boundaries by a certain amount
def buffer_shapes(feature, buffer_radius):

    feature_shape = shape(feature['geometry'])
    buffered_shape = feature_shape.buffer(buffer_radius)

    return buffered_shape.__geo_interface__

# Defining CustomFunction component for buffering shapes
buffer_shapes_component = CustomFunction(
    component_title = 'Buffer Shapes',
    description = 'For a given annotation, perform a buffer operation by a specified value.',
    urls = [
        'https://shapely.readthedocs.io/en/stable/manual.html#constructive-methods'
    ],
    function = lambda feature,radius: buffer_shapes(feature,radius),
    input_spec = [
        {
            'name': 'feature',
            'type': 'annotation',
            'property': 'feature'
        },
        {
            'name': 'buffer_radius',
            'type': 'numeric',
            'min': -10,
            'max': 100
        }
    ],
    output_spec = [
        {
            'name': 'Buffered Annotation',
            'description': 'Buffered Annotation Boundaries',
            'type': 'annotation'
        }
    ],
    forEach = True
)



# define sub-compartment segmentation function
def stain_mask(image, mask, nuc_thresh, eosin_thresh):

    seg_params = [
        {
            'name': 'Nuclei',
            'threshold': nuc_thresh,
            'min_size': 5
        },
        {
            'name': 'Eosinophilic',
            'threshold': eosin_thresh,
            'min_size': 10
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
    #hsv_image = np.uint8(255*exposure.equalize_adapthist(hsv_image))
    #hsv_image = np.uint8(255*gaussian(hsv_image,sigma=0.5))

    p2, p98 = np.percentile(hsv_image, (2, 98))
    hsv_image = exposure.rescale_intensity(hsv_image, in_range=(p2, p98))

    for idx,param in enumerate(seg_params):

        # Check for if the current sub-compartment is nuclei
        if param['name'].lower()=='nuclei':

            remaining_pixels = np.multiply(hsv_image,remainder_mask)
            masked_remaining_pixels = np.multiply(remaining_pixels,mask)

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

            # Applying manual threshold
            masked_remaining_pixels[masked_remaining_pixels<=param['threshold']] = 0
            masked_remaining_pixels[masked_remaining_pixels>0] = 1

            # Filtering by minimum size
            small_object_filtered = (1/255)*np.uint8(remove_small_objects(masked_remaining_pixels>0,param['min_size']))

            sub_mask = small_object_filtered

        sub_comp_image[sub_mask>0,idx] = 1
        remainder_mask -= sub_mask>0

    # Assigning remaining pixels within the boundary mask to the last sub-compartment
    remaining_pixels = np.multiply(mask,remainder_mask)
    #remaining_pixels = remainder_mask
    sub_comp_image[remaining_pixels>0,idx] = 1

    final_mask = np.zeros_like(remainder_mask)
    final_mask += sub_comp_image[:,:,0]
    final_mask += 2*sub_comp_image[:,:,1]
    final_mask += 3*sub_comp_image[:,:,2]

    final_mask[~mask] = 0
    return final_mask

# Defining CustomFunction component for sub-compartment segmentation
stain_mask_component = CustomFunction(
    component_title = 'Sub-Compartment Segmentation',
    description = 'For a given structure, use image analysis to segment different sub-compartments',
    urls = [
        'https://github.com/SarderLab/HistoLens'
    ],
    function = lambda image,mask,nuc_thresh,eosin_thresh: stain_mask(image,mask,nuc_thresh,eosin_thresh),
    input_spec = [
        {
            'name': 'image',
            'type': 'image',
            'property': 'image'
        },
        {
            'name': 'mask',
            'type': 'mask',
            'property': 'mask'
        },
        {
            'name': 'nuc_thresh',
            'type': 'numeric',
            'min': 0,
            'max': 255
        },
        {
            'name': 'eosin_thresh',
            'type': 'numeric',
            'min':0,
            'max': 255
        }
    ],
    output_spec = [
        {
            'name': 'Sub-Compartment Mask',
            'type': 'image',
            'description': 'Derived sub-compartment segmentation, 1 = Nuclei, 2 = Eosinophilic, 3 = Luminal Space'
        }
    ],
    forEach = True
)





def main():

    # Grabbing first item from demo DSA instance
    #base_url = 'https://demo.kitware.com/histomicstk/api/v1'
    #item_id = ['5bbdeed1e629140048d01bcb','58b480ba92ca9a000b08c89d']
    base_url = os.environ.get('DSA_URL')

    item_id = [
        '6495a4e03e6ae3107da10dc5',
        '6495a4df3e6ae3107da10dc2'
    ] 

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )
    
    vis_session = Visualization(
        tileservers=[dsa_handler.get_tile_server(i) for i in item_id],
        components = [
            [
                SlideMap(),
                buffer_shapes_component,
            ],
            [
                SlideMap(),
                stain_mask_component
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()


