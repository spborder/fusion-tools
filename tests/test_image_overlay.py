"""Testing image overlay component
"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization
from fusion_tools.tileserver import LocalTileServer
from fusion_tools.components import SlideMap, SlideImageOverlay


def main():

    slide_list = ['C:\\Users\\samuelborder\\Downloads\\10H_LargeGlobalFlatfield.tifStitchedO.svs']

    annotations = [
        SlideImageOverlay(
            image_path = 'C:\\Users\\samuelborder\\Downloads\\10H_LargeGlobalFlatfield.tif Y00003 X00008.jpg'
        )
    ]
    
    vis_session = Visualization(
        local_slides = slide_list,
        local_annotations=annotations,
        components = [
            [
                SlideMap()
            ]
        ],
        app_options = {
            'port': 8060
        }
    )

    vis_session.start()


if __name__=='__main__':
    main()

