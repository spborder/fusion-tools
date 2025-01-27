"""
Testing non-interactive feature extraction functions
"""

import os
import sys
sys.path.append('./src/')
import numpy as np
from skimage.filters import threshold_otsu
from skimage.segmentation import watershed
from skimage import exposure
from skimage.color import rgb2hsv
import scipy.ndimage as ndi
from skimage.morphology import remove_small_holes, remove_small_objects
from skimage.feature import peak_local_max
from skimage.transform import rescale


from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.tileserver import DSATileServer 
from fusion_tools.feature_extraction import ParallelFeatureExtractor


def main():

    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    item_id = '64f545302d82d04be3e39eec'

    # Starting visualization session
    tile_server = DSATileServer(
        api_url = base_url,
        item_id = item_id
    )

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )

    print('Getting annotations')
    annotations = dsa_handler.get_annotations(
        item = item_id
    )

    print([f'{a["properties"]["name"]}: {len(a["features"])}' for a in annotations])

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
                #masked_remaining_pixels = np.multiply(remaining_pixels,mask)
                masked_remaining_pixels = remaining_pixels

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
        remaining_pixels = np.multiply(mask,remainder_mask)
        #remaining_pixels = remainder_mask
        sub_comp_image[remaining_pixels>0,idx] = 1

        final_mask = np.zeros_like(remainder_mask)
        final_mask += sub_comp_image[:,:,0]
        final_mask += 2*sub_comp_image[:,:,1]
        final_mask += 3*sub_comp_image[:,:,2]

        return final_mask


    
    feature_extractor = ParallelFeatureExtractor(
        image_source = tile_server,
        feature_list = [
            'distance_transform',
            'morphology',
            'color',
            'texture'
        ],
        preprocess = lambda image: rescale(image,2,channel_axis=-1),
        sub_mask = lambda image,mask: stain_mask(image,mask),
        mask_names = ['Nuclei','Eosinophilic','Luminal Space'],
        channel_names = ['Red','Green','Blue'],
        n_jobs = 4,
        verbose = True
    )

    feature_df = feature_extractor.start(annotations[0]['features'])

    print(feature_df)
    import json
    print(json.dumps(feature_df.to_dict('records'),indent=4))
    feature_df.to_csv('.\\tests\\test_features.csv')







if __name__=='__main__':
    main()

