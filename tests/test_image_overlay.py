"""Testing image overlay component
"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.components import SlideMap, SlideImageOverlay


def main():

    base_dir = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\'
    local_slide_list = [
        base_dir+'XY01_IU-21-015F.svs',
    ]


    annotations = [
        SlideImageOverlay(
            image_path = 'C:\\Users\\samuelborder\\Downloads\\20250224_095335.jpg'
        )
    ]
    
    vis_session = Visualization(
        local_slides = local_slide_list,
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

