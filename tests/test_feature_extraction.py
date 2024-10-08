"""
Testing non-interactive feature extraction functions
"""

import os
import sys
sys.path.append('./src/')


from fusion_tools.handler import DSAHandler
from fusion_tools.tileserver import DSATileServer 
from fusion_tools.feature_extraction import (
    ParallelFeatureExtractor, distance_transform_features, color_features,
    texture_features, morphological_features, relative_distance, threshold_channels
)


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
    
    feature_extractor = ParallelFeatureExtractor(
        image_source = tile_server,
        feature_list = [
            lambda image,mask,coords: distance_transform_features(image,mask,coords),
            lambda image,mask,coords: color_features(image,mask,coords),
            lambda image,mask,coords: texture_features(image,mask,coords),
            lambda image,mask,coords: morphological_features(image,mask,coords)
        ],
        preprocess = None,
        n_jobs = 4,
        verbose = True
    )

    feature_df = feature_extractor.start(annotations[0]['features'])

    print(feature_df)
    feature_df.to_csv('.\\tests\\test_features.csv')







if __name__=='__main__':
    main()

