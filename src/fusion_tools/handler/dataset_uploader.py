"""DSAUploader component and UploadType 
"""
import os
import time
import shutil

import json
import numpy as np
import pandas as pd
import requests
from flask import request

from typing_extensions import Union

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
#import dash_treeview_antd as dta
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
import dash_uploader as du

from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import load_annotations

from fusion_tools.components.base import DSATool, BaseSchema
from fusion_tools.handler.plugin import DSAPluginRunner, DSAPluginGroup
from fusion_tools.handler.resource_selector import DSAResourceSelector

from girder_job_sequence import Job, Sequence
from girder_job_sequence.utils import from_list, from_dict
import threading
import large_image


# Maximum allowed size of uploads (Mb)
MAX_UPLOAD_SIZE = 1e4
# Minimum chunk size (Mb)
MIN_UPLOAD_SIZE = 6

WSI_TYPES = [i for i in list(large_image.listSources()['extensions'].keys()) if not i in ['json','yaml','yml']]
ANN_TYPES = ['json','geojson','xml','csv']


class DSAUploadType(BaseSchema):
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

        # At a minimum, input files just has to contain at least one element and at least one "required" element
        # Other acceptable keys include "type", "description", "accepted_types", and "parent"
        assert len(self.input_files)>0
        assert all([type(i) in [dict,str] for i in self.input_files])

        default_vals = {
            'accepted_types': None,
            'preprocessing_plugins': None,
            'type': 'item',
            'parent': None,
            'required': True
        }

        # Checking the input file types
        files = [i for i in self.input_files if type(i)==dict]        
        assert all(['name' in i for i in files])
        files = [i for i in self.input_files if 'type' in files]
        assert all([i['type'] in ['item','file','annotation'] for i in files])

        # Checking that all the file and annotation types have a "parent"
        files = [i for i in files if i['type'] in ['file','annotation']]
        assert all(['parent' in i for i in files])

        for idx,i in enumerate(self.input_files):
            if type(i)==dict:
                if not all([j in i for j in default_vals]):
                    for key,val in default_vals.items():
                        if not key in i:
                            i[key] = val
            elif type(i)==str:
                i_dict = {
                    'name': i
                } | default_vals
                self.input_files[idx] = i_dict
        
        
        # Checking format of required_metadata (if it's a dictionary it has to have 'name'and 'required')
        if not self.required_metadata is None:
            req_meta_check = []
            for r in self.required_metadata:
                if type(r)==str:
                    req_meta_check.append(True)
                elif type(r)==dict:
                    req_meta_check.append(
                        all([i in r for i in ['name', 'required', 'item']])
                    )
        else:
            req_meta_check = [True]
            self.required_metadata = []

        assert all(req_meta_check)

        # All processing_plugins have to have a "dict" or "list" type
        assert all([isinstance(i,dict) or isinstance(i,list) for i in self.processing_plugins])

        # Lists within self.processing_plugins are interpreted as a sequence
        # Jobs that aren't in a sequence are determined to be independent of other processing steps
        # and are therefore executed at the same time as the first job in each sequence.
        """
        self.job_sequences = []
        for p in self.processing_plugins:
            if type(p)==dict:
                self.job_sequences.append(from_dict(p))
            elif type(p)==list:
                self.job_sequences.append(from_list(p))
        """

# RequestData is from the documentation for dash-uploader with the keys modified from "flow" to "resumable" (there must have been some update that they didn't account for initially)
class RequestData:
    # A helper class that contains data from the request
    # parsed into handier form.

    def __init__(self, request):
        """
        Parameters
        ----------
        request: flask.request
            The Flask request object
        """
        # Available fields: https://github.com/flowjs/flow.js
        self.n_chunks_total = request.form.get("resumableTotalChunks", type=int)
        self.chunk_number = request.form.get("resumableChunkNumber", default=1, type=int)
        self.filename = request.form.get("resumableFilename", default="error", type=str)
        self.total_size = request.form.get('resumableTotalSize',default=0,type=int)
        # 'unique' identifier for the file that is being uploaded.
        # Made of the file size and file name (with relative path, if available)
        self.unique_identifier = request.form.get(
            "resumableIdentifier", default="error", type=str
        )
        # flowRelativePath is the flowFilename with the directory structure included
        # the path is relative to the chosen folder.
        self.relative_path = request.form.get("resumableRelativePath", default="", type=str)
        if not self.relative_path:
            self.relative_path = self.filename

        # Get the chunk data.
        # Type of `chunk_data`: werkzeug.datastructures.FileStorage
        self.chunk_data = request.files["file"]
        self.upload_id = request.form.get("upload_id", default="", type=str)

class DSAUploadHandler:
    def __init__(self,server,upload_folder,use_upload_id):
        self.server = server
        self.upload_folder = upload_folder
        self.use_upload_id = use_upload_id

        # 2**20 is 1MB in binary
        self.min_chunk_size = MIN_UPLOAD_SIZE * (2**20)

    def post_before(self,req_data):
        # Creating item to upload to
        upload_info = json.loads(req_data.upload_id)

        if upload_info['fusion_upload_type'] in ['item','file']:
            print(f'Creating file: {req_data.filename}')
            post_response = requests.post(
                upload_info['api_url']+'/file',
                params = {
                    'token': upload_info['token'],
                    'parentType': upload_info['parentType'],
                    'parentId': upload_info['parentId'],
                    'name': req_data.filename,
                    'size': req_data.total_size
                }
            )

            self.current_upload = post_response.json()
        else:
            self.current_upload = []

    def post_file_chunk(self,api_url,token,parentId,chunk,offset):

        post_response = requests.post(
            api_url+f'/file/chunk',
            params={
                'token': token,
                'uploadId': parentId,
                'offset': offset * self.min_chunk_size
            },
            data = chunk
        )
        return post_response.json()

    def remove_file(self,path):
        os.unlink(path)
    
    def save_annotation_chunk(self):

        r = RequestData(request)

        # Getting temporary directory containing chunks
        tmp_chunk_path = self.upload_folder / r.unique_identifier
        if not tmp_chunk_path.exists():
            tmp_chunk_path.mkdir(parents=True)

        chunk_name = f'{r.filename}_{r.chunk_number}'
        chunk_file = tmp_chunk_path / chunk_name

        # Making a lock file
        lock_file_path = tmp_chunk_path / f'.lock_{r.chunk_number}'

        with open(lock_file_path,'a'):
            os.utime(lock_file_path,None)

        # Save the chunk, delete the lock
        r.chunk_data.save(chunk_file)
        self.remove_file(lock_file_path)

        # Check if all chunks are present
        upload_complete = all([os.path.exists(os.path.join(tmp_chunk_path,f'{r.filename}_{i}')) for i in range(1,r.n_chunks_total+1)])

        # Reassembling if the upload is complete
        if upload_complete:
            # Wait until all the lock files are removed
            wait = 0
            while any([os.path.isfile(os.path.join(tmp_chunk_path,f'.lock_{i}')) for i in range(1,r.n_chunks_total+1)]):
                wait +=1
                if wait>=5:
                    raise Exception(
                        f"Error uploading files to {tmp_chunk_path}"
                    )
                time.sleep(1)
            
            target_file_path = os.path.join(self.upload_folder,r.filename)
            if os.path.exists(target_file_path):
                # dash-uploader implements a retry() callback for this if it doesn't go through the first time
                self.remove_file(target_file_path)
            
            with open(target_file_path,'ab') as target_file:
                chunk_paths = [os.path.join(tmp_chunk_path,f'{r.filename}_{i}') for i in range(1,r.n_chunks_total+1)]
                for p in chunk_paths:
                    with open(p,'rb') as stored_chunk:
                        target_file.write(stored_chunk.read())
            
            shutil.rmtree(tmp_chunk_path)

    def post_annotations(self, upload_info):

        r = RequestData(request)
        processed_annotations = load_annotations(os.path.join(self.upload_folder,r.filename))
        self.remove_file(os.path.join(self.upload_folder,r.filename))

        response = requests.post(
            upload_info['api_url']+f'/annotation/item/{upload_info["parentId"]}?token={upload_info["token"]}',
            data = json.dumps(processed_annotations),
            headers = {
                'X-HTTP-Method': 'POST',
                'Content-Type': 'application/json'
            }
        )

        return response.json()

    def post(self):

        r = RequestData(request)
        upload_info = json.loads(r.upload_id)

        if r.chunk_number==1:
            self.post_before(r)
        
        if upload_info['fusion_upload_type'] in ['item','file']:
            post_response = self.post_file_chunk(
                api_url=upload_info['api_url'],
                token = upload_info['token'],
                parentId=self.current_upload['_id'],
                chunk = r.chunk_data.read(),
                offset = r.chunk_number-1
            )
        else:

            self.save_annotation_chunk()

            if r.chunk_number==r.n_chunks_total:
                post_response = self.post_annotations(
                    upload_info
                )
                post_response = {
                    'n_annotations': post_response,
                    '_modelType': 'annotation'
                }
            else:
                post_response = r.filename

        return json.dumps(post_response | upload_info)

    def get_before(self):
        pass

    def get(self):
        return 200

    def get_after(self):
        pass

    def post_after(self):
        pass


class DSAUploader(DSATool):
    """Handler for DSAUploader component, handling uploading data to a specific folder, adding metadata, and running sets of preprocessing plugins.

    :param DSATool: Sub-class of Tool specific to DSA components. Updates with session data by default.
    :type DSATool: None
    """

    title = 'DSA Uploader'
    description = 'Uploading slides and associated files to a particular folder on attached DSA instance. Access pre-processing plugins.'

    def __init__(self,
                 handler,
                 dsa_upload_types: Union[DSAUploadType,list] = []):
        

        super().__init__()
        self.handler = handler
        self.dsa_upload_types = dsa_upload_types

    def load(self,component_prefix:int):

        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}',escape = lambda input_id: self.prefix_escape(input_id)),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

        self.plugin_inputs_handler = DSAPluginGroup(
            handler = self.handler
        )
        self.plugin_inputs_handler.load(self.component_prefix)
        
    def update_layout(self, session_data:dict, use_prefix:bool):

        if self.get_user_external_token(session_data) is None:
            uploader_children = html.Div(
                dbc.Alert(
                    'Make sure to login first in order to upload!',
                    color = 'warning'
                )
            )
   
        else:
            self.plugin_inputs_handler.update_layout(session_data,use_prefix=use_prefix)
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
                        html.H3(self.title)
                    ),
                    html.Hr(),
                    dbc.Row(
                        self.description
                    ),
                    html.Hr(),
                    html.Div(
                        self.plugin_inputs_handler.blueprint.embed(self.blueprint),
                        style = {'display':'none'}
                    ),
                    uploader_children
                ])
            )
        ],style = {'maxHeight': '90vh','overflow': 'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix=self.component_prefix,escape = lambda input_id: self.prefix_escape(input_id)).transform_layout(layout)

        return layout
        
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
            ],
            prevent_initial_call = True
        )(self.make_file_uploads)

        # Callback for enabling "Done" button when all required files are uploaded and enabling child uploads of items
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-file-upload','index': ALL},'isCompleted')
            ],
            [
                State({'type': 'dsa-uploader-upload-type-drop','index': ALL},'value'),
                State({'type': 'dsa-uploader-file-upload','index': ALL},'fileNames'),
                State('anchor-vis-store','data'),
                State({'type': 'dsa-uploader-upload-files-store','index': ALL},'data')
            ],
            [
                Output({'type': 'dsa-uploader-file-upload-div','index': ALL},'children'),
                Output({'type': 'dsa-uploader-file-upload-done-button','index': ALL},'disabled'),
                Output({'type': 'dsa-uploader-upload-type-drop','index': ALL},'disabled'),
                Output({'type': 'dsa-uploader-upload-files-store','index': ALL},'data')
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
                State({'type':'dsa-uploader-upload-files-store','index': ALL},'data'),
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
        #TODO: Submitting metadata depends on if the "item" that the metadata is attached to is uploaded yet
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-metadata-table','index': ALL},'data')
            ],
            [
                State({'type': 'dsa-uploader-upload-type-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'dsa-uploader-metadata-submit-button','index': ALL},'disabled')
            ],
            prevent_initial_call = True
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
            ],
            prevent_initial_call = True
        )(self.add_row_custom_metadata)

        # Callback for submitting metadata
        self.blueprint.callback(
            [
                Input({'type': 'dsa-uploader-metadata-submit-button','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-uploader-upload-files-store','index': ALL},'data'),
                State({'type': 'dsa-uploader-metadata-table','index': ALL},'data'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-uploader-metadata-submit-status-div','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.submit_metadata)

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

    def organize_folder_contents(self, folder_info:dict, show_empty:bool=True, ignore_histoqc:bool=True, user_token: Union[str,None] = None)->list:
        """For a given folder selection, return a list of slides(0th) and folders (1th)

        :param folder_info: Folder info dict returned by self.handler.get_path_info(path)
        :type folder_info: dict
        :param show_empty: Whether or not to display folders which contain 0 slides, defaults to False
        :type show_empty: bool, optional
        :param user_token: User token to authenticate external queries
        :type user_token: Union[str,None], optional
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
                ignore_histoqc=ignore_histoqc,
                user_token = user_token
            )

            folder_slides_folders = [i['folderId'] for i in all_folder_slides]
            unique_folders = list(set(folder_slides_folders))
            folders_in_folder = []
            for u in unique_folders:
                if not u==folder_info['_id'] and not u in folders_in_folder:
                    # This is for all folders in this folder
                    # This grabs parent folders of this folder
                    u_folder_info = self.handler.get_folder_info(folder_id=u,user_token = user_token)
                    u_folder_rootpath = self.handler.get_folder_rootpath(u, user_token = user_token)
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
                        path = child_folder_path,
                        user_token = user_token
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
                    path = f'/user/{folder_info["login"]}/{u_f}',
                    user_token = user_token
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
                folder_type = folder_info['_modelType'],
                user_token = user_token
            )
            
            for f in empty_folders:
                if not f['_id'] in folders_in_folder and not f['_id'] in unique_folders:
                    folder_info = self.handler.get_folder_info(f["_id"],user_token = user_token)
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

    def gen_collections_dataframe(self, user_token:Union[str,None] = None):
        """Generating dataframe containing current collections

        :return: Dataframe with each Collection
        :rtype: pd.DataFrame
        """
        collections_info = []
        collections = self.handler.get_collections(user_token = user_token)
        for c in collections:
            folder_count = self.handler.get_path_info(path = f'/collection/{c["name"]}',user_token = user_token)
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

    def gen_metadata_table(self, required_metadata: list, upload_items: list):
        """Generates metadata tables that the user can modify to add metadata to an uploaded item.

        :param required_metadata: List of required metadata items
        :type required_metadata: list
        :param upload_items: List of the names of uploaded items which can be used as targets of metadata values
        :type upload_items: list
        """
        dict_items = [i for i in required_metadata if type(i)==dict]
        dropdown_rows = [i for i in dict_items if 'values' in i]
        free_rows = [{'name':i, 'item': '', 'required': False} for i in required_metadata if type(i)==str]
        free_rows += [{'name': i['name'], 'item': i['item'], 'required': i['required']} for i in required_metadata if not 'values' in i]
        
        table_list = []
        for m_idx,m in enumerate([dropdown_rows,free_rows]):
            # Skip generating this table if now rows are present
            if len(m)==0:
                continue

            m_df = pd.DataFrame.from_records([
                {'Target': i['item'], 'Key': i['name'],'Value': '','row_id': idx}
                for idx,i in enumerate(m)
            ])
            required_rows = [r_idx for r_idx,r in enumerate(m) if r['required']]

            dropdown_conditional = [
                {
                    'if': {
                        'column_id': 'Target',
                        'filter_query': '{row_id} eq '+str(b)
                    },
                    'options': [
                        {'label': c, 'value': c}
                        for c in upload_items
                    ]
                }
                for b in range(len(m)) if m[b]['item']==''
            ]

            if m_idx==0:
                dropdown_conditional += [
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
                ]

            metadata_table = dash_table.DataTable(
                id = {'type': f'{self.component_prefix}-dsa-uploader-metadata-table','index': m_idx},
                data = m_df.to_dict('records'),
                columns = [
                    {'id': 'Target', 'name': 'Target','presentation': 'dropdown'},
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
                dropdown_conditional = dropdown_conditional,
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
                    {'Target': '', 'Key': '', 'Value': ''}
                ], 
                columns = [
                    {'id': 'Target', 'name': 'Target','presentation': 'dropdown'},
                    {'id': 'Key', 'name': 'Key'},
                    {'id': 'Value', 'name': 'Value'}
                ],
                dropdown = {
                    'Target': {
                        'options': [
                            {'label': w, 'value': w}
                            for w in upload_items
                        ]
                    }
                },
                editable = True,
                row_deletable = True,
                page_current = 0,
                page_size = 10,
                css=[{"selector": ".Select-menu-outer", "rule": "display: block !important"}]
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

        user_external_token = self.get_user_external_token(session_data)
        user_external_login = self.get_user_external_login(session_data)

        if not ctx.triggered_id:
            raise exceptions.PreventUpdate

        if 'dsa-uploader-collection-button' in ctx.triggered_id['type']:
            
            if not any([i['value'] for i in ctx.triggered]):
                raise exceptions.PreventUpdate

            collection_df = self.gen_collections_dataframe(user_token = user_external_token)
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

            path_parts = ['/user/',f'{user_external_login}/']

        elif 'dsa-uploader-folder-table' in ctx.triggered_id['type']:
            
            if not any([i['value'] for i in ctx.triggered]):
                raise exceptions.PreventUpdate
            
            path_parts = path_parts+[folder_table_data[folder_table_rows[0]]['Name']+'/']

            folder_info = self.handler.get_path_info(
                path = ''.join(path_parts)[:-1],
                user_token = user_external_token
            )

            # Don't need to know the slides in that folder
            _, folder_folders = self.organize_folder_contents(
                folder_info=folder_info,
                user_token = user_external_token
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
                    path = ''.join(path_parts)[:-1],
                    user_token = user_external_token
                )

                if not path_parts==['/user/',user_external_login+'/']:
                    # Don't need to know the slides in that folder
                    _, folder_folders = self.organize_folder_contents(
                        folder_info=folder_info,
                        user_token = user_external_token
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
                    folder_folders = self.gen_collections_dataframe(user_token = user_external_token).to_dict('records')
                elif path_parts =='/user/':
                    folder_folders = [
                        {
                            'Name': i['login']
                        }
                        for i in self.handler.gc.get(f'/user?token={user_external_token}')
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

        user_external_token = self.get_user_external_token(session_data)

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
                    user_token=user_external_token
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
                            dcc.Store(
                                id = {'type': f'{self.component_prefix}-dsa-uploader-upload-files-store','index': 0},
                                storage_type = 'memory',
                                data = json.dumps({'uploaded_files': []})
                            ),
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

    def create_upload_component(self, file_info, user_info, idx):
        
        # "item" type uploads have a parentId = the Id of the folder they are being uploaded to
        # "file" and "annotation" type uploads have a parentId = the item that they are being added to
        # if the parent "item" for a "file" or "annotation" does not exist yet, then the uploader should be disabled

        upload_id_dict = {
            'api_url': self.handler.girderApiUrl,
            'token': user_info['token'],
            'fusion_upload_name': file_info['name'],
            'fusion_upload_type': file_info['type'],
            'parentType': file_info['parentType'],
            'parentId': file_info['parentId']
        }

        upload_component = du.Upload(
            id = {'type': f'{self.component_prefix}-dsa-uploader-file-upload','index': idx},
            max_file_size = MAX_UPLOAD_SIZE,
            chunk_size = MIN_UPLOAD_SIZE,
            filetypes = file_info['accepted_types'],
            cancel_button = True,
            pause_button = True,
            upload_id = json.dumps(upload_id_dict),
            disabled = False
        )

        return upload_component

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

        user_external_token = self.get_user_external_token(session_data)

        upload_path_parts = self.extract_path_parts(get_pattern_matching_value(upload_folder_path))
        folder_info = self.handler.get_path_info(
            path = ''.join(upload_path_parts)[:-1],
            user_token = user_external_token
        )

        selected_upload_type = self.dsa_upload_types[[i.name for i in self.dsa_upload_types].index(upload_type_value)]

        file_uploads = html.Div([
            dbc.Stack([
                html.Div([
                    html.H5(f'{f["name"]}',style={'textTransform':'none'}),
                    html.Div(
                        self.create_upload_component(
                            file_info = f | {'parentId': folder_info["_id"],'parentType': 'folder', 'fusion_upload_name': f['name'], 'fusion_upload_type': f['type']},
                            user_info = session_data['user']['external'],
                            idx = f_idx
                        ) if f['type']=='item' else 
                        dbc.Alert(f'This upload will be created when: {f["parent"]} is uploaded',color='warning'),
                        id = {'type': f'{self.component_prefix}-dsa-uploader-file-upload-div','index': f_idx},
                        style = {'width': '100%'}
                    ),
                    dbc.Tooltip(
                        target = {'type': f'{self.component_prefix}-dsa-uploader-file-upload-div','index': f_idx},
                        placement='top',
                        children = ','.join(f['accepted_types'])
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

    def enable_upload_done(self, uploads_complete, upload_type, current_filenames,session_data,upload_file_data):
        """Enabling the "Done" button when all required uploads are uploaded

        :param uploads_complete: Current uploadComplete flags from active UploadComponents
        :type uploads_complete: list
        :param upload_type: Selected type of upload
        :type upload_type: list
        """
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        upload_file_data = json.loads(get_pattern_matching_value(upload_file_data))
        upload_type = get_pattern_matching_value(upload_type)
        selected_upload_type = self.dsa_upload_types[[i.name for i in self.dsa_upload_types].index(upload_type)]

        user_external_token = self.get_user_external_token(session_data)

        # Getting the filenames (json.dumps(post_response))
        current_filenames = [i for i in current_filenames if not i is None]
        if len(current_filenames)>0:
            current_filenames = current_filenames[0]
        else:
            current_filenames = None
        completed_filenames = []
        if current_filenames is None:
            raise exceptions.PreventUpdate
        
        for c in current_filenames:
            if not c is None:
                #TODO: "fileNames" is a list of files by default so in theory this could be expanded to accept multiple
                # uploads to the same container
                if type(c)==str:
                    completed_filenames.append(json.loads(c))
                elif type(c)==list:
                    completed_filenames.append(json.loads(c[0]))

        upload_file_data['uploaded_files'].extend(completed_filenames)
        input_file_types = [i['fusion_upload_name'] for i in completed_filenames][0]

        completed_upload_file = selected_upload_type.input_files[[i['name'] for i in selected_upload_type.input_files].index(input_file_types)]
        child_files = [
            [idx,i] for idx,i in enumerate(selected_upload_type.input_files) if i['parent']==input_file_types
        ]

        upload_div_children = [no_update]*len(ctx.outputs_list[0])
        for c in child_files:
            file_info = {
                'api_url': self.handler.girderApiUrl,
                'token': user_external_token,
                'fusion_upload_name': c[1]['name'],
                'fusion_upload_type': c[1]['type'],
                'parentType': 'item',
                'parentId': completed_filenames[0]['itemId']
            }

            upload_div_children[c[0]] = self.create_upload_component(
                file_info = c[1] | file_info,
                user_info = session_data['user']['external'],
                idx = c[0]
            )

        if 'name' in completed_filenames[0]:
            upload_div_children[ctx.triggered_id['index']] = dbc.Alert(f'Success! {completed_filenames[0]["name"]}', color = 'success')
        elif 'n_annotations' in completed_filenames[0]:
            upload_div_children[ctx.triggered_id['index']] = dbc.Alert(f'Success! {completed_filenames[0]["n_annotations"]} Annotations Added!',color = 'success')
        else:
            upload_div_children[ctx.triggered_id['index']] = dbc.Alert(f'Success!', color = 'success')

        # Checking if all required uploads are done:
        required_files = [i['name'] for i in selected_upload_type.input_files if i['required']]
        uploaded_files = [i['fusion_upload_name'] for i in upload_file_data['uploaded_files']]
        
        if len(set(required_files).difference(uploaded_files))==0:
            done_disabled = [False]
        else:
            done_disabled = [True]
        
        # Disabling upload type drop
        upload_type_disabled = [True]

        return upload_div_children, done_disabled, upload_type_disabled, [json.dumps(upload_file_data)]

    def populate_processing_plugins(self, done_clicked,upload_type,path_parts,upload_files_data, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        upload_type = get_pattern_matching_value(upload_type)
        selected_upload_type = self.dsa_upload_types[[i.name for i in self.dsa_upload_types].index(upload_type)]

        session_data = json.loads(session_data)
        upload_files_data = json.loads(get_pattern_matching_value(upload_files_data))
        # Modifying session data to include information on uploaded files (used by plugin inputs handler)
        session_data['uploaded_files'] = upload_files_data['uploaded_files']

        uploaded_items = [i['name'] for i in selected_upload_type.input_files if i['type']=='item']
        metadata_table_list = self.gen_metadata_table(selected_upload_type.required_metadata, uploaded_items)
        any_required = [i for i in selected_upload_type.required_metadata if type(i)==dict]
        any_required = any([i['required'] for i in any_required if 'required' in i])

        # Getting input components for the processing plugins
        processing_plugin_children = self.plugin_inputs_handler.update_layout(
            session_data=session_data,
            use_prefix=True,
            plugin_groups=selected_upload_type.processing_plugins
        )

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
                                children = processing_plugin_children
                            ),
                            html.Div(
                                id = {'type': f'{self.component_prefix}-dsa-uploader-all-plugins-run-status','index': 0},
                                children = []
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
                    req_meta_check.append(not d['Value']=='' and not d['Target']=='')
        
        submit_disable = not all(req_meta_check)

        return [submit_disable]

    def add_row_custom_metadata(self, clicked, custom_metadata):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        # Just appending a new blank row to the current data
        custom_metadata.append(
            {'Target': '', 'Key': '', 'Value': ''}
        )

        return custom_metadata

    def submit_metadata(self, clicked, upload_files_data, tables_data, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        upload_files_data = json.loads(get_pattern_matching_value(upload_files_data))['uploaded_files']
        upload_names = [i['fusion_upload_name'] for i in upload_files_data]

        user_external_token = self.get_user_external_token(session_data)

        target_dict = {}
        for t in tables_data:
            for row in t:
                if not row['Target']=='':
                    target_id = upload_files_data[upload_names.index(row['Target'])]['itemId']

                    if target_id in target_dict:
                        target_dict[target_id] = target_dict[target_id] | {row['Key']:row['Value']}
                    else:
                        target_dict[target_id] = {row['Key']:row['Value']}

        status_div = []
        for t in list(target_dict.keys()):
            success = self.handler.add_metadata(
                item = t,
                metadata = target_dict[t],
                user_token = user_external_token
            )
            
            if success:
                status_div.append(dbc.Alert(f'Metadata added to {t}!',color = 'success'))
            else:
                status_div.append(dbc.Alert(f'Error adding metadata to item: {t}',color='danger'))

        return status_div




