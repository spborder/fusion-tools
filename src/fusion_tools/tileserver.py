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

from copy import deepcopy
import numpy as np
import uvicorn

from shapely.geometry import box, shape

from fusion_tools.visualization.database import (
    fusionDB, User, VisSession, Item, Layer, Structure,
    ImageOverlay, Annotation) 
from fusion_tools.utils.shapes import (
    load_annotations,
    histomics_to_geojson, 
    detect_image_overlay, 
    detect_geojson, 
    detect_histomics,
    structures_within_poly,
    extract_nested_prop)


class Slide:
    """Local slide object with built-in methods for checking paths, loading annotations
    """
    def __init__(self,
                 image_filepath: Union[str,None] = None,
                 annotations: Union[str,list,dict,None] = None,
                 metadata: Union[dict,None] = None,
                 image_style: Union[dict,None] = None):
        
        self.image_filepath = image_filepath
        self.annotations = annotations
        self.metadata = metadata
        self.image_style = image_style

        # Checking path exists
        assert(os.path.exists(self.image_filepath))
        
        # Checking image is readable by large_image
        if image_style is None:
            img_source = large_image.open(self.image_filepath)
        else:
            img_source = large_image.open(
                self.image_filepath,
                style = self.image_style
            )

        self.image_metadata = img_source.getMetadata()

        # Treating 3-frame images as RGB by default
        if 'frames' in self.image_metadata:
            if len(self.image_metadata['frames'])==3:
                new_tile_source = large_image.open(
                    self.image_filepath,
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
                self.image_style = {
                    "bands": [
                        {
                            "framedelta": c_idx,
                            "palette": ["rgba(0,0,0,0)","rgba("+",".join(["255" if i==c_idx else "0" for i in range(3)]+["255"])+")"]
                        }
                        for c_idx in range(3)
                    ]
                }


        if type(self.annotations)==str:
            assert(os.path.exists(self.annotations))

        self.processed_annotations, self.annotations_metadata = self.load_annotations(self.annotations)

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

    def load_annotations(self, annotations):

        geojson_annotations = []
        annotations_metadata = []
        if not annotations is None:
            if type(annotations)==str:
                new_loaded_annotations = load_annotations(annotations)
                if not new_loaded_annotations is None:
                    geojson_annotations.append(new_loaded_annotations)
                    annotations_metadata.append(self.extract_meta_dict(new_loaded_annotations))
                else:
                    print(f'Unrecognized annotation format: {annotations}')
                    geojson_annotations.append([])
                    annotations_metadata.append([])

            elif hasattr(annotations,"to_dict"):
                geojson_annotations.append([annotations.to_dict()])
                annotations_metadata.append(self.extract_meta_dict(annotations))

            elif type(annotations)==list:
                for n in annotations:
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
                        
            elif type(annotations)==dict:
                if 'annotation' in annotations:
                    converted_annotations = histomics_to_geojson(annotations)
                    geojson_annotations.append([converted_annotations])
                    annotations_metadata.append(self.extract_meta_dict([converted_annotations]))
                else:
                    geojson_annotations.append([annotations])
                    annotations_metadata.append(self.extract_meta_dict([annotations]))
        else:
            geojson_annotations.append([])
            annotations_metadata.append([])

        return geojson_annotations, annotations_metadata    


class TileServer:
    """Components which pull information from a slide(s)
    """
    pass

class LocalTileServer(TileServer):
    """Tile server from image saved locally. Uses large-image to read and parse image formats (default: [common])
    """
    def __init__(self,
                 database: Union[fusionDB,None] = None,
                 tile_server_port:int = 8050,
                 host: str = 'localhost',
                 protocol: str = 'http',
                 cors_options: dict = {'origins': ['*'], 'allow_methods': ['*'], 'allow_headers': ['*'], 'expose_headers': ['*'], 'max_age': '36000000'}
                 ):
        """Constructor method

        :param local_image_path: File path for image saved locally
        :type local_image_path: str
        :param tile_server_port: Tile server path where tiles are accessible from, defaults to '8050'
        :type tile_server_port: str, optional
        """

        self.database = database
        self.tile_server_port = tile_server_port
        self.host = host
        self.protocol = protocol
        self.cors_options = cors_options

        self.app = FastAPI()

        self.router = APIRouter()
        self.router.add_api_route('/',self.root,methods=["GET","OPTIONS"])
        self.router.add_api_route('/names',self.get_names,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/tiles/{z}/{x}/{y}',self.get_tile,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/image_metadata',self.get_image_metadata,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/metadata',self.get_metadata,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/tiles/region',self.get_region,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/tiles/thumbnail',self.get_thumbnail,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/annotations',self.get_annotations,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/annotations/metadata',self.get_annotations_metadata,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/annotations/data/list',self.get_annotations_property_keys,methods=["GET","OPTIONS"])
        self.router.add_api_route('/{image}/annotations/data',self.get_annotations_property_data,methods=["GET","OPTIONS"])


    def __str__(self):
        return f'TileServer class to {self.host}:{self.tile_server_port}'

    def __len__(self):
        """Return number of items 

        :return: Count of items in local database
        :rtype: int
        """
        count = self.database.count(
            table_name = 'item'
        )

        return count
    
    def add_new_image(self,new_image_id:str, new_image_path:str, new_annotations:Union[str,list,dict,None] = None, new_metadata:Union[dict,None] = None, new_image_style:Union[dict,None] = None):

        # Verifying filepaths and loading annotations
        new_local_item = Slide(
            image_filepath=new_image_path,
            annotations = new_annotations,
            metadata = new_metadata,
            image_style=new_image_style
        )

        slide_name = new_image_path.split(os.sep)[-1]
        # Adding information to database
        self.database.add_slide(new_image_id,slide_name,new_local_item)

    def root(self):
        return {'message': "Oh yeah, now we're cooking"}

    def get_names(self):
        """Get names of items in fusionDB

        :return: Message dictionary containing list of all item names
        :rtype: dict
        """
        item_names = self.database.get_names(
            table_name = 'item'
        )

        return {'message': item_names}

    def get_tiles_url(self,slide_id):
        tiles_url = f'{self.protocol}://{self.host}:{self.tile_server_port}/{slide_id}/tiles/'+'{z}/{x}/{y}'
        return tiles_url

    def get_regions_url(self,slide_id):
        regions_url = f'{self.protocol}://{self.host}:{self.tile_server_port}/{slide_id}/tiles/region'
        return regions_url

    def get_annotations_url(self,slide_id):
        annotations_url = f'{self.protocol}://{self.host}:{self.tile_server_port}/{slide_id}/annotations'
        return annotations_url

    def get_annotations_metadata_url(self,slide_id):
        annotations_metadata_url = f'{self.protocol}://{self.host}:{self.tile_server_port}/{slide_id}/annotations/metadata'
        return annotations_metadata_url

    def get_metadata_url(self,slide_id):
        metadata_url = f'{self.protocol}://{self.host}:{self.tile_server_port}/{slide_id}/metadata'
        return metadata_url
        
    def get_image_metadata_url(self,slide_id):
        image_metadata_url = f'{self.protocol}://{self.host}:{self.tile_server_port}/{slide_id}/image_metadata'
        return image_metadata_url

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
            return Response(content = 'invalid image index', media_type='application/json',status_code=400)
    
    def get_image_metadata(self,image:int):
        """Getting large-image metadata for image

        :return: Dictionary containing metadata for local image
        :rtype: Response
        """
        if image<len(self.tiles_metadatas) and image>=0:
            return Response(content = json.dumps(self.tiles_metadatas[image]),media_type = 'application/json')
        else:
            return Response(content = 'invalid image index',media_type='application/json', status_code=400)
        
    def get_metadata(self, image:int):
        """Getting metadata associated with slide/case/patient

        :param image: Index of local image
        :type image: int
        """
        if image<len(self.metadata) and image>=0:
            return Response(content = json.dumps(self.metadata[image]),media_type = 'application/json')
        else:
            return Response(content = 'invalid image index',media_type='application/json',status_code=400)
    
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
            return Response(content = 'invalid image index', media_type = 'application/json', status_code = 400)

    def get_thumbnail(self, image:int):
        """Grabbing an image thumbnail

        :param image: _description_
        :type image: int
        """

        if image<len(self.names) and image>=0:
            thumbnail,mime_type = large_image.open(self.local_image_paths[image]).getThumbnail(encoding='PNG')
            return Response(content = thumbnail, media_type = 'image/png')
        else:
            return Response(content = 'invalid image index', media_type = 'application/json', status_code=400)

    def get_annotations(self,image:int, top:Union[int,None]=None, left:Union[int,None]=None, bottom: Union[int,None]=None, right: Union[int,None]=None):
        
        #TODO: Add region parameters here. Enable grabbing annotations only from certain regions.
        if image<len(self.names) and image>=0:
            if all([i is None for i in [top,left,bottom,right]]):
                # Returning all annotations by default
                return Response(
                    content = json.dumps(self.annotations[image]),
                    media_type='application/json'
                )
            else:
                # Parsing region of annotations:
                if all([not i is None for i in [top,left,bottom,right]]):
                    image_anns = self.annotations[image]
                    image_region_anns = []
                    # Shapely box requires minx, miny, maxx, maxy
                    query_poly = box(left,top,right,bottom)

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
                                    filtered_anns['properties'] = ann['properties']
                                    image_region_anns.append(filtered_anns)
                                else:
                                    image_region_anns.append({
                                        'type': 'FeatureCollection',
                                        'features':[],
                                        'properties':ann['properties']
                                    })
                            elif type(ann)==list:
                                for g in ann:
                                    filtered_g = structures_within_poly(
                                        original = g,
                                        query=query_poly
                                    )
                                    if len(filtered_g['features'])>0:
                                        filtered_g['properties'] = g['properties']
                                        image_region_anns.append(filtered_g)
                                    else:
                                        image_region_anns.append({
                                            'type': 'FeatureCollection',
                                            'features':[],
                                            'properties':g['properties']
                                        })

                        else:
                            print(f'Unrecognized annotation format found for image: {image}, {self.names[image]}')
                    return Response(
                        content = json.dumps(image_region_anns), 
                        media_type='application/json'
                    )

        else:
            return Response(
                content = 'invalid image index',
                media_type = 'application/json', 
                status_code = 400
            )

    def get_annotations_metadata(self,image:int):
        
        if image<len(self.names) and image>=0:
            return Response(
                content = json.dumps(self.annotations_metadata[image]),
                media_type='application/json'
            )
        else:
            return Response(
                content = 'invalid image index',
                media_type = 'application/json',
                status_code = 400,
            )

    def get_annotations_property_keys(self,image:int):
        """Getting the names of properties stored in an image's annotations

        :param image: Local image index
        :type image: int
        """

        if image<len(self.names) and image>=0:
            image_anns = self.annotations[image]

            property_list = []
            property_names = []
            for a in image_anns:
                features = a.get('features',[])
                a_id = a.get('properties',{}).get('_id',None)
                a_name = a.get('properties',{}).get('name',None)

                for f in features:
                    f_props = f.get('properties')
                    if not f_props is None:
                        f_main_keys = list(f_props.keys())
                        for f_m in f_main_keys:
                            if type(f_props[f_m]) in [list,dict]:
                                values_list = extract_nested_prop(f_props[f_m],4)
                            elif type(f_props[f_m]) in [str,int,float]:
                                values_list = [{f_m: f_props[f_m]}]
                            
                            for v in values_list:
                                v_key = list(v.keys())[0]
                                v_val = list(v.values())[0]

                                if v_key in property_names:
                                    v_info = property_list[property_names.index(v_key)]
                                    if type(v_val)==str:
                                        if not v_val in v_info['distinct']:
                                            v_info['distinct'].append(v_val)
                                            v_info['distinctcount'] += 1
                                        
                                    elif type(v_val) in [int,float]:
                                        if v_val>v_info['max']:
                                            v_info['max'] = v_val
                                        elif v_val<v_info['min']:
                                            v_info['min'] = v_val
                                        
                                    v_info['count'] += 1

                                    property_list[property_names.index(v_key)] = v_info
                                else:
                                    property_names.append(v_key)
                                    
                                    v_info = {
                                        'key': v_key.lower().replace(' --> ','.'),
                                        'title': v_key,
                                        'count': 1
                                    }

                                    if type(v_val)==str:
                                        v_info['type'] = 'string'
                                        v_info['distinct'] = [v_val]
                                        v_info['distinctcount'] = 1
                                    else:
                                        v_info['type'] = 'number'
                                        v_info['max'] = v_val
                                        v_info['min'] = v_val

                                    property_list.append(v_info)
                                        
        
            return Response(
                content = json.dumps(property_list),
                media_type='application/json',
                status_code=200
            )

        else:                           
            return Response(
                content = 'invalid image index',
                media_type = 'application/json',
                status_code = 400,
            )       

    def get_annotations_property_data(self,image:int,include_keys:Union[str,list,None],include_anns:Union[str,list,None]):
        """Getting data from annotations of specified image, attempting to mirror output of https://github.com/girder/large_image/blob/master/girder_annotation/girder_large_image_annotation/utils/__init__.py

        :param image: Index of local image to grab data from
        :type image: int
        :param include_keys: List of property names to grab from annotations
        :type include_keys: list
        :param include_anns: Which annotations to include (name/id or __all__ or list)
        :type include_anns: Union[str,list,None]
        :return: 
        :rtype: _type_
        """
                
        if image<len(self.names) and image>=0:
            image_anns = self.annotations[image]

            if include_anns is None:
                include_anns = '__all__'

            bbox_list = ['bbox.x0','bbox.y0','bbox.x1','bbox.y1']

            data_list = []
            for a in image_anns:
                features = a.get('features',[])
                a_id = a.get('properties',{}).get('_id',None)
                a_name = a.get('properties',{}).get('name',None)

                # Accepting either annotation layer name or id
                if not include_anns=='__all__':
                    if type(include_anns)==str:
                        if not include_anns==a_id and not include_anns==a_name:
                            continue
                    elif type(include_anns)==list:
                        if not a_id in include_anns and not a_name in include_anns:
                            continue
                            
                for f in features:
                    f_props = f.get('properties')
                    f_bbox = list(shape(f['geometry']).bounds)
                    f_props_cols = []
                    if not f_props is None:
                        for k in include_keys:
                            # Need to specify non-feature keys
                            if k in ['annotation.id','annotation.name','item.id','item.name']:
                                if k=='annotation.id':
                                    f_props_cols.append(a_id)
                                elif k=='annotation.name':
                                    f_props_cols.append(a_name)
                                elif k=='item.id':
                                    f_props_cols.append(str(image))
                                elif k=='item.name':
                                    f_props_cols.append(self.names[image])

                            elif k in bbox_list:
                                # Adding bounding box coordinates
                                f_props_cols.append(f_bbox[bbox_list.index(k)])

                            else:
                                # Getting keys and nested keys
                                if '-->' in k:
                                    f_sub_keys = k.split('-->')
                                    f_sub_props = deepcopy(f_props)
                                    for sk in f_sub_keys:
                                        if not f_sub_props is None:
                                            f_sub_props = f_sub_props.get(sk)
                                else:
                                    f_sub_props = f_props.get(k)

                                # Converting to float if able
                                try:
                                    f_sub_props = float(f_sub_props)
                                    f_props_cols.append(f_sub_props)
                                except ValueError:
                                    f_props_cols.append(f_sub_props)                                       
                    else:
                        f_props_cols = [None]*len(include_keys)

                    data_list.append(f_props_cols)

            return Response(
                content = json.dumps({'data': data_list}),
                media_type='application/json',
                status_code=200
            )

        else:                           
            return Response(
                content = 'invalid image index',
                media_type = 'application/json',
                status_code = 400,
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
            allow_origins=self.cors_options['origins'],
            allow_methods=self.cors_options['allow_methods'],
            allow_credentials = True,
            allow_headers=self.cors_options['allow_headers'],
            expose_headers=self.cors_options['expose_headers'],
            max_age=self.cors_options['max_age']
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


