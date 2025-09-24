"""

Testing tile server with local tile source

"""

import os
import sys
sys.path.append('./src/')
from fusion_tools.tileserver import LocalTileServer
from fusion_tools.database.database import fusionDB
import threading


def main():

    path_to_slide = 'tests/test_images/histology_image.svs'
    path_to_db = '.fusion_assets/'

    database = fusionDB(
        db_url = f'sqlite:///{path_to_db}fusion_database.db',
        echo = False
    )

    tile_server = LocalTileServer(
        database = database,
        tile_server_port=8080
    )

    tile_server.add_new_image(
        new_image_id = 'blah'*6,
        new_image_path = path_to_slide,
        new_annotations = None,
        new_metadata = {}
    )


    print(tile_server)
    #new_thread = threading.Thread(
    #    target = tile_server.start,
    #    name = 'local_tile_server',
    #    daemon=True
    #)
    #new_thread.start()
    tile_server.start()

if __name__=='__main__':
    main()


