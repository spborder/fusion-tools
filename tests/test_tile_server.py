"""

Testing tile server with local tile source

"""

import os
import sys
sys.path.append('./src/')
from fusion_tools.visualization import TileServer, LocalSlideViewer
import threading


def main():

    path_to_slide = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\XY01_IU-21-015F.svs'

    tile_server = TileServer(
        local_image_path = path_to_slide
    )

    new_thread = threading.Thread(target = tile_server.start, name = 'local_tile_server', args = ['8050'])
    new_thread.daemon = True
    new_thread.start()

    slide_viewer = LocalSlideViewer(
        tile_server_port='8050',
        app_port = '8080'
    )


if __name__=='__main__':
    main()








