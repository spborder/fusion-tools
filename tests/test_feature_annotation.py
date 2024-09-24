"""Testing FeatureAnnotation component
"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization, DSAHandler
from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import SlideMap, FeatureAnnotation, BulkLabels


import pandas as pd

def main():

    # Grabbing first item from demo DSA instance
    base_url = 'https://demo.kitware.com/histomicstk/api/v1'
    item_id = '5bbdeed1e629140048d01bcb'

    # Starting visualization session
    tile_server = DSATileServer(
        api_url = base_url,
        item_id = item_id
    )

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )

    annotations = dsa_handler.get_annotations(
        item = item_id
    )
    
    vis_session = Visualization(
        components = [
            [
                SlideMap(
                    tile_server = tile_server,
                    annotations = annotations
                ),
                [
                    FeatureAnnotation(
                        storage_path = os.getcwd()+'\\tests\\Test_Annotations\\',
                        tile_server = tile_server,
                        labels_format = 'json',
                        annotations_format = 'rgb'
                    ),
                    BulkLabels(
                        geojson_anns = annotations,
                        tile_server = tile_server,
                        storage_path = os.getcwd()+'\\tests\\Test_Annotations\\'
                    )
                ]
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()























