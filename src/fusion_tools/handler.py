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
    
    def get_path_info(self, item_path: str) -> dict:
        """Get information for a given resource path

        :param item_path: Path in DSA instance for a given resource
        :type item_path: str
        :return: Dictionary containing id and metadata, etc.
        :rtype: dict
        """

        # First searching for the "resource"
        assert any([i in item_path for i in ['collection','user']])

        resource_find = self.gc.get('/resource/lookup',parameters={'path': item_path})

        return resource_find
    
    def get_folder_slide_count(self, folder_path: str, ignore_histoqc = True) -> list:
        """Get number of slides contained in a folder

        :param folder_path: Path in DSA for a folder
        :type folder_path: str
        :param ignore_histoqc: Whether or not to ignore images in the histoqc_outputs folder, defaults to True
        :type ignore_histoqc: bool, optional
        :return: List of image items contained within a folder
        :rtype: list
        """

        if '/' in folder_path:
            folder_info = self.get_path_info(folder_path)
        else:
            folder_info = self.gc.get(f'/folder/{folder_path}')

        folder_items = self.gc.get(f'/resource/{folder_info["_id"]}/items',
                                                  parameters = {
                                                      'type': 'folder',
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

        :param survey_args: Setup arguments for survey questions
        :type survey_args: dict
        """
        pass
    
    def create_uploader(self, folder_id:str, uploader_args:dict):
        """Create uploader component layout to a specific folder. "uploader_args" contains optional additional arguments.

        :param folder_id: ID for folder to upload to
        :type folder_id: str
        :param uploader_args: Optional arguments
        :type uploader_args: dict
        """
        pass

    def create_dataset_builder(self,builder_args:dict):
        """Table view allowing parsing of dataset/slide-level metadata and adding remote/local slides to current session.

        :param builder_args: Optional arguments to include in dataset builder layout.
        :type builder_args: dict
        """
        pass

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
                self.gc.delete(f'/slicer_cli_web/cli/{current_cli[cli_names.index(i)]['_id']}')
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
        pass

    def run_plugin(self, plugin_id:str, arguments:dict):
        """Run a plugin given a set of input arguments

        :param plugin_id: ID for plugin to run.
        :type plugin_id: str
        :param arguments: Dictionary containing keys/values for each input argument to a plugin
        :type arguments: dict
        """
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
                 handler: Union[DSAHandler,list] = []
                ):
        
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
                collections_info.append({
                    'Collection': c['name'],
                    'Number of Slides': len(self.handler.get_folder_slide_count(folder_path = c['_id']))
                } | c['meta'])


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
                    dbc.Row([
                        html.Div(
                            id = {'type': 'dataset-builder-collection-div','index': 0},
                            children = []
                        )
                    ],style={'marginBottom':'10px'}),
                    html.Hr(),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'dataset-builder-collection-contents-div','index':0},
                            children = []
                        )
                    ],style = {'marginBottom':'10px'})
                ])
            )
        ], style = {'maxHeight': '90vh','overflow': 'scroll'})


        self.blueprint.layout = layout

    def get_callbacks(self):

        # Callback for collection selection (populating table with collection contents)

        # Callback for selecting folder/item from collection-contents-div

        # Callback for plotting slide-level metadata if there is any

        # Callback for viewing thumbnail of selected slide(s)
        pass


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



