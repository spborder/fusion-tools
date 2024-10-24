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
        local_image_path = 'C:\\Users\\samuelborder\\Downloads\\10H_LargeGlobalFlatfield.tifStitchedO.svs',
        tile_server_port='8080',
        host = 'localhost'
    )
    new_thread = threading.Thread(target = tile_server.start, name = 'local_tile_server', args = [])
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
        ],
        app_options = {
            'port': '8060'
        }
    )

    vis_session.start()


if __name__=='__main__':
    main()













