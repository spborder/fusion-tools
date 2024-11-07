"""

Testing property plotter using remote slide with rich annotation properties


"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization, DSAHandler
from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import SlideMap,OverlayOptions, PropertyViewer, PropertyPlotter, HRAViewer
from fusion_tools.utils.shapes import align_object_props


import pandas as pd

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
    
    vis_session = Visualization(
        tileservers = dsa_tileserver,
        components = [
            [
                SlideMap(),
                [
                    OverlayOptions(),
                    PropertyViewer(),
                    PropertyPlotter(),
                    HRAViewer()
                ]
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()

