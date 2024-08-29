"""

Testing tile server with local tile source

"""

import os
import sys
sys.path.append('./src/')
from fusion_tools.visualization.components import LocalTileServer
import threading


def main():

    path_to_slide = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\XY01_IU-21-015F.svs'

    tile_server = LocalTileServer(
        local_image_path = path_to_slide
    )

    #TODO: Should this be included in the tile_server.start method?
    new_thread = threading.Thread(target = tile_server.start, name = 'local_tile_server', args = ['8050'])
    new_thread.daemon = True
    new_thread.start()


if __name__=='__main__':
    main()


