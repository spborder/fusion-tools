"""

Testing tile server with local tile source

"""

import os
import sys
sys.path.append('./src/')
from fusion_tools.visualization import TileServer, LocalSlideViewer


def main():

    path_to_slide = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\XY01_IU-21-015F.svs'

    tile_server = TileServer(
        local_image_path = path_to_slide
    )
    tile_server.start()

    slide_viewer = LocalSlideViewer(
        local_image_path = path_to_slide,
        port = '8080'
    )


if __name__=='__main__':
    main()









