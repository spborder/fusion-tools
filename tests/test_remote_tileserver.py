"""

Testing remote tile server from DSA instance


"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization
from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import SlideMap


def main():

    base_url = 'https://demo.kitware.com/histomicstk/api/v1'

    # Starting visualization session
    tile_server = DSATileServer(
        api_url = base_url,
        item_id = '5bbdeed1e629140048d01bcb'
    )

    vis_session = Visualization(
        components = [
            [
                SlideMap(
                    tile_server = tile_server,
                    annotations = None
                )
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()

