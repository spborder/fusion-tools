"""

Tile server components

"""
import os
from fastapi import FastAPI, APIRouter, Response
from fastapi.middleware.cors import CORSMiddleware
import large_image
import requests
import json
from typing_extensions import Union

import numpy as np
import uvicorn

from shapely.geometry import box, shape

from fusion_tools.utils.shapes import (load_annotations,
                                       histomics_to_geojson, 
                                       detect_image_overlay, 
                                       detect_geojson, 
                                       detect_histomics,
                                       structures_within_poly)

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
                 local_metadata: Union[dict,list] = [],
                 tile_server_port:int = 8050,
                 host: str = 'localhost',
                 cors_options: dict = {'origins': ['*'], 'allow_methods': ['*'], 'allow_headers': ['*'], 'expose_headers': ['*']}
                 ):
        """Constructor method

        :param local_image_path: File path for image saved locally
        :type local_image_path: str
        :param tile_server_port: Tile server path where tiles are accessible from, defaults to '8050'
        :type tile_server_port: str, optional
        """

        self.local_image_paths = local_image_path if type(local_image_path)==list else [local_image_path]
        self.local_image_annotations = local_image_annotations if type(local_image_annotations)==list else [local_image_annotations]
        self.local_metadata = local_metadata
        self.tile_server_port = tile_server_port
        self.host = host
        self.cors_options = cors_options

        self.cors_headers = {
            'Access-Control-Allow-Origin': self.cors_options['origins'],
            'Access-Control-Allow-Methods': self.cors_options['allow_methods'],
            'Access-Control-Allow-Headers': self.cors_options['allow_headers'],
            'Access-Control-Expose-Headers': self.cors_options['expose_headers'],
            'Access-Control-Allow-Credentials': True
        }

        self.names = [i.split(os.sep)[-1] for i in self.local_image_paths]
   
        self.tile_sources = [large_image.open(i,encoding='PNG') for i in self.local_image_paths]
        self.tiles_metadatas = [i.getMetadata() for i in self.tile_sources]
        self.annotations, self.annotations_metadata = self.load_annotations()
        self.metadata = self.local_metadata if not self.local_metadata is None else [{} for i in self.local_image_paths]

        self.app = FastAPI()

        self.router = APIRouter()
        self.router.add_api_route('/',self.root,methods=["GET"])
        self.router.add_api_route('/names',self.get_names,methods=["GET"])
        self.router.add_api_route('/{image}/tiles/{z}/{x}/{y}',self.get_tile,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/image_metadata',self.get_image_metadata,methods=["GET"])
        self.router.add_api_route('/{image}/metadata',self.get_metadata,methods=["GET"])
        self.router.add_api_route('/{image}/tiles/region',self.get_region,methods=["GET"])
        self.router.add_api_route('/{image}/tiles/thumbnail',self.get_thumbnail,methods=["GET"])
        self.router.add_api_route('/{image}/annotations',self.get_annotations,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/annotations/metadata',self.get_annotations_metadata,methods=["GET","OPTIONS"])

    def load_annotations(self):

        geojson_annotations = []
        annotations_metadata = []
        if not self.local_image_annotations is None:
            if type(self.local_image_annotations)==str:
                new_loaded_annotations = load_annotations(self.local_image_annotations)
                if not new_loaded_annotations is None:
                    geojson_annotations.append(new_loaded_annotations)
                    annotations_metadata.append(self.extract_meta_dict(new_loaded_annotations))
                else:
                    print(f'Unrecognized annotation format: {self.local_image_annotations}')
                    geojson_annotations.append([])
                    annotations_metadata.append([])

            elif hasattr(self.local_image_annotations,"to_dict"):
                geojson_annotations.append([self.local_image_annotations.to_dict()])
                annotations_metadata.append(self.extract_meta_dict(self.local_image_annotations))

            elif type(self.local_image_annotations)==list:
                for n in self.local_image_annotations:
                    processed_anns = []
                    if not n is None:
                        if hasattr(n,"to_dict"):
                            processed_anns.append(n.to_dict())
                        elif type(n)==dict:
                            if 'annotation' in n:
                                converted = histomics_to_geojson(n)
                                processed_anns.append(converted)
                            else:
                                processed_anns.append(n)
                        elif type(n)==str:
                            loaded_anns = load_annotations(n)
                            if not loaded_anns is None:
                                if type(loaded_anns)==list:
                                    processed_anns.extend(loaded_anns)
                                elif type(loaded_anns)==dict:
                                    processed_anns.append(loaded_anns)
                            else:
                                print(f'Unrecognized Format: {n}')

                        elif type(n)==np.ndarray:
                            print(f'Found annotations of type: {type(n)}, make sure to specify if this is an overlay image (use fusion_tools.SlideImageOverlay) or a label mask (use fusion_tools.utils.shapes.load_label_mask)')
                        else:
                            print(f'Unknown annotations type found: {n}')
                    
                    geojson_annotations.append(processed_anns)
                    annotations_metadata.append(self.extract_meta_dict(processed_anns))
                        
            elif type(self.local_image_annotations)==dict:
                if 'annotation' in self.local_image_annotations:
                    converted_annotations = histomics_to_geojson(self.local_image_annotations)
                    geojson_annotations.append([converted_annotations])
                    annotations_metadata.append(self.extract_meta_dict([converted_annotations]))
                else:
                    geojson_annotations.append([self.local_image_annotations])
                    annotations_metadata.append(self.extract_meta_dict([self.local_image_annotations]))
        else:
            geojson_annotations.append([])
            annotations_metadata.append([])

        return geojson_annotations, annotations_metadata

    def extract_meta_dict(self, annotations):

        if not type(annotations)==list:
            annotations = [annotations]

        ann_metadata = []
        for a in annotations:
            if hasattr(a,'to_dict'):
                a = a.to_dict()
                
            if 'properties' in a:
                ann_metadata.append({
                    'name': a['properties']['name'],
                    '_id': a['properties']['_id'] 
                })
            elif 'image_path' in a:
                ann_metadata.append(a)

        return ann_metadata

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
        self.tiles_metadatas.append(new_tiles_metadata)

        if not new_metadata is None:
            self.metadata.append(new_metadata)
        else:
            self.metadata.append({})

        if not new_annotations is None:
            if type(new_annotations)==str:
                new_loaded_annotations = load_annotations(new_annotations)
                if not new_loaded_annotations is None:
                    self.annotations.append(new_loaded_annotations)
                    self.annotations_metadata.append(self.extract_meta_dict(new_loaded_annotations))
                else:
                    print(f'Unrecognized annotation format: {new_annotations}')
                    self.annotations.append([])
                    self.annotations_metadata.append([])

            elif hasattr(new_annotations,"to_dict"):
                self.annotations.append([new_annotations.to_dict()])
                self.annotations_metadata.append(self.extract_meta_dict(new_annotations))

            elif type(new_annotations)==list:
                processed_anns = []
                for n in new_annotations:
                    if not n is None:
                        if hasattr(n,"to_dict"):
                            processed_anns.append(n.to_dict())
                        elif type(n)==dict:
                            if 'annotation' in n:
                                converted = histomics_to_geojson(n)
                                processed_anns.append(converted)
                            else:
                                processed_anns.append(n)
                        elif type(n)==str:
                            loaded_anns = load_annotations(n)
                            if not loaded_anns is None:
                                if type(loaded_anns)==list:
                                    processed_anns.extend(loaded_anns)
                                elif type(loaded_anns)==dict:
                                    processed_anns.append(loaded_anns)
                            else:
                                print(f'Unrecognized format: {n}')

                        elif type(n)==np.ndarray:
                            print(f'Found annotations of type: {type(n)}, make sure to specify if this is an overlay image (use fusion_tools.SlideImageOverlay) or a label mask (use fusion_tools.utils.shapes.load_label_mask)')
                        else:
                            print(f'Unknown annotations type found: {n}')
                
                self.annotations.append(processed_anns)
                self.annotations_metadata.append(self.extract_meta_dict(processed_anns))
                    
            elif type(new_annotations)==dict:
                if 'annotation' in new_annotations:
                    converted_annotations = histomics_to_geojson(new_annotations)
                    self.annotations.append([converted_annotations])
                    self.annotations_metadata.append(self.extract_meta_dict([converted_annotations]))
                else:
                    self.annotations.append([new_annotations])
                    self.annotations_metadata.append(self.extract_meta_dict([new_annotations]))
        else:
            self.annotations.append([])
            self.annotations_metadata.append([])

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

    def get_name_annotations_metadata_url(self,name):

        if name in self.names:
            name_index = self.names.index(name)

            return f'http://{self.host}:{self.tile_server_port}/{name_index}/annotations/metadata'
        else:
            return None

    def get_name_metadata_url(self,name):
        
        if name in self.names:
            name_index = self.names.index(name)

            return f'http://{self.host}:{self.tile_server_port}/{name_index}/metadata'
        else:
            return None
        
    def get_name_image_metadata_url(self,name):

        if name in self.names:
            name_index = self.names.index(name)

            return f'http://{self.host}:{self.tile_server_port}/{name_index}/image_metadata'

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

            return Response(content = raw_tile, media_type='image/png',headers=self.cors_headers)
        else:
            return Response(content = 'invalid image index', media_type='application/json',status_code=400,headers=self.cors_headers)
    
    def get_image_metadata(self,image:int):
        """Getting large-image metadata for image

        :return: Dictionary containing metadata for local image
        :rtype: Response
        """
        if image<len(self.tiles_metadatas) and image>=0:
            return Response(content = json.dumps(self.tiles_metadatas[image]),media_type = 'application/json',headers=self.cors_headers)
        else:
            return Response(content = 'invalid image index',media_type='application/json', status_code=400,headers=self.cors_headers)
        
    def get_metadata(self, image:int):
        """Getting metadata associated with slide/case/patient

        :param image: Index of local image
        :type image: int
        """
        if image<len(self.metadata) and image>=0:
            return Response(content = json.dumps(self.metadata[image]),media_type = 'application/json',headers=self.cors_headers)
        else:
            return Response(content = 'invalid image index',media_type='application/json',status_code=400,headers=self.cors_headers)
    
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

            return Response(content = image_region, media_type = 'image/png',headers=self.cors_headers)
        else:
            return Response(content = 'invalid image index', media_type = 'application/json', status_code = 400,headers=self.cors_headers)

    def get_thumbnail(self, image:int):
        """Grabbing an image thumbnail

        :param image: _description_
        :type image: int
        """

        if image<len(self.names) and image>=0:
            thumbnail,mime_type = large_image.open(self.local_image_paths[image]).getThumbnail(encoding='PNG')
            return Response(content = thumbnail, media_type = 'image/png',headers=self.cors_headers)
        else:
            return Response(content = 'invalid image index', media_type = 'application/json', status_code=400,headers=self.cors_headers)

    def get_annotations(self,image:int, top:Union[int,None]=None, left:Union[int,None]=None, bottom: Union[int,None]=None, right: Union[int,None]=None):
        
        #TODO: Add region parameters here. Enable grabbing annotations only from certain regions.
        if image<len(self.names) and image>=0:
            if all([i is None for i in [top,left,bottom,right]]):
                # Returning all annotations by default
                return Response(
                    content = json.dumps(self.annotations[image]),
                    media_type='application/json',
                    headers = self.cors_headers
                )
            else:
                # Parsing region of annotations:
                if all([not i is None for i in [top,left,bottom,right]]):
                    image_anns = self.annotations[image]
                    image_region_anns = []
                    query_poly = box(top,left,bottom,right)

                    if type(image_anns)==dict:
                        image_anns = [image_anns]
                    for ann in image_anns:
                        if detect_image_overlay(ann):
                            image_bounds_box = box(*ann['image_bounds'])
                            if image_bounds_box.intersects(query_poly):
                                image_region_anns.append(ann)
                                # If it doesn't intersect should it return anything?

                        elif detect_geojson(ann):
                            
                            if type(ann)==dict:
                                filtered_anns = structures_within_poly(
                                    original = ann,
                                    query= query_poly
                                )
                                if len(filtered_anns['features'])>0:
                                    image_region_anns.append(filtered_anns)
                            elif type(ann)==list:
                                for g in ann:
                                    filtered_g = structures_within_poly(
                                        original = g,
                                        query=query_poly
                                    )
                                    if len(filtered_g['features'])>0:
                                        image_region_anns.append(filtered_g)
                        else:
                            print(f'Unrecognized annotation format found for image: {image}, {self.names[image]}')
                    return Response(
                        content = json.dumps(image_region_anns), 
                        media_type='application/json',
                        headers = self.cors_headers
                    )

        else:
            return Response(
                content = 'invalid image index',
                media_type = 'application/json', 
                status_code = 400,
                headers = self.cors_headers
            )

    def get_annotations_metadata(self,image:int):
        
        if image<len(self.names) and image>=0:
            return Response(
                content = json.dumps(self.annotations_metadata[image]),
                media_type='application/json',
                headers = self.cors_headers
            )
        else:
            return Response(
                content = 'invalid image index',
                media_type = 'application/json',
                status_code = 400,
                headers = self.cors_headers
            )

    def start(self):
        """Starting tile server instance on a provided port

        :param port: Tile server port from which tiles are accessed, defaults to '8050'
        :type port: str, optional
        """
        self.app.include_router(self.router)
        
        # Enabling CORS (https://fastapi.tiangolo.com/tutorial/cors/#use-corsmiddleware)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins =self.cors_options['origins'],
            allow_methods=self.cors_options['allow_methods'],
            allow_headers=self.cors_options['allow_headers'],
            expose_headers=self.cors_options['expose_headers']
        )

        uvicorn.run(self.app,host=self.host,port=self.tile_server_port)

class DSATileServer(TileServer):
    """Use for linking visualization with remote tiles API (DSA server)
    """
    def __init__(self,
                 api_url: str,
                 item_id: str,
                 user_token: Union[str,None]=None):
        """Constructor method

        :param api_url: URL for DSA API (ends in /api/v1)
        :type api_url: str
        :param item_id: Girder item Id to get tiles from
        :type item_id: str
        """

        self.base_url = api_url
        self.item_id = item_id

        #TODO: Add some method for appending the user_token to these URLs (Might be better to save this on the 
        # component side so that that property can be dynamic)
        if user_token is None:
            info_url = f'{api_url}/item/{item_id}'

        else:
            info_url = f'{api_url}/item/{item_id}?token={user_token}'

        item_info = requests.get(info_url).json()
        self.item_metadata = item_info['meta']
        self.name = item_info['name']

        self.metadata_url = info_url

        self.tiles_url = f'{api_url}/item/{item_id}/tiles/zxy/'+'{z}/{x}/{y}'
        self.regions_url = f'{api_url}/item/{item_id}/tiles/region'
        self.image_metadata_url = f'{api_url}/item/{item_id}/tiles'

        self.tiles_metadata = requests.get(
            f'{api_url}/item/{item_id}/tiles'
        ).json()

        #TODO: Add some method here for accessing the /annotation/{ann_id}/region endpoint?
        self.annotations_url = f'{api_url}/annotation/item/{item_id}'

        if user_token is None:
            self.annotations_metadata_url = f'{api_url}/annotation?itemId={item_id}'
        else:
            self.annotations_metadata_url = f'{api_url}/annotation?token={user_token}&itemId={item_id}'

        annotations_metadata = requests.get(self.annotations_metadata_url).json()
        self.annotations_geojson_url = [f'{api_url}/annotation/{a["_id"]}/geojson' for a in annotations_metadata]

        self.annotations_region_url = f'{api_url}/annotation/'


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


