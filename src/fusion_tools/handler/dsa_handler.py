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
from fusion_tools.components import Tool
from fusion_tools.utils.shapes import load_annotations, detect_histomics

from fusion_tools.handler.login import DSALoginComponent
from fusion_tools.handler.dataset_uploader import DSAUploader
from fusion_tools.handler.dataset_builder import DatasetBuilder
from fusion_tools.handler.plugin import DSAPluginProgress, DSAPluginRunner
from fusion_tools.handler import Handler

#TODO: Consider making a function decorator for authentication just to clean up all the 
# self.gc.setToken and +f'?token={user_token}' lines


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

        if user_token is None or user_token=='':
            request_string = self.gc.urlBase+f'/item/{item_id}/tiles/region?left={coords_list[0]}&top={coords_list[1]}&right={coords_list[2]}&bottom={coords_list[3]}'
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

    def get_image_thumbnail(self, item_id:str, user_token:Union[str,None]=None)->np.ndarray:


        if user_token is None or user_token=='':
            request_string = self.gc.urlBase+f'/item/{item_id}/tiles/thumbnail'
        else:
            request_string = self.gc.urlBase+f'/item/{item_id}/tiles/thumbnail?token={user_token}'

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

    def get_annotation_names(self, item:str, user_token: Union[str,None]=None):

        if not user_token is None:
            self.gc.setToken(user_token)

        annotation_info = self.gc.get('/annotation',parameters={'itemId': item})

        annotation_names = [i['annotation']['name'] for i in annotation_info]

        return annotation_names

    def query_annotation_count(self, item:Union[str,list], user_token:Union[str,None]=None) -> pd.DataFrame:
        """Get count of structures in an item

        :param item: Girder item Id for image of interest
        :type item: Union[str,list]
        :return: Dataframe containing name and count of annotated structures
        :rtype: pd.DataFrame
        """

        if type(item)==str:
            item = [item]

        if not user_token is None:
            self.gc.setToken(user_token)

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
    
    def get_path_info(self, path: str, user_token:Union[str,None]=None) -> dict:
        """Get information for a given resource path

        :param item_path: Path in DSA instance for a given resource
        :type item_path: str
        :return: Dictionary containing id and metadata, etc.
        :rtype: dict
        """
        # First searching for the "resource"
        assert any([i in path for i in ['collection','user']])

        if not user_token is None:
            self.gc.setToken(user_token)

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
    
    def get_file_info(self, fileId:str, user_token: Union[str,None]=None)->dict:
        """Getting information for a given file (specifically what item it's attached to).

        :param fileId: Girder Id of a file
        :type fileId: str
        :param user_token: User session token, defaults to None
        :type user_token: Union[str,None], optional
        :return: Information on file
        :rtype: dict
        """

        if not user_token is None:
            self.gc.setToken(user_token)

        file_info = self.gc.get(f'file/{fileId}')

        return file_info
    
    def get_item_info(self, itemId:str, user_token: Union[str,None]=None):

        if not user_token is None:
            self.gc.setToken(user_token)
        
        item_info = self.gc.get(f'item/{itemId}')

        return item_info

    def get_folder_info(self, folder_id:str, user_token:Union[str,None]=None)->dict:
        """Getting folder info from ID

        :param folder_id: ID assigned to that folder
        :type folder_id: str
        :return: Dictionary with details like name, parentType, meta, updated, size, etc.
        :rtype: dict
        """

        if not user_token is None:
            self.gc.setToken(user_token)

        try:
            folder_info = self.gc.get(f'/folder/{folder_id}') | self.gc.get(f'/folder/{folder_id}/details')

            return folder_info
        except girder_client.HttpError:
            #TODO: Change up the return here for an error
            return 'Folder not found!'
        
    def get_folder_rootpath(self, folder_id:str, user_token:Union[str,None]=None)->list:
        """Get the rootpath for a given folder Id.

        :param folder_id: Girder Id for a folder
        :type folder_id: str
        :return: List of objects in that folder's path that are parents
        :rtype: list
        """

        if not user_token is None:
            self.gc.setToken(user_token)

        try:
            folder_rootpath = self.gc.get(f'/folder/{folder_id}/rootpath')

            return folder_rootpath
        except girder_client.HttpError:
            #TODO: Change up the return here for error
            return 'Folder not found!'
    
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
        
    def get_folder_folders(self, folder_id:str, folder_type:str = 'folder', user_token:Union[str,None]=None):
        """Get the folders within a folder

        :param folder_id: Girder Id for a folder
        :type folder_id: str
        :param folder_type: Either "folder" or "collection", defaults to 'folder'
        :type folder_type: str, optional
        """

        if not user_token is None:
            self.gc.setToken(user_token)

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

        if not user_token is None:
            self.gc.setToken(user_token)

        if '/' in folder_path:
            folder_info = self.get_path_info(folder_path,user_token)
        else:
            if folder_type=='folder':
                folder_info = self.gc.get(f'/folder/{folder_path}')
            else:
                folder_info = self.gc.get(f'/collection/{folder_path}')

        folder_items = self.gc.get(f'/resource/{folder_info["_id"]}/items',
                                                  parameters = {
                                                      'type': folder_type,
                                                      'limit': 0 
                                                  })

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

        if not user_token is None:
            self.gc.setToken(user_token)

        if annotation_id is None:
            # Grab all annotations for that item
            if format in [None, 'geojson']:
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

    def get_collections(self, user_token:Union[str,None]=None)->list:
        """Get list of all available collections in DSA instance.

        :return: List of available collections info.
        :rtype: list
        """
        if not user_token is None:
            self.gc.setToken(user_token)

        collections = self.gc.get('/collection')

        return collections

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

    def post_annotations(self, item:str, annotations: Union[str,list,dict,None] = None, user_token:Union[str,None]=None):
        """Add annotations to an item in Girder.

        :param item: ID for the item that is receiving the annotations
        :type item: str
        :param annotations: Formatted dictionary, path, or list of dictionaries/paths with the annotations., defaults to None
        :type annotations: Union[str,list,dict,None], optional
        """
        if not user_token is None:
            self.gc.setToken(user_token)

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
        
    def add_metadata(self, item:str, metadata:dict, user_token:Union[str,None]=None):
        """Add metadata key/value to a specific item

        :param item: ID for item that is receiving the metadata
        :type item: str
        :param metadata: Metadata key/value combination (can contain multiple keys and values (JSON formatted))
        :type metadata: dict
        """

        if not user_token is None:
            self.gc.setToken(user_token)

        try:
            # Adding item-level metadata
            self.gc.put(f'/item/{item}/metadata',parameters={'metadata':json.dumps(metadata)})

            return True
        except Exception as e:
            return False

    def list_plugins(self, user_token:str):
        """List all of the plugins/CLIs available for the current DSA instance
        """
        
        return self.gc.get(f'/slicer_cli_web/cli?token={user_token}')

    def add_plugin(self, image_name:Union[str,list], user_token:Union[str,None]=None):
        """Add a plugin/CLI to the current DSA instance by name of the Docker image (requires admin login)

        :param image_name: Name of Docker image on Docker Hub
        :type image_name: str
        """
        if type(image_name)==str:
            image_name = [image_name]

        if not user_token is None:
            self.gc.setToken(user_token)
        
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
            
            put_response = self.gc.put('/slicer_cli_web/docker_image',parameters={'name':i})
            print(f'--------Image: {i} successfully added--------------')
            put_responses.append(put_response)
        return put_responses
        
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

    def get_user_jobs(self, user_id:str, user_token: str, offset: int = 0, limit: int = 0):


        self.gc.setToken(user_token)
        request_response = self.gc.get(
            f'/job',
            parameters={
                'userId': user_id,
                'limit': limit,
                'offset': offset
            }
        )

        return request_response
    
    def get_specific_job(self, job_id:str, user_token:str):

        self.gc.setToken(user_token)
        request_response = self.gc.get(
            f'/job/{job_id}'
        )

        return request_response
    
    def cancel_job(self, job_id:str, user_token:str):

        self.gc.setToken(user_token)
        request_response = self.gc.put(
            f'/job/{job_id}/cancel'
        )

        return request_response

    def run_plugin(self, plugin_id:str, arguments:dict, user_token:str):
        """Run a plugin given a set of input arguments

        :param plugin_id: ID for plugin to run.
        :type plugin_id: str
        :param arguments: Dictionary containing keys/values for each input argument to a plugin
        :type arguments: dict
        """
        
        # Make sure that the arguments are formatted correctly
        request_output = requests.post(
            url = self.handler.gc.urlBase + f'slicer_cli_web/cli/{plugin_id}/run?token={user_token}',
            params = {
                'girderApiUrl': self.handler.girderApiUrl,
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











