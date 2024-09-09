"""

Testing MultiFrameSlideMap

"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization, DSAHandler
from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import MultiFrameSlideMap


def main():

    # Grabbing first item from demo DSA instance
    base_url = 'https://demo.kitware.com/histomicstk/api/v1'
    item_id = '60e6135c25f89bfa9369f2c9'

    # Starting visualization session
    tile_server = DSATileServer(
        api_url = base_url,
        item_id = item_id
    )
    print(tile_server.tiles_metadata)

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )

    # Checking how many annotations this item has:
    #print('This item has the following annotations: ')
    #print(dsa_handler.query_annotation_count(item=item_id).to_dict('records'))

    annotations = dsa_handler.get_annotations(
        item = item_id
    )

    vis_session = Visualization(
        components = [
            [
                MultiFrameSlideMap(
                    tile_server = tile_server,
                    annotations = annotations
                )
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()









