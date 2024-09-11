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

    # Starting local tile server
    tile_server = LocalTileServer(
        local_image_path = 'C:\\Users\\samuelborder\\Downloads\\10H_LargeGlobalFlatfield.tifStitchedO.svs'
    )

    new_thread = threading.Thread(target = tile_server.start, name = 'local_tile_server', args = ['8050'])
    new_thread.daemon = True
    new_thread.start()

    annotations = [
        SlideImageOverlay(
            image_path = 'C:\\Users\\samuelborder\\Downloads\\10H_LargeGlobalFlatfield.tif Y00003 X00008.jpg'
        )
    ]
    
    vis_session = Visualization(
        components = [
            [
                SlideMap(
                    tile_server = tile_server,
                    annotations = annotations
                )
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()













