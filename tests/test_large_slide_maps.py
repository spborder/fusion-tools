"""Testing out LargeSlideMap components
"""

import os
import sys
sys.path.append('./src/')
import json
import requests

from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.visualization import Visualization
from fusion_tools.components.maps import LargeSlideMap, SlideMap
from fusion_tools.components import OverlayOptions



def main():

    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    item_id = '64f545302d82d04be3e39eec'

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )

    dsa_tileserver = [
        dsa_handler.get_tile_server(item_id)
    ]
    
    base_dir = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\'
    local_slide_list = [
        base_dir+'XY01_IU-21-015F_001.svs'
    ]
    local_annotations_list = [
        base_dir+'XY01_IU-21-015F_001.xml'
    ]

    vis_session = Visualization(
        local_slides = local_slide_list,
        local_annotations = local_annotations_list,
        tileservers = dsa_tileserver,
        components = [
            [
                LargeSlideMap(
                    min_zoom = 4
                ),
                [
                    OverlayOptions()
                ]
            ]
        ]
    )

    vis_session.start()




















if __name__=='__main__':
    main()
