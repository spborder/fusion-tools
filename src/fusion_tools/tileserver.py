"""

Tile server components

"""

from fastapi import FastAPI, APIRouter, Response
import large_image
import requests
import json

import numpy as np
import uvicorn


class TileServer:
    """
    Components which pull information from a slide(s)
    """
    pass

class LocalTileServer(TileServer):
    """
    Tile server from image saved locally. Uses large-image to read and parse image formats (default: [common])
    """
    def __init__(self,
                 local_image_path: str,
                 tile_server_port = '8050'
                 ):

        self.local_image_path = local_image_path

        self.tile_server_port = tile_server_port

        self.tiles_url = f'http://localhost:{self.tile_server_port}/tiles/'+'{z}/{x}/{y}'
        self.regions_url = f'http://locahost:{self.tile_server_port}/tiles/region'

        self.tile_source = large_image.open(self.local_image_path,encoding='PNG')
        self.tiles_metadata = self.tile_source.getMetadata()

        self.router = APIRouter()
        self.router.add_api_route('/',self.root,methods=["GET"])
        self.router.add_api_route('/tiles/{z}/{x}/{y}',self.get_tile,methods=["GET"])
        self.router.add_api_route('/metadata',self.get_metadata,methods=["GET"])
        self.router.add_api_route('/tiles/region',self.get_region,methods=["GET"])
    
    def __str__(self):
        return f'TileServer class for {self.local_image_path} to http://localhost:{self.tile_server_port}'

    def root(self):
        return {'message': "Oh yeah, now we're cooking"}

    def get_tile(self,z:int, x:int, y:int, style = {}):
        try:
            raw_tile = self.tile_source.getTile(
                        x = x,
                        y = y,
                        z = z
                    )
            
        except large_image.exceptions.TileSourceXYZRangeError:
            # This error appears for any negative tile coordinates
            raw_tile = np.zeros((self.tiles_metadata['tileHeight'],self.tiles_metadata['tileWidth']),dtype=np.uint8).tobytes()

        return Response(content = raw_tile, media_type='image/png')
    
    def get_metadata(self):
        return Response(content = json.dumps(self.tiles_metadata),media_type = 'application/json')
    
    def get_region(self, top: int, left: int, bottom:int,right:int):
        """
        Grabbing a specific region in the image based on bounding box coordinates
        """
        image, mime_type = self.tile_source.getRegion(
            region = {
                'left': left,
                'top': top,
                'right': right,
                'bottom': bottom
            }
        )

        return Response(content = image, media_type = 'image/png')

    def start(self, port = 8050):
        app = FastAPI()
        app.include_router(self.router)

        uvicorn.run(app,host='0.0.0.0',port=port)

class DSATileServer(TileServer):
    """
    Use for linking visualization with remote tiles API (DSA server)
    """
    def __init__(self,
                 api_url: str,
                 item_id: str
                 ):

        self.base_url = api_url
        self.tiles_url = f'{api_url}/item/{item_id}/tiles/zxy/'+'{z}/{x}/{y}'
        self.regions_url = f'{api_url}/item/{item_id}/tiles/region'

        self.tiles_metadata = requests.get(
            f'{api_url}/item/{item_id}/tiles'
        ).json()

    def __str__(self):
        return f'DSATileServer for {self.base_url}'

class CustomTileServer(TileServer):
    """
    If using some other tiles endpoint (must pass tileSize and levels in dictionary)
    """
    def __init__(self,
                 tiles_url:str,
                 regions_url:str,
                 image_metadata: dict
                 ):
        
        self.tiles_url = tiles_url
        self.regions_url = regions_url

        assert all([i in image_metadata for i in ['tileWidth','tileHeight','sizeX','sizeY','levels']])
        self.tiles_metadata = image_metadata

    def __str__(self):
        return f'CustomTileServer for {self.tiles_url}'


