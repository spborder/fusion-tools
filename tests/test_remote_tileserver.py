"""

Testing remote tile server from DSA instance


"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import SlideMap


def main():

    # Grabbing first item from demo DSA instance
    base_url = 'https://demo.kitware.com/histomicstk/api/v1'
    item_id = '5bbdeed1e629140048d01bcb'

    # Starting visualization session
    dsa_handler = DSAHandler(
        girderApiUrl=base_url
    )
    tile_server = dsa_handler.get_tile_server(item_id)

    vis_session = Visualization(
        tileservers = [tile_server],
        components = [
            [
                SlideMap()
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()

