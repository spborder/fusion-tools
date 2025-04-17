"""Testing CustomFunction component
"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import SlideMap, CustomFunction, FUSIONFunction

import geojson
import rasterio.features
import geopandas as gpd

from skimage.filters import threshold_otsu

import plotly.express as px
import plotly.graph_objects as go
from matplotlib import cm
from PIL import Image
from skimage.transform import resize

from shapely.geometry import shape
import numpy as np
from skimage.segmentation import watershed
from skimage.color import rgb2hsv
import scipy.ndimage as ndi
from skimage.morphology import remove_small_holes, remove_small_objects
from skimage import exposure
from skimage.feature import peak_local_max

from io import BytesIO
import base64

# function that just expands geometry boundaries by a certain amount
def buffer_shapes(feature, buffer_radius):

    feature_shape = shape(feature['geometry'])
    buffered_shape = feature_shape.buffer(buffer_radius)

    return buffered_shape.__geo_interface__

# Defining CustomFunction component for buffering shapes
buffer_shapes_component = FUSIONFunction(
    title = 'Buffer Shapes',
    description = 'For a given annotation, perform a buffer operation by a specified value.',
    urls = [
        'https://shapely.readthedocs.io/en/stable/manual.html#constructive-methods'
    ],
    function = lambda feature,radius: buffer_shapes(feature,radius),
    function_type = 'forEach',
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
stain_mask_component = FUSIONFunction(
    title = 'Sub-Compartment Segmentation',
    description = 'For a given structure, use image analysis to segment different sub-compartments',
    urls = [
        'https://github.com/SarderLab/HistoLens'
    ],
    function = lambda image,mask,nuc_thresh,eosin_thresh: stain_mask(image,mask,nuc_thresh,eosin_thresh),
    function_type = 'forEach',
    input_spec = [
        {
            'name': 'image',
            'description': 'Raw RGB image containing IHC-stained histology',
            'type': 'image',
            'property': 'image'
        },
        {
            'name': 'mask',
            'description': 'Boundary mask generated from exterior vertices',
            'type': 'mask',
            'property': 'mask'
        },
        {
            'name': 'nuc_thresh',
            'description': 'Threshold applied to HSV-transformed image (S-channel) to segment the Hematoxylin channel.',
            'type': 'numeric',
            'min': 0,
            'max': 255
        },
        {
            'name': 'eosin_thresh',
            'description':'Threshold applied to HSV-transformed image (S-channel) to segment the Eosin channel.',
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
)


# Defining functions for finding interstitial distance transform
def find_tissue(image):

    # Mean of all channels/frames to make grayscale mask
    gray_mask = np.squeeze(np.mean(image,axis=-1))

    threshold_val = 1.15*threshold_otsu(gray_mask)
    tissue_mask = gray_mask <= threshold_val

    tissue_mask = remove_small_holes(tissue_mask,area_threshold=150)
    tissue_mask = remove_small_objects(tissue_mask,min_size=100)

    return tissue_mask

def make_interstitium_dt_map(annotations, image):

    non_spot_annotations = [i for i in annotations if not i['properties']['name']=='Spots']

    im_width = int(image.shape[1])
    im_height = int(image.shape[0])

    im_mask = np.zeros((im_height,im_width),dtype=np.uint8)
    for a in non_spot_annotations:
        for b in a['features']:
            a_mask = rasterio.features.rasterize([shape(b['geometry'])],out_shape = (im_height,im_width))
            im_mask += a_mask

    bin_d_mask = im_mask>0
    slide_tissue_mask = find_tissue(image)>0
    non_structure_tissue = 255*np.uint8(slide_tissue_mask) - 255*np.uint8(bin_d_mask)

    heat_data = ndi.distance_transform_edt(non_structure_tissue)
    
    # Colormapping distance transform and converting to RGBA
    c_map = cm.get_cmap('jet')

    heat_data -= np.min(heat_data)
    heat_data /= np.max(heat_data)

    rgba_heat = 255*np.uint8(c_map(np.uint8(255*heat_data)))
    a_heat = int(255*0.5)*np.ones((rgba_heat.shape[0],rgba_heat.shape[1],1),dtype=np.uint8)
    
    # Making all non-tissue regions transparent
    a_heat[heat_data==0] = 0
    rgba_heat[:,:,-1] = a_heat[:,:,0]

    rgba_heat = np.uint8(255*resize(rgba_heat,output_shape=(image.shape[0],image.shape[1],4)))

    image = Image.fromarray(image).convert('RGB')
    #image.putalpha(255)

    return image, Image.fromarray(rgba_heat).convert('RGBA')

from dash_extensions.enrich import html, Input, Output, State
from dash import dcc, ALL, ctx, exceptions, Patch
def make_interstitium_dt_output(output,output_index):

    tissue_img, dt_mask = output
    tissue_img.putalpha(255)

    main_figure = go.Figure(
        layout = {'margin': {'t':0,'b':0,'l':0,'r':0}}
    )
    main_figure.add_trace(go.Image(z=tissue_img))
    main_figure.add_trace(go.Image(z=dt_mask,opacity=0.5,colormodel='rgba'))

    tissue_img_base_div = html.Div([
        dcc.Graph(
            figure = main_figure,
            id = {'type': 'dt-overlay-fig','index': 0}
        )
    ])

    dt_component = html.Div([
        tissue_img_base_div,
        dcc.Slider(
            min = 0,
            max = 1,
            step = 0.1,
            value = 0.5,
            id = {'type': 'dt-overlay-slider','index': output_index}
        )
    ])

    return dt_component

def update_dt_opacity(slider_val):

    if not any([i['value'] is not None for i in ctx.triggered]):
        raise exceptions.PreventUpdate
    
    updated_transparency = Patch()
    updated_transparency['data'][1]['opacity'] = slider_val[0]

    return [updated_transparency]

interstitium_thickness = FUSIONFunction(
    title = 'Interstitial Distance',
    description = 'Display distance between annotated structures as a heatmap',
    function = lambda annotations, image: make_interstitium_dt_map(annotations, image),
    function_type = 'ROI',
    input_spec = [
        {
            'name': 'annotations',
            'description': 'Annotations between which to find thickness',
            'type': 'annotation'
        },
        {
            'name': 'image',
            'description': 'Tissue containing interstitium and annotated structures.',
            'type': 'image'
        }
    ],
    output_spec = [
        {
            'type': 'function',
            'function': lambda output, output_index: make_interstitium_dt_output(output,output_index)
        }
    ],
    output_callbacks = [
        {
            'inputs': [
                Input({'type': 'dt-overlay-slider','index': ALL},'value')
            ],
            'outputs': [
                Output({'type': 'dt-overlay-fig','index':ALL},'figure')
            ],
            'function': lambda slider_val: update_dt_opacity(slider_val)
        }
    ]
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
                CustomFunction(
                    title = 'Test Functions',
                    description='Testing out different input/output types',
                    custom_function=[
                        buffer_shapes_component,
                        stain_mask_component,
                        interstitium_thickness
                    ]
                ),
            ],
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()


