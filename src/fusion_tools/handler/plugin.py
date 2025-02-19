"""Components related to DSA Plugins
"""

import requests
import json
import numpy as np
import lxml.etree as ET

from typing_extensions import Union
import girder_client

from PIL import Image
from io import BytesIO

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform

from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools import DSATool
from fusion_tools.handler.resource_selector import DSAResourceSelector

from girder_job_sequence import Job, Sequence
from girder_job_sequence.utils import from_list

PARAMETER_TAGS = ['integer','float','double','boolean','string','integer-vector','float-vector','double-vector','string-vector',
                'integer-enumeration','float-enumeration','double-enumeration','string-enumeration','file','directory','image',
                'geometry','point','pointfile','region','table','transform']

class DSAPluginGroup(DSATool):
    """Blueprint object which creates input layout for sets of plugins/sequences of plugins

    :param DSATool: Class for components that integrate with DSA
    :type DSATool: None
    """
    def __init__(self,
                 handler:None
                ):
        
        super().__init__()
        self.handler = handler

    def __str__(self):
        return 'DSA Plugin Group'

    def load(self, component_prefix: int):
        
        self.component_prefix = component_prefix

        self.title = 'DSA Plugin Group'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()
    
    def load_plugin(self, plugin_dict:dict, session_data:dict, component_index:int, sequence=False):
        
        exe_dict = None
        self.handler.gc.setToken(
            session_data['current_user']['token']
        )

        try:
            job_obj = Job(
                self.handler.gc,
                plugin_id = plugin_dict['_id'] if '_id' in plugin_dict else None,
                docker_image = plugin_dict['image'] if 'image' in plugin_dict else None,
                cli = plugin_dict['name'] if 'name' in plugin_dict else None,
                input_args = plugin_dict['input_args'] if 'input_args' in plugin_dict else []
            )

            exe_dict = job_obj.executable_dict
        except girder_client.HttpError:
            # Error getting this plugin
            return dbc.Alert(f'Error getting plugin: {plugin_dict}',color='danger')

        if 'input_args' in plugin_dict:
            # Parsing through the provided input_args and pulling them out of the plugin_parameters
            inputs_list = []
            for in_arg in plugin_dict['input_args']:
                if type(in_arg)==str:
                    # Looking for the input with this name and setting default from input (if specified)
                    exe_input = self.find_executable_input(exe_dict,in_arg)
                    exe_input['disabled'] = False
                elif type(in_arg)==dict:
                    # Looking for the input with in_arg['name'] and setting default from in_arg
                    exe_input = self.find_executable_input(exe_dict, in_arg['name'])
                    if exe_input is None:
                        # For "output" channel files, {parameter_name}_folder is also needed but won't be specified in the XML
                        exe_input = {
                            'name': in_arg['name'],
                            'label': in_arg['name'],
                            'description': 'Output file folder',
                            'type': 'directory'
                        }
                    
                    exe_input['disabled'] = in_arg['disabled'] if 'disabled' in in_arg else False

                    if 'default' in in_arg:
                        if type(in_arg['default']) in [int,float,str]:
                            exe_input['default'] = in_arg['default']
                        elif type(in_arg['default'])==dict:
                            # Defining input from uploaded items/file id
                            if 'value' in in_arg['default']:
                                exe_input['default'] = in_arg['default']
                            
                            elif in_arg['default']['type'] in ['upload_folder','upload_item']:
                                # Find uploaded_items:
                                uploaded_items = [i for i in session_data['uploaded_files'] if i['_modelType']=='item']
                                # Which one matches the default name
                                uploaded_item_names = [i['name'] for i in uploaded_items]
                                if in_arg['default']['name'] in uploaded_item_names:
                                    matching_item = uploaded_items[uploaded_item_names.index(in_arg['default']['name'])]

                                    if in_arg['default']['type']=='upload_folder':
                                        folder_info = self.handler.get_folder_info(matching_item['folderId'],session_data['current_user']['token'])
                                        exe_input['default'] = {
                                            'name': folder_info['name'],
                                            '_id': folder_info['_id']
                                        }
                                    elif in_arg['default']['type']=='upload_item':
                                        exe_input['default'] = {
                                            'name': matching_item['name'],
                                            '_id': matching_item['_id']
                                        }
                                    
                                else:
                                    exe_input['default'] = None
                            
                            elif in_arg['default']['type']=='upload_file':
                                uploaded_files = [i for i in session_data['uploaded_files'] if i['_modelType']=='file']
                                uploaded_file_names = [i['name'] for i in uploaded_files]
                                if in_arg['default']['name'] in uploaded_file_names:
                                    matching_file = uploaded_files[uploaded_file_names.index(in_arg['default']['name'])]
                                    exe_input['default'] = {
                                        'name': matching_file['name'],
                                        '_id': matching_file['_id']
                                    }
                                else:
                                    exe_input['default'] = None

                            elif in_arg['default']['type']=='upload_annotation':
                                uploaded_annotations = [i for i in session_data['uploaded_files'] if i['_modelType']=='annotation']

                                if 'fileName' in in_arg['default']:
                                    uploaded_parent_names = [i['parentName'] for i in uploaded_annotations]
                                    if in_arg['default']['fileName'] in uploaded_parent_names:
                                        matching_parent = uploaded_annotations[uploaded_parent_names.index(in_arg['default']['name'])]
                                        annotation_info = self.handler.get_annotation_names(matching_parent['_id'], user_token = session_data['current_user']['token'])

                                        if 'annotationName' in in_arg['default']:
                                            annotation_names = [i['annotation']['name'] for i in annotation_info]
                                            if in_arg['default']['annotationName'] in annotation_names:
                                                matching_annotation = annotation_info[annotation_names.index(in_arg['default']['annotationName'])]
                                                exe_input['default'] = {
                                                    'name': matching_annotation['annotation']['name'],
                                                    '_id': matching_annotation['_id']
                                                }
                                            else:
                                                exe_input['default'] = None
                                        elif 'annotationId' in in_arg['default']:
                                            annotation_ids = [i['_id'] for i in annotation_info]
                                            if in_arg['default']['annotationId'] in annotation_ids:
                                                matching_annotation = annotation_info[annotation_ids.index(in_arg['default']['annotationId'])]
                                                exe_input['default'] = {
                                                    'name': matching_annotation['annotation']['name'],
                                                    '_id': matching_annotation['_id']
                                                }
                                            else:
                                                exe_input['default'] = None
                                    else:
                                        exe_input['default'] = None

                                elif 'fileId' in in_arg['default']:
                                    uploaded_parent_ids = [i['_id'] for i in uploaded_annotations]
                                    if in_arg['default']['fileId'] in uploaded_parent_ids:
                                        matching_parent = uploaded_annotations[uploaded_parent_ids.index(in_arg['default']['fileId'])]
                                        annotation_info = self.handler.get_annotation_names(matching_parent['_id'], user_token = session_data['current_user']['token'])

                                        if 'annotationName' in in_arg['default']:
                                            annotation_names = [i['annotation']['name'] for i in annotation_info]
                                            if in_arg['default']['annotationName'] in annotation_names:
                                                matching_annotation = annotation_info[annotation_names.index(in_arg['default']['annotationName'])]
                                                exe_input['default'] = {
                                                    'name': matching_annotation['annotation']['name'],
                                                    '_id': matching_annotation['_id']
                                                }
                                            else:
                                                exe_input['default'] = None
                                        elif 'annotationId' in in_arg['default']:
                                            annotation_ids = [i['_id'] for i in annotation_info]
                                            if in_arg['default']['annotationId'] in annotation_ids:
                                                matching_annotation = annotation_info[annotation_ids.index(in_arg['default']['annotationId'])]
                                                exe_input['default'] = {
                                                    'name': matching_annotation['annotation']['name'],
                                                    '_id': matching_annotation['_id']
                                                }
                                            else:
                                                exe_input['default'] = None
                                    else:
                                        exe_input['default'] = None

                                else:
                                    exe_input['default'] = None

                            else:
                                exe_input['default'] = None
                        else:
                            exe_input['default'] = None
                    
                inputs_list.append(exe_input)
        else:
            inputs_list = []
            for ip in exe_dict['parameters']:
                # ip = input, ipp = input parameter
                inputs_list.extend([ipp | {'disabled': False} for ipp in ip['inputs']])

        # Now creating the interactive component (without component-prefix, can transform later)
        plugin_component = html.Div([
            dcc.Store(
                id = {'type': 'dsa-plugin-plugin-info-store','index': component_index},
                data = json.dumps({
                    '_id': job_obj.plugin_id,
                    'exe_dict': exe_dict.copy()
                }),
                storage_type = 'memory'
            ),
            dbc.Row([
                html.H5(
                    html.A(
                        exe_dict['title'],
                        target = '_blank',
                        href = exe_dict['documentation'] if 'documentation' in exe_dict else None
                    )
                )
            ]),
            html.Hr(),
            dbc.Row([
                exe_dict['description']
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
                        for author in exe_dict['author'].split(',')
                    ]
                )
            ]),
            html.Hr(),
            html.Div(
                dbc.Stack([
                    self.make_input_component(inp,inp_idx, sequence = sequence)
                    for inp_idx, inp in enumerate(inputs_list)
                ],direction='vertical',gap=2),
                style = {'maxHeight': '80vh','overflow':'scroll'}
            ),
            dbc.Button(
                'Submit Plugin',
                className = 'd-grid col-12 mx-auto',
                color = 'success',
                disabled = False,
                id = {'type': 'dsa-plugin-submit-button','index': component_index}
            ) if not sequence else html.Div()
        ])

        return plugin_component

    def find_executable_input(self, executable_dict, input_name)->dict:

        exe_input = None
        for p in executable_dict['parameters']:
            for inp in p['inputs']:
                if inp['name']==input_name:
                    exe_input = inp
                    break
        
        return exe_input

    def make_input_component(self, input_dict, input_index, sequence):
        
        input_desc_column = [
            dbc.Row(html.H6(input_dict['label'])),
            dbc.Row(html.P(input_dict['description']))
        ]

        if 'enumeration' in input_dict['type']:
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dcc.Dropdown(
                            options = [
                                {'label': i, 'value': i}
                                for i in input_dict['options']
                            ],
                            multi = False,
                            disabled = input_dict['disabled'],
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            id = {'type': 'dsa-plugin-input','index': input_index} if not sequence else {'type': 'dsa-plugin-sequence-input','index': input_index},
                            style = {'width': '100%'}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['region','geometry','point']:
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        'This component is still in progress'
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['file','directory','image']:

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        self.make_file_component(
                            select_type = input_dict['type'],
                            value = input_dict['default'] if 'default' in input_dict else "",
                            component_index = input_index,
                            disabled = input_dict['disabled'],
                            sequence = sequence
                        )
                    ], md = 7)
                ]),
                html.Hr()
            ])      
        elif input_dict['type']=='boolean':
            # This input type cannot be disabled
            if input_dict['default'] is None:
                input_dict['default'] = False

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dcc.RadioItems(
                            options = [
                                {'label': 'True', 'value': 1},
                                {'label': 'False','value': 0}
                            ],
                            value = 1 if input_dict['default'] else 0,
                            id = {'type': 'dsa-plugin-input','index': input_index} if not sequence else {'type': 'dsa-plugin-sequence-input','index': input_index}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['integer','float','string','double'] or 'vector' in input_dict['type']:
            if not 'constraints' in input_dict:
                input_dict['constraints'] = None

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dcc.Input(
                            type = 'text' if input_dict['type']=='string' else 'number',
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            maxLength = 1000,
                            disabled = input_dict['disabled'],
                            min = input_dict['constraints']['min'] if not input_dict['constraints'] is None else [],
                            max = input_dict['constraints']['max'] if not input_dict['constraints'] is None else [],
                            #step = input_dict['constraints']['step'] if not input_dict['constraints'] is None else [],
                            id = {'type': 'dsa-plugin-input','index': input_index} if not sequence else {'type': 'dsa-plugin-sequence-input','index': input_index},
                            style = {'width': '100%'}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])

        return input_component

    def make_file_component(self, select_type: str, value: Union[str,dict], component_index:int,disabled:bool,sequence:bool=False):

        if type(value)==dict:
            if all([i in value for i in ['name','_id']]):
                selector_value = value['name']
                input_value = value['_id']
            elif 'value' in value:
                selector_value = value['value']
                input_value = value['value']
        else:
            selector_value = value
            input_value = value

        file_component = html.Div([
            dbc.InputGroup([
                dbc.InputGroupText(
                    f'{select_type}: '
                ),
                dbc.Input(
                    id = {'type': 'dsa-plugin-resource-selector-input','index': component_index},
                    placeholder = select_type,
                    type = 'text',
                    required = True,
                    value = selector_value,
                    maxLength = 1000,
                    disabled = True
                ),
                dbc.Input(
                    id = {'type': 'dsa-plugin-input','index': component_index} if not sequence else {'type': 'dsa-plugin-sequence-input','index': component_index},
                    value = input_value,
                    style = {'display': 'none'}
                ),
                dbc.Button(
                    children = [
                        html.I(
                            className = 'fa-solid fa-file'
                        )
                    ],
                    id = {'type': 'dsa-plugin-resource-selector-open-modal','index': component_index} if not sequence else {'type': 'dsa-plugin-sequence-resource-selector-open-modal','index': component_index},
                    disabled = disabled
                )
            ])
        ])

        return file_component

    def update_layout(self, session_data: dict, use_prefix:bool, plugin_groups: Union[list,dict,None]=None):
        """Updating layout of the plugin group blueprint, creates accordions for each singular plugin and outlined accordions corresponding to sequences.
        For more information on plugin sequences, see: https://github.com/spborder/girder-job-sequence

        :param session_data: Current session data, includes current user information ('_id', 'token')
        :type session_data: dict
        :param use_prefix: Used to indicate whether or not this is an initialization (False) of the layout or just updating components (True)
        :type use_prefix: bool
        :param plugin_groups: Either a list of plugins and sequence(s) or dictionary for single plugin, defaults to None
        :type plugin_groups: Union[list,dict,None], optional
        """

        plugin_components = []
        if not plugin_groups is None:
            if type(plugin_groups)==dict:
                plugin_groups = [plugin_groups]
            
            plugin_count = 0
            sequence_plugin_count = 0
            sequence_count = 0
            for p_idx, p in enumerate(plugin_groups):
                if type(p)==dict:
                    # This is a singular job that can be executed independently of any other processing plugin
                    p_component = self.load_plugin(
                        plugin_dict = p,
                        session_data = session_data,
                        component_index = plugin_count,
                        sequence=False
                    )

                    plugin_components.append(
                        dmc.AccordionItem([
                            dmc.AccordionControl(p['name']),
                            dmc.AccordionPanel(
                                dbc.Stack([
                                    p_component,
                                    html.Div(
                                        id = {'type': 'dsa-plugin-submit-status-div','index': plugin_count},
                                        children = []
                                    )
                                ])
                            )
                        ],value=f'dsa-plugin-{plugin_count}',style={'marginBottom':'10px','marginTop': '10px'})
                    )
                    plugin_count += 1
                elif type(p)==list:
                    # This is a sequential job where multiple jobs are submitted to a sequence handler at the same time and executed one-by-one
                    sequence_color = f'rgb({np.random.randint(0,255)},{np.random.randint(0,255)},{np.random.randint(0,255)})'
                    sequence_components = []
                    for j_idx,j in enumerate(p):
                        j_component = self.load_plugin(
                            plugin_dict = j,
                            session_data = session_data,
                            component_index = sequence_plugin_count,
                            sequence=True
                        )

                        sequence_components.append(
                            dmc.AccordionItem([
                                dmc.AccordionControl(j['name']),
                                dmc.AccordionPanel(
                                    dbc.Stack([
                                        j_component
                                    ])
                                )
                            ],value = f'dsa-plugin-sequence-{sequence_count}-{j_idx}')
                        )
                        sequence_plugin_count += 1
                    
                    sequence_components.append(
                        dmc.AccordionItem([
                            dmc.AccordionControl(f'Submit Sequence {sequence_count+1}'),
                            dmc.AccordionPanel(
                                dbc.Stack([
                                    dbc.Button(
                                        'Submit Sequence',
                                        id = {'type': 'dsa-plugin-sequence-submit-button','index': sequence_count},
                                        className = 'd-grid col-12 mx-auto',
                                        n_clicks = 0,
                                        color = 'success',
                                        disabled = False
                                    ),
                                    html.Div(
                                        id = {'type': 'dsa-plugin-sequence-status-div','index': sequence_count},
                                        children = []
                                    )
                                ])
                            )
                        ], value = f'dsa-sequence-{sequence_count}-submit',style={'marginBottom':'10px'})
                    )

                plugin_components.append(
                    dbc.Stack(
                        children = [
                            html.H5(f'Sequence {sequence_count+1} Plugins'),
                            dmc.Accordion(
                                id = {'type': 'dsa-plugin-sequence-accordion','index': sequence_count},
                                children = sequence_components,
                            )
                        ],
                        style = {
                            'padding': '10px 10px 10px 10px',
                            'outline-style':'dashed',
                            'outline-color': sequence_color
                        }
                    )
                )
                sequence_count += 1


        layout = html.Div([
            dbc.Card([
                dbc.CardHeader(self.title),
                dbc.CardBody([
                    dbc.Row(
                        'Below are separate input components for running a desired set of plugins. Individual plugins can be executed independently while plugins that are part of a Sequence are submitted all at once.'
                    ),
                    html.Hr(),
                    html.Div(
                        id = {'type': 'dsa-plugin-plugin-parent-div','index': 0},
                        children = plugin_components
                    )
                ])
            ])
        ],style = {'maxHeight': '90vh','overflow': 'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(layout)

        return layout

    def gen_layout(self, session_data:dict):
        """Initializing layout of blueprint.

        :param session_data: Dictionary containing information from current session
        :type session_data: dict
        """

        self.blueprint.layout = self.update_layout(session_data, use_prefix=False)

    def get_callbacks(self):
        """Registering callbacks with blueprint object.
        """

        # Callback for running individual plugin
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-submit-button','index': MATCH},'n_clicks'),
            ],
            [
                State({'type': 'dsa-plugin-plugin-info-store','index': ALL},'data'),
                State({'type': 'dsa-plugin-input','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-submit-status-div','index': MATCH},'children'),
                Output({'type': 'dsa-plugin-submit-button','index': MATCH},'disabled'),
            ],
            prevent_initial_call = True
        )(self.submit_plugin)

        # Callback for running sequence
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-sequence-submit-button','index': MATCH},'n_clicks')
            ],
            [
                State({'type': 'dsa-plugin-sequence-info-store','index': ALL},'data'),
                State({'type': 'dsa-plugin-sequence-input','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-runner-submit-status-div','index': MATCH},'children'),
                Output({'type': 'dsa-plugin-runner-submit-button','index': MATCH},'disabled')
            ],
            prevent_initial_call = True
        )(self.submit_sequence)

        # Callback for opening the resource selector modal with information

        # Callback for creating a wildcard input

    def submit_plugin(self):
        pass

    def submit_sequence(self):
        pass

    def create_wildcard_input(self):
        pass





class DSAPluginRunner(DSATool):
    """Handler for DSAPluginRunner component, letting users specify input arguments to plugins to run on connected DSA instance.

    :param DSATool: Class for components that integrate with DSA.
    :type DSATool: None
    """
    def __init__(self,
                 handler: None
                 ):
        
        super().__init__()
        self.handler = handler


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
        
        self.handler.gc.setToken(
            session_data['current_user']['token']
        )

        job_obj = Job(
            self.handler.gc,
            plugin_id = None,
            docker_image = plugin_info['image'],
            cli = plugin_info['name'],
            input_args = plugin_info['input_args']
        )

        exe_dict = job_obj.executable_dict
        if not exe_dict is None:
            plugin_info = {
                '_id': job_obj.plugin_id,
                'executable_dict': exe_dict.copy()
            }
        else:
            plugin_info = None


        return exe_dict, plugin_info

    def load_plugin(self, plugin_dict, session_data, uploaded_files_data, component_index, add_run_button=True):

        # Each plugin_dict will have 'name', 'image', and 'input_args'
        # 'name' and 'image' are used to identify the CLI
        # 'input_args' is a list of either strings or dictionaries limiting which arguments the user can adjust

        # Getting plugin xml (have to be logged in to get)
        if not 'executable_dict' in plugin_dict:
            cli_dict, plugin_info = self.get_executable_dict(plugin_dict,session_data)
        else:
            cli_dict = plugin_dict['executable_dict']
            plugin_info = plugin_dict

        if cli_dict is None:
            return dbc.Alert(f'Error loading plugin: {plugin_dict}',color = 'danger')

        if 'input_args' in plugin_dict:
            # Parsing through the provided input_args and pulling them out of the plugin parameters
            inputs_list = []
            for in_arg in plugin_dict['input_args']:
                if type(in_arg)==str:
                    # Looking for the input with this name and setting default from input (if specified)
                    exe_input = self.find_executable_input(cli_dict, in_arg)
                    exe_input['disabled'] = False
                elif type(in_arg)==dict:
                    # Looking for the input with in_arg['name'] and setting default from in_arg
                    exe_input = self.find_executable_input(cli_dict,in_arg['name'])
                    if exe_input is None:
                        # For "output" channel files, {parameter_name}_folder is also needed but won't be specified in the XML
                        if '_folder' in in_arg['name']:
                            exe_input = {
                                'name': in_arg['name'],
                                'label': in_arg['name'],
                                'description': 'Output file folder',
                                'type': 'directory'
                            }

                    exe_input['disabled'] = in_arg['disabled'] if 'disabled' in in_arg else False
                    if 'default' in in_arg:
                        if type(in_arg['default']) in [int,float,str]:
                            exe_input['default'] = in_arg['default']
                        elif type(in_arg['default'])==dict:
                            # Defining input from uploaded file item/file ID
                            # This one isn't used in the default DSAPluginRunner but is accessed from DSAUploader
                            if 'value' in in_arg['default']:
                                exe_input['default'] = in_arg['default']

                            elif in_arg['default']['type']=='upload_folder':
                                # Find uploaded item:
                                ex_item = [i for i in uploaded_files_data['uploaded_files'] if 'itemId' in i][0]
                                ex_itemId = ex_item['itemId'] if 'itemId' in ex_item else ex_item['_id']

                                ex_item_info = self.handler.get_item_info(ex_itemId, session_data['current_user']['token'])
                                folder_info = self.handler.get_folder_info(ex_item_info['folderId'],session_data['current_user']['token'])
                                exe_input['default'] = {
                                    'name': folder_info['name'],
                                    '_id': folder_info['_id']
                                }
                            
                            elif in_arg['default']['type']=='input_file':
                                input_file_arg = in_arg['default']['name']
                                input_file_arg_idx = [i['fusion_upload_name'] for i in uploaded_files_data['uploaded_files']].index(input_file_arg)
                                exe_input['default'] = {
                                    'name': uploaded_files_data['uploaded_files'][input_file_arg_idx]['name'],
                                    '_id': uploaded_files_data['uploaded_files'][input_file_arg_idx]['_id']
                                }

                            elif in_arg['default']['type']=='input_annotation':
                                input_annotation_arg = in_arg['default']['name']
                                input_file_arg_idx = [i['fusion_upload_name'] for i in uploaded_files_data['uploaded_files']].index(input_annotation_arg)
                                item_id = uploaded_files_data['uploaded_files'][input_file_arg_idx]['parentId']
                                annotation_names = self.handler.get_annotation_names(
                                    item = item_id,
                                    user_token = session_data['current_user']['token']
                                )
                                exe_input['default'] = ','.join(annotation_names)

                            elif in_arg['default']['type']=='output_file':
                                pass

                            elif in_arg['default']['type']=='output_annotation':
                                pass

                else:
                    raise TypeError
                
                inputs_list.append(exe_input)
        else:
            inputs_list = []
            for p in cli_dict['parameters']:
                inputs_list.extend([j | {'disabled': False} for j in p['inputs']])

        # Now creating the interactive component (without component-prefix, (can transform later))
        plugin_component = html.Div([
            dcc.Store(
                id = {'type': 'dsa-plugin-runner-plugin-info-store','index': component_index} if add_run_button else {'type': 'dsa-plugin-runner-sequence-info-store','index': component_index},
                data = json.dumps(plugin_info),
                storage_type='memory'
            ),
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
                    self.make_input_component(inp,inp_idx, sequence=not add_run_button)
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
                disabled = False,
                id = {'type': 'dsa-plugin-runner-submit-button','index': component_index}
            ) if add_run_button else html.Div()
        ])

        return plugin_component

    def make_file_component(self,select_type:str, value: Union[str,dict], component_index:int, disabled: bool, sequence: bool = False):
        #TODO: Modal containing interactive components for selecting folders/files
        #TODO: if this component is for a parameter in the with "channel" = "output" then it needs two parameters:
        # The file name (str) and the folder _id with an additional parameter "{parameter_name}_folder"
        
        if type(value)==dict:
            if all([i in value for i in ['name','_id']]):
                selector_value = value['name']
                input_value = value['_id']
            elif 'value' in value:
                selector_value = value['value']
                input_value = value['value']
        else:
            selector_value = value
            input_value = value


        file_component = html.Div([
            dbc.Modal(
                id = {'type': 'dsa-plugin-runner-file-selector-modal','index':component_index},
                children = [
                    html.Div(
                        id = {'type': 'dsa-plugin-runner-file-selector-div','index':component_index},
                        children = []
                    )
                ],
                is_open = False
            ),
            dbc.InputGroup([
                dbc.InputGroupText(
                    f'{select_type}: '
                ),
                dbc.Input(
                    id = {'type': 'dsa-plugin-runner-file-selector-input','index': component_index},
                    placeholder = select_type,
                    type = 'text',
                    required = True,
                    value = selector_value,
                    maxLength = 1000,
                    disabled=True
                ),
                dbc.Input(
                    id = {'type': 'dsa-plugin-runner-input','index': component_index} if not sequence else {'type': 'dsa-plugin-runner-sequence-input','index': component_index},
                    value = input_value,
                    style = {'display': 'none'}
                ),
                dbc.Button(
                    children = [
                        html.I(
                            className = 'fa-solid fa-file'
                        )
                    ],
                    id = {'type': 'dsa-plugin-runner-file-selector-open-modal','index': component_index},
                    disabled = disabled
                )
            ])
        ])

        return file_component

    def make_input_component(self, input_dict, input_index,sequence=False):

        # Input components will either be an Input, a Dropdown, a Slider, or a region selector (custom)
        input_desc_column = [
            dbc.Row(html.H6(input_dict['label'])),
            dbc.Row(html.P(input_dict['description']))
        ]
        
        if 'enumeration' in input_dict['type']:
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dcc.Dropdown(
                            options = [
                                {'label': i, 'value': i}
                                for i in input_dict['options']
                            ],
                            multi = False,
                            disabled = input_dict['disabled'],
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            id = {'type': 'dsa-plugin-runner-input','index': input_index} if not sequence else {'type': 'dsa-plugin-runner-sequence-input','index': input_index},
                            style = {'width': '100%'}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['region','geometry','point']:
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        'This component is still in progress'
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['file','directory','image']:

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        self.make_file_component(
                            select_type=input_dict['type'],
                            value = input_dict['default'] if 'default' in input_dict else "",
                            component_index=input_index,
                            disabled = input_dict['disabled'],
                            sequence = sequence
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type']=='boolean':
            # This input type cannot be disabled
            if input_dict['default'] is None:
                input_dict['default'] = False

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md = 5),
                    dbc.Col([
                        dcc.RadioItems(
                            options = [
                                {'label': 'True','value': 1},
                                {'label': 'False','value': 0}
                            ],
                            value = 1 if input_dict['default'] else 0,
                            id = {'type': 'dsa-plugin-runner-input','index': input_index} if not sequence else {'type': 'dsa-plugin-runner-sequence-input','index': input_index},
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])
        elif input_dict['type'] in ['integer','float','string','double'] or 'vector' in input_dict['type']:
            if not 'constraints' in input_dict:
                input_dict['constraints'] = None

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dcc.Input(
                            type = 'text' if input_dict['type']=='string' else 'number',
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            maxLength = 1000,
                            disabled = input_dict['disabled'],
                            min = input_dict['constraints']['min'] if not input_dict['constraints'] is None else [],
                            max = input_dict['constraints']['max'] if not input_dict['constraints'] is None else [],
                            #step = input_dict['constraints']['step'] if not input_dict['constraints'] is None else [],
                            id = {'type': 'dsa-plugin-runner-input','index': input_index} if not sequence else {'type': 'dsa-plugin-runner-sequence-input','index': input_index},
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

    def run_plugin_request(self, plugin_id, session_data, input_params_dict):
        
        request_output = requests.post(
            url = self.handler.gc.urlBase + f'slicer_cli_web/cli/{plugin_id}/run?token={session_data["current_user"]["token"]}',
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
            ],
            prevent_initial_call = True
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
            ],
            prevent_initial_call=True
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
            ],
            prevent_initial_call = True
        )(self.submit_plugin)

    def open_file_select_modal(self, clicked, is_open, session_data):

        print(ctx.triggered)
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        modal_children = []


        return not is_open, modal_children

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
                uploaded_files_data=None,
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


        plugin_cli_dict, plugin_info = self.get_executable_dict(selected_plugin,session_data)
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
                 handler):
        
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
        self.job_status_color_key = {
            '0': 'rgb(176,184,178)',
            '1': 'rgb(219,224,67)',
            '2': 'rgb(67,172,224)',
            '3': 'rgb(50,168,82)',
            '4': 'rgb(224,27,27)',
            '5': 'rgb(227,27,154)'
        }
    
        self.modal_className = 'mw-100 p-5'

    def __str__(self):
        return 'DSA Plugin Progress'

    def load(self,component_prefix:int):
        
        self.component_prefix = component_prefix

        self.title = 'DSA Plugin Progress'

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def generate_plugin_table(self, session_data:dict, offset:int, limit: int, next_clicks:int, prev_clicks:int, use_prefix:bool):

        # Getting all jobs for this user:
        user_jobs = self.handler.get_user_jobs(
            user_id = session_data['current_user']['_id'],
            user_token = session_data['current_user']['token'],
            offset = offset,
            limit = limit
        )

        job_properties = ['title','type','updated','when','status','_id']
        
        table_head = dmc.TableThead(
            dmc.TableTr(
                [
                    dmc.TableTh(i)
                    for i in job_properties
                ]
            )
        )

        if len(user_jobs)>0:
            table_rows = []
            for job_idx,job in enumerate(user_jobs):
                job_row = []
                for prop in job_properties:
                    if not prop=='status':
                        job_row.append(
                            dmc.TableTd(job[prop])
                        )
                    else:
                        job_row.append(
                            dmc.TableTd(self.job_status_key[str(job[prop])],style = {'background': self.job_status_color_key[str(job[prop])]})
                        )

                # Adding logs/cancel buttons
                job_row.append(
                    dmc.TableTd(
                        dbc.Button(
                            'Logs',
                            color = 'warning',
                            id = {'type': 'dsa-plugin-progress-get-logs','index': job_idx},
                            n_clicks = 0
                        )
                    )
                )

                job_row.append(
                    dmc.TableTd(
                        dbc.Button(
                            'Cancel',
                            color = 'danger',
                            id = {'type': 'dsa-plugin-progress-cancel-job','index': job_idx},
                            n_clicks = 0
                        )
                    )
                )

                table_rows.append(
                    dmc.TableTr(job_row, id = {'type': 'dsa-plugin-progress-table-row','index': job_idx})
                )

        else:
            if next_clicks>0:
                table_rows.append(
                    dmc.Tr([
                        'You have exceed all of the jobs for this user!'
                    ])
                )
            else:
                table_rows.append(
                    dmc.Tr([
                        'You have not run any jobs yet!'
                    ])
                )

        table_caption = dmc.TableCaption([
            dbc.Stack([
                dbc.Button(
                    'Load Previous 5 jobs',
                    color = 'secondary',
                    n_clicks = prev_clicks,
                    className = 'd-grid col-6 mx-auto',
                    id = {'type': 'dsa-plugin-progress-load-prev-jobs','index': 0}
                ),
                dbc.Button(
                    'Load Next 5 jobs',
                    color = 'primary',
                    n_clicks = next_clicks,
                    className = 'd-grid col-6 mx-auto',
                    id = {'type': 'dsa-plugin-progress-load-next-jobs','index': 0}
                )
            ],direction = 'horizontal',gap=2)
        ])

        table_body = dmc.TableTbody(table_rows)

        if use_prefix:
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(table_head)
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(table_body)
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(table_caption)

        return [table_head, table_body, table_caption]

    def update_layout(self, session_data:dict, use_prefix:bool):
        
        if 'current_user' in session_data:
            running_plugins = self.generate_plugin_table(session_data, 0, 5, 0, 0, False)
            running_plugins = dmc.Table(
                running_plugins,
                id = {'type': 'dsa-plugin-progress-table-content','index': 0}
            )

        else:
            running_plugins = dbc.Alert(
                'You must be logged in to view running plugins!',
                color = 'warning'
            )

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
                    dbc.Row(
                        html.Div(
                            running_plugins,
                            style = {'maxHeight': '40vh','overflow': 'scroll'}
                        )
                    ),
                    dbc.Row(
                        html.Div(
                            id = {'type': 'dsa-plugin-progress-logs-content','index': 0},
                            children = []
                        )
                    )
                ])
            )
        ])

        if use_prefix:
            PrefixIdTransform(prefix=self.component_prefix).transform_layout(layout)

        return layout

    def gen_layout(self,session_data:Union[dict,None]):
        
        self.blueprint.layout = self.update_layout(session_data=session_data,use_prefix=False)

    def get_callbacks(self):

        # Callback for loading next/prev jobs
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-progress-load-next-jobs','index': ALL},'n_clicks'),
                Input({'type': 'dsa-plugin-progress-load-prev-jobs','index': ALL},'n_clicks')
            ],
            [
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-progress-table-content','index':ALL},'children')
            ],
            prevent_initial_call = True
        )(self.load_new_jobs)

        # Callback for cancelling plugin/loading logs
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-progress-get-logs','index': ALL},'n_clicks'),
                Input({'type': 'dsa-plugin-progress-cancel-job','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-plugin-progress-table-row','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-progress-logs-content','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.get_logs_or_cancel)

    def load_new_jobs(self, next_clicked, prev_clicked, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        next_clicked = get_pattern_matching_value(next_clicked)
        prev_clicked = get_pattern_matching_value(prev_clicked)
        if prev_clicked>next_clicked:
            next_clicked = 0
            prev_clicked = 0
            offset = 0
        
        else:
            offset = next_clicked - prev_clicked
       
        session_data = json.loads(session_data)
        new_table_content = self.generate_plugin_table(
                                session_data = session_data,
                                offset = offset,
                                limit = 5,
                                next_clicks = next_clicked,
                                prev_clicks = prev_clicked,
                                use_prefix = True
                            )


        return [new_table_content]

    def get_logs_or_cancel(self, logs_clicked, cancel_clicked, table_rows, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)

        if 'dsa-plugin-progress-get-logs' in ctx.triggered_id['type']:
            row_clicked = ctx.triggered_id['index']
            job_id = table_rows[row_clicked][5]['props']['children']

            job_logs = self.handler.get_specific_job(
                job_id = job_id,
                user_token = session_data['current_user']['token']
            )

            job_logs_div = html.Div(
                [
                    html.Div([html.P(i) for i in line.split('\n')])
                    for line in job_logs['log']
                ],
                style = {'maxHeight': '20vh','overflow': 'scroll'}
            )

        elif 'dsa-plugin-progress-cancel-job' in ctx.triggered_id['type']:
            row_clicked = ctx.triggered_id['index']
            job_id = table_rows[row_clicked][5]['props']['children']

            cancel_response = self.handler.cancel_job(
                job_id = job_id,
                user_token = session_data['current_user']['token']
            )

            job_logs_div = html.Div(
                'Cancel request sent! Close and re-open to see updated status'
            )


        return [job_logs_div]
    






















