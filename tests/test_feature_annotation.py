"""Testing FeatureAnnotation component
"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import SlideMap, FeatureAnnotation, BulkLabels


import pandas as pd

def main():

    # Grabbing first item from demo DSA instance
    base_url = 'https://demo.kitware.com/histomicstk/api/v1'
    item_id = '5bbdeed1e629140048d01bcb'

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )
    
    vis_session = Visualization(
        tileservers=[dsa_handler.get_tile_server(item_id)],
        components = [
            [
                SlideMap(),
                [
                    FeatureAnnotation(
                        storage_path = os.getcwd()+'\\tests\\Test_Annotations\\',
                        labels_format = 'json',
                        annotations_format = 'rgb'
                    ),
                    BulkLabels()
                ]
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()


