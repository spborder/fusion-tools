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

    def get_image_region(self, item_id: str, coords_list: list, style: Union[dict,None] = None)->np.ndarray:
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

        if style is None:
            image_array = np.uint8(
                np.array(
                    Image.open(
                        BytesIO(
                            requests.get(
                                self.gc.urlBase+f'/item/{item_id}/tiles/region?token={self.user_token}&left={coords_list[0]}&top={coords_list[1]}&right={coords_list[2]}&bottom={coords_list[3]}'
                            ).content
                        )
                    )
                )
            )
        
        else:
            print('Adding style parameters are in progress')
            raise NotImplementedError

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

    def query_annotation_count(self, item:Union[str,list]) -> pd.DataFrame:
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

            return resource_find
        except girder_client.HttpError:
            #TODO: Make this error handling a little better (return some error type)
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
    
    def create_uploader(self, folder_id:str, uploader_args:dict):
        """Create uploader component layout to a specific folder. "uploader_args" contains optional additional arguments.

        :param folder_id: ID for folder to upload to
        :type folder_id: str
        :param uploader_args: Optional arguments
        :type uploader_args: dict
        """

        #TODO: 

        pass

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

    def list_plugins(self):
        """List all of the plugins/CLIs available for the current DSA instance
        """
        
        return self.gc.get('/slicer_cli_web/cli')

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
        
    def create_user_folder(self, parent_path, folder_name, metadata = None):
        """
        Creating a folder in user's public folder
        """
        public_folder_path = parent_path
        public_folder_id = self.gc.get('/resource/lookup',parameters={'path':public_folder_path})['_id']

        # Creating folder
        if not metadata is None:
            new_folder = self.gc.loadOrCreateFolder(
                folderName = folder_name,
                parentId = public_folder_id,
                parentType = 'folder',
                metadata = metadata
            )
        else:
            new_folder = self.gc.loadOrCreateFolder(
                folderName = folder_name,
                parentId = public_folder_id,
                parentType = 'folder'
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
        pass


class DatasetBuilder(Tool):
    """Handler for DatasetBuilder component, enabling selection/deselection of folders and slides to add to current visualization session.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self,
                 handler: Union[DSAHandler,list] = [],
                 include_only: Union[list,None] = None
                ):
        
        self.include_only = include_only
        self.handler = handler

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

    def gen_layout(self, session_data: Union[dict,None]):
        """Generating DatasetBuilder layout, adding to DashBlueprint() object to be embedded in larger layout.

        :param session_data: Data on current session, not used in this component.
        :type session_data: Union[dict,None]
        """

        collections_info = []
        if type(self.handler)==list:
            #TODO: Get this working for stringing together multiple DSA instances
            # Just have to find a way to link back to the right DSAHandler instance
            collections = [] 
        else:
            collections = self.handler.get_collections()
            for c in collections:
                slide_count = self.handler.get_collection_slide_count(collection_name = c['name'])
                folder_count = self.handler.get_path_info(path = f'/collection/{c["name"]}')
                if slide_count>0:
                    collections_info.append({
                        'Collection Name': c['name'],
                        'Collection ID': c['_id'],
                        'Number of Slides': slide_count,
                        'Number of Folders': folder_count['nFolders']
                    } | c['meta'])

        collections_df = pd.DataFrame.from_records(collections_info)

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
                            data = json.dumps({'include_slides':[], 'selected_collections': [], 'available_collections': collections_info})
                        )
                    ),
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
                    ],style = {'marginBottom':'10px','maxHeight':'70vh','overflow':'scroll'})
                ])
            )
        ], style = {'maxHeight': '90vh','overflow': 'scroll'})


        self.blueprint.layout = layout

    def get_callbacks(self):

        # Callback for collection selection (populating table with collection contents)
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-collections-table','index': ALL},'selected_rows')
            ],
            [
                State({'type':'dataset-builder-data-store','index': ALL},'data')
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
                State({'type': 'dataset-builder-collection-folder-nav-parent','index': MATCH},'children')
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
                Input({'type':'dataset-builder-slide-remove-icon','index': ALL},'n_clicks'),
                Input({'type':'dataset-builder-slide-remove-all-button','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'dataset-builder-selected-slides','index': ALL},'children')
            ]
        )(self.slide_selection)

        # Callback for plotting slide-level metadata if there is any

        # Callback for viewing thumbnail of selected slide(s)

    def make_selectable_dash_table(self, dataframe:pd.DataFrame, id:dict, multi_row:bool = True):
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
            selected_columns = [],
            selected_rows = [],
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
        print(folder_info)

        # Starting with slides (which will report parent folderId but not that parent's folderId (if applicable))
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

                if folder_ids[-1]==folder_info['_id']:
                    child_folder_path = '/collection/'+'/'.join([i['object']['name'] for i in u_folder_rootpath]+[u_folder_info['name']])
                else:
                    # Folder that is immediate child of current folder:
                    child_folder_idx = folder_ids.index(folder_info['_id'])
                    child_folder_path = '/collection/'+'/'.join([i['object']['name'] for i in u_folder_rootpath[:child_folder_idx+2]])

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

    def collection_selection(self, collection_rows, builder_data):
        """Callback for when one/multiple collections are selected from the collections table

        :param collection_rows: Row indices of selected collections
        :type collection_rows: list
        :param builder_data: Data store on available collections and currently included slides
        :type builder_data: list
        :return: Children of collection-contents-div (items/folders within selected collections)
        :rtype: list
        """
        selected_collections = get_pattern_matching_value(collection_rows)
        builder_data = json.loads(get_pattern_matching_value(builder_data))

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
            folder_slides, folder_folders = self.organize_folder_contents(
                folder_info = self.handler.get_path_info(f'/collection/{collection_info["Collection Name"]}')
            )

            if len(folder_slides)>0:

                non_nested_df = pd.DataFrame.from_records(folder_slides)
                non_nested_table = self.make_selectable_dash_table(
                    dataframe=non_nested_df,
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-slide-table','index': idx},
                    multi_row=True
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
                                    html.A('/collection'),
                                    html.A(
                                        f'/{collection_info["Collection Name"]}/',
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
                        ], style = {'marginTop':'10px'},id = {'type': f'{self.component_prefix}-dataset-builder-collection-slide-div','index': idx})
                    ]),
                    dbc.CardFooter(html.P(f'Selected Slides: 0',id = {'type': f'{self.component_prefix}-selected-slide-count','index': idx}))
                ]),
                style = {'marginBottom':'10px'}
            )
            
            return new_card
        
        if len(selected_collections)>0:
            if len(list(set(selected_collections).difference(builder_data['selected_collections'])))>0:
                # Adding a new collection
                new_collection_idx = list(set(selected_collections).difference(builder_data['selected_collections']))[0]
                collection_contents.append(add_collection_card(builder_data['available_collections'][new_collection_idx],new_collection_idx))
            elif len(list(set(builder_data['selected_collections']).difference(selected_collections)))>0:
                # Removing a collection
                rem_collection_idx = list(set(builder_data['selected_collections']).difference(selected_collections))[0]
                del collection_contents[builder_data['selected_collections'].index(rem_collection_idx)]

        else:
            collection_contents = ['Select a Collection to get started!']

        builder_data['selected_collections'] = selected_collections
        builder_data = json.dumps(builder_data)
            
        return [collection_contents], [builder_data]

    def update_folder_div(self,folder_row,crumb_click,collection_folders,current_crumbs):
        """Selecting a folder from the collection's folder table

        :param folder_row: Selected folder (list of 1 index)
        :type folder_row: list
        :param crumb_click: If one of the folder path parts was clicked it will trigger this.
        :type crumb_click: int
        :param collection_folders: Current data in the collection's folder table
        :type collection_folders: list
        :param current_crumbs: List of current path parts that can be selected to go up a folder
        :type current_crumbs: list
        :return: Sub-folder and slide selection tables for further selection
        :rtype: tuple
        """


        if type(current_crumbs)==list:
            current_crumbs = current_crumbs[0]['props']['children']
        else:
            current_crumbs = current_crumbs['props']['children']

        new_crumbs = []
        path_parts = []
        for i in current_crumbs:
            path_part = i['props']['children']
            if not path_part in ['/collection','/user']:
                crumb = html.A(
                    path_part,
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-crumb','index': ctx.triggered_id['index']},
                    style = {'color': 'rgb(0,0,255)'}
                )
            else:
                crumb = html.A(path_part)

            path_parts.append(path_part)
            new_crumbs.append(crumb)
        
        if 'dataset-builder-collection-folder-table' in ctx.triggered_id['type']:
            print('folder selected from table')
            
            # Triggers callback when creating new folder table
            if len(folder_row)==0:
                return no_update, no_update, no_update

            new_folder_name = collection_folders[folder_row[0]]['Folder Name']
            folder_table_style = {'display':'inline-block','width':'100%'}
            
            new_crumbs += [html.A(
                new_folder_name + '/',
                id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-crumb','index': ctx.triggered_id['index']},
                style = {'color': 'rgb(0,0,255)'}
            )]
            
            folder_path = ''.join(path_parts+[new_folder_name])
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
                slides_table = self.make_selectable_dash_table(
                    dataframe=pd.DataFrame.from_records(folder_slides),
                    id = {'type': f'{self.component_prefix}-dataset-builder-slide-table','index': ctx.triggered_id['index']},
                    multi_row=True
                )
            else:
                slides_table = html.Div()


        elif 'dataset-builder-collection-folder-crumb' in ctx.triggered_id['type']:
            n_clicks = [i['props']['n_clicks'] if 'n_clicks' in i['props'] else 0 for i in current_crumbs]
            n_click_idx = np.argmax(n_clicks)
            if n_click_idx==len(current_crumbs)-1:
                folder_table_style = no_update
            else:
                folder_table_style = {'display':'inline-block','width':'100%'}
                new_crumbs = new_crumbs[:n_click_idx+1]
                
                new_path = ''.join(path_parts[:n_click_idx+1])[:-1]
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
                    slides_table = self.make_selectable_dash_table(
                        dataframe=pd.DataFrame.from_records(folder_slides),
                        id = {'type': f'{self.component_prefix}-dataset-builder-slide-table','index': ctx.triggered_id['index']},
                        multi_row=True
                    )
                else:
                    slides_table = html.Div()
                
        new_crumbs = dbc.Stack(new_crumbs,direction='horizontal')

        return folder_table_style, folder_table, slides_table, new_crumbs

    def slide_selection(self, slide_rows, slide_all, slide_rem, slide_rem_all):

        print(ctx.triggered)
        print(slide_rows)
        print(slide_all)
        print(slide_rem)
        print(slide_rem_all)

        raise exceptions.PreventUpdate





class DSAUploadType:
    """Formatted upload type for a DSAUploader Component.
    """
    def __init__(self,
                 name: str,
                 input_files: list = [],
                 processing_plugins:Union[list,None] = None,
                 required_metadata: Union[list,None] = None):
        """Constructor method

        :param name: Name for this upload type (appears in dropdown menu in DSAUploader component)
        :type name: str
        :param input_files: List of dictionaries containing the following keys: name:str, description: str, accepted_types: Union[list,None], preprocessing_plugins: Union[list,None]
        :type input_files: list
        :param processing_plugins: List of plugins to run after data has been uploaded. Allows for input of plugin-specific arguments after completion of file uploads., defaults to None
        :type processing_plugins: Union[list,None], optional
        :param required_metadata: List of "keys" which require user input either by uploading a file or by manual addition.
        :type required_metadata: Union[list,None], optional
        """
        
        self.name = name
        self.input_files = input_files
        self.processing_plugins = processing_plugins
        self.required_metadata = required_metadata




class DSAUploader(Tool):
    """Handler for DSAUploader component, handling uploading data to a specific folder, adding metadata, and running sets of preprocessing plugins.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self,
                 dsa_handler: Union[DSAHandler,list] = [],
                 dsa_upload_types: Union[DSAUploadType,list] = []):
        
        self.dsa_handler = dsa_handler
        self.dsa_upload_types = dsa_upload_types

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

    def gen_layout(self,session_data:Union[dict,None]):

        #TODO: Layout start:
        # Whether the upload is to a specific collection or to a User folder (Public/Private)
        # Selecting folder to upload to based on previous selection
        # Select which type of upload this is
        # Load upload type format based on DSAUploadType properties

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
                    dbc.Row([
                        html.Div(
                            id = {'type': 'dsa-uploader-collection-or-user-div','index': 0},
                            children = []
                        )
                    ]),
                    html.Hr(),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'dsa-uploader-folder-in-div','index': 0},
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
            )
        ],style = {'maxHeight': '90vh','overflow': 'scroll'})

        self.blueprint.layout = layout
        
    def get_callbacks(self):

        # Callback for selecting whether to upload to public/private collection or user public/private folder
        # Callback for selecting folder to upload to based on previous selection
        # Callback for populating with DSAUploadType specifications
        # Callback for running processing plugin with inputs

        pass


class DSAPluginRunner(Tool):
    """Handler for DSAPluginRunner component, letting users specify input arguments to plugins to run on connected DSA instance.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self,
                 dsa_handler: DSAHandler):
        
        self.dsa_handler = dsa_handler

    def load(self, component_prefix: int):
        pass

    def gen_layout(self, session_data:Union[dict,None]):
        pass

    def get_callbacks(self):
        pass


class DSAPluginProgress(Tool):
    """Handler for DSAPluginProgress component, letting users check the progress of currently running or previously run plugins as well as cancellation of running plugins.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self,
                 dsa_handler: DSAHandler):
        
        self.dsa_handler = dsa_handler
    
    def load(self,component_prefix:int):
        
        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def gen_layout(self,session_data:Union[dict,None]):

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
        
        self.blueprint.layout = layout

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



