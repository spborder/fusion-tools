"""

Tile server components

"""
import os
from fastapi import FastAPI, APIRouter, Response
import large_image
import requests
import json
from typing_extensions import Union

import numpy as np
import uvicorn

from fusion_tools.utils.shapes import load_annotations, convert_histomics

class TileServer:
    """Components which pull information from a slide(s)
    """
    pass

class LocalTileServer(TileServer):
    """Tile server from image saved locally. Uses large-image to read and parse image formats (default: [common])
    """
    def __init__(self,
                 local_image_path: Union[str,list,None] = [],
                 local_image_annotations: Union[str,list] = [],
                 tile_server_port:int = 8050,
                 host: str = 'localhost'
                 ):
        """Constructor method

        :param local_image_path: File path for image saved locally
        :type local_image_path: str
        :param tile_server_port: Tile server path where tiles are accessible from, defaults to '8050'
        :type tile_server_port: str, optional
        """

        self.local_image_paths = local_image_path if type(local_image_path)==list else [local_image_path]
        self.local_image_annotations = local_image_annotations if type(local_image_annotations)==list else [local_image_annotations]
        self.tile_server_port = tile_server_port
        self.host = host

        self.names = [i.split(os.sep)[-1] for i in self.local_image_paths]
   
        self.tile_sources = [large_image.open(i,encoding='PNG') for i in self.local_image_paths]
        self.tiles_metadatas = [i.getMetadata() for i in self.tile_sources]
        self.annotations = self.load_annotations()

        self.app = FastAPI()
        self.router = APIRouter()
        self.router.add_api_route('/',self.root,methods=["GET"])
        self.router.add_api_route('/names',self.get_names,methods=["GET"])
        self.router.add_api_route('/{image}/tiles/{z}/{x}/{y}',self.get_tile,methods=["GET"])
        self.router.add_api_route('/{image}/metadata',self.get_metadata,methods=["GET"])
        self.router.add_api_route('/{image}/tiles/region',self.get_region,methods=["GET"])
        self.router.add_api_route('/{image}/annotations',self.get_annotations,methods=["GET"])

    def load_annotations(self):

        geojson_annotations = []
        for a in self.local_image_annotations:
            loaded_annotations = load_annotations(a)
            if not loaded_annotations is None:
                geojson_annotations.append(loaded_annotations)
            else:
                print(f'Invalid annotations format found: {a}')

        return geojson_annotations

    def __str__(self):
        return f'TileServer class for {self.local_image_path} to {self.host}:{self.tile_server_port}'

    def __len__(self):
        return len(self.tile_sources)
    
    def add_new_image(self,new_image_path:str, new_annotations:Union[str,list,dict,None], new_metadata:Union[dict,None] = None):

        self.local_image_paths.append(new_image_path)
        self.names.append(new_image_path.split(os.sep)[-1])
        new_tile_source = large_image.open(new_image_path)
        new_tiles_metadata = new_tile_source.getMetadata()

        # Treating 3-frame images as RGB by default
        if 'frames' in new_tiles_metadata:
            if len(new_tiles_metadata['frames'])==3:
                new_tile_source = large_image.open(
                    new_image_path,
                    style = {
                        "bands": [
                            {
                                "framedelta": c_idx,
                                "palette": ["rgba(0,0,0,0)","rgba("+",".join(["255" if i==c_idx else "0" for i in range(3)]+["255"])+")"]
                            }
                            for c_idx in range(3)
                        ]
                    }
                )

        self.tile_sources.append(new_tile_source)
        if not new_metadata is None:
            self.tiles_metadata.append(new_tiles_metadata | {'user': new_metadata})
        else:
            self.tiles_metadatas.append(new_tiles_metadata)

        if not new_annotations is None:
            if type(new_annotations)==str:
                new_loaded_annotations = load_annotations(new_annotations)
                if not new_loaded_annotations is None:
                    self.annotations.append(new_loaded_annotations)
                else:
                    print(f'Unrecognized annotation format: {new_annotations}')
                    self.annotations.append([])

            elif hasattr(new_annotations,"to_dict"):
                self.annotations.append([new_annotations.to_dict()])

            elif type(new_annotations)==list:
                processed_anns = []
                for n in new_annotations:
                    if hasattr(n,"to_dict"):
                        processed_anns.append(n.to_dict())
                    elif type(n)==dict:
                        if 'annotation' in n:
                            converted = convert_histomics(n)
                            processed_anns.append(converted)
                        else:
                            processed_anns.append(n)
                    elif type(n)==str:
                        loaded_anns = load_annotations(n)
                        if type(loaded_anns)==list:
                            processed_anns.extend(loaded_anns)
                        elif type(loaded_anns)==dict:
                            processed_anns.append(loaded_anns)

                    elif type(n)==np.ndarray:
                        print(f'Found annotations of type: {type(n)}, make sure to specify if this is an overlay image (use fusion_tools.SlideImageOverlay) or a label mask (use fusion_tools.utils.shapes.load_label_mask)')
                    else:
                        print(f'Unknown annotations type found: {n}')
                
                self.annotations.append(processed_anns)
                    
            elif type(new_annotations)==dict:
                if 'annotation' in new_annotations:
                    converted_annotations = convert_histomics(new_annotations)
                    self.annotations.append([converted_annotations])
                else:
                    self.annotations.append([new_annotations])
        else:
            self.annotations.append([])

    def root(self):
        return {'message': "Oh yeah, now we're cooking"}

    def get_names(self):
        return {'message': self.names}

    def get_name_tiles_url(self,name):

        if name in self.names:
            name_index = self.names.index(name)

            name_meta = self.tiles_metadatas[name_index]
            if 'frames' in name_meta:
                if len(name_meta['frames'])==3:
                    tiles_url = f'http://{self.host}:{self.tile_server_port}/{name_index}/tiles/'+'{z}/{x}/{y}'
                    #tiles_url += '/?style={"bands": [{"framedelta":0,"palette":"rgba(255,0,0,255)"},{"framedelta":1,"palette":"rgba(0,255,0,255)"},{"framedelta":2,"palette":"rgba(0,0,255,255)"}]}'
                else:
                    tiles_url = f'http://{self.host}:{self.tile_server_port}/{name_index}/tiles/'+'{z}/{x}/{y}'
            else:
                tiles_url = f'http://{self.host}:{self.tile_server_port}/{name_index}/tiles/'+'{z}/{x}/{y}'

            return tiles_url
        else:
            return None

    def get_name_regions_url(self,name):

        if name in self.names:
            name_index = self.names.index(name)

            return f'http://{self.host}:{self.tile_server_port}/{name_index}/tiles/region'
        else:
            return None

    def get_name_annotations_url(self,name):

        if name in self.names:
            name_index = self.names.index(name)

            return f'http://{self.host}:{self.tile_server_port}/{name_index}/annotations'
        else:
            return None

    def get_name_metadata_url(self,name):
        
        if name in self.names:
            name_index = self.names.index(name)

            return f'http://{self.host}:{self.tile_server_port}/{name_index}/metadata'
        else:
            return None

    def get_tile(self,image:int,z:int, x:int, y:int, style:str = ''):
        """Tiles endpoint, returns an image tyle based on provided coordinates

        :param z: Zoom level for tile
        :type z: int
        :param x: X tile coordinate
        :type x: int
        :param y: Y tile coordinate
        :type y: int
        :param style: Additional style arguments to pass to large-image, defaults to {}
        :type style: dict, optional
        :return: Image tile containing bytes encoded pixel information
        :rtype: Response
        """
        
        if image<len(self.tile_sources) and image>=0:
            try:
                if not style=='':
                    self.tile_sources[image] = large_image.open(self.local_image_paths[image],style=json.loads(style))

                raw_tile = self.tile_sources[image].getTile(
                            x = x,
                            y = y,
                            z = z,
                        )
                
            except large_image.exceptions.TileSourceXYZRangeError:
                # This error appears for any negative tile coordinates
                raw_tile = np.zeros(
                    (
                        self.tiles_metadatas[image]['tileHeight'],
                        self.tiles_metadatas[image]['tileWidth']
                    ),
                    dtype=np.uint8
                ).tobytes()

            return Response(content = raw_tile, media_type='image/png')
        else:
            return Response(content = 'invalid image index', media_type='application/json')
    
    def get_metadata(self,image:int):
        """Getting large-image metadata for image

        :return: Dictionary containing metadata for local image
        :rtype: Response
        """
        if image<len(self.tiles_metadatas) and image>=0:
            return Response(content = json.dumps(self.tiles_metadatas[image]),media_type = 'application/json')
        else:
            return Response(content = 'invalid image index',media_type='application/json')
    
    def get_region(self, image:int, top: int, left: int, bottom:int, right:int,style:str = ''):
        """
        Grabbing a specific region in the image based on bounding box coordinates
        """
        """Grabbing a specific region of the image based on bounding box coordinates

        :return: Image region (bytes encoded)
        :rtype: Response
        """
        if image<len(self.tile_sources) and image>=0:
            if not style=='':
                self.tile_sources[image] = large_image.open(self.local_image_paths[image],style = json.loads(style))
            image_region, mime_type = self.tile_sources[image].getRegion(
                region = {
                    'left': left,
                    'top': top,
                    'right': right,
                    'bottom': bottom
                },
            )

            return Response(content = image_region, media_type = 'image/png')
        else:
            return Response(content = 'invalid image index', media_type = 'application/json')

    def get_annotations(self,image:int):

        if image<len(self.names) and image>=0:
            return Response(content = json.dumps(self.annotations[image]),media_type='application/json')

    def start(self):
        """Starting tile server instance on a provided port

        :param port: Tile server port from which tiles are accessed, defaults to '8050'
        :type port: str, optional
        """
        self.app.include_router(self.router)
        uvicorn.run(self.app,host=self.host,port=self.tile_server_port)

class DSATileServer(TileServer):
    """Use for linking visualization with remote tiles API (DSA server)

    """
    def __init__(self,
                 api_url: str,
                 item_id: str
                 ):
        """Constructor method

        :param api_url: URL for DSA API (ends in /api/v1)
        :type api_url: str
        :param item_id: Girder item Id to get tiles from
        :type item_id: str
        """

        self.base_url = api_url
        self.item_id = item_id

        self.name = requests.get(
            f'{api_url}/item/{item_id}'
        ).json()['name']

        self.tiles_url = f'{api_url}/item/{item_id}/tiles/zxy/'+'{z}/{x}/{y}'
        self.regions_url = f'{api_url}/item/{item_id}/tiles/region'
        self.metadata_url = f'{api_url}/item/{item_id}/tiles'

        self.tiles_metadata = requests.get(
            f'{api_url}/item/{item_id}/tiles'
        ).json()

        self.annotations_url = f'{api_url}/annotation/item/{item_id}'

    def __str__(self):
        return f'DSATileServer for {self.base_url}'

class CustomTileServer(TileServer):
    """CustomTileServer component if using some other tiles endpoint (must pass tileSize and levels in dictionary)
    """
    def __init__(self,
                 tiles_url:str,
                 regions_url:str,
                 image_metadata: dict,
                 annotations_url: Union[str,None] = None,
                 name: str = None
                 ):
        """Constructor method

        :param tiles_url: URL to grab tiles from (ends in "/{z}/{x}/{y}")
        :type tiles_url: str
        :param regions_url: URL to grab image regions from
        :type regions_url: str
        :param image_metadata: Dictionary containing at least ['tileWidth','tileHeight','sizeX','sizeY','levels']
        :type image_metadata: dict
        """
        
        self.tiles_url = tiles_url
        self.regions_url = regions_url
        self.annotations_url = annotations_url
        self.name = name

        assert all([i in image_metadata for i in ['tileWidth','tileHeight','sizeX','sizeY','levels']])
        self.tiles_metadata = image_metadata

    def __str__(self):
        return f'CustomTileServer for {self.tiles_url}'


