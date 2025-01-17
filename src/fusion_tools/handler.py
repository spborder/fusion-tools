"""
Handler for requests made to a running DSA instance.

"""

import os
import sys

import girder_client

import requests
import json
import numpy as np
import pandas as pd
import uuid
import lxml.etree as ET

from typing_extensions import Union

from skimage.draw import polygon
from PIL import Image
from io import BytesIO

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
from dash.dash_table.Format import Format, Scheme
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import dash_treeview_antd as dta
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
from dash_extensions.javascript import Namespace, arrow_function

from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import Tool
from fusion_tools.utils.shapes import load_annotations, detect_histomics
from fusion_tools.visualization.vis_utils import get_pattern_matching_value

from upload_component import UploadComponent


class Handler:
    pass

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
    
    def get_path_info(self, path: str) -> dict:
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
    
    def get_folder_info(self, folder_id:str)->dict:
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
        
    def get_folder_rootpath(self, folder_id:str)->list:
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
    
    def get_collection_slide_count(self, collection_name, ignore_histoqc = True) -> int:
        """Get a count of all of the slides in a given collection across all child folders

        :param collection_name: Name of collection ('/collection/{}')
        :type collection_name: str
        :param ignore_histoqc: Whether to ignore folders containing histoqc outputs (not slides)., defaults to True
        :type ignore_histoqc: bool, optional
        :return: Total count of slides (large-image objects) in a given collection
        :rtype: int
        """
        
        collection_info = self.get_path_info(f'/collection/{collection_name}')
        collection_slides = self.get_folder_slides(collection_info['_id'], folder_type = 'collection', ignore_histoqc = True)

        return len(collection_slides)
        
    def get_folder_folders(self, folder_id:str, folder_type:str = 'folder'):
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
        
    def get_folder_slides(self, folder_path:str, folder_type:str = 'folder', ignore_histoqc:bool = True) -> list:
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
            folder_info = self.get_path_info(folder_path)
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

    def get_annotations(self, item:str, annotation_id: Union[str,list,None]=None, format: Union[str,None]='geojson'):
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

    def get_collections(self)->list:
        """Get list of all available collections in DSA instance.

        :return: List of available collections info.
        :rtype: list
        """

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

    def post_annotations(self, item:str, annotations: Union[str,list,dict,None] = None):
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
                f'/annotation/{item}/item?token={self.user_token}',
                data = json.dumps(annotations),
                headers = {
                    'X-HTTP-Method': 'POST',
                    'Content-Type': 'application/json'
                }
            )
        else:
            # Default format is GeoJSON (#TODO: Have to verify that lists of GeoJSONs are acceptable)
            self.gc.post(
                f'/annotation/{item}/item?token={self.user_token}',
                data = json.dumps(annotations),
                headers = {
                    'X-HTTP-Method': 'POST',
                    'Content-Type': 'application/json'
                }
            )
        return True
        
    def add_metadata(self, item:str, metadata:dict):
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
        except:
            return False

    def list_plugins(self, user_token:str):
        """List all of the plugins/CLIs available for the current DSA instance
        """
        
        return self.gc.get(f'/slicer_cli_web/cli?token={user_token}')

    def add_plugin(self, image_name:Union[str,list]):
        """Add a plugin/CLI to the current DSA instance by name of the Docker image (requires admin login)

        :param image_name: Name of Docker image on Docker Hub
        :type image_name: str
        """
        if type(image_name)==str:
            image_name = [image_name]
        
        current_cli = self.list_plugins()
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

    def create_plugin_inputs(self, plugin_id:str):
        """Creates formatted input component for the specified plugin/CLI ID.

        :param plugin_id: ID for plugin to create input component for.
        :type plugin_id: str
        """

        #TODO: Process:
        # 1) Get XML for plugin
        # 2) Read <parameters> and <parameters advanced=True> tags separate out
        # 3) Create inputs for basic types of inputs (string, integer, float, and string-enumeration)
        # 4) Create inputs for more difficult types of inputs (region, image, file, folder)
        # 5) Create a "Run" button (if "test" option is available create a "Test" button as well)
        # 6) Check progress in PluginProgress component
        # 7) Create some kinda popup or something indicating that the plugin is currently running and to check back later for results
        pass

    def run_plugin(self, plugin_id:str, arguments:dict):
        """Run a plugin given a set of input arguments

        :param plugin_id: ID for plugin to run.
        :type plugin_id: str
        :param arguments: Dictionary containing keys/values for each input argument to a plugin
        :type arguments: dict
        """
        #TODO: Process:
        # 1) Parse arguments
        # 2) Submit plugin run request
        # 3) Return job info 
        pass

    def create_plugin_progress(self):
        """Creates component that monitors current and past job logs.
        """
        pass

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


class DSATool(Tool):
    """A sub-class of Tool specific to DSA components. 
    The only difference is that these components always update relative to the session data.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self):

        super().__init__()
        self.session_update = True




class DSALoginComponent(DSATool):
    """Handler for DSALoginComponent, enabling login to the running DSA instance

    :param DSATool: Sub-class of Tool specific to DSA components. Updates with session data by default.
    :type DSATool: None

    """
    def __init__(self,
                 handler: DSAHandler,
                 default_user: Union[dict,None] = None
                ):
        self.handler = handler
        self.default_user = default_user

        self.session_update = True

    def load(self,component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'DSA Login Component'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()
    
    def update_layout(self, session_data:dict, use_prefix:bool):
        
                
        layout = html.Div([
            html.H4(
                id = {'type': 'dsa-login-current-user','index': 0},
                children = [
                    f'Welcome, {session_data["current_user"]["login"]}!' if "current_user" in session_data else 'Welcome, Guest!'
                ]
            ),
            html.Hr(),
            html.Div(
                id = {'type': 'dsa-login-div','index': 0},
                children = [
                    dbc.Stack([
                        dbc.Button(
                            'Login',
                            className = 'd-grid col-6 mx-auto',
                            color = 'success',
                            id = {'type': 'dsa-login-button','index': 0}
                        ),
                        dbc.Tooltip(
                            'For registered users, login to view your previous uploads or shared collections!',
                            target = {'type': 'dsa-login-button','index': 0},
                            placement='top'
                        ),
                        dbc.Button(
                            'Create an Account',
                            className = 'd-grid col-6 mx-auto',
                            color = 'warning',
                            id = {'type': 'dsa-login-create-account-button','index': 0}
                        ),
                        dbc.Tooltip(
                            'Create an account in order to upload slides to the DSA instance, to access user surveys, or to share data!',
                            target = {'type': 'dsa-login-create-account-button','index': 0},
                            placement='top'
                        )
                    ],direction='horizontal',gap=2)
                ]
            )
        ],style = {'marginTop':'10px','marginBottom':'10px','marginLeft':'10px','marginRight':'10px'})

        if use_prefix:
            PrefixIdTransform(prefix=self.component_prefix).transform_layout(layout)

        return layout

    def gen_layout(self,session_data:dict):
        """Creating the layout for this component, assigning it to the DashBlueprint object

        :param session_data: Dictionary containing relevant information for the current session
        :type session_data: dict
        """

        self.blueprint.layout = self.update_layout(session_data,use_prefix=False)

    def get_callbacks(self):

        # Callback for selecting Login vs. Create Account
        self.blueprint.callback(
            [
                Input({'type': 'dsa-login-button','index': ALL},'n_clicks'),
                Input({'type': 'dsa-login-create-account-button','index': ALL},'n_clicks'),
                Input({'type': 'dsa-login-back-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'dsa-login-div','index': ALL},'children')
            ]
        )(self.display_login_fields)

        # Callback for clicking Login button with username and password
        self.blueprint.callback(
            [
                Input({'type': 'dsa-login-login-submit','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-login-username-input','index': ALL},'value'),
                State({'type': 'dsa-login-password-input','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-login-username-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-password-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-login-error-div','index':ALL},'children'),
                Output({'type': 'dsa-login-current-user','index': ALL},'children'),
                Output('anchor-vis-store','data')
            ]
        )(self.submit_login)

        # Callback for clicking Create Account with input details
        self.blueprint.callback(
            [
                Input({'type':'dsa-login-create-account-submit','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-login-firstname-input','index': ALL},'value'),
                State({'type': 'dsa-login-lastname-input','index': ALL},'value'),
                State({'type': 'dsa-login-email-input','index': ALL},'value'),
                State({'type': 'dsa-login-username-input','index': ALL},'value'),
                State({'type': 'dsa-login-password-input','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-login-email-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-username-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-password-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-create-account-error-div','index': ALL},'children'),
                Output({'type': 'dsa-login-current-user','index': ALL},'children'),
                Output('anchor-vis-store','data')
            ]
        )(self.submit_create_account)
        
    def display_login_fields(self, login_clicked, create_account_clicked, back_clicked):
        """Displaying login fields depending on if login, create account, or back is clicked

        :param login_clicked: Login button clicked
        :type login_clicked: list
        :param create_account_clicked: Create Account button clicked
        :type create_account_clicked: list
        :param back_clicked: Back icon clicked
        :type back_clicked: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        if 'dsa-login-button' in ctx.triggered_id['type']:
            # Create input fields for "username" and "password" and a button for Login
            new_children = html.Div([
                dbc.Row([
                    dbc.Col(
                        html.A(
                            dbc.Stack([
                                html.P(
                                    html.I(
                                        className = 'fa-solid fa-arrow-left',
                                        style = {'marginRight':'5px'}
                                    )
                                ),
                                html.P(
                                    'Back'
                                )
                            ],direction='horizontal'),
                            id = {'type': f'{self.component_prefix}-dsa-login-back-icon','index': 0},
                            n_clicks = 0
                        )
                    )
                ]),
                dbc.Stack([
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Username: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-username-input','index': 0},
                            placeholder='username',
                            type = 'text',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = '^[a-z0-9]+$'
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-username-error-div','index': 0},
                        children = []
                    ),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Password: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-password-input','index': 0},
                            type = 'password',
                            required = True,
                            value = [],
                            maxLength = 1000
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-password-error-div','index': 0},
                        children = []
                    ),
                    dbc.Button(
                        'Login!',
                        className = 'd-grid col-12 mx-auto',
                        color = 'primary',
                        id = {'type': f'{self.component_prefix}-dsa-login-login-submit','index': 0},
                        n_clicks = 0
                    ),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-login-error-div','index': 0},
                        children = []
                    )
                ],direction = 'vertical',gap=1)
            ])

        elif 'dsa-login-create-account-button' in ctx.triggered_id['type']:
            # Create input fields for "username" and "password" and a button for Login
            new_children = html.Div([
                dbc.Row([
                    dbc.Col(
                        html.A(
                            dbc.Stack([
                                html.P(
                                    html.I(
                                        className = 'fa-solid fa-arrow-left',
                                        style = {'marginRight':'2px'}
                                    )
                                ),
                                html.P(
                                    'Back'
                                )
                            ],direction='horizontal'),
                            id = {'type': f'{self.component_prefix}-dsa-login-back-icon','index': 0},
                            n_clicks = 0
                        )
                    )
                ]),
                dbc.Stack([
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'First Name: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-firstname-input','index': 0},
                            placeholder='First Name',
                            type = 'text',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = '^[a-zA-Z]+$'
                        )
                    ]),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Last Name: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-lastname-input','index':0},
                            placeholder = 'Last Name',
                            type = 'text',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = '^[a-zA-Z]+$'
                        )
                    ]),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Email: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-email-input','index':0},
                            placeholder = 'email address',
                            type = 'email',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = "^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$"
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-email-error-div','index': 0},
                        children = []
                    ),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Username: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-username-input','index': 0},
                            placeholder='username',
                            type = 'text',
                            required = True,
                            value = [],
                            maxLength = 1000,
                            pattern = '^[a-z0-9]+$'
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-username-error-div','index': 0},
                        children = []
                    ),
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Password: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-login-password-input','index': 0},
                            type = 'password',
                            required = True,
                            value = [],
                            maxLength = 1000
                        )
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-password-error-div','index': 0},
                        children = []
                    ),
                    dbc.Button(
                        'Login!',
                        className = 'd-grid col-12 mx-auto',
                        color = 'primary',
                        id = {'type': f'{self.component_prefix}-dsa-login-create-account-submit','index': 0},
                        n_clicks = 0
                    ),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-login-create-account-error-div','index':0},
                        children = []
                    )
                ],direction='vertical',gap=1)
            ])
    
        elif 'dsa-login-back-icon' in ctx.triggered_id['type']:
            new_children = dbc.Stack([
                dbc.Button(
                    'Login',
                    className = 'd-grid col-6 mx-auto',
                    color = 'success',
                    id = {'type': f'{self.component_prefix}-dsa-login-button','index': 0}
                ),
                dbc.Tooltip(
                    'For registered users, login to view your previous uploads or shared collections!',
                    target = {'type': f'{self.component_prefix}-dsa-login-button','index': 0},
                    placement='top'
                ),
                dbc.Button(
                    'Create an Account',
                    className = 'd-grid col-6 mx-auto',
                    color = 'warning',
                    id = {'type': f'{self.component_prefix}-dsa-login-create-account-button','index': 0}
                ),
                dbc.Tooltip(
                    'Create an account in order to upload slides to the DSA instance, to access user surveys, or to share data!',
                    target = {'type': f'{self.component_prefix}-dsa-create-account-button','index': 0},
                    placement='top'
                )
            ],direction='horizontal',gap=2)

        return [new_children]
    
    def submit_login(self, login_clicked,username_input, password_input, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        
        username_input = get_pattern_matching_value(username_input)
        password_input = get_pattern_matching_value(password_input)

        if username_input is None or username_input == '':
            username_error_div = dbc.Alert('Make sure to enter a username!',color = 'danger')
        else:
            username_error_div = []
        
        if password_input is None or password_input == '':
            password_error_div = dbc.Alert('Make sure to enter your password!',color = 'danger')
        else:
            password_error_div = []

        if not any([i is None or i=='' for i in [username_input,password_input]]):
            new_login_output = self.handler.authenticate_new(
                username = username_input,
                password= password_input
            )
            if not type(new_login_output)==str:
                session_data['current_user'] = new_login_output
                current_user = f"Welcome, {new_login_output['login']}"
                session_data = json.dumps(session_data)
                login_error_div = []
            else:
                session_data = no_update
                current_user = no_update
                login_error_div = dbc.Alert(f'Error logging in with username: {username_input}',color = 'danger')
        else:
            session_data = no_update
            current_user = no_update
            login_error_div = []
        
        return [username_error_div], [password_error_div], [login_error_div], [current_user], session_data

    def submit_create_account(self, clicked,firstname_input, lastname_input, email_input, username_input, password_input,session_data):
        
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        
        firstname_input = get_pattern_matching_value(firstname_input)
        lastname_input = get_pattern_matching_value(lastname_input)
        username_input = get_pattern_matching_value(username_input)
        password_input = get_pattern_matching_value(password_input)
        email_input = get_pattern_matching_value(email_input)

        if username_input is None or username_input=='':
            username_error_div = dbc.Alert('Make sure to enter a username!',color = 'danger')
        else:
            username_error_div = []
        
        if password_input is None or password_input == '':
            password_error_div = dbc.Alert('Make sure to enter your password!',color = 'danger')
        else:
            password_error_div = []

        if email_input is None or email_input == '':
            email_error_div = dbc.Alert('Make sure to enter a valid email address! (And not the same as any other account)',color = 'danger')
        else:
            email_error_div = []

        if not any([i is None or i =='' for i in [firstname_input,lastname_input,email_input,username_input,password_input]]):
            create_user_output = self.handler.create_new_user(
                username = username_input,
                password = password_input,
                email = email_input,
                firstName = firstname_input,
                lastName= lastname_input
            )
            if create_user_output:
                session_data['current_user'] = create_user_output
                current_user = f"Welcome, {create_user_output['login']}"
                session_data = json.dumps(session_data)
                create_account_error_div = []
            else:
                session_data = no_update
                current_user = no_update
                create_account_error_div = dbc.Alert(f'Error creating account with username: {username_input}',color = 'danger')
        else:
            session_data = no_update
            current_user = no_update
            create_account_error_div = []
        
        return [username_error_div],[password_error_div],[email_error_div], [create_account_error_div], [current_user],session_data
        


class DatasetBuilder(DSATool):
    """Handler for DatasetBuilder component, enabling selection/deselection of folders and slides to add to current visualization session.

    :param DSATool: Sub-class of Tool specific to DSA components. Updates with session data by default.
    :type DSATool: None
    """
    def __init__(self,
                 handler: Union[DSAHandler,list] = [],
                 include_only: Union[list,None] = None
                ):
        
        super().__init__()
        self.include_only = include_only
        self.handler = handler

    def __str__(self):
        return 'Dataset Builder'

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Dataset Builder'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def gen_collections_dataframe(self,session_data:dict):

        collections_info = []
        collections = self.handler.get_collections()
        for c in collections:
            #slide_count = self.handler.get_collection_slide_count(collection_name = c['name'])
            folder_count = self.handler.get_path_info(path = f'/collection/{c["name"]}')
            #if slide_count>0:
            collections_info.append({
                'Collection Name': c['name'],
                'Collection ID': c['_id'],
                #'Number of Slides': slide_count,
                'Number of Folders': folder_count['nFolders'],
                'Last Updated': folder_count['updated']
            } | c['meta'])

        if 'current_user' in session_data:
            collections_info.append({
                'Collection Name': f'User: {session_data["current_user"]["login"]}',
                'Collection ID': session_data["current_user"]['_id'],
                'Number of Folder': 2,
                'Last Updated': '-'
            })
            
        collections_df = pd.DataFrame.from_records(collections_info)

        return collections_df

    def update_layout(self, session_data:dict, use_prefix: bool):
        """Generating DatasetBuilder layout

        :return: Div object containing interactive components for the SlideMap object.
        :rtype: dash.html.Div.Div
        """

        # Adding current session data here
        starting_slides = []
        starting_slides_components = []
        starting_slide_idx = 0
        for s in session_data['current']:
            if 'api_url' in s:
                if s['api_url']==self.handler.girderApiUrl:
                    # Getting the id of the DSA slide from this same instance
                    slide_id = s['tiles_url'].split('/item/')[1].split('/')[0]
                    starting_slides.append(slide_id)
                    starting_slides_components.append(
                        self.make_selected_slide(
                            slide_id = slide_id,
                            idx = starting_slide_idx,
                            use_prefix= not use_prefix
                        )
                    )
                    starting_slide_idx += 1
            else:
                thumbnail_address = s['regions_url'].replace('region','thumbnail')
                slide_index = thumbnail_address.split('/')[-3]
                starting_slides.append(f'local{slide_index}')
                starting_slides_components.append(
                    self.make_selected_slide(
                        slide_id = thumbnail_address,
                        idx = starting_slide_idx,
                        local_slide=True,
                        use_prefix = not use_prefix
                    )
                )
                starting_slide_idx+=1

        
        collections_df = self.gen_collections_dataframe(session_data)

        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Dataset Builder')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Search through available collections, folders, and slides to assemble a visualization session.'
                    ),
                    html.Hr(),
                    html.Div(
                        dcc.Store(
                            id = {'type':'dataset-builder-data-store','index': 0},
                            storage_type='memory',
                            data = json.dumps({'selected_slides':starting_slides, 'selected_collections': [], 'available_collections': collections_df.to_dict("records")})
                        )
                    ),
                    dbc.Row([
                        html.Div(
                            id = {'type':'dataset-builder-local-slides-div','index': 0},
                            children = [
                                self.make_selectable_dash_table(
                                    dataframe=pd.DataFrame.from_records([
                                        {
                                            'Slide Name': j['name'],
                                            'Slide ID': f'local{j_idx}'
                                        }
                                        for j_idx,j in enumerate(session_data['local'])
                                    ]),
                                    id = {'type':'dataset-builder-slide-table','index': 999},
                                    multi_row= True,
                                    selected_rows = [idx for idx,i in enumerate(session_data['local']) if i in session_data['current']]
                                )
                            ],
                            style = {'marginBottom':'5px'}
                        )
                    ]),
                    html.Hr(),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'dataset-builder-collection-div','index': 0},
                            children = [
                                self.make_selectable_dash_table(
                                    dataframe = collections_df,
                                    id = {'type': 'dataset-builder-collections-table','index': 0},
                                    multi_row = True
                                )
                            ]
                        )
                    ],style={'marginBottom':'10px'}),
                    html.Hr(),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'dataset-builder-collection-contents-div','index':0},
                            children = []
                        )
                    ],style = {'marginBottom':'10px','maxHeight':'70vh','overflow':'scroll'}),
                    html.Div([
                        dmc.Affix([
                            dmc.Accordion([
                                dmc.AccordionItem([
                                    dmc.AccordionControl(
                                        dbc.Stack([
                                            html.I(className='fa-solid fa-microscope',style={'marginRight':'2px'}),
                                            html.H5(f'Visualization Session: ({len(starting_slides)})',style={'textTransform':'none'},id = {'type': 'dataset-builder-vis-session-count','index': 0})
                                        ],direction='horizontal')
                                    ),
                                    dmc.AccordionPanel([
                                        html.Div(
                                            id = {'type':'dataset-builder-selected-slides','index': 0},
                                            children = starting_slides_components,
                                            style = {'maxHeight':'50vh','overflow':'scroll'}
                                        )
                                    ])
                                ],value = 'dataset-builder-vis-session')
                            ],style={'width':'25vw'},radius='lg',variant='separated',chevronPosition='left')
                        ],
                        position = {'bottom':'20','right':'20'})
                    ])
                ])
            )
        ], style = {'maxHeight': '90vh','overflow': 'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix = self.component_prefix).transform_layout(layout)
        
        return layout

    def gen_layout(self, session_data: Union[dict,None]):
        """Generating DatasetBuilder layout, adding to DashBlueprint() object to be embedded in larger layout.

        :param session_data: Data on current session, not used in this component.
        :type session_data: Union[dict,None]
        """

        self.blueprint.layout = self.update_layout(session_data,use_prefix=False)

    def get_callbacks(self):

        # Callback for collection selection (populating table with collection contents)
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-collections-table','index': ALL},'selected_rows')
            ],
            [
                State({'type':'dataset-builder-data-store','index': ALL},'data'),
                State({'type':'dataset-builder-collection-contents-div','index': ALL},'children')
            ],
            [
                Output({'type':'dataset-builder-collection-contents-div','index': ALL},'children'),
                Output({'type':'dataset-builder-data-store','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.collection_selection)

        # Callback for selecting folder from collection-contents-div
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-collection-folder-table','index':MATCH},'selected_rows'),
                Input({'type':'dataset-builder-collection-folder-crumb','index':ALL},'n_clicks')
            ],
            [
                State({'type':'dataset-builder-collection-folder-table','index': MATCH},'data'),
                State({'type': 'dataset-builder-collection-folder-nav-parent','index': MATCH},'children'),
                State({'type':'dataset-builder-data-store','index': ALL},'data')
            ],
            [
                Output({'type':'dataset-builder-collection-folder-div','index': MATCH},'style'),
                Output({'type':'dataset-builder-collection-folder-div','index':MATCH},'children'),
                Output({'type':'dataset-builder-collection-slide-div','index':MATCH},'children'),
                Output({'type':'dataset-builder-collection-folder-nav-parent','index': MATCH},'children')
            ],
            prevent_initial_call = True
        )(self.update_folder_div)

        # Callback for selecting slide(s) to be added to visualization session
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-slide-table','index':ALL},'selected_rows'),
                Input({'type':'dataset-builder-slide-select-all','index':ALL},'n_clicks'),
                Input({'type':'dataset-builder-slide-remove-all','index':ALL},'n_clicks'),
                Input({'type':'dataset-builder-slide-remove-icon','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dataset-builder-collection-folder-nav-parent','index': ALL},'children'),
                State({'type':'dataset-builder-slide-table','index': ALL},'data'),
                State({'type':'dataset-builder-data-store','index': ALL},'data'),
                State({'type':'dataset-builder-selected-slides','index': ALL},'children'),
                State({'type':'dataset-builder-collection-contents-div','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dataset-builder-selected-slides','index': ALL},'children'),
                Output({'type': 'dataset-builder-vis-session-count','index': ALL},'children'),
                Output({'type':'dataset-builder-data-store','index':ALL},'data')
            ]
        )(self.slide_selection)

        # Passing current visualization data to the visualization session for usage in other pages
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-data-store','index': ALL},'data')
            ],
            [
                State('anchor-vis-store','data')
            ],
            [
                Output('anchor-vis-store','data')
            ]
        )(self.update_vis_store)

        # Callback for plotting slide-level metadata if there is any

    def make_selectable_dash_table(self, dataframe:pd.DataFrame, id:dict, multi_row:bool = True, selected_rows: list = []):
        """Generate a selectable DataTable to add to the layout

        :param dataframe: Pandas DataFrame containing columns/rows of interest
        :type dataframe: pd.DataFrame
        :param id: Dictionary containing "type" and "index" keys for interactivity
        :type id: dict
        :param multi_row: Whether to allow selection of multiple rows in the table or just single, defaults to True
        :type multi_row: bool, optional
        :return: dash_table.DataTable component to be added to layout
        :rtype: dash_table.DataTable
        """

        #Optional: Can hide "ID" columns by adding any column containing "ID" to a list of "hidden_columns"

        dataframe = pd.json_normalize(dataframe.to_dict('records'))
        selectable_table = dash_table.DataTable(
            id = id,
            columns = [{'name':i,'id':i,'deletable':False} for i in dataframe.columns],
            data = dataframe.to_dict('records'),
            editable = False,
            filter_action='native',
            sort_action = 'native',
            sort_mode = 'multi',
            column_selectable = 'single',
            row_selectable = 'multi' if multi_row else 'single',
            row_deletable = False,
            selected_rows = selected_rows,
            page_action='native',
            page_current=0,
            page_size=10,
            style_cell = {
                'overflow':'hidden',
                'textOverflow':'ellipsis',
                'maxWidth':0                
            },
            tooltip_data = [
                {
                    column: {'value':str(value),'type':'markdown'}
                    for column, value in row.items()
                } for row in dataframe.to_dict('records')
            ],
            tooltip_duration = None
        )

        return selectable_table

    def organize_folder_contents(self, folder_info:dict, show_empty:bool=False, ignore_histoqc:bool=True)->list:
        """For a given folder selection, return a list of slides(0th) and folders (1th)

        :param folder_info: Folder info dict returned by self.handler.get_path_info(path)
        :type folder_info: dict
        :param show_empty: Whether or not to display folders which contain 0 slides, defaults to False
        :type show_empty: bool, optional
        :return: List of slides within the current folder as well as folders within that folder
        :rtype: list
        """

        folder_folders = []
        folder_slides = []

        # Starting with slides (which will report parent folderId but not that parent's folderId (if applicable))
        if folder_info['_modelType'] in ['folder','collection']:
            all_folder_slides = self.handler.get_folder_slides(
                folder_path = folder_info['_id'],
                folder_type = folder_info['_modelType'],
                ignore_histoqc=ignore_histoqc
            )

            folder_slides_folders = [i['folderId'] for i in all_folder_slides]
            unique_folders = list(set(folder_slides_folders))
            folders_in_folder = []
            for u in unique_folders:
                if not u==folder_info['_id'] and not u in folders_in_folder:
                    # This is for all folders in this folder
                    # This grabs parent folders of this folder
                    u_folder_info = self.handler.get_folder_info(folder_id=u)
                    u_folder_rootpath = self.handler.get_folder_rootpath(u)
                    # Folders in order from collection-->child folder-->etc.
                    folder_ids = [i['object']['_id'] for i in u_folder_rootpath]

                    if any([i['object']['_modelType']=='collection' for i in u_folder_rootpath]):
                        base_model = 'collection'
                    else:
                        base_model = 'user'

                    if folder_ids[-1]==folder_info['_id']:
                        child_folder_path = f'/{base_model}/'+'/'.join([i['object']['name'] if i['object']['_modelType'] in ['folder','collection'] else i['object']['login'] for i in u_folder_rootpath]+[u_folder_info['name']])
                    else:
                        # Folder that is immediate child of current folder:
                        child_folder_idx = folder_ids.index(folder_info['_id'])
                        child_folder_path = f'/{base_model}/'+'/'.join([i['object']['name'] if i['object']['_modelType'] in ['folder','collection'] else i['object']['login'] for i in u_folder_rootpath[:child_folder_idx+2]])


                    child_folder_path_info = self.handler.get_path_info(
                        path = child_folder_path
                    )
                    if not child_folder_path_info['_id'] in folders_in_folder:
                        folders_in_folder.append(child_folder_path_info['_id'])
                        
                        # Adding folder to list if the number of items is above zero or show_empty is True
                        folder_folders.append({
                            'Folder Name': child_folder_path_info['name'],
                            'Folder ID': child_folder_path_info['_id'],
                            'Number of Folders': child_folder_path_info['nFolders'],
                            'Number of Slides': child_folder_path_info['nItems'],
                            'Last Updated': child_folder_path_info['updated']
                        } | child_folder_path_info['meta'])

                elif u==folder_info['_id']:
                    # This means that there are some slides that are direct children (not in a sub-folder) in this folder. 
                    # This adds them all at once
                    for i in all_folder_slides:
                        if i['folderId']==folder_info['_id']:
                            folder_slides.append(
                                {
                                    'Slide Name': i['name'],
                                    'Slide ID': i['_id'],
                                    'Last Updated':i['updated']
                                } | {k:v for k,v in i['meta'].items() if type(v)==str}
                            )

        else:
            
            user_folders = ['Private','Public']
            for u_f in user_folders:
                user_folder_info = self.handler.get_path_info(
                    path = f'/user/{folder_info["login"]}/{u_f}'
                )

                folder_folders.append({
                    'Folder Name': user_folder_info['name'],
                    'Folder ID': user_folder_info['_id'],
                    'Number of Folders': user_folder_info['nFolders'],
                    'Number of Slides': user_folder_info['nItems'],
                    'Last Updated': user_folder_info['updated']
                })

        if show_empty:
            # This is how you get all the empty folders within a folder (does not get child empty folders)
            empty_folders = self.handler.get_folder_folders(
                folder_id = folder_info['_id'],
                folder_type = folder_info['_modelType']
            )
            
            for f in empty_folders:
                if not f['_id'] in folders_in_folder and not f['_id'] in unique_folders:
                    folder_info = self.handler.gc.get(f'/folder/{f["_id"]}/details')
                    folder_folders.append(
                        {
                            'Folder Name': f['name'],
                            'Folder ID': f['_id'],
                            'Number of Folders': folder_info['nFolders'],
                            'Number of Slides': folder_info['nItems'],
                            'Last Updated': f['updated']
                        }
                    )


        return folder_slides, folder_folders

    def make_selected_slide(self, slide_id:str,idx:int,local_slide:bool = False, use_prefix:bool = True):
        """Creating a visualization session component for a selected slide

        :param slide_id: Girder Id for the slide to be added
        :type slide_id: str
        :param local_slide: Whether or not the slide is from the LocalTileServer or if it's in the cloud
        :type local_slide: bool
        :param use_prefix: Whether or not to add the component prefix (initially don't add, when updating the layout do add)
        :param use_prefix: bool
        """
        
        if not local_slide:
            item_info = self.handler.gc.get(f'/item/{slide_id}')
            item_thumbnail = self.handler.get_image_thumbnail(slide_id)
            folder_info = self.handler.get_folder_info(item_info['folderId'])
            slide_info = {
                k:v for k,v in item_info.items() if type(v) in [int,float,str]
            }
        else:
            # For local slides, "slide_id" is the request for getting the slide thumbnail
            item_idx = int(slide_id.split('/')[-3])

            try:
                item_thumbnail = Image.open(BytesIO(requests.get(slide_id).content))
                local_names = requests.get(slide_id.replace(f'{item_idx}/tiles/thumbnail','names')).json()['message']
            except (requests.exceptions.ConnectionError, requests.exceptions.RetryError):
                # Triggered on initialization of application because the LocalTileServer instance is not running yet
                item_thumbnail = np.zeros((256,256,3)).astype(np.uint8)
                local_names = ['LOADING LOCALTILESERVER']*(item_idx+1)

            folder_info = {'name': 'Local Slides'}
            slide_info = {'name': local_names[item_idx]}               


        slide_card = html.Div([
            dbc.Card([
                dbc.CardHeader(f"{folder_info['name']}/{slide_info['name']}"),
                dbc.CardBody([
                    dbc.Stack([
                        html.Img(
                            src=Image.fromarray(item_thumbnail) if type(item_thumbnail)==np.ndarray else item_thumbnail
                        ),
                        html.A(
                            html.I(
                                id = {'type': f'{self.component_prefix}-dataset-builder-slide-remove-icon','index': idx} if use_prefix else {'type': 'dataset-builder-slide-remove-icon','index': idx},
                                n_clicks = 0,
                                className = 'bi bi-x-circle-fill fa-2x',
                                style = {'color': 'rgb(255,0,0)','marginRight':'2px'}
                            )
                        )
                    ],direction='horizontal',gap=3)
                ])
            ])
        ],style = {'marginBottom': '2px','width':'25vw'})
        
        return slide_card        

    def collection_selection(self, collection_rows, builder_data, collection_div_children):
        """Callback for when one/multiple collections are selected from the collections table

        :param collection_rows: Row indices of selected collections
        :type collection_rows: list
        :param builder_data: Data store on available collections and currently included slides
        :type builder_data: list
        :param colleciton_div_children: Child cards created by collection_selection
        :type colleciton_div_children: list
        :return: Children of collection-contents-div (items/folders within selected collections)
        :rtype: list
        """
        selected_collections = get_pattern_matching_value(collection_rows)
        builder_data = json.loads(get_pattern_matching_value(builder_data))

        collection_card_indices = self.get_component_indices(collection_div_children)

        if selected_collections is None and len(builder_data['selected_collections'])==0:
            return ['Select a Collection to get started'], no_update
        elif selected_collections is None and len(builder_data['selected_collections'])>0:
            selected_collections = []

        if len(selected_collections)==1 and len(builder_data['selected_collections'])==0:
            collection_contents = []
        else:
            collection_contents = Patch()

        def add_collection_card(collection_info,idx):
            # For each collection, grab all items and unique folders (as well as those that are not nested in a folder)
            if not 'User: ' in collection_info["Collection Name"]:
                folder_slides, folder_folders = self.organize_folder_contents(
                    folder_info = self.handler.get_path_info(f'/collection/{collection_info["Collection Name"]}')
                )
            else:
                folder_slides, folder_folders = self.organize_folder_contents(
                    folder_info=self.handler.get_path_info(f'/user/{collection_info["Collection Name"].replace("User: ","")}')
                )

            if len(folder_slides)>0:

                # Checking if any of the slides are already present in the "selected_slides"
                current_selected_slides = builder_data['selected_slides']
                selected_rows = [
                    idx for idx,i in enumerate(folder_slides)
                    if i['Slide ID'] in current_selected_slides
                ]

                non_nested_df = pd.DataFrame.from_records(folder_slides)
                non_nested_table = self.make_selectable_dash_table(
                    dataframe=non_nested_df,
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-slide-table','index': idx},
                    multi_row=True,
                    selected_rows=selected_rows
                )

            else:
                non_nested_table= html.Div()

            if len(folder_folders)>0:
                folder_table = self.make_selectable_dash_table(
                    dataframe=pd.DataFrame.from_records(folder_folders),
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-table','index': idx},
                    multi_row=False
                )
            else:
                folder_table = html.Div()

            new_card = html.Div(
                dbc.Card([
                    dbc.CardHeader(f'Collection: {collection_info["Collection Name"]}'),
                    dbc.CardBody([
                        html.H6(
                            children = [
                                dbc.Stack([
                                    html.A('/collection' if not 'User: ' in collection_info['Collection Name'] else '/user'),
                                    html.A(
                                        f'/{collection_info["Collection Name"].replace("User: ","")}/',
                                        id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-crumb','index': idx},
                                        style = {'color': 'rgb(0,0,255)'}
                                    )
                                ],direction='horizontal')
                            ],
                            id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-nav-parent','index': idx},
                            style = {'textTransform':'none','display':'inline'}
                        ),
                        html.Hr(),
                        html.Div([
                            folder_table
                        ], id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-div','index': idx}),
                        html.Hr(),
                        html.Div([
                            non_nested_table
                        ], style = {'marginTop':'10px'},id = {'type': f'{self.component_prefix}-dataset-builder-collection-slide-div','index': idx}),
                        html.Div(
                            dbc.Stack([
                                dbc.Button(
                                    'Select All!',
                                    className = 'd-grid col-6 mx-auto',
                                    n_clicks = 0,
                                    color = 'success',
                                    id = {'type':f'{self.component_prefix}-dataset-builder-slide-select-all','index': idx}
                                ),
                                dbc.Button(
                                    'Remove All',
                                    className = 'd-grid col-6 mx-auto',
                                    n_clicks = 0,
                                    color = 'danger',
                                    id = {'type': f'{self.component_prefix}-dataset-builder-slide-remove-all','index':idx}
                                )
                            ],direction='horizontal',style = {'marginTop':'10px'})
                            if len(folder_slides)>0 else []
                        )
                    ]),
                ]),
                style = {'marginBottom':'10px'},
                id = {'type': f'{self.component_prefix}-dataset-builder-collection-card-div','index': idx}
            )
            
            return new_card
        
        if len(selected_collections)>0:
            if len(list(set(selected_collections).difference(builder_data['selected_collections'])))>0:
                # Adding a new collection
                new_collection_idx = list(set(selected_collections).difference(builder_data['selected_collections']))[0]
                new_component_idx = max(collection_card_indices)+1 if len(collection_card_indices)>0 else 0

                collection_contents.append(add_collection_card(builder_data['available_collections'][new_collection_idx],new_component_idx))
            elif len(list(set(builder_data['selected_collections']).difference(selected_collections)))>0:
                # Removing a collection
                rem_collection_idx = list(set(builder_data['selected_collections']).difference(selected_collections))[0]
                del collection_contents[builder_data['selected_collections'].index(rem_collection_idx)]

        else:
            collection_contents = ['Select a Collection to get started!']

        builder_data['selected_collections'] = selected_collections
        builder_data = json.dumps(builder_data)
            
        return [collection_contents], [builder_data]

    def extract_path_parts(self, current_parts:Union[list,dict], search_key: list = ['props','children'])->tuple:
        """Recursively extract pieces of folder paths stored as clickable components.

        :param current_parts: list or dictionary containing html.A or dbc.Stack of html.A components.
        :type current_parts: Union[list,dict]
        :param search_key: Property keys to search for in nested dicts, defaults to ['props','children']
        :type search_key: list, optional
        :return: Tuple containing all the parts of the folder path
        :rtype: tuple
        """
        path_pieces = ()
        if type(current_parts)==list:
            for c in current_parts:
                if type(c)==dict:
                    for key,value in c.items():
                        if key in search_key:
                            if type(value)==str:
                                path_pieces += (value,)
                            elif type(value) in [list,dict]:
                                path_pieces += self.extract_path_parts(value)
                elif type(c)==list:
                    path_pieces += self.extract_path_parts(c)
        elif type(current_parts)==dict:
            for key,value in current_parts.items():
                if key in search_key:
                    if type(value)==str:
                        path_pieces += (value,)
                    elif type(value) in [list,dict]:
                        path_pieces += self.extract_path_parts(value)

        return path_pieces

    def get_clicked_part(self, current_parts: Union[list,dict])->list:
        """Get the "n_clicks" value for components which have "id". If they have "id" but not "n_clicks", assign 0

        :param current_parts: Either a list or dictionary containing components
        :type current_parts: Union[list,dict]
        :return: List of values corresponding to "n_clicks" 
        :rtype: list
        """
        
        n_clicks_list = []
        if type(current_parts)==list:
            for c in current_parts:
                if type(c)==dict:
                    if 'id' in list(c.keys()):
                        if 'n_clicks' in list(c.keys()):
                            n_clicks_list.append(c['n_clicks'])
                        else:
                            n_clicks_list.append(0)
                    else:
                        for key,value in c.items():
                            if key=='props':
                                n_clicks_list += self.get_clicked_part(value)
                            elif key=='n_clicks':
                                n_clicks_list.append(value)
                elif type(c)==list:
                    n_clicks_list += self.get_clicked_part(c)
        elif type(current_parts)==dict:
            if 'id' in list(current_parts.keys()):
                if 'n_clicks' in list(current_parts.keys()):
                    n_clicks_list.append(current_parts['n_clicks'])
                else:
                    n_clicks_list.append(0)
            else:
                for key,value in current_parts.items():
                    if type(value)==dict:
                        if key=='props':
                            n_clicks_list += self.get_clicked_part(value)
                        elif key=='n_clicks':
                            n_clicks_list.append(value)
                    elif type(value)==list:
                        n_clicks_list += self.get_clicked_part(value)

        return n_clicks_list

    def get_component_indices(self, components: Union[list,dict])->list:
        
        index_list = []
        if type(components)==list:
            for c in components:
                if type(c)==dict:
                    for key,value in c.items():
                        if key=='id':
                            index_list.append(value['index'])
                        elif key in ['props','children']:
                            index_list += self.get_component_indices(value)
                elif type(c)==list:
                    index_list += self.get_component_indices(c)

        elif type(components)==dict:
            for key,value in components.items():
                if key=='id':
                    index_list.append(value['index'])
                elif key in ['props','children']:
                    index_list += self.get_component_indices(value)

        return index_list

    def update_folder_div(self,folder_row,crumb_click,collection_folders,current_crumbs,builder_data):
        """Selecting a folder from the collection's folder table

        :param folder_row: Selected folder (list of 1 index)
        :type folder_row: list
        :param crumb_click: If one of the folder path parts was clicked it will trigger this.
        :type crumb_click: int
        :param collection_folders: Current data in the collection's folder table
        :type collection_folders: list
        :param current_crumbs: List of current path parts that can be selected to go up a folder
        :type current_crumbs: list
        :param builder_data: Current contents of data store for dataset-builder, used for determining if a slide is already selected
        :type builder_data: list
        :return: Sub-folder and slide selection tables for further selection
        :rtype: tuple
        """

        path_parts = self.extract_path_parts(current_crumbs)
        new_crumbs = []
        for i in path_parts:
            if not i in ['/collection','/user']:
                new_crumbs.append(
                    html.A(
                        i,
                        id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-crumb','index': ctx.triggered_id['index']},
                        style = {'color': 'rgb(0,0,255)'}
                    )
                )
            else:
                new_crumbs.append(
                    html.A(i)
                )

        builder_data = json.loads(get_pattern_matching_value(builder_data))
        
        if 'dataset-builder-collection-folder-table' in ctx.triggered_id['type']:
            
            # Triggers callback when creating new folder table
            if len(folder_row)==0:
                return no_update, no_update, no_update

            new_folder_name = collection_folders[folder_row[0]]['Folder Name']
            folder_table_style = {'display':'inline-block','width':'100%'}
            
            new_crumbs += [
                html.A(
                    new_folder_name + '/',
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-crumb','index': ctx.triggered_id['index']},
                    style = {'color': 'rgb(0,0,255)'}
                )
            ]
            
            folder_path = ''.join(list(path_parts+(new_folder_name,)))
            folder_info = self.handler.get_path_info(
                path = folder_path
            )
            
            folder_slides, folder_folders = self.organize_folder_contents(
                folder_info=folder_info
            )

            if len(folder_folders)>0:
                folder_table = self.make_selectable_dash_table(
                    dataframe = pd.DataFrame.from_records(folder_folders),
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-table','index': ctx.triggered_id['index']},
                    multi_row=False
                )
            else:
                folder_table_style = {'display':'none'}
                folder_table = no_update

                
            if len(folder_slides)>0:
                current_selected_slides = builder_data['selected_slides']
                selected_rows = [
                    idx for idx,i in enumerate(folder_slides)
                    if i['Slide ID'] in current_selected_slides
                ]

                slides_table = html.Div([
                    self.make_selectable_dash_table(
                        dataframe=pd.DataFrame.from_records(folder_slides),
                        id = {'type': f'{self.component_prefix}-dataset-builder-slide-table','index': ctx.triggered_id['index']},
                        multi_row=True,
                        selected_rows= selected_rows
                    ),
                    dbc.Stack([
                        dbc.Button(
                            'Select All!',
                            className = 'd-grid col-6 mx-auto',
                            n_clicks = 0,
                            color = 'success',
                            id = {'type':f'{self.component_prefix}-dataset-builder-slide-select-all','index': ctx.triggered_id['index']}
                        ),
                        dbc.Button(
                            'Remove All',
                            className = 'd-grid col-6 mx-auto',
                            n_clicks = 0,
                            color = 'danger',
                            id = {'type': f'{self.component_prefix}-dataset-builder-slide-remove-all','index':ctx.triggered_id['index']}
                        )
                    ],direction='horizontal',style = {'marginTop':'10px'})
                ])
            else:
                slides_table = html.Div()


        elif 'dataset-builder-collection-folder-crumb' in ctx.triggered_id['type']:
            n_clicks = [0]+self.get_clicked_part(current_crumbs)
            n_click_idx = np.argmax(n_clicks)
            if n_click_idx==len(current_crumbs)-1:
                folder_table_style = no_update
                folder_table = no_update
            else:
                folder_table_style = {'display':'inline-block','width':'100%'}
                new_crumbs = new_crumbs[:n_click_idx+1]
                
                new_path = ''.join(list(path_parts)[:n_click_idx+1])[:-1]
                folder_info = self.handler.get_path_info(
                    path = new_path
                )
                
                folder_slides, folder_folders = self.organize_folder_contents(
                    folder_info=folder_info
                )

                if len(folder_folders)>0:
                    folder_table = self.make_selectable_dash_table(
                        dataframe = pd.DataFrame.from_records(folder_folders),
                        id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-table','index': ctx.triggered_id['index']},
                        multi_row=False
                    )
                else:
                    folder_table = no_update
                    folder_table_style = {'display':'none'}

                    
                if len(folder_slides)>0:

                    current_selected_slides = builder_data['selected_slides']
                    selected_rows = [
                        idx for idx,i in enumerate(folder_slides)
                        if i['Slide ID'] in current_selected_slides
                    ]

                    slides_table = html.Div([
                        self.make_selectable_dash_table(
                            dataframe=pd.DataFrame.from_records(folder_slides),
                            id = {'type': f'{self.component_prefix}-dataset-builder-slide-table','index': ctx.triggered_id['index']},
                            multi_row=True,
                            selected_rows=selected_rows
                        ),
                        dbc.Stack([
                            dbc.Button(
                                'Select All!',
                                className = 'd-grid col-6 mx-auto',
                                n_clicks = 0,
                                color = 'success',
                                id = {'type':f'{self.component_prefix}-dataset-builder-slide-select-all','index': ctx.triggered_id['index']}
                            ),
                            dbc.Button(
                                'Remove All',
                                className = 'd-grid col-6 mx-auto',
                                n_clicks = 0,
                                color = 'danger',
                                id = {'type': f'{self.component_prefix}-dataset-builder-slide-remove-all','index':ctx.triggered_id['index']}
                            )
                        ],direction='horizontal',style = {'marginTop':'10px'})
                    ])
                else:
                    slides_table = html.Div()
                
        new_crumbs = dbc.Stack(new_crumbs,direction='horizontal')

        return folder_table_style, folder_table, slides_table, new_crumbs

    def slide_selection(self, slide_rows, slide_all, slide_rem_all, slide_rem, current_crumbs, slide_table_data, builder_data, current_slide_components, current_collection_components, vis_session_data):

        builder_data = json.loads(get_pattern_matching_value(builder_data))
        vis_session_data = json.loads(vis_session_data)

        current_slide_indices = self.get_component_indices(current_slide_components)
        current_collection_indices = list(set(self.get_component_indices(current_collection_components)))

        # When slide-table is not in layout
        if not ctx.triggered_id:
            raise exceptions.PreventUpdate
        
        active_folders = []
        for p in current_crumbs:
            path = ''.join(list(self.extract_path_parts(p)))
            active_folders.append(path)

        current_selected_slides = builder_data['selected_slides']

        selected_slides = Patch()
        
        if 'dataset-builder-slide-table' in ctx.triggered_id['type']:
            # This part has to get triggered for both selection and de-selection of rows in a slide-table
            table_selected_slides = []
            not_selected_slides = []
            for s_r,slide_table in zip(slide_rows,slide_table_data):
                if not s_r is None:
                    table_selected_slides.extend([slide_table[i] for i in s_r])
                    not_selected_slides.extend([slide_table[i] for i in range(len(slide_table)) if not i in s_r])

            new_slides = list(set([i['Slide ID'] for i in table_selected_slides]).difference(current_selected_slides))
            
            for s_idx,s in enumerate(new_slides):
                if not 'local' in s:
                    new_slide_component = self.make_selected_slide(
                        slide_id = s,
                        idx = max(current_slide_indices)+s_idx+1 if len(current_slide_indices)>0 else s_idx
                    )
                else:
                    local_idx = int(s.split('local')[-1])
                    new_slide_component = self.make_selected_slide(
                        slide_id = vis_session_data['local'][local_idx]['regions_url'].replace('region','thumbnail'),
                        idx = max(current_slide_indices)+s_idx+1 if len(current_slide_indices)>0 else s_idx,
                        local_slide=True
                    )

                selected_slides.append(new_slide_component)

            current_selected_slides.extend(new_slides)

            new_rem_slides = list(set(current_selected_slides) & set([i['Slide ID'] for i in not_selected_slides]))
            print(f'new_rem_slides: {new_rem_slides}')
            for d_idx,d in enumerate(new_rem_slides):
                del selected_slides[current_selected_slides.index(d)]
                del current_selected_slides[current_selected_slides.index(d)]           

        elif 'dataset-builder-slide-select-all' in ctx.triggered_id['type']:
            # This part only gets triggered when n_clicks is greater than 0 (ignore trigger on creation)
            if any([i['value'] for i in ctx.triggered]):
                select_all_idx = ctx.triggered_id['index']
                select_all_slides = slide_table_data[current_collection_indices.index(select_all_idx)]

                new_slides = list(set([i['Slide ID'] for i in select_all_slides]).difference(current_selected_slides))
                selected_slides.extend([
                    self.make_selected_slide(
                        slide_id = s,
                        idx = max(current_slide_indices)+s_idx+1 if len(current_slide_indices)>0 else s_idx
                    )
                    for s_idx,s in enumerate(new_slides)
                ])
                current_selected_slides.extend(new_slides)

            else:
                raise exceptions.PreventUpdate

        elif 'dataset-builder-slide-remove-all' in ctx.triggered_id['type']:
            # This part only gets triggered when n_clicks is greater than 0 (ignore trigger on creation)
            if any([i['value'] for i in ctx.triggered]):
                remove_all_idx = ctx.triggered_id['index']
                remove_all_slides = slide_table_data[current_collection_indices.index(remove_all_idx)]

                new_rem_slides = list(set(current_selected_slides) & set([i['Slide ID'] for i in remove_all_slides]))
                for d_idx,d in enumerate(new_rem_slides):
                    del selected_slides[current_selected_slides.index(d)]
                    del current_selected_slides[current_selected_slides.index(d)]

            else:
                raise exceptions.PreventUpdate      
            
        elif 'dataset-builder-slide-remove-icon' in ctx.triggered_id['type']:
            rem_idx = current_slide_indices.index(ctx.triggered_id['index'])
            del selected_slides[rem_idx]
            del current_selected_slides[rem_idx]

        else:
            raise exceptions.PreventUpdate
        
        # Need folder id, rootpath, slide info, 
        builder_data['selected_slides'] = current_selected_slides
        builder_data = json.dumps(builder_data)

        # Updated count of included slides:
        included_slide_count = f'Visualization Session ({len(current_selected_slides)})'

        return [selected_slides], [included_slide_count], [builder_data]

    def update_vis_store(self, new_slide_data, current_vis_data):
        """Updating current visualization session based on selected slide(s)

        :param new_slide_data: New slides to be added to the Visualization Session
        :type new_slide_data: list
        :param current_vis_data: Current Visualization Session data
        :type current_vis_data: list
        :return: Updated Visualization Session 
        :rtype: str
        """
        
        new_slide_data = get_pattern_matching_value(new_slide_data)
        if new_slide_data is None:
            raise exceptions.PreventUpdate
        
        new_slide_data = json.loads(get_pattern_matching_value(new_slide_data))
        current_vis_data = json.loads(current_vis_data)
        prev_vis_data_in_handler = []
        for i in current_vis_data['current']:
            if 'api_url' in i:
                if i['api_url']==self.handler.girderApiUrl:
                    prev_vis_data_in_handler.append(i)
            else:
                prev_vis_data_in_handler.append(i)

        # Adding new slides to current_vis_data
        new_slide_info = []
        for s in new_slide_data['selected_slides']:
            if not 'local' in s:
                slide_info = self.handler.gc.get(f'/item/{s}')
                new_slide_info.append(
                    {
                        'name': slide_info['name'],
                        'api_url': self.handler.girderApiUrl,
                        'tiles_url': f'{self.handler.girderApiUrl}/item/{s}/tiles/zxy'+'/{z}/{x}/{y}',
                        'regions_url': f'{self.handler.girderApiUrl}/item/{s}/tiles/region',
                        'metadata_url': f'{self.handler.girderApiUrl}/item/{s}/tiles',
                        'annotations_url': f'{self.handler.girderApiUrl}/annotation/item/{s}'
                    }
                )
            else:
                local_idx = int(s.split('local')[-1])
                new_slide_info.append(
                    current_vis_data['local'][local_idx]
                )
        
        prev_slides_in_handler = [i['tiles_url'] for i in prev_vis_data_in_handler]
        new_slides_in_handler = [i['tiles_url'] for i in new_slide_info]

        if sorted(prev_slides_in_handler)==sorted(new_slides_in_handler):
            return no_update
        else:
            new_slides = [new_slide_info[idx] for idx,i in enumerate(new_slides_in_handler) if not i in prev_slides_in_handler]
            rem_slides = [prev_slides_in_handler[idx] for idx,i in enumerate(prev_slides_in_handler) if not i in new_slides_in_handler]

            for s_idx,s in enumerate(current_vis_data['current']):
                if s['tiles_url'] in rem_slides:
                    del current_vis_data['current'][s_idx]
            
            current_vis_data['current'].extend(new_slides)

            return json.dumps(current_vis_data)




class DSAUploadType:
    """Formatted upload type for a DSAUploader Component.
    """
    def __init__(self,
                 name: str,
                 description: str,
                 input_files: list = [],
                 processing_plugins:Union[list,None] = None,
                 required_metadata: Union[list,None] = None):
        """Constructor method

        :param name: Name for this upload type (appears in dropdown menu in DSAUploader component)
        :type name: str
        :param input_files: List of dictionaries containing the following keys: name:str, description: str, accepted_types: Union[list,None], preprocessing_plugins: Union[list,None], main: bool, required: bool
        :type input_files: list
        :param processing_plugins: List of plugins to run after data has been uploaded. Allows for input of plugin-specific arguments after completion of file uploads., defaults to None
        :type processing_plugins: Union[list,None], optional
        :param required_metadata: List of "keys" which require user input either by uploading a file or by manual addition. Can either be a list of strings or a list of dicts with keys 'key':str,'values':list,'required':bool and strings (assumed required=True)
        :type required_metadata: Union[list,None], optional
        """
        
        self.name = name
        self.description = description

        # At least one element in input_files must contain 'main': True and 'required': True 
        # (just to ensure there has to be something uploaded and it has to at least be the main file)
        self.input_files = input_files
        self.processing_plugins = processing_plugins
        self.required_metadata = required_metadata

        # At a minimum, input files just has to contain at least one element, at least one "main" element (kept as individual item), and at least one "required" element
        # Other acceptable keys include "description", "accepted_types", "annotation", and "parent"
        assert len(self.input_files)>0
        assert any([i['main'] for i in self.input_files])
        assert any([i['required'] for i in self.input_files if i['main']])
        
        # Checking format of required_metadata (if it's a dictionary it has to have 'name'and 'required')
        if not self.required_metadata is None:
            req_meta_check = []
            for r in self.required_metadata:
                if type(r)==str:
                    req_meta_check.append(True)
                elif type(r)==dict:
                    req_meta_check.append(
                        all([i in r for i in ['name', 'required']])
                    )
        else:
            req_meta_check = [True]
            self.required_metadata = []

        assert all(req_meta_check)

        # All processing_plugins have to have a "dict" type
        assert all([isinstance(i,dict) for i in self.processing_plugins])



class DSAUploader(DSATool):
    """Handler for DSAUploader component, handling uploading data to a specific folder, adding metadata, and running sets of preprocessing plugins.

    :param DSATool: Sub-class of Tool specific to DSA components. Updates with session data by default.
    :type DSATool: None
    """
    def __init__(self,
                 handler: Union[DSAHandler,list] = [],
                 dsa_upload_types: Union[DSAUploadType,list] = []):
        

        super().__init__()
        self.handler = handler
        self.dsa_upload_types = dsa_upload_types

    def __str__(self):
        return 'DSA Uploader'

    def load(self,component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Dataset Uploader'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def update_layout(self, session_data:dict, use_prefix:bool):

        #TODO: Layout start:
        # Whether the upload is to a specific collection or to a User folder (Public/Private)
        # Selecting folder to upload to based on previous selection
        # Select which type of upload this is
        # Load upload type format based on DSAUploadType properties

        if not 'current_user' in session_data:
            uploader_children = html.Div(
                dbc.Alert(
                    'Make sure to login first in order to upload!',
                    color = 'warning'
                )
            )
   
        else:
            uploader_children = html.Div([
                dbc.Row([
                    dcc.Loading(
                        html.Div(
                            id = {'type': 'dsa-uploader-collection-or-user-div','index': 0},
                            children = [
                                html.Div(
                                    id = {'type': 'dsa-uploader-folder-nav-parent','index': 0},
                                    children = []
                                ),
                                dbc.Stack([
                                    dbc.Button(
                                        'Collection',
                                        n_clicks = 0,
                                        className = 'd-grid col-6 mx-auto',
                                        color = 'primary',
                                        id = {'type': 'dsa-uploader-collection-button','index': 0}
                                    ),
                                    dbc.Button(
                                        'User Folder',
                                        n_clicks = 0,
                                        className = 'd-grid col-6 mx-auto',
                                        color = 'secondary',
                                        id = {'type': 'dsa-uploader-user-folder-button','index': 0}
                                    )
                                ],direction = 'horizontal',gap = 3)
                            ]
                        )
                    ),
                    html.Div(
                        id = {'type': 'dsa-uploader-new-folder-div','index': 0},
                        children = []
                    ),
                    html.Div(
                        id = {'type': 'dsa-uploader-new-folder-error-div','index': 0},
                        children = []
                    )
                ]),
                html.Hr(),
                dbc.Row([
                    html.Div(
                        id = {'type': 'dsa-uploader-upload-type-div','index': 0},
                        children = []
                    )
                ]),
                html.Hr(),
                dbc.Row([
                    html.Div(
                        id = {'type': 'dsa-uploader-processing-plugins-div','index': 0},
                        children = []
                    )
                ])
            ])

        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Dataset Uploader')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Uploading slides and associated files to a particular folder on attached DSA instance. Access pre-processing plugins.'
                    ),
                    html.Hr(),
                    uploader_children
                ])
            )
        ],style = {'maxHeight': '90vh','overflow': 'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix=self.component_prefix).transform_layout(layout)

        return layout

    def gen_layout(self,session_data:Union[dict,None]):

        self.blueprint.layout = self.update_layout(session_data,use_prefix=False)
        
    def get_callbacks(self):

        # Callback for running processing plugin with inputs

        # Callback for selecting whether to upload to public/private collection or user public/private folder
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-collection-button','index': ALL},'n_clicks'),
                Input({'type': 'dsa-uploader-user-folder-button','index': ALL},'n_clicks'),
                Input({'type': 'dsa-uploader-folder-table','index': ALL},'selected_rows'),
                Input({'type': 'dsa-uploader-folder-crumb','index': ALL},'n_clicks'),
                Input({'type': 'dsa-uploader-folder-back-icon','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-uploader-folder-table','index': ALL},'data'),
                State({'type': 'dsa-uploader-folder-nav-parent','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-uploader-collection-or-user-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-folder-nav-parent','index': ALL},'children'),
                Output({'type': 'dsa-uploader-new-folder-div','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.populate_folder_div)

        # Callback for creating a new folder at a specific location
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-new-folder-button','index': ALL},'n_clicks'),
                Input({'type': 'dsa-uploader-new-folder-submit-button','index': ALL},'n_clicks'),
                Input({'type': 'dsa-uploader-new-folder-cancel-button','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-uploader-new-folder-input','index': ALL},'value'),
                State({'type': 'dsa-uploader-folder-nav-parent','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-uploader-new-folder-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-new-folder-error-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-folder-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-folder-nav-parent','index': ALL},'children'),
                Output({'type': 'dsa-uploader-new-folder-button','index': ALL},'disabled')
            ],
            prevent_initial_call = True
        )(self.populate_new_folder)

        # Callback for after selecting a folder to upload to, populating dropdown menu with provided upload types
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-select-folder','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-uploader-folder-nav-parent','index': ALL},'children')
            ],
            [
                Output({'type': 'dsa-uploader-upload-type-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-folder-nav-parent','index': ALL},'children'),
                Output({'type': 'dsa-uploader-new-folder-button','index': ALL},'disabled'),
                Output({'type': 'dsa-uploader-select-folder','index': ALL},'disabled'),
                Output({'type': 'dsa-uploader-folder-back-icon-div','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.populate_upload_type)

        # Callback for populating with DSAUploadType specifications
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-upload-type-drop','index': ALL},'value')
            ],
            [
                State({'type': 'dsa-uploader-folder-nav-parent','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-uploader-upload-type-description-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-upload-type-upload-files-div','index': ALL},'children')
            ]
        )(self.make_file_uploads)

        # Callback for incorrect type of file in upload component
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-file-upload','index': MATCH},'fileTypeFlag')
            ],
            [
                Output({'type': 'dsa-uploader-file-upload-status-div','index': MATCH},'children')
            ]
        )(self.wrong_file_type)

        # Callback for enabling "Done" button when all required files are uploaded
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-file-upload','index': ALL},'uploadComplete')
            ],
            [
                State({'type': 'dsa-uploader-upload-type-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'dsa-uploader-file-upload-div','index': ALL},'style'),
                Output({'type': 'dsa-uploader-file-upload-status-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-file-upload-done-button','index': ALL},'disabled')
            ],
            prevent_initial_call = True
        )(self.enable_upload_done)

        # Callback for populating processing-plugins div after "Done" button is clicked
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-file-upload-done-button','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-uploader-upload-type-drop','index': ALL},'value'),
                State({'type': 'dsa-uploader-folder-nav-parent','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-uploader-processing-plugins-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-upload-type-drop','index': ALL},'disabled'),
                Output({'type': 'dsa-uploader-file-upload-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-file-upload-done-button','index': ALL},'disabled')
            ],
            prevent_initial_call = True
        )(self.populate_processing_plugins)

        # Callback for checking if required metadata rows are populated
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-metadata-table','index': ALL},'data')
            ],
            [
                State({'type': 'dsa-uploader-upload-type-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'dsa-uploader-metadata-submit-button','index': ALL},'disabled')
            ]
        )(self.enable_submit_metadata)

        # Callback for adding new row to custom metadata table
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-metadata-table-add-row','index': MATCH},'n_clicks')
            ],
            [
                State({'type': 'dsa-uploader-metadata-table','index': MATCH},'data')
            ],
            [
                Output({'type': 'dsa-uploader-metadata-table','index': MATCH},'data')
            ]
        )(self.add_row_custom_metadata)

        # Callback for submitting metadata
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-metadata-submit-button','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-uploader-metadata-table','index': ALL},'data')
            ],
            [
                Output({'type': 'dsa-uploader-metadata-submit-status-div','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.submit_metadata)

        # Callback for running plugin
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-runner-submit-button','index': MATCH},'n_clicks')
            ],
            [
                State({'type': 'dsa-plugin-runner-input','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-runner-submit-status-div','index': MATCH},'children'),
                Output({'type': 'dsa-plugin-runner-submit-button','index': MATCH},'disabled')
            ]
        )(self.submit_plugin)

        # Callback for checking that all plugins have been submitted successfully


    def make_selectable_dash_table(self, dataframe:pd.DataFrame, id:dict, multi_row:bool = True, selected_rows: list = []):
        """Generate a selectable DataTable to add to the layout

        :param dataframe: Pandas DataFrame containing columns/rows of interest
        :type dataframe: pd.DataFrame
        :param id: Dictionary containing "type" and "index" keys for interactivity
        :type id: dict
        :param multi_row: Whether to allow selection of multiple rows in the table or just single, defaults to True
        :type multi_row: bool, optional
        :return: dash_table.DataTable component to be added to layout
        :rtype: dash_table.DataTable
        """

        #Optional: Can hide "ID" columns by adding any column containing "ID" to a list of "hidden_columns"

        dataframe = pd.json_normalize(dataframe.to_dict('records'))
        selectable_table = dash_table.DataTable(
            id = id,
            columns = [{'name':i,'id':i,'deletable':False} for i in dataframe.columns],
            data = dataframe.to_dict('records'),
            editable = False,
            filter_action='native',
            sort_action = 'native',
            sort_mode = 'multi',
            column_selectable = 'single',
            row_selectable = 'multi' if multi_row else 'single',
            row_deletable = False,
            selected_rows = selected_rows,
            page_action='native',
            page_current=0,
            page_size=10,
            style_cell = {
                'overflow':'hidden',
                'textOverflow':'ellipsis',
                'maxWidth':0                
            },
            tooltip_data = [
                {
                    column: {'value':str(value),'type':'markdown'}
                    for column, value in row.items()
                } for row in dataframe.to_dict('records')
            ],
            tooltip_duration = None
        )

        return selectable_table

    def organize_folder_contents(self, folder_info:dict, show_empty:bool=True, ignore_histoqc:bool=True)->list:
        """For a given folder selection, return a list of slides(0th) and folders (1th)

        :param folder_info: Folder info dict returned by self.handler.get_path_info(path)
        :type folder_info: dict
        :param show_empty: Whether or not to display folders which contain 0 slides, defaults to False
        :type show_empty: bool, optional
        :return: List of slides within the current folder as well as folders within that folder
        :rtype: list
        """

        folder_folders = []
        folder_slides = []

        # Starting with slides (which will report parent folderId but not that parent's folderId (if applicable))
        if folder_info['_modelType'] in ['folder','collection']:
            all_folder_slides = self.handler.get_folder_slides(
                folder_path = folder_info['_id'],
                folder_type = folder_info['_modelType'],
                ignore_histoqc=ignore_histoqc
            )

            folder_slides_folders = [i['folderId'] for i in all_folder_slides]
            unique_folders = list(set(folder_slides_folders))
            folders_in_folder = []
            for u in unique_folders:
                if not u==folder_info['_id'] and not u in folders_in_folder:
                    # This is for all folders in this folder
                    # This grabs parent folders of this folder
                    u_folder_info = self.handler.get_folder_info(folder_id=u)
                    u_folder_rootpath = self.handler.get_folder_rootpath(u)
                    # Folders in order from collection-->child folder-->etc.
                    folder_ids = [i['object']['_id'] for i in u_folder_rootpath]

                    if any([i['object']['_modelType']=='collection' for i in u_folder_rootpath]):
                        base_model = 'collection'
                    else:
                        base_model = 'user'

                    if folder_ids[-1]==folder_info['_id']:
                        child_folder_path = f'/{base_model}/'+'/'.join([i['object']['name'] if i['object']['_modelType'] in ['folder','collection'] else i['object']['login'] for i in u_folder_rootpath]+[u_folder_info['name']])
                    else:
                        # Folder that is immediate child of current folder:
                        child_folder_idx = folder_ids.index(folder_info['_id'])
                        child_folder_path = f'/{base_model}/'+'/'.join([i['object']['name'] if i['object']['_modelType'] in ['folder','collection'] else i['object']['login'] for i in u_folder_rootpath[:child_folder_idx+2]])


                    child_folder_path_info = self.handler.get_path_info(
                        path = child_folder_path
                    )
                    if not child_folder_path_info['_id'] in folders_in_folder:
                        folders_in_folder.append(child_folder_path_info['_id'])
                        
                        # Adding folder to list if the number of items is above zero or show_empty is True
                        folder_folders.append({
                            'Name': child_folder_path_info['name'],
                            'Folder ID': child_folder_path_info['_id'],
                            'Number of Folders': child_folder_path_info['nFolders'],
                            'Number of Slides': child_folder_path_info['nItems'],
                            'Last Updated': child_folder_path_info['updated']
                        } | child_folder_path_info['meta'])

                elif u==folder_info['_id']:
                    # This means that there are some slides that are direct children (not in a sub-folder) in this folder. 
                    # This adds them all at once
                    for i in all_folder_slides:
                        if i['folderId']==folder_info['_id']:
                            folder_slides.append(
                                {
                                    'Slide Name': i['name'],
                                    'Slide ID': i['_id'],
                                    'Last Updated':i['updated']
                                } | {k:v for k,v in i['meta'].items() if type(v)==str}
                            )

        else:
            
            user_folders = ['Private','Public']
            for u_f in user_folders:
                user_folder_info = self.handler.get_path_info(
                    path = f'/user/{folder_info["login"]}/{u_f}'
                )

                folder_folders.append({
                    'Name': user_folder_info['name'],
                    'Folder ID': user_folder_info['_id'],
                    'Number of Folders': user_folder_info['nFolders'],
                    'Number of Slides': user_folder_info['nItems'],
                    'Last Updated': user_folder_info['updated']
                })

        if show_empty:
            # This is how you get all the empty folders within a folder (does not get child empty folders)
            empty_folders = self.handler.get_folder_folders(
                folder_id = folder_info['_id'],
                folder_type = folder_info['_modelType']
            )
            
            for f in empty_folders:
                if not f['_id'] in folders_in_folder and not f['_id'] in unique_folders:
                    folder_info = self.handler.gc.get(f'/folder/{f["_id"]}/details')
                    folder_folders.append(
                        {
                            'Name': f['name'],
                            'Folder ID': f['_id'],
                            'Number of Folders': folder_info['nFolders'],
                            'Number of Slides': folder_info['nItems'],
                            'Last Updated': f['updated']
                        }
                    )


        return folder_slides, folder_folders

    def gen_collections_dataframe(self):
        """Generating dataframe containing current collections

        :return: Dataframe with each Collection
        :rtype: pd.DataFrame
        """
        collections_info = []
        collections = self.handler.get_collections()
        for c in collections:
            folder_count = self.handler.get_path_info(path = f'/collection/{c["name"]}')
            collections_info.append({
                'Name': c['name'],
                'ID': c['_id'],
                'Number of Folders': folder_count['nFolders'],
                'Last Updated': folder_count['updated']
            } | c['meta'])
            
        collections_df = pd.DataFrame.from_records(collections_info)

        return collections_df

    def extract_path_parts(self, current_parts:Union[list,dict], search_key: list = ['props','children'])->tuple:
        """Recursively extract pieces of folder paths stored as clickable components.

        :param current_parts: list or dictionary containing html.A or dbc.Stack of html.A components.
        :type current_parts: Union[list,dict]
        :param search_key: Property keys to search for in nested dicts, defaults to ['props','children']
        :type search_key: list, optional
        :return: Tuple containing all the parts of the folder path
        :rtype: tuple
        """
        path_pieces = ()
        if type(current_parts)==list:
            for c in current_parts:
                if type(c)==dict:
                    for key,value in c.items():
                        if key in search_key:
                            if type(value)==str:
                                path_pieces += (value,)
                            elif type(value) in [list,dict]:
                                path_pieces += self.extract_path_parts(value)
                elif type(c)==list:
                    path_pieces += self.extract_path_parts(c)
        elif type(current_parts)==dict:
            for key,value in current_parts.items():
                if key in search_key:
                    if type(value)==str:
                        path_pieces += (value,)
                    elif type(value) in [list,dict]:
                        path_pieces += self.extract_path_parts(value)

        return path_pieces

    def get_clicked_part(self, current_parts: Union[list,dict])->list:
        """Get the "n_clicks" value for components which have "id". If they have "id" but not "n_clicks", assign 0

        :param current_parts: Either a list or dictionary containing components
        :type current_parts: Union[list,dict]
        :return: List of values corresponding to "n_clicks" 
        :rtype: list
        """
        
        n_clicks_list = []
        if type(current_parts)==list:
            for c in current_parts:
                if type(c)==dict:
                    if 'id' in list(c.keys()):
                        if 'n_clicks' in list(c.keys()):
                            n_clicks_list.append(c['n_clicks'])
                        else:
                            n_clicks_list.append(0)
                    else:
                        for key,value in c.items():
                            if key=='props':
                                n_clicks_list += self.get_clicked_part(value)
                            elif key=='n_clicks':
                                n_clicks_list.append(value)
                elif type(c)==list:
                    n_clicks_list += self.get_clicked_part(c)
        elif type(current_parts)==dict:
            if 'id' in list(current_parts.keys()):
                if 'n_clicks' in list(current_parts.keys()):
                    n_clicks_list.append(current_parts['n_clicks'])
                else:
                    n_clicks_list.append(0)
            else:
                for key,value in current_parts.items():
                    if type(value)==dict:
                        if key=='props':
                            n_clicks_list += self.get_clicked_part(value)
                        elif key=='n_clicks':
                            n_clicks_list.append(value)
                    elif type(value)==list:
                        n_clicks_list += self.get_clicked_part(value)

        return n_clicks_list

    def gen_metadata_table(self, required_metadata: list):
        
        dict_items = [i for i in required_metadata if type(i)==dict]
        dropdown_rows = [i for i in dict_items if type(i['values'])==list]
        free_rows = [{'name':i,'required': False} for i in required_metadata if type(i)==str]

        table_list = []
        for m_idx,m in enumerate([dropdown_rows,free_rows]):
            m_df = pd.DataFrame.from_records([
                {'Key': i['name'],'Value': '','row_id': idx}
                for idx,i in enumerate(m)
            ])
            required_rows = [r_idx for r_idx,r in enumerate(m) if r['required']]

            metadata_table = dash_table.DataTable(
                id = {'type': f'{self.component_prefix}-dsa-uploader-metadata-table','index': m_idx},
                data = m_df.to_dict('records'),
                columns = [
                    {'id': 'Key','name': 'Key'},
                    {'id': 'Value','name': 'Value','presentation': 'dropdown'} if m_idx==0 else {'id': 'Value','name':'Value'}
                ],
                editable = True,
                style_data_conditional = [
                    {
                        'if': {
                            'row_index': required_rows
                        },
                        'border': '2px solid rgb(255,0,0)'
                    }
                ],
                dropdown_conditional = [
                    {
                        'if': {
                            'column_id': 'Value',
                            'filter_query': '{row_id} eq '+str(k)
                        },
                        'options': [
                            {'label': l, 'value': l}
                            for l in m[k]['values']
                        ]
                    }
                    for k in range(len(m))
                ] if m_idx==0 else [],
                page_current = 0,
                page_size = 10,
                tooltip_data = [
                    {
                        column:{'value':str(value), 'type':'markdown'}
                        for column,value in row.items()
                    } for row in m_df.to_dict('records')
                ],
                tooltip_duration = None,
                css=[{"selector": ".Select-menu-outer", "rule": "display: block !important"}]
            )
            table_list.append(metadata_table)

        # Creating a "Custom Metadata" table where you can add rows
        custom_metadata_table = dbc.Stack([
            dash_table.DataTable(
                id = {'type': f'{self.component_prefix}-dsa-uploader-metadata-table','index': m_idx+1},
                data = [
                    {'Key': '', 'Value': ''}
                ], 
                columns = [
                    {'id': 'Key', 'name': 'Key'},
                    {'id': 'Value', 'name': 'Value'}
                ],
                editable = True,
                row_deletable = True,
                page_current = 0,
                page_size = 10,
                tooltip_data = [
                    {
                        column:{'value':str(value), 'type':'markdown'}
                        for column,value in row.items()
                    } for row in m_df.to_dict('records')
                ],
                tooltip_duration = None
            ),
            dbc.Button(
                'Add Row',
                className = 'd-grid col-12 mx-auto',
                color = 'success',
                n_clicks = 0,
                id = {'type': f'{self.component_prefix}-dsa-uploader-metadata-table-add-row','index': m_idx+1}
            )
        ],direction='vertical',gap=2)

        table_list.append(custom_metadata_table)
        

        return table_list
    
    def populate_folder_div(self, collection_clicked, user_clicked, folder_table_rows, folder_crumb, back_clicked, folder_table_data, folder_crumb_parent,session_data):
        """Generate the collection/user folder div.

        :param collection_clicked: Whether "Collection" was clicked
        :type collection_clicked: list
        :param user_clicked: Whether "User" was clicked
        :type user_clicked: list
        :param folder_table_rows: Which rows in the folder table were clicked (all set to multi_row=False).
        :type folder_table_rows: list
        :param folder_crumb: Whether a part of the file path was clicked.
        :type folder_crumb: list
        :param back_clicked: Whether the back arrow as clicked.
        :type back_clicked: list
        :param folder_table_data: The current row data in the folder table.
        :type folder_table_data: list
        :param folder_crumb_parent: The parent container of all the folder path parts.
        :type folder_crumb_parent: list
        :param session_data: Current visualization session data
        :type session_data: list
        """

        path_parts = list(self.extract_path_parts(get_pattern_matching_value(folder_crumb_parent)))
        session_data = json.loads(session_data)
        folder_table_rows = get_pattern_matching_value(folder_table_rows)
        folder_table_data = get_pattern_matching_value(folder_table_data)

        if not ctx.triggered_id:
            raise exceptions.PreventUpdate

        if 'dsa-uploader-collection-button' in ctx.triggered_id['type']:
            
            if not any([i['value'] for i in ctx.triggered]):
                raise exceptions.PreventUpdate

            collection_df = self.gen_collections_dataframe()
            folder_table_div = html.Div([
                html.Div(
                    children = self.make_selectable_dash_table(
                        dataframe = collection_df,
                        id = {'type': f'{self.component_prefix}-dsa-uploader-folder-table','index': 0},
                        multi_row = False,
                        selected_rows = []
                    ),
                    id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                )
            ])

            path_parts = ['/collection/']
        
        elif 'dsa-uploader-user-folder-button' in ctx.triggered_id['type']:
            if not any([i['value'] for i in ctx.triggered]):
                raise exceptions.PreventUpdate
            
            user_folder_df = pd.DataFrame.from_records([
                {
                    'Name': i
                }
                for i in ['Private','Public']
            ])
            folder_table_div = html.Div([
                html.Div(
                    children = self.make_selectable_dash_table(
                        dataframe=user_folder_df,
                        id = {'type': f'{self.component_prefix}-dsa-uploader-folder-table','index': 0},
                        multi_row = False,
                        selected_rows = []
                    ),
                    id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                )
            ])

            path_parts = ['/user/',f'{session_data["current_user"]["login"]}/']

        elif 'dsa-uploader-folder-table' in ctx.triggered_id['type']:
            
            if not any([i['value'] for i in ctx.triggered]):
                raise exceptions.PreventUpdate
            
            path_parts = path_parts+[folder_table_data[folder_table_rows[0]]['Name']+'/']

            folder_info = self.handler.get_path_info(
                    path = ''.join(path_parts)[:-1]
                )

            # Don't need to know the slides in that folder
            _, folder_folders = self.organize_folder_contents(
                folder_info=folder_info
            )

            if len(folder_folders)>0:
                folder_table_div = html.Div([
                    html.Div(
                        children = self.make_selectable_dash_table(
                            dataframe = pd.DataFrame.from_records(folder_folders),
                            id = {'type': f'{self.component_prefix}-dsa-uploader-folder-table','index': 0},
                            multi_row = False,
                            selected_rows=[]
                        ),
                        id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                    ),
                    html.Hr(),
                        dbc.Stack([
                            dbc.Button(
                                'Create New Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'primary',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-button','index': 0}
                            ),
                            dbc.Button(
                                'Upload to this Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'success',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-select-folder','index': 0}
                            )
                        ],direction='horizontal',gap = 1)
                ])
            else:
                folder_table_div = html.Div([
                    html.Div(
                        children = dbc.Alert('This folder contains no more folders',color='warning'),
                        id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                    ),
                    html.Hr(),
                        dbc.Stack([
                            dbc.Button(
                                'Create New Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'primary',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-button','index': 0}
                            ),
                            dbc.Button(
                                'Upload to this Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'success',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-select-folder','index': 0}
                            )
                        ],direction='horizontal',gap = 1)
                ])
        
        elif 'dsa-uploader-folder-crumb' in ctx.triggered_id['type']:

            n_clicks = self.get_clicked_part(folder_crumb_parent)
            n_click_idx = np.argmax(n_clicks)

            if sum(n_clicks)==0:
                raise exceptions.PreventUpdate

            if n_click_idx==len(path_parts)-1:
                folder_table_div = html.Div([
                    html.Div(
                        children = self.make_selectable_dash_table(
                            dataframe = pd.DataFrame.from_records(folder_table_data),
                            id = {'type': f'{self.component_prefix}-dsa-uploader-folder-table','index': 0},
                            multi_row = False,
                            selected_rows = []
                        ),
                        id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                    ) if not folder_table_data is None else 
                    html.Div(
                        children = dbc.Alert('This folder contains no more folders',color='warning'),
                        id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                    ),
                    html.Hr(),
                        dbc.Stack([
                            dbc.Button(
                                'Create New Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'primary',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-button','index': 0}
                            ),
                            dbc.Button(
                                'Upload to this Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'success',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-select-folder','index': 0}
                            )
                        ],direction='horizontal',gap = 1)
                ])

                path_parts = path_parts[:-1]

            elif n_click_idx>0:

                path_parts = path_parts[:n_click_idx+1]
                folder_info = self.handler.get_path_info(
                    path = ''.join(path_parts)[:-1]
                )

                if not path_parts==['/user/',session_data['current_user']['login']+'/']:
                    # Don't need to know the slides in that folder
                    _, folder_folders = self.organize_folder_contents(
                        folder_info=folder_info
                    )
                else:
                    folder_folders = [
                        {
                            'Name': i
                        }
                        for i in ['Private','Public']
                    ]


                if len(folder_folders)>0:
                    folder_table_div = html.Div([
                        html.Div(
                            children = self.make_selectable_dash_table(
                                dataframe = pd.DataFrame.from_records(folder_folders),
                                id = {'type': f'{self.component_prefix}-dsa-uploader-folder-table','index': 0},
                                multi_row = False,
                                selected_rows=[]
                            ),
                            id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                        ),
                        html.Hr(),
                        dbc.Stack([
                            dbc.Button(
                                'Create New Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'primary',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-button','index': 0}
                            ),
                            dbc.Button(
                                'Upload to this Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'success',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-select-folder','index': 0}
                            )
                        ],direction='horizontal',gap = 1)
                    ])
                else:
                    folder_table_div = html.Div([
                        html.Div(
                            children = dbc.Alert('This folder contains no more folders',color='warning'),
                            id = {'type':f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                        ),
                        html.Hr(),
                        dbc.Stack([
                            dbc.Button(
                                'Create New Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'primary',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-button','index': 0}
                            ),
                            dbc.Button(
                                'Upload to this Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'success',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-select-folder','index': 0}
                            )
                        ],direction='horizontal',gap = 1)
                    ])

            elif n_click_idx==0:
                path_parts = path_parts[0]

                if path_parts == '/collection/':
                    folder_folders = self.gen_collections_dataframe().to_dict('records')
                elif path_parts =='/user/':
                    folder_folders = [
                        {
                            'Name': i['login']
                        }
                        for i in self.handler.gc.get(f'/user?token={session_data["current_user"]["token"]}')
                    ]

                if len(folder_folders)>0:
                    folder_table_div = html.Div([
                        html.Div(
                            children = self.make_selectable_dash_table(
                                dataframe = pd.DataFrame.from_records(folder_folders),
                                id = {'type': f'{self.component_prefix}-dsa-uploader-folder-table','index': 0},
                                multi_row = False,
                                selected_rows=[]
                            ),
                            id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                        ),
                        html.Hr(),
                        dbc.Stack([
                            dbc.Button(
                                'Create New Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'primary',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-button','index': 0}
                            ),
                            dbc.Button(
                                'Upload to this Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'success',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-select-folder','index': 0}
                            )
                        ],direction='horizontal',gap = 1)
                    ])
                else:
                    folder_table_div = html.Div([
                        html.Div(
                            children = dbc.Alert('This folder contains no more folders',color='warning'),
                            id = {'type': f'{self.component_prefix}-dsa-uploader-folder-div','index': 0}
                        ),
                        html.Hr(),
                        dbc.Stack([
                            dbc.Button(
                                'Create New Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'primary',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-button','index': 0}
                            ),
                            dbc.Button(
                                'Upload to this Folder',
                                className = 'd-grid col-6 mx-auto',
                                color = 'success',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-select-folder','index': 0}
                            )
                        ],direction='horizontal',gap = 1)
                    ])

        elif 'dsa-uploader-folder-back-icon' in ctx.triggered_id['type']:

            collection_or_user_div_children = [
                html.Div(
                    id = {'type': f'{self.component_prefix}-dsa-uploader-folder-nav-parent','index': 0},
                    children = []
                ),
                dbc.Stack([
                    dbc.Button(
                        'Collection',
                        n_clicks = 0,
                        className = 'd-grid col-6 mx-auto',
                        color = 'primary',
                        id = {'type': f'{self.component_prefix}-dsa-uploader-collection-button','index': 0}
                    ),
                    dbc.Button(
                        'User Folder',
                        n_clicks = 0,
                        className = 'd-grid col-6 mx-auto',
                        color = 'secondary',
                        id = {'type': f'{self.component_prefix}-dsa-uploader-user-folder-button','index': 0}
                    )
                ],direction = 'horizontal',gap = 3)
            ]

            return [collection_or_user_div_children], [html.Div()], [html.Div()]

        new_crumbs = []
        for i in path_parts:
            new_crumbs.append(
                html.A(
                    i,
                    id = {'type': f'{self.component_prefix}-dsa-uploader-folder-crumb','index': 0},
                    style = {'color': 'rgb(0,0,255)'}
                )
            )

        collection_or_user_div_children = html.Div([
            html.Div(
                html.A(
                    children = dbc.Stack([
                        html.P(
                            html.I(
                                className = 'fa-solid fa-arrow-left',
                                style = {'marginRight': '2px'}
                            )
                        ),
                        html.P(
                            'Back'
                        )
                    ],direction = 'horizontal'),
                    n_clicks = 0,
                    id = {'type': f'{self.component_prefix}-dsa-uploader-folder-back-icon','index': 0}
                ),
                id = {'type': f'{self.component_prefix}-dsa-uploader-folder-back-icon-div','index': 0}
            ),
            html.H5(
                children = [
                    dbc.Stack(new_crumbs,direction='horizontal',gap=1)
                ],
                id = {'type': f'{self.component_prefix}-dsa-uploader-folder-nav-parent','index': 0},
                style = {'textTransform': 'none','display': 'inline'}
            ),
            html.Hr(),
            folder_table_div
        ])

        # Clearing the new folder div
        new_folder_div = html.Div()

        return [collection_or_user_div_children], [new_crumbs], [new_folder_div]
    
    def populate_new_folder(self, create_clicked, submit_clicked, cancel_clicked, new_folder_name, parent_path, session_data):
        """Callback for creating a new folder at a specific location.

        :param create_clicked: Whether Create Folder was clicked
        :type create_clicked: list
        :param submit_clicked: Whether Submit folder was clicked
        :type submit_clicked: list 
        :param cancel_clicked: Whether Cancel was clicked
        :type cancel_clicked: list                 
        :param new_folder_name: Name of new folder
        :type new_folder_name: list
        :param parent_path: Parent of folder path parts
        :type parent_path: list
        :param session_data: Current Visualization Session data
        :type session_data: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)

        if 'dsa-uploader-new-folder-button' in ctx.triggered_id['type']:

            folder_table_div = no_update
            new_path_parts = no_update
            new_folder_disable = True

            new_folder_div = html.Div([
                dbc.InputGroup([
                    dbc.InputGroupText(
                        'Folder Name: '
                    ),
                    dbc.Input(
                        id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-input','index': 0},
                        placeholder = 'fusion-tools Upload',
                        type = 'text',
                        required = True,
                        value = [],
                        maxLength = 1000,
                    ),
                    dbc.Button(
                        'Create Folder!',
                        color = 'primary',
                        n_clicks = 0,
                        id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-submit-button','index': 0}
                    ),
                    dbc.Button(
                        'Cancel',
                        color = 'danger',
                        n_clicks = 0,
                        id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-cancel-button','index': 0}
                    )
                ])
            ],style = {'marginTop':'10px'})

            error_div = []

        elif 'dsa-uploader-new-folder-submit-button' in ctx.triggered_id['type']:

            folder_path = list(self.extract_path_parts(get_pattern_matching_value(parent_path)))
            folder_name = get_pattern_matching_value(new_folder_name)

            try:
                new_folder_info = self.handler.create_user_folder(
                    parent_path = ''.join(folder_path)[:-1],
                    folder_name = folder_name,
                    user_token=session_data['current_user']['token']
                )
            except Exception as e:
                print('Some error encountered in creating the folder')
                print(f'Status Code: {e.status_code}')
                print(e.json())
                new_folder_info = {'ok':False}
                error_div = dbc.Alert(f'Error creating folder at: {"".join(folder_path)+folder_name}',color='danger')

            if new_folder_info.ok and new_folder_info.status_code==200:
                error_div = dbc.Alert(f'Success!',color = 'success')
                new_folder_disable = False

                new_path_parts = []
                for i in folder_path+[folder_name]:
                    new_path_parts.append(
                        html.A(
                            i,
                            id = {'type': f'{self.component_prefix}-dsa-uploader-folder-crumb','index': 0},
                            style = {'color': 'rgb(0,0,255)'}
                        )
                    )

                new_path_parts = dbc.Stack(new_path_parts,direction='horizontal',gap=1)

                new_folder_div = html.Div([
                    dbc.InputGroup([
                        dbc.InputGroupText(
                            'Folder Name: '
                        ),
                        dbc.Input(
                            id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-input','index': 0},
                            placeholder = 'fusion-tools Upload',
                            type = 'text',
                            required = True,
                            value = folder_name,
                            maxLength = 1000,
                            disabled=True
                        ),
                        dbc.Button(
                            'Create Folder!',
                            color = 'success',
                            disabled = True,
                            n_clicks = 0,
                            id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-submit-button','index': 0}
                        ),
                        dbc.Button(
                            'Cancel',
                            color = 'danger',
                            disabled = True,
                            n_clicks = 0,
                            id = {'type': f'{self.component_prefix}-dsa-uploader-new-folder-cancel-button','index': 0}
                        )
                    ])
                ],style = {'marginTop':'10px'})

                folder_table_div = html.Div([
                    dbc.Alert('This folder contains no more folders',color = 'warning')
                ])

            else:
                new_path_parts = no_update
                new_folder_div = no_update
                folder_table_div = no_update
                new_folder_disable = True

                error_div = dbc.Alert(f'Error creating folder at: {"".join(folder_path)+folder_name}',color='danger')

        elif 'dsa-uploader-new-folder-cancel-button' in ctx.triggered_id['type']:
            new_folder_div = html.Div()
            error_div = []
            folder_table_div = no_update
            new_path_parts = no_update
            new_folder_disable = False


        return [new_folder_div], [error_div], [folder_table_div], [new_path_parts], [new_folder_disable]

    def populate_upload_type(self, select_clicked,path_parts):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        upload_div_contents = html.Div([
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader('Available Upload Types'),
                        dbc.CardBody([
                            html.Div([
                                #html.P('Different data types require different sets and types of files in order to have sufficient information for visualization and analysis'),
                                #html.B(),
                                html.H5('Select the type of data you would like to upload from the menu below'),
                                html.Hr(),
                                dcc.Dropdown(
                                    options = [
                                        {
                                            'label': i.name, 'value': i.name
                                        }
                                        for i in self.dsa_upload_types
                                    ],
                                    value = [],
                                    placeholder='Selected Upload Type',
                                    id = {'type': f'{self.component_prefix}-dsa-uploader-upload-type-drop','index': 0}
                                ),
                                html.B(),
                                html.Div(
                                    id = {'type': f'{self.component_prefix}-dsa-uploader-upload-type-description-div','index': 0},
                                    children = []
                                )
                            ],style = {'height': '30vh','maxHeight': '40vh','overflow': 'scroll'})
                        ])
                    ])
                ],md = 4),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader('Upload Files'),
                        dbc.CardBody([
                            html.Div(
                                id = {'type': f'{self.component_prefix}-dsa-uploader-upload-type-upload-files-div','index': 0},
                                children = [],
                                style = {'maxHeight': '40vh','overflow': 'scroll'}
                            )
                        ])
                    ])
                ])
            ])
        ])

        path_parts = list(self.extract_path_parts(get_pattern_matching_value(path_parts)))
        disabled_path_parts = []
        for p in path_parts:
            disabled_path_parts.append(
                html.P(p)
            )
        
        disabled_path_parts = dbc.Stack(
            disabled_path_parts,
            direction = 'horizontal'
        )

        back_icon_children = dbc.Stack([
                html.P(
                    html.I(
                        className = 'fa-solid fa-arrow-left',
                        style = {'marginRight': '2px'}
                    )
                ),
                html.P(
                    'Back'
                )
            ],direction = 'horizontal'
        )

        new_folder_disable = True
        select_folder_disable = True

        return [upload_div_contents], [disabled_path_parts], [new_folder_disable], [select_folder_disable], [back_icon_children]

    def make_file_uploads(self, upload_type_value, upload_folder_path, session_data):
        """Making the file upload components for the selected UploadType

        :param upload_type_value: Selected UploadType from the dropdown menu
        :type upload_type_value: list
        :param upload_folder_path: Folder path to upload to
        :type upload_folder_path: list
        :param session_data: Current visualization session data
        :type session_data: str
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        upload_type_value = get_pattern_matching_value(upload_type_value)

        upload_path_parts = self.extract_path_parts(get_pattern_matching_value(upload_folder_path))
        folder_info = self.handler.get_path_info(
            path = ''.join(upload_path_parts)[:-1]
        )

        selected_upload_type = self.dsa_upload_types[[i.name for i in self.dsa_upload_types].index(upload_type_value)]

        file_uploads = html.Div([
            dbc.Stack([
                html.Div([
                    html.H5(f'{f["name"]}, ({",".join(f["accepted_types"])})'),
                    html.Div(
                        UploadComponent(
                            id = {'type': f'{self.component_prefix}-dsa-uploader-file-upload','index': f_idx},
                            uploadComplete=False,
                            baseurl=self.handler.gc.urlBase,
                            girderToken= session_data['current_user']['token'],
                            parentId = folder_info['_id'],
                            filetypes = f['accepted_types'] if 'accepted_types' in f else []
                        ),
                        id = {'type': f'{self.component_prefix}-dsa-uploader-file-upload-div','index': f_idx}
                    ),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-dsa-uploader-file-upload-status-div','index': f_idx},
                        children = []
                    ),
                    html.P(f['description'] if 'description' in f else '')
                ])
                for f_idx,f in enumerate(selected_upload_type.input_files)
            ]),
            dbc.Row([
                dbc.Col(
                    html.Div(
                        dbc.Button(
                            'Done!',
                            className = 'd-grid col-4 mx-auto',
                            n_clicks = 0,
                            color = 'success',
                            disabled = True,
                            id = {'type': f'{self.component_prefix}-dsa-uploader-file-upload-done-button','index': 0}
                        )
                    )
                )
            ],align='right')
        ])

        upload_type_description = html.P(selected_upload_type.description)

        return [upload_type_description], [file_uploads]

    def wrong_file_type(self, wrong_file_flag):
        """Callback triggered if an attempt is made to upload a file that is not in the accepted types list

        :param wrong_file_flag: Wrong file type is triggered
        :type wrong_file_flag: bool
        """
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        wrong_file_alert = dbc.Alert('Incorrect file type!',color = 'danger')

        return wrong_file_alert

    def enable_upload_done(self, uploads_complete, upload_type):
        """Enabling the "Done" button when all required uploads are uploaded

        :param uploads_complete: Current uploadComplete flags from active UploadComponents
        :type uploads_complete: list
        :param upload_type: Selected type of upload
        :type upload_type: list
        """
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        upload_type = get_pattern_matching_value(upload_type)
        selected_upload_type = self.dsa_upload_types[[i.name for i in self.dsa_upload_types].index(upload_type)]

        success_divs = []
        upload_div_style = []
        for u in uploads_complete:
            if u:
                success_divs.append(
                    dbc.Alert('Success!',color = 'success')
                )
                upload_div_style.append(
                    {'display': 'none'}
                )
            else:
                success_divs.append(no_update)
                upload_div_style.append(no_update)

        required_uploads_done = []
        for idx,i in enumerate(selected_upload_type.input_files):
            if i['required']:
                if uploads_complete[idx]:
                    required_uploads_done.append(True)
                else:
                    required_uploads_done.append(False)
            else:
                required_uploads_done.append(True)

        if all(required_uploads_done):
            return upload_div_style,success_divs,[False]
        else:
            return upload_div_style,success_divs,[True]
        
    def populate_processing_plugins(self, done_clicked,upload_type,path_parts,session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        upload_type = get_pattern_matching_value(upload_type)
        selected_upload_type = self.dsa_upload_types[[i.name for i in self.dsa_upload_types].index(upload_type)]

        path_parts = self.extract_path_parts(get_pattern_matching_value(path_parts))
        path_info = self.handler.get_path_info(
            path = ''.join(path_parts)[:-1]
        )
        session_data = json.loads(session_data)

        metadata_table_list = self.gen_metadata_table(selected_upload_type.required_metadata)
        any_required = [i for i in selected_upload_type.required_metadata if type(i)==dict]
        any_required = any([i['required'] for i in any_required if 'required' in i])

        # Getting input components for the processing plugins
        plugin_components = []
        plugin_handler = DSAPluginRunner(
            handler = self.handler
        )
        for p_idx,p in enumerate(selected_upload_type.processing_plugins):
            p_component = plugin_handler.load_plugin(
                plugin_dict = p,
                session_data = session_data,
                component_index = p_idx
            )
            PrefixIdTransform(prefix = self.component_prefix).transform_layout(p_component)

            plugin_components.append(p_component)


        processing_plugin_div = html.Div([
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader('Required Metadata'),
                        dbc.CardBody([
                            html.P('Add any required metadata below: '),
                            html.Hr(),
                            dbc.Stack(metadata_table_list,direction='vertical',style = {'marginBottom':'5px'}),
                            html.B(),
                            dbc.Button(
                                'Submit Metadata',
                                className = 'd-grid col-12 mx-auto',
                                n_clicks = 0,
                                color = 'success',
                                disabled = any_required,
                                id = {'type': f'{self.component_prefix}-dsa-uploader-metadata-submit-button','index': 0}
                            ),
                            html.Div(
                                id = {'type': f'{self.component_prefix}-dsa-uploader-metadata-submit-status-div','index': 0},
                                children = []
                            )
                        ])
                    ])
                ],md = 6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader('Processing Plugins'),
                        dbc.CardBody([
                            html.Div(
                                dmc.Accordion(
                                    id = {'type': f'{self.component_prefix}-dsa-uploader-plugin-accordion','index': 0},
                                    children = [
                                        dmc.AccordionItem([
                                            dmc.AccordionControl(p_name['name']),
                                            dmc.AccordionPanel(
                                                dbc.Stack([
                                                    p_component,
                                                    html.Div(
                                                        id = {'type': f'{self.component_prefix}-dsa-plugin-runner-submit-status-div','index': p_idx},
                                                        children = []
                                                    )
                                                ])
                                            )
                                        ],value = f'dsa-uploader-plugin-{p_idx}')
                                        for p_idx,(p_name,p_component) in enumerate(zip(selected_upload_type.processing_plugins,plugin_components))
                                    ]
                                )
                            )
                        ])
                    ])
                ],md = 6)
            ])
        ])

        upload_type_disable = True
        file_upload_divs = [dbc.Alert('Done Uploading',color = 'secondary')]*len(ctx.outputs_list[2])
        done_button_disable = True

        return [processing_plugin_div], [upload_type_disable], file_upload_divs, [done_button_disable]
    
    def enable_submit_metadata(self, all_table_data, upload_type):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        upload_type = get_pattern_matching_value(upload_type)
        selected_upload_type = self.dsa_upload_types[[i.name for i in self.dsa_upload_types].index(upload_type)]

        # Getting which metadata fields are required
        required_metadata = [i for i in selected_upload_type.required_metadata if type(i)==dict]
        required_metadata= [i['name'] for i in required_metadata if i['required']]

        req_meta_check = []
        for t in all_table_data:
            for d in t:
                if d['Key'] in required_metadata:
                    req_meta_check.append(not d['Value']=='')
        
        submit_disable = not all(req_meta_check)

        return [submit_disable]

    def add_row_custom_metadata(self, clicked, custom_metadata):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        # Just appending a new blank row to the current data
        custom_metadata.append(
            {'Key': '', 'Value': ''}
        )

        return custom_metadata

    def submit_metadata(self, clicked, tables_data):
        
        # This button being "clickable" means that all required metadata fields are already input
        metadata_json = []
        for t in tables_data:
            metadata_json.extend([
                {i['Key']:i['Value']}
                for i in t
            ])

        #TODO: Have to get the "main" item to which the metadata is added 
        # (what to do if there are multiple "main" items?? Should that not be allowed?)
        success = self.handler.add_metadata(
            item = '',
            metadata = metadata_json
        )
        
        if success:
            status_div = dbc.Alert('Metadata added!',color = 'success')
        else:
            status_div = dbc.Alert(f'Error adding metadata to item: {""}',color='danger')

        return [status_div]

    def submit_plugin(self, clicked, docker_select, cli_select, plugin_inputs,session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        plugin_list = self.handler.list_plugins()
        docker_select = get_pattern_matching_value(docker_select)
        included_cli = [i for i in plugin_list if i['image']==docker_select]

        cli_select = get_pattern_matching_value(cli_select)
        selected_plugin = [i for i in included_cli if i['name']==cli_select][0]

        session_data = json.loads(session_data)

        plugin_cli_dict = self.get_executable_dict(selected_plugin,session_data)
        plugin_input_infos = []
        for p in plugin_cli_dict['parameters']:
            plugin_input_infos.extend(p['input_list'])

        input_dict = {}
        for input_info, input_value in zip(plugin_input_infos,plugin_inputs):
            input_dict[input_info['name']] = input_value

        submit_request = self.run_plugin_request(
            plugin_id = selected_plugin['_id'],
            session_data=session_data,
            input_params_dict = input_dict
        )

        if submit_request.status_code==200:
            status_div = dbc.Alert('Plugin successfully submitted!',color='success')
            button_disable = True
        else:
            status_div = dbc.Alert(f'Error submitting plugin: {selected_plugin["_id"]}',color = 'danger')
            button_disable = False

        return status_div, button_disable




class DSAPluginRunner(Tool):
    """Handler for DSAPluginRunner component, letting users specify input arguments to plugins to run on connected DSA instance.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self,
                 handler: DSAHandler):
        
        super().__init__()
        self.handler = handler
        self.parameter_tags = ['integer','float','double','boolean','string','integer-vector','float-vector','double-vector','string-vector',
                        'integer-enumeration','float-enumeration','double-enumeration','string-enumeration','file','directory','image',
                        'geometry','point','pointfile','region','table','transform']

    def load(self, component_prefix: int):
        
        self.component_prefix = component_prefix

        self.title = 'DSA Plugin Runner'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def get_executable_dict(self, plugin_info,session_data):
        
        exe_dict = None
        plugin_cli = None
        plugin_list = self.handler.list_plugins(user_token=session_data['current_user']['token'])

        for p in plugin_list:
            if p['image']==plugin_info['image'] and p['name']==plugin_info['name']:
                plugin_cli = p
                break

        if plugin_cli:
            plugin_xml_req = requests.get(
                self.handler.gc.urlBase+f'slicer_cli_web/cli/{plugin_cli["_id"]}/xml?token={session_data["current_user"]["token"]}'
            )
            if plugin_xml_req.status_code==200:
                plugin_xml = ET.fromstring(plugin_xml_req.content)
                exe_dict = self.parse_executable(plugin_xml)

        return exe_dict

    def load_plugin(self, plugin_dict, session_data, component_index):

        # Each plugin_dict will have 'name', 'image', and 'input_args'
        # 'name' and 'image' are used to identify the CLI
        # 'input_args' is a list of either strings or dictionaries limiting which arguments the user can adjust

        # Getting plugin xml (have to be logged in to get)
        cli_dict = self.get_executable_dict(plugin_dict,session_data)
        if cli_dict is None:
            return dbc.Alert(f'Error loading plugin: {plugin_dict}',color = 'danger')

        if 'input_args' in plugin_dict:
            # Parsing through the provided input_args and pulling them out of the plugin parameters
            inputs_list = []
            for in_arg in plugin_dict['input_args']:
                if type(in_arg)==str:
                    # Looking for the input with this name and setting default from input (if specified)
                    exe_input = self.find_executable_input(cli_dict, in_arg)

                elif type(in_arg)==dict:
                    # Looking for the input with in_arg['name'] and setting default from in_arg
                    exe_input = self.find_executable_input(cli_dict,in_arg['name'])
                    if 'default' in in_arg:
                        exe_input['default'] = in_arg['default']

                else:
                    raise TypeError
                
                inputs_list.append(exe_input)
        else:
            inputs_list = []
            for p in cli_dict['parameters']:
                inputs_list.extend(p['inputs'])

        # Now creating the interactive component (without component-prefix, (can transform later))
        plugin_component = html.Div([
            dbc.Row([
                html.H5(html.A(cli_dict['title'],target='_blank',href=cli_dict['documentation']))
            ]),
            html.Hr(),
            dbc.Row([
                cli_dict['description']
            ]),
            dbc.Row([
                dmc.AvatarGroup(
                    children = [
                        dmc.Tooltip(
                            dmc.Avatar(
                                ''.join([n[0] for n in author.split() if not n[0] in ['(',')']]),
                                size = 'lg',
                                radius = 'xl',
                                color = f'rgb({np.random.randint(0,255)},{np.random.randint(0,255)},{np.random.randint(0,255)})'
                            ),
                            label = author,
                            position = 'bottom'
                        )
                        for author in cli_dict['author'].split(',')
                    ]
                )
            ]),
            html.Hr(),
            html.Div(
                dbc.Stack([
                    self.make_input_component(inp,inp_idx)
                    for inp_idx,inp in enumerate(inputs_list)
                    ],
                    direction='vertical',gap=2
                ),
                style = {'maxHeight': '80vh','overflow': 'scroll'}
            ),
            dbc.Button(
                'Submit Plugin',
                className = 'd-grid col-12 mx-auto',
                color = 'success',
                disabled = True,
                id = {'type': 'dsa-plugin-runner-submit-button','index': component_index}
            )
        ])

        return plugin_component

    def make_input_component(self, input_dict, input_index):

        # Input components will either be an Input, a Dropdown, a Slider, or a region selector (custom)
        if 'enumeration' in input_dict['type']:
            input_component = html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Row(html.H6(input_dict['label'])),
                        dbc.Row(input_dict['description'])
                    ],md=5),
                    dbc.Col([
                        dcc.Dropdown(
                            options = [
                                {'label': i, 'value': i}
                                for i in input_dict['options']
                            ],
                            multi = False,
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            id = {'type': 'dsa-plugin-runner-input','index': input_index},
                            style = {'width': '100%'}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['region','geometry','point']:
            input_component = html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Row(html.H6(input_dict['label'])),
                        dbc.Row(input_dict['description'])
                    ],md=5),
                    dbc.Col([
                        'This component is still in progress'
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['file','directory','image']:
            input_component = html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Row(html.H6(input_dict['label'])),
                        dbc.Row(input_dict['description'])
                    ],md=5),
                    dbc.Col([
                        'This component is still in progress'
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type']=='boolean':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Row(html.H6(input_dict['label'])),
                        dbc.Row(input_dict['description'])
                    ],md = 5),
                    dbc.Col([
                        dcc.RadioItems(
                            options = [
                                {'label': 'True','value': 1},
                                {'label': 'False','value': 0}
                            ],
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            id = {'type': 'dsa-plugin-runner-input','index': input_index}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['integer','float','string','double'] or 'vector' in input_dict['type']:
            input_component = html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Row(html.H6(input_dict['label'])),
                        dbc.Row(input_dict['description'])
                    ],md=5),
                    dbc.Col([
                        dcc.Input(
                            type = 'text' if input_dict['type']=='string' else 'number',
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            maxLength = 1000,
                            min = input_dict['constraints']['min'] if not input_dict['constraints'] is None else [],
                            max = input_dict['constraints']['max'] if not input_dict['constraints'] is None else [],
                            #step = input_dict['constraints']['step'] if not input_dict['constraints'] is None else [],
                            id = {'type': 'dsa-plugin-runner-input','index': input_index},
                            style = {'width': '100%'}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])

        return input_component

    def find_executable_input(self, executable_dict, input_name)->dict:

        exe_input = None
        for p in executable_dict['parameters']:
            for inp in p['inputs']:
                if inp['name']==input_name:
                    exe_input = inp
                    break
        
        return exe_input

    def parse_executable(self, exe_xml)->dict:

        executable_dict = {
            'title': exe_xml.find('title').text,
            'description': exe_xml.find('description').text,
            'author': exe_xml.find('contributor').text,
            'documentation': exe_xml.find('documentation-url').text,
        }

        parameters_list = []
        for param in exe_xml.iterfind('parameters'):
            param_dict = {
                'advanced': param.get('advanced',default=False)
            }
            if param.find('label') is not None:
                param_dict['label'] = param.find('label').text
            if param.find('description') is not None:
                param_dict['description'] = param.find('description').text

            input_list = []
            for sub_el in param:
                if sub_el.tag in self.parameter_tags:
                    input_dict = {
                        'type': sub_el.tag,
                        'label': sub_el.find('label').text,
                        'description': sub_el.find('description').text
                    }

                    default_value = sub_el.find('default')
                    if not default_value is None:
                        input_dict['default'] = default_value.text
                    else:
                        input_dict['default'] = None

                    if 'enumeration' in sub_el.tag:
                        options_list = []
                        for opt in sub_el.iterfind('element'):
                            options_list.append(opt.text)
                        
                        input_dict['options'] = options_list
                    else:
                        constraints = sub_el.get('constraints',default=None)
                        if constraints is not None:
                            # Have to see if the constraints need the "text" attrib
                            constraints_dict = {
                                'min': constraints.get('min').text,
                                'max': constraints.get('max').text,
                                'step': constraints.get('step').text
                            }
                            input_dict['constraints'] = constraints_dict
                        else:
                            input_dict['constraints'] = constraints

                    input_list.append(input_dict)

            param_dict['inputs'] = input_list

            parameters_list.append(param_dict)

        executable_dict['parameters'] = parameters_list

        return executable_dict

    def run_plugin_request(self, plugin_id, session_data, input_params_dict):

        request_output = requests.post(
            url = self.handler.gc.urlBase + f'slicer_cli_web/{plugin_id}/run?token={session_data["current_user"]["token"]}',
            params = {
                'girderApiUrl': self.handler.gc.urlBase,
                'girderToken': session_data['current_user']['token']
            } | input_params_dict
        )

        return request_output

    def update_layout(self, session_data:dict, use_prefix: bool):
        
        plugin_list = self.handler.list_plugins(user_token = session_data['current_user']['token'])

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        html.H3('DSA Plugin Runner')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Select a plugin to run on the cloud!'
                    ),
                    html.Hr(),
                    dcc.Dropdown(
                        options = [
                            {'label': i['image'], 'value': i['image']}
                            for i in plugin_list
                        ],
                        value = [],
                        multi = False,
                        placeholder = 'Docker Image containing Plugin',
                        id = {'type': 'dsa-plugin-runner-docker-drop','index': 0}
                    ),
                    html.Hr(),
                    dcc.Dropdown(
                        options = [],
                        value = [],
                        multi = False,
                        placeholder = 'Plugin Name',
                        id = {'type': 'dsa-plugin-runner-cli-drop','index': 0}
                    ),
                    html.Div(
                        id = {'type': 'dsa-plugin-runner-inputs-div','index': 0},
                        children = []
                    ),
                    html.Div(
                        id = {'type': 'dsa-plugin-runner-submit-status-div','index': 0},
                        children = [],
                        style = {'marginTop': '5px'}
                    )
                ])
            ])
        ])

        if use_prefix:
            PrefixIdTransform(prefix = self.component_prefix).transform_layout(layout)

        return layout

    def gen_layout(self, session_data:dict):
        
        self.blueprint.layout = self.update_layout(session_data, use_prefix=False)

    def get_callbacks(self):

        # Callback to get all the CLIs for a selected Docker image
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-runner-docker-drop','index': ALL},'value')
            ],
            [
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-runner-cli-drop','index': ALL},'options')
            ]
        )(self.update_cli_options)

        # Callback to load plugin input components from CLI selection
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-runner-cli-drop','index': ALL},'value')
            ],
            [
                State({'type': 'dsa-plugin-runner-docker-drop','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-runner-plugin-inputs-div','index': ALL},'children')
            ]
        )(self.populate_plugin_inputs)

        # Callback for running plugin
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-runner-submit-button','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-plugin-runner-docker-drop','index': ALL},'value'),
                State({'type': 'dsa-plugin-runner-cli-drop','index': ALL},'value'),
                State({'type': 'dsa-plugin-runner-input','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-runner-submit-status-div','index': ALL},'children')
            ]
        )(self.submit_plugin)

    def update_cli_options(self, docker_select,session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        docker_select = get_pattern_matching_value(docker_select)
        session_data = json.loads(session_data)
        plugin_list = self.handler.list_plugins(user_token=session_data['current_user']['token'])
        included_cli = [i['name'] for i in plugin_list if i['image']==docker_select]

        return [included_cli]
    
    def populate_plugin_inputs(self, cli_select, docker_select,session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        plugin_list = self.handler.list_plugins(user_token = session_data['current_user']['token'])
        docker_select = get_pattern_matching_value(docker_select)
        included_cli = [i for i in plugin_list if i['image']==docker_select]

        cli_select = get_pattern_matching_value(cli_select)
        selected_plugin = [i for i in included_cli if i['name']==cli_select]
        if len(selected_plugin)>0:
            selected_plugin = selected_plugin[0]
            plugin_components = self.load_plugin(
                plugin_dict = selected_plugin,
                session_data = session_data,
                component_index = 0
            )

            # This method doesn't include the component prefix by default so have to add it here
            PrefixIdTransform(prefix = self.component_prefix).transform_layout(plugin_components)

        else:
            plugin_components = dbc.Alert(f'Plugin: {cli_select} not found in {docker_select}',color='danger')

        return [plugin_components]

    def submit_plugin(self, clicked, docker_select, cli_select, plugin_inputs,session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        session_data = json.loads(session_data)
        plugin_list = self.handler.list_plugins(user_token = session_data['current_user']['token'])

        docker_select = get_pattern_matching_value(docker_select)
        included_cli = [i for i in plugin_list if i['image']==docker_select]

        cli_select = get_pattern_matching_value(cli_select)
        selected_plugin = [i for i in included_cli if i['name']==cli_select][0]


        plugin_cli_dict = self.get_executable_dict(selected_plugin,session_data)
        plugin_input_infos = []
        for p in plugin_cli_dict['parameters']:
            plugin_input_infos.extend(p['input_list'])


        input_dict = {}
        for input_info, input_value in zip(plugin_input_infos,plugin_inputs):
            input_dict[input_info['name']] = input_value

        submit_request = self.run_plugin_request(
            plugin_id = selected_plugin['_id'],
            session_data=session_data,
            input_params_dict = input_dict
        )

        if submit_request.status_code==200:
            status_div = dbc.Alert('Plugin successfully submitted!',color='success')
        else:
            status_div = dbc.Alert(f'Error submitting plugin: {selected_plugin["_id"]}',color = 'danger')

        return [status_div]




class DSAPluginProgress(DSATool):
    """Handler for DSAPluginProgress component, letting users check the progress of currently running or previously run plugins as well as cancellation of running plugins.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self,
                 handler: DSAHandler):
        
        super().__init__()
        self.handler = handler
        self.job_status_key = {
            '0': 'INACTIVE',
            '1': 'QUEUED',
            '2': 'RUNNING',
            '3': 'SUCCESS',
            '4': 'ERROR',
            '5': 'CANCELED'
        }
    
    def load(self,component_prefix:int):
        
        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def update_layout(self, session_data:dict, use_prefix:bool):
        
        
        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('DSA Plugin Progress')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Monitor the progress of currently running plugins.'
                    ),
                ])
            )
        ])

        if use_prefix:
            PrefixIdTransform(prefix=self.component_prefix).transform_layout(layout)

        return layout

    def gen_layout(self,session_data:Union[dict,None]):
        
        self.blueprint.layout = self.update_layout(session_data=session_data,use_prefix=False)

    def get_callbacks(self):

        # Callback for getting latest logs for plugin
        # Callback for cancelling plugin

        pass




class SurveyType:
    def __init__(self,
                 question_list:list = [],
                 users: list = [],
                 storage_folder: str = ''
                ):
        """Type of survey to expose to select users.

        :param question_list: List of questions to include in the survey as well as expected types for responses.
        :type question_list: list, optional
        :param users: List of usernames that the survey is accessible to.
        :type users: list, optional
        :param storage_folder: Id of folder that will contain survey results
        :type storage_folder: str, optional
        
        """    

        self.question_list = question_list
        self.users = users
        self.storage_folder = storage_folder

class DSASurvey(Tool):
    """Handler for DSASurvey component, letting users add a survey questionnaire to a layout (with optional login for targeting specific users).

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self,
                 dsa_handler: DSAHandler,
                 survey: SurveyType):
        
        self.dsa_handler = dsa_handler
        self.survey = survey

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def gen_layout(self, session_data:Union[dict,None]):

        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('DSA Survey')
                    ),
                    html.Hr(),
                    dbc.Row()
                ])
            )
        ])

        self.blueprint.layout = layout

    def get_callbacks(self):

        # Callback for submitting survey responses
        # Callback for admins seeing current survey responses
        # Callback for admins to download current survey results
        # Callback for admins to add usernames to the survey


        pass



