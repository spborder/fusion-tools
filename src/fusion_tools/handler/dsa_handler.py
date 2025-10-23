"""Classes related to the DSAHandler and Tool components
"""
import girder_client

import requests
import json
import numpy as np
import pandas as pd
import uuid

from typing_extensions import Union

from skimage.draw import polygon
from PIL import Image
from io import BytesIO

from fusion_tools.tileserver import DSATileServer
from fusion_tools.utils.shapes import load_annotations, detect_histomics, histomics_to_geojson

from fusion_tools.handler.login import DSALoginComponent
from fusion_tools.handler.dataset_uploader import DSAUploader
from fusion_tools.handler.dataset_builder import DatasetBuilder
from fusion_tools.handler.plugin import DSAPluginProgress, DSAPluginRunner
from fusion_tools.handler.save_session import DSASession
from fusion_tools.components.base import Handler

def tokenator(method):
    """Token decorator function to handle setting and unsetting girder user tokens for select functions

    :param method: Function in handler 
    :type method: function
    """
    def wrapper(self,*args,**kwargs):
        
        if self.user_token is None:
            self.gc.setToken(kwargs.get('user_token',None))
            result = method(self, *args, **kwargs)
            self.gc.token = None
        else:
            self.gc.setToken(self.user_token)
            result = method(self,*args,**kwargs)

        return result
    return wrapper

class DSAHandler(Handler):
    """Handler for DSA (digital slide archive) instance
    """
    def __init__(self,
                 girderApiUrl: str,
                 username: Union[str,None] = None,
                 password: Union[str,None] = None):
        """Constructor method

        :param girderApiUrl: URL for API for desired DSA instance (ends in /api/v1)
        :type girderApiUrl: str
        :param username: Username to use for accessing private collections, defaults to None
        :type username: Union[str,None], optional
        :param password: Password to use for accessing private collections, defaults to None
        :type password: Union[str,None], optional
        """
        
        self.girderApiUrl = girderApiUrl
        self.username = username
        self.password = password

        self.gc = girder_client.GirderClient(apiUrl=self.girderApiUrl)
        if not any([i is None for i in [self.username,self.password]]):
            self.gc.authenticate(
                username = self.username,
                password=self.password
            )

            # Token used for authenticating requests
            self.user_token = self.gc.get(f'/token/session')['token']
            self.gc.setToken(self.user_token)
        
        else:
            self.user_token = None

    def authenticate_new(self, username:str, password:str):

        try:
            user_info = self.gc.authenticate(
                username = username,
                password = password
            )
            user_info['token'] = self.gc.get('token/session')['token']
            return user_info
        
        except girder_client.AuthenticationError:
            return f'Error logging in with username: {username}'

    @tokenator
    def get_image_region(self, item_id: str, coords_list: list, style: Union[dict,None] = None, user_token:Union[str,None]=None)->np.ndarray:
        """
        Grabbing image region from list of bounding box coordinates
        """
        """Extract image region from an item

        :param item_id: Girder item id for image containing region of interest
        :type item_id: str
        :param coords_list: List of coordinates (left, top, right, bottom) of region of interest
        :type coords_list: list
        :param style: Additional style arguments (for extracting multi-frame image regions with artificial colors)
        :type style: Union[dict,None], optional

        :raises NotImplementedError: If style is provided raises this error, feature still in progress
        :return: Image region in Numpy format
        :rtype: np.ndarray
        """

        image_array = np.zeros((256,256))

        if user_token is None or user_token=='' and self.user_token is None:
            request_string = self.gc.urlBase+f'/item/{item_id}/tiles/region?left={coords_list[0]}&top={coords_list[1]}&right={coords_list[2]}&bottom={coords_list[3]}'
        else:
            if user_token is None or user_token=='':
                request_string = self.gc.urlBase+f'/item/{item_id}/tiles/region?token={self.user_token}&left={coords_list[0]}&top={coords_list[1]}&right={coords_list[2]}&bottom={coords_list[3]}'
            else:
                request_string = self.gc.urlBase+f'/item/{item_id}/tiles/region?token={user_token}&left={coords_list[0]}&top={coords_list[1]}&right={coords_list[2]}&bottom={coords_list[3]}'


        if style is None:
            image_array = np.uint8(
                np.array(
                    Image.open(
                        BytesIO(
                            requests.get(
                                request_string
                            ).content
                        )
                    )
                )
            )
        
        else:
            print('Adding style parameters are in progress')
            raise NotImplementedError

        return image_array

    @tokenator
    def get_image_thumbnail(self, item_id:str, user_token:Union[str,None]=None, return_url:bool=False)->np.ndarray:


        if user_token is None or user_token=='' and self.user_token is None:
            request_string = self.gc.urlBase+f'/item/{item_id}/tiles/thumbnail'
            #request_string = self.gc.urlBase+f'/item/{item_id}/zxy/0/0/0'
        else:
            if not self.user_token is None and user_token is None:
                request_string = self.gc.urlBase+f'/item/{item_id}/tiles/thumbnail?token={self.user_token}'
                #request_string = self.gc.urlBase+f'/item/{item_id}/zxy/0/0/0?token={self.user_token}'
            else:
                request_string = self.gc.urlBase+f'/item/{item_id}/tiles/thumbnail?token={user_token}'
                #request_string = self.gc.urlBase+f'/item/{item_id}/zxy/0/0/0?token={user_token}'

        if not return_url:
            try:
                image_array = np.uint8(
                    np.array(
                        Image.open(
                            BytesIO(
                                requests.get(
                                    request_string
                                ).content
                            )
                        )
                    )
                )
            except:
                print(f'Thumbnail exception encountered for item: {item_id}')
                image_array = np.zeros((256,256,3)).astype(np.uint8)

            return image_array
        else:
            return request_string

    def make_boundary_mask(self, exterior_coords: list) -> np.ndarray:
        """Making boundary mask for a set of exterior coordinates

        :param exterior_coords: List of exterior vertex coordinates
        :type exterior_coords: list
        :return: Binary mask of external boundaries of object
        :rtype: np.ndarray
        """
        x_coords = [i[0] for i in exterior_coords]
        y_coords = [i[1] for i in exterior_coords]

        min_x = min(x_coords)
        max_x = max(x_coords)
        min_y = min(y_coords)
        max_y = max(y_coords)
        
        scaled_coords = [[int(i[0]-min_x), int(i[1]-min_y)] for i in exterior_coords]

        boundary_mask = np.zeros((int(max_y-min_y),int(max_x-min_x)))

        row,col = polygon(
            [i[1] for i in scaled_coords],
            [i[0] for i in scaled_coords],
            (int(max_y-min_y), int(max_x-min_x))
        )

        boundary_mask[row,col] = 1

        return boundary_mask

    @tokenator
    def get_annotation_names(self, item:str, user_token: Union[str,None]=None, return_info:bool=False):

        annotation_info = self.gc.get('/annotation',parameters={'itemId': item})

        if not return_info:
            annotation_names = [i['annotation']['name'] for i in annotation_info]
            return annotation_names
        else:
            return annotation_info

    @tokenator
    def query_annotation_count(self, item:Union[str,list], user_token:Union[str,None]=None) -> pd.DataFrame:
        """Get count of structures in an item

        :param item: Girder item Id for image of interest
        :type item: Union[str,list]
        :return: Dataframe containing name and count of annotated structures
        :rtype: pd.DataFrame
        """

        if type(item)==str:
            item = [item]

        ann_counts = []
        for it in item:
            item_dict = {}
            if '/' in it:
                item_info = self.get_path_info(it)
            else:
                item_info = self.gc.get(f'/item/{it}')

            item_dict['name'] = item_info['name']
            item_dict['id'] = item_info['_id']
            item_anns = self.gc.get(f'/annotation',parameters={'itemId':it})

            if len(item_anns)>0:
                for ann in item_anns:
                    ann_centroids = self.gc.get(f'/annotation/{ann["_id"]}')
                    ann_count = len(ann_centroids['annotation']['elements'])

                    item_dict[ann['annotation']['name']] = ann_count

            ann_counts.append(item_dict)

        ann_counts_df = pd.DataFrame.from_records(ann_counts).fillna(0)

        return ann_counts_df
    
    @tokenator
    def get_path_info(self, path: str, user_token:Union[str,None]=None) -> dict:
        """Get information for a given resource path

        :param item_path: Path in DSA instance for a given resource
        :type item_path: str
        :return: Dictionary containing id and metadata, etc.
        :rtype: dict
        """
        # First searching for the "resource"
        assert any([i in path for i in ['collection','user']])

        try:
            resource_find = self.gc.get('/resource/lookup',parameters={'path': path})
            if resource_find['_modelType']=='collection':
                resource_find = resource_find | self.gc.get(f'/collection/{resource_find["_id"]}/details')
            elif resource_find['_modelType']=='folder':
                resource_find = resource_find | self.gc.get(f'/folder/{resource_find["_id"]}/details')
            elif resource_find['_modelType']=='user':
                resource_find = resource_find | self.gc.get(f'/user/{resource_find["_id"]}/details')

            return resource_find
        except girder_client.HttpError:
            #TODO: Make this error handling a little better (return some error type)
            print(f'path: {path} not found')
            return 'Resource not found'
    
    @tokenator
    def get_file_info(self, fileId:str, user_token: Union[str,None]=None)->dict:
        """Getting information for a given file (specifically what item it's attached to).

        :param fileId: Girder Id of a file
        :type fileId: str
        :param user_token: User session token, defaults to None
        :type user_token: Union[str,None], optional
        :return: Information on file
        :rtype: dict
        """

        file_info = self.gc.get(f'file/{fileId}')

        return file_info
    
    @tokenator
    def get_item_info(self, itemId:str, user_token: Union[str,None]=None):
        
        item_info = self.gc.get(f'item/{itemId}')

        return item_info

    @tokenator
    def get_folder_info(self, folder_id:str, user_token:Union[str,None]=None)->dict:
        """Getting folder info from ID

        :param folder_id: ID assigned to that folder
        :type folder_id: str
        :return: Dictionary with details like name, parentType, meta, updated, size, etc.
        :rtype: dict
        """

        try:
            folder_info = self.gc.get(f'/folder/{folder_id}') | self.gc.get(f'/folder/{folder_id}/details')

            return folder_info
        except girder_client.HttpError:
            #TODO: Change up the return here for an error
            return 'Folder not found!'
    
    @tokenator
    def get_folder_rootpath(self, folder_id:str, user_token:Union[str,None]=None)->list:
        """Get the rootpath for a given folder Id.

        :param folder_id: Girder Id for a folder
        :type folder_id: str
        :return: List of objects in that folder's path that are parents
        :rtype: list
        """

        try:
            folder_rootpath = self.gc.get(f'/folder/{folder_id}/rootpath')

            return folder_rootpath
        except girder_client.HttpError:
            #TODO: Change up the return here for error
            return 'Folder not found!'
    
    @tokenator
    def get_collection_slide_count(self, collection_name, ignore_histoqc = True, user_token:Union[str,None]=None) -> int:
        """Get a count of all of the slides in a given collection across all child folders

        :param collection_name: Name of collection ('/collection/{}')
        :type collection_name: str
        :param ignore_histoqc: Whether to ignore folders containing histoqc outputs (not slides)., defaults to True
        :type ignore_histoqc: bool, optional
        :return: Total count of slides (large-image objects) in a given collection
        :rtype: int
        """
        
        collection_info = self.get_path_info(f'/collection/{collection_name}',user_token)
        collection_slides = self.get_folder_slides(collection_info['_id'], folder_type = 'collection', ignore_histoqc = True, user_token = user_token)

        return len(collection_slides)
    
    @tokenator
    def get_folder_folders(self, folder_id:str, folder_type:str = 'folder', user_token:Union[str,None]=None):
        """Get the folders within a folder

        :param folder_id: Girder Id for a folder
        :type folder_id: str
        :param folder_type: Either "folder" or "collection", defaults to 'folder'
        :type folder_type: str, optional
        """

        try:
            folder_folders = self.gc.get(
                f'/folder',
                parameters = {
                    'parentType': folder_type,
                    'parentId': folder_id,
                    'limit': 0
                })

            return folder_folders
        except girder_client.HttpError:
            #TODO: Fix error return
            return 'Folder not found!'
    
    @tokenator
    def get_folder_slides(self, folder_path:str, folder_type:str = 'folder', ignore_histoqc:bool = True, user_token:Union[str,None]=None) -> list:
        """Get all slides in a folder

        :param folder_path: Path in DSA for a folder
        :type folder_path: str
        :param folder_type: Whether it's a folder or a collection
        :type folder_type: str, optional
        :param ignore_histoqc: Whether or not to ignore images in the histoqc_outputs folder, defaults to True
        :type ignore_histoqc: bool, optional
        :return: List of image items contained within a folder
        :rtype: list
        """

        assert folder_type in ['folder','collection']

        if '/' in folder_path:
            folder_info = self.get_path_info(folder_path,user_token)
        else:
            if folder_type=='folder':
                folder_info = self.gc.get(f'/folder/{folder_path}')
            else:
                folder_info = self.gc.get(f'/collection/{folder_path}')

        #TODO: This specific query is restricted to admins for some really inconvenient reason
        #folder_items = self.gc.get(f'/resource/{folder_info["_id"]}/items',
        #                                          parameters = {
        #                                              'type': folder_type,
        #                                              'limit': 0 
        #                                          })

        if folder_type=='folder':
            folder_items = self.gc.get(f'/item',
                                    parameters = {
                                        'folderId': folder_info["_id"],
                                        'limit': 0
                                    })
        else:
            folder_items = []

        if len(folder_items)>0:
            if ignore_histoqc:
                folders_in_folder = list(set([i['folderId'] for i in folder_items]))
                folder_names = [
                    self.gc.get(f'/folder/{i}')['name']
                    for i in folders_in_folder
                ]

                if 'histoqc_outputs' not in folder_names:
                    ignore_folders = []
                else:
                    ignore_folders = [folders_in_folder[i] for i in range(len(folder_names)) if folder_names[i]=='histoqc_outputs']

            else:
                ignore_folders = []

            folder_image_items = [i for i in folder_items if 'largeImage' in i and not i['folderId'] in ignore_folders]

        else:
            folder_image_items = []

        return folder_image_items

    @tokenator
    def get_annotations(self, item:str, annotation_id: Union[str,list,None]=None, format: Union[str,None]='geojson',user_token:Union[str,None]=None):
        """Get annotations for an item in DSA

        :param item: Girder item Id for desired image
        :type item: str
        :param annotation_id: If only a subset of annotations is desired, pass their ids here, defaults to None
        :type annotation_id: Union[str,list,None], optional
        :param format: Desired format of annotations, defaults to 'geojson'
        :type format: Union[str,None], optional
        :raises NotImplementedError: Invalid format passed
        :raises NotImplementedError: Invalid format passed
        :return: Annotations for the queried item Id
        :rtype: list
        """
        assert format in [None, 'geojson','histomics']

        if annotation_id is None:
            # Grab all annotations for that item
            if format in [None, 'geojson']:

                try:
                    annotation_ids = self.gc.get(
                        f'/annotation',
                        parameters = {
                            'itemId': item
                        }
                    )
                    annotations = []
                    for a in annotation_ids:
                        if '_id' in a['annotation']:
                            a_id = a['annotation']['_id']
                            ann_geojson = self.gc.get(
                                f'/annotation/{a["annotation"]["_id"]}/geojson'
                            )
                        elif '_id' in a:
                            a_id = a['_id']
                            ann_geojson = self.gc.get(
                                f'/annotation/{a["_id"]}/geojson'
                            )

                        for f in ann_geojson['features']:
                            if 'properties' in f:
                                if 'user' in f['properties']:
                                    f['properties'] = f['properties']['user']

                                f['properties']['name'] = a['annotation']['name']
                            else:
                                f['properties'] = {'name': a['annotation']['name']}


                        if 'properties' not in ann_geojson:
                            ann_geojson['properties'] = {
                                'name': a['annotation']['name']
                            }

                        ann_geojson['properties']['_id'] = a_id
                        for f_idx, f in enumerate(ann_geojson['features']):
                            f['properties'] = f['properties'] | {'_index': f_idx, '_id': uuid.uuid4().hex[:24],'name': ann_geojson['properties']['name']}

                        annotations.append(ann_geojson)
                except:
                    # Bug if polyline annotations are uploaded without "closed": True set then it yields a ChunkedEncodingError since it fails validation converting to GeoJSON
                    annotations = self.gc.get(
                        f'/annotation/item/{item}'
                    )
                    annotations = histomics_to_geojson(annotations)

            elif format=='histomics':

                annotations = self.gc.get(
                    f'/annotation/item/{item}'
                )
            
            else:
                print(f'format: {format} not implemented!')
                raise NotImplementedError
        
        else:
            if type(annotation_id)==str:
                annotation_id = [annotation_id]
            
            annotations = []
            for a in annotation_id:
                if format in [None,'geojson']:
                    if '_id' in a['annotation']:
                        a_id = a['annotation']['_id']
                        ann_geojson = self.gc.get(
                            f'/annotation/{a["annotation"]["_id"]}/geojson'
                        )
                    elif '_id' in a:
                        a_id = a['_id']
                        ann_geojson = self.gc.get(
                            f'/annotation/{a["_id"]}/geojson'
                        )

                    for f in ann_geojson['features']:
                        if 'properties' in f:
                            if 'user' in f['properties']:
                                f['properties'] = f['properties']['user']
                                del f['properties']['user']
                            f['properties']['name'] = a['annotation']['name']
                        else:
                            f['properties'] = {'name': a['annotation']['name']}

                    if 'properties' not in ann_geojson:
                        ann_geojson['properties'] = {
                            'name': a['annotation']['name']
                        }
                        
                    ann_geojson['properties']['_id'] = a_id

                    for f_idx,f in ann_geojson['features']:
                        f['properties'] = f['properties'] | {'_index': f_idx, '_id': uuid.uuid4().hex[:24],'name': ann_geojson['properties']['name']}

                    annotations.append(ann_geojson)
                elif format=='histomics':
                    if '_id' in a['annotation']:
                        ann_json = self.gc.get(
                            f'/annotation/{a["annotation"]["_id"]}'
                        )
                    elif '_id' in a:
                        ann_json = self.gc.get(
                            f'/annotation/{a["_id"]}'
                        )
                    annotations.append(ann_json)
                else:
                    print(f'format: {format} is not implemented!')
                    raise NotImplementedError

        return annotations

    def get_tile_server(self, item:str)->DSATileServer:
        """Create a tileserver for a given item

        :param item: Girder Item Id for the slide you want to create a tileserver for
        :type item: str
        :return: DSATileServer instance 
        :rtype: DSATileServer
        """

        return DSATileServer(api_url = self.girderApiUrl, item_id = item)

    @tokenator
    def get_collections(self, user_token:Union[str,None]=None)->list:
        """Get list of all available collections in DSA instance.

        :return: List of available collections info.
        :rtype: list
        """
        #if not user_token is None:
        #    self.gc.setToken(user_token)

        collections = self.gc.get('/collection')

        return collections
    
    @tokenator
    def create_collection(self, collection_name:str, collection_description:Union[str,None]=None,public:bool=True,user_token:Union[str,None]=None):

        collection_post = self.gc.post(
            'collection',
            parameters={
                'name': collection_name,
                'description': collection_description if not collection_description is None else '',
                'public': public
            }
        )

        return collection_post

    @tokenator
    def create_folder(self, parentId:str, parentType:str, folder_name:str, folder_description:Union[str,None]=None,public:bool=True,user_token:Union[str,None]=None):

        folder_post_response = self.gc.post(
            'folder',
            parameters={
                'parentType':parentType,
                'parentId':parentId,
                'name': folder_name,
                'description': folder_description if not folder_description is None else '',
                'reuseExisting': True,
                'public': public
            }
        )

        return folder_post_response

    @tokenator
    def upload_session(self, session_data:dict, user_token:Union[str,None]=None):
        """Upload session data to dedicated fusion-tools sessions collection

        :param session_data: Visualization session data to be saved on DSA instance
        :type session_data: dict
        :param user_token: user token, defaults to None
        :type user_token: Union[str,None], optional
        """

        collections = self.get_collections(user_token)
        collection_names = [i['name'] for i in collections]

        if not 'fusion-tools Sessions' in collection_names:
            # Creating the collection/folder if it's not there already
            collection_post_result = self.create_collection(
                collection_name = 'fusion-tools Sessions',
                collection_description='Session information related to fusion-tools uploaded by users.',
                user_token = user_token
            )

            folder_post_response = self.create_folder(
                parentId = collection_post_result['_id'],
                parentType='collection',
                folder_name = 'fusion-tools Sessions',
                folder_description = 'Saved Sessions',
                user_token = user_token
            )

            session_collection_id = collection_post_result['_id']
            folder_id = folder_post_response['_id']

        else:
            # Grabbing the folder id that is already present
            session_collection_id = collections[collection_names.index('fusion-tools Sessions')]['_id']

            session_folders = self.get_folder_folders(
                folder_id = session_collection_id,
                folder_type = 'collection',
                user_token=user_token
            )
            folder_names = [i['name'] for i in session_folders]
            folder_id = session_folders[folder_names.index('fusion-tools Sessions')]['_id']

        session_data_data = json.dumps(session_data)
        session_data_size = len(session_data_data.encode('utf-8'))

        # Making new item
        make_file_response = self.gc.post(
            'file',
            parameters={
                'parentType':'folder',
                'parentId': folder_id,
                'name': 'fusion-tools session.json',
                'size': session_data_size
            }
        )

        post_response = self.gc.post(f'/file/chunk',
            parameters={
                'size':session_data_size,
                'offset':0,
                'uploadId':make_file_response['_id']
                },
            data = session_data_data
        )

        return post_response

    @tokenator
    def get_session_data(self, session_id:str, user_token:Union[str,None]=None):

        # downloading session file specified by id
        try:
            session_item_file = self.gc.get(f'item/{session_id}/files')[0]
        except girder_client.HttpError:
            session_item_file = {'_id':session_id}
            
        file_contents = self.gc.get(
            f'file/{session_item_file["_id"]}/download'
        )

        return file_contents

    def create_save_session(self):
        return DSASession(handler = self)

    def create_survey(self, survey_args:dict):
        """Create a survey component which will route collected data to a specific file in the connected DSA instance.

        :param survey_args: Setup arguments for survey questions (keys = questions list, usernames list, storage folder)
        :type survey_args: dict
        """

        #TODO: Process:
        # 1) Parse survey args
        # 2) Return SurveyComponent
        pass
    
    def create_uploader(self, upload_types:list):
        """Create uploader component layout to a specific folder. "uploader_args" contains optional additional arguments.

        :param upload_types: List of UploadTypes objects including current varieties of formatted, linked upload procedures
        :type upload_types: list
        """

        dsa_uploader = DSAUploader(
            handler= self,
            dsa_upload_types=upload_types
        )

        return dsa_uploader

    def create_dataset_builder(self,include:Union[list,None]=None):
        """Table view allowing parsing of dataset/slide-level metadata and adding remote/local slides to current session.

        :param include: List of collections to only include (None = include everything accessible to this user), defaults to None
        :type include: Union[list,None], optional
        :return: DatasetBuilder instance
        :rtype: DatasetBuilder
        """
        
        dataset_builder = DatasetBuilder(
            handler = self,
            include_only=include
        )

        return dataset_builder

    def create_metadata_table(self,metadata_args:dict):
        """Create table of metadata keys/values for a folder or collection

        :param metadata_args: Additional arguments specifying location of folder and any keys to ignore.
        :type metadata_args: dict
        """
        pass
    
    @tokenator
    def post_annotations(self, item:str, annotations: Union[str,list,dict,None] = None, user_token:Union[str,None]=None):
        """Add annotations to an item in Girder.

        :param item: ID for the item that is receiving the annotations
        :type item: str
        :param annotations: Formatted dictionary, path, or list of dictionaries/paths with the annotations., defaults to None
        :type annotations: Union[str,list,dict,None], optional
        """

        if type(annotations)==str:
            annotations = load_annotations(annotations)
        
        if type(annotations)==dict:
            annotations = [annotations]
        
        if all([detect_histomics(a) for a in annotations]):
            self.gc.post(
                f'/annotation/item/{item}?token={self.user_token}',
                data = json.dumps(annotations),
                headers = {
                    'X-HTTP-Method': 'POST',
                    'Content-Type': 'application/json'
                }
            )
        else:
            # Default format is GeoJSON (#TODO: Have to verify that lists of GeoJSONs are acceptable)
            self.gc.post(
                f'/annotation/item/{item}?token={self.user_token}',
                data = json.dumps(annotations),
                headers = {
                    'X-HTTP-Method': 'POST',
                    'Content-Type': 'application/json'
                }
            )
        return True
    
    @tokenator
    def add_metadata(self, item:str, metadata:dict, user_token:Union[str,None]=None):
        """Add metadata key/value to a specific item

        :param item: ID for item that is receiving the metadata
        :type item: str
        :param metadata: Metadata key/value combination (can contain multiple keys and values (JSON formatted))
        :type metadata: dict
        """

        try:
            # Adding item-level metadata
            self.gc.put(f'/item/{item}/metadata',parameters={'metadata':json.dumps(metadata)})

            return True
        except Exception as e:
            return False

    @tokenator
    def list_plugins(self, user_token:str):
        """List all of the plugins/CLIs available for the current DSA instance
        """
        return self.gc.get(f'/slicer_cli_web/cli')

    @tokenator
    def add_plugin(self, image_name:Union[str,list], user_token:Union[str,None]=None):
        """Add a plugin/CLI to the current DSA instance by name of the Docker image (requires admin login)

        :param image_name: Name of Docker image on Docker Hub
        :type image_name: str
        """
        if type(image_name)==str:
            image_name = [image_name]
        
        current_cli = self.list_plugins(user_token)
        cli_names = [i['image'] for i in current_cli]
        put_responses = []
        for i in image_name:
            if i in cli_names:
                print(f'------Deleting old version of {i}-------')
                self.gc.delete(f'/slicer_cli_web/cli/{current_cli[cli_names.index(i)]["_id"]}')
                self.gc.delete(
                    f'/slicer_cli_web/docker_image',
                    parameters = {
                        'name': i,
                        'delete_from_local_repo': True
                    }
                )
            
            put_response = self.gc.put('/slicer_cli_web/docker_image',parameters={'name':i,'pull': True})
            print(f'--------Image: {i} successfully added--------------')
            put_responses.append(put_response)
        return put_responses
    
    @tokenator
    def create_user_folder(self, parent_path, folder_name, user_token, description = ''):
        """
        Creating a folder in user's public folder
        """
        parent_folder_id = self.gc.get('/resource/lookup',parameters={'path':parent_path})['_id']

        # Creating folder
        new_folder = requests.post(
            self.gc.urlBase + f'/folder?token={user_token}&parentType=folder&parentId={parent_folder_id}&name={folder_name}&description={description}'
        )

        return new_folder
    
    @tokenator
    def create_new_user(self,username,password,email,firstName,lastName):
        """Create a new user on this DSA instance

        :param username: Username (publically visible)
        :type username: str
        :param password: Password (not publically visible)
        :type password: str
        :param email: Email (must not overlap with other users)
        :type email: str
        :param firstName: First Name to use for user
        :type firstName: str
        :param lastName: Last Name to use for user
        :type lastName: str
        """

        try:
            self.gc.post(
                '/user',
                parameters = {
                    'login': username.lower(),
                    'password': password,
                    'email': email,
                    'firstName': firstName,
                    'lastName': lastName
                }
            )
            user_info = self.gc.authenticate(username.lower(),password)
            user_info['token'] = self.gc.get('token/session')['token']

            return user_info

        except:
            print('---------Error creating new account!------------')
            print('Make sure you are using a unique email address!')

            return False

    @tokenator
    def get_user_jobs(self, user_id:str, user_token: str, offset: int = 0, limit: int = 0):

        request_response = self.gc.get(
            f'/job',
            parameters={
                'userId': user_id,
                'limit': limit,
                'offset': offset
            }
        )

        return request_response
    
    @tokenator
    def get_specific_job(self, job_id:str, user_token:str):

        request_response = self.gc.get(
            f'/job/{job_id}'
        )

        return request_response
    
    @tokenator
    def cancel_job(self, job_id:str, user_token:str):

        request_response = self.gc.put(
            f'/job/{job_id}/cancel'
        )

        return request_response

    @tokenator
    def run_plugin(self, plugin_id:str, arguments:dict, user_token:Union[str,None]=None):
        """Run a plugin given a set of input arguments

        :param plugin_id: ID for plugin to run.
        :type plugin_id: str
        :param arguments: Dictionary containing keys/values for each input argument to a plugin
        :type arguments: dict
        """
        
        # Make sure that the arguments are formatted correctly
        request_output = requests.post(
            url = self.gc.urlBase + f'slicer_cli_web/cli/{plugin_id}/run?token={user_token}',
            params = {
                'girderApiUrl': self.girderApiUrl,
                'girderToken': user_token
            } | arguments
        )

        return request_output

    def create_plugin_progress(self):
        """Creates component that monitors current and past job logs.
        """

        plugin_progress = DSAPluginProgress(
            handler = self
        )

        return plugin_progress        

    def create_login_component(self):
        """Creates login button for multiple DSA users to use the same fusion-tools instance
        """
        
        login_component = DSALoginComponent(
            handler = self,
            default_user = {
                'username': self.username,
                'token': self.user_token
            }
        )

        return login_component











