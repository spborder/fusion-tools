"""Components related to DSA Plugins
"""

import requests
import json
import numpy as np
import uuid

from typing_extensions import Union
import girder_client


# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform

from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.components.base import DSATool
from fusion_tools.handler.resource_selector import DSAResourceSelector

from girder_job_sequence import Job, Sequence
from girder_job_sequence.utils import from_list, from_dict
import threading

PARAMETER_TAGS = ['integer','float','double','boolean','string','integer-vector','float-vector','double-vector','string-vector',
                'integer-enumeration','float-enumeration','double-enumeration','string-enumeration','file','directory','image',
                'geometry','point','pointfile','region','table','transform']

class DSAPluginGroup(DSATool):
    """Blueprint object which creates input layout for sets of plugins/sequences of plugins

    :param DSATool: Class for components that integrate with DSA
    :type DSATool: None
    """

    title = 'DSA Plugin Group'
    description = ''


    def __init__(self,
                 handler:None
                ):
        
        super().__init__()
        self.handler = handler

    def load(self, component_prefix: int):
        
        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}',escape = lambda input_id: self.prefix_escape(input_id)),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

        # Adding DSAResourceSelector to DSAPluginGroup
        self.resource_selector = DSAResourceSelector(
            handler = self.handler
        )
        self.resource_selector.load(self.component_prefix)
        self.resource_selector.gen_layout({})

        #TODO: Either add a region selector to DSAResourceSelector or create a separate region selector component
    
    def load_plugin(self, plugin_dict:dict, session_data:dict, component_index:int, sequence=False):
        

        user_external_token = self.get_user_external_token(session_data)
        exe_dict = None
        self.handler.gc.setToken(
            user_external_token
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
                                uploaded_items = [i for i in session_data['uploaded_files'] if i['_modelType']=='file']
                                # Which one matches the default name
                                uploaded_item_names = [i['fusion_upload_name'] for i in uploaded_items]
                                if in_arg['default']['name'] in uploaded_item_names:
                                    matching_item = uploaded_items[uploaded_item_names.index(in_arg['default']['name'])]
                                    matching_item_info = self.handler.get_item_info(matching_item['itemId'],user_external_token)
                                    if in_arg['default']['type']=='upload_folder':
                                        folder_info = self.handler.get_folder_info(matching_item_info['folderId'],user_external_token)
                                        exe_input['default'] = {
                                            'name': folder_info['name'],
                                            '_id': folder_info['_id']
                                        }
                                    elif in_arg['default']['type']=='upload_item':
                                        exe_input['default'] = {
                                            'name': matching_item_info['name'],
                                            '_id': matching_item_info['_id']
                                        }
                                    
                                else:
                                    exe_input['default'] = None
                            
                            elif in_arg['default']['type']=='upload_file':
                                uploaded_files = [i for i in session_data['uploaded_files'] if i['_modelType']=='file']
                                uploaded_file_names = [i['fusion_upload_name'] for i in uploaded_files]
                                if in_arg['default']['name'] in uploaded_file_names:
                                    matching_file = uploaded_files[uploaded_file_names.index(in_arg['default']['name'])]
                                    exe_input['default'] = {
                                        'name': matching_file['name'],
                                        '_id': matching_file['_id']
                                    }
                                else:
                                    exe_input['default'] = None
                            
                            elif in_arg['default']['type']=='intermediate_file':
                                # This is for creating a wildcard input
                                if 'wildcard' in in_arg['default']:
                                    exe_input['default'] = {
                                        'name': in_arg['default']['wildcard'],
                                        '_id': in_arg['default']['wildcard']
                                    }
                                if 'transform' in in_arg['default']:
                                    base = in_arg['default']['transform']['base']
                                    uploaded_files = [i for i in session_data['uploaded_files'] if i['_modelType']=='file']
                                    uploaded_file_names = [i['fusion_upload_name'] for i in uploaded_files]
                                    if base in uploaded_file_names:
                                        matching_file = uploaded_files[uploaded_file_names.index(base)]

                                        if 'ext' in in_arg['default']['transform']:
                                            old_ext = matching_file['name'].split('.')[-1]
                                            new_name = matching_file['name'].replace(f'.{old_ext}',in_arg['default']['transform']['ext'])

                                            exe_input['default'] = {
                                                'name': new_name,
                                                '_id': "{{'type':'file','item_type':'_id','item_query':'"+matching_file['itemId']+"','file_type': 'fileName','file_query':'"+new_name+"'}}"
                                            }

                                        elif 'replace' in in_arg['default']['transform']:
                                            replace_str = in_arg['default']['transform']['replace']
                                            new_name = matching_file['name'].replace(replace_str[0],replace_str[1])

                                            exe_input['default'] = {
                                                'name': new_name,
                                                '_id': "{{'type':'file','item_type':'_id','item_query':'"+matching_file['itemId']+"','file_type':'fileName','file_query':'"+new_name+"'}}"
                                            }

                                            
                                        else:
                                            exe_input['default'] = None

                                    else:
                                        exe_input['default'] = None

                            elif in_arg['default']['type']=='upload_annotation':
                                uploaded_annotations = [i for i in session_data['uploaded_files'] if i['_modelType']=='annotation']

                                if 'fileName' in in_arg['default']:
                                    uploaded_parent_names = [i['parentName'] for i in uploaded_annotations]
                                    if in_arg['default']['fileName'] in uploaded_parent_names:
                                        matching_parent = uploaded_annotations[uploaded_parent_names.index(in_arg['default']['name'])]
                                        annotation_info = self.handler.get_annotation_names(matching_parent['_id'], user_token = user_external_token)

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
                                        annotation_info = self.handler.get_annotation_names(matching_parent['_id'], user_token = user_external_token)

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

                            elif in_arg['default']['type']=='output_file':
                                # This will need fileName and folderId keys
                                output_file_name = in_arg['default']['fileName']
                                output_folder_id = in_arg['default']['folderId']

                                exe_input['default'] = {}
                                if type(output_file_name)==str:
                                    exe_input['default']['fileName'] = output_file_name
                                elif type(output_file_name)==dict:
                                    reference = output_file_name['name']
                                    uploaded_items = [i for i in session_data['uploaded_files'] if i['_modelType']=='file']
                                    # Which one matches the default name
                                    uploaded_item_names = [i['fusion_upload_name'] for i in uploaded_items]
                                    if reference in uploaded_item_names:
                                        matching_item = uploaded_items[uploaded_item_names.index(reference)]
                                        matching_item_info = self.handler.get_item_info(matching_item['itemId'],user_external_token)

                                        item_name = matching_item_info['name']
                                        # Could do something with this, add a _output.{ref_ext} or something if a new extension isn't provided
                                        ref_ext = item_name.split('.')[-1]
                                        if 'ext' in output_file_name:
                                            new_ext = output_file_name['ext'] if '.' in output_file_name['ext'] else f'.{output_file_name["ext"]}'
                                            if '.' in item_name:
                                                exe_input['default']['fileName'] = '.'.join(item_name.split('.')[:-1])+new_ext
                                            else:
                                                exe_input['default']['fileName'] = item_name+new_ext
                                        else:
                                            exe_input['default']['fileName'] = item_name

                                if type(output_folder_id)==str:
                                    exe_input['default']['folderId'] = output_folder_id
                                elif type(output_folder_id)==dict:
                                    reference = output_folder_id['name']
                                    uploaded_items = [i for i in session_data['uploaded_files'] if i['_modelType']=='file']
                                    # Which one matches the default name
                                    uploaded_item_names = [i['fusion_upload_name'] for i in uploaded_items]
                                    if reference in uploaded_item_names:
                                        matching_item = uploaded_items[uploaded_item_names.index(reference)]
                                        matching_item_info = self.handler.get_item_info(matching_item['itemId'],user_external_token)
                                        folder_info = self.handler.get_folder_info(matching_item_info['folderId'],user_external_token)

                                        exe_input['default']['folderId'] = folder_info['_id']
                                    else:
                                        exe_input['default'] = None
                                else:
                                    exe_input['default'] = None

                            else:
                                exe_input['default'] = None
                        else:
                            exe_input['default'] = None
                
                if not sequence:
                    inputs_list.append(exe_input | {'plugin_id': job_obj.plugin_id, 'unique_plugin_id': plugin_dict["unique_plugin_id"]})
                else:
                    inputs_list.append(exe_input | {'plugin_id': job_obj.plugin_id, 'unique_plugin_id': plugin_dict["unique_plugin_id"], 'sequence_id': plugin_dict['sequence_id']})
        else:
            inputs_list = []
            for ip in exe_dict['parameters']:
                # ip = input, ipp = input parameter
                if not sequence:
                    inputs_list.extend([ipp | {'disabled': False, 'plugin_id': job_obj.plugin_id, 'unique_plugin_id': plugin_dict['unique_plugin_id']} for ipp in ip['inputs']])
                else:
                    inputs_list.extend([ipp | {'disabled': False, 'plugin_id': job_obj.plugin_id, 'unique_plugin_id': plugin_dict['unique_plugin_id'], 'sequence_id': plugin_dict['sequence_id']} for ipp in ip['inputs']])


        # Now creating the interactive component (without component-prefix, can transform later)
        # https://stackoverflow.com/questions/21716940/is-there-a-way-to-track-the-number-of-times-a-function-is-called
        file_input_idx = [0]
        plugin_component = html.Div([
            dcc.Store(
                id = {'type': 'dsa-plugin-plugin-info-store','index': component_index} if not sequence else {'type': 'dsa-plugin-sequence-plugin-info-store','index': component_index},
                data = json.dumps({
                    '_id': job_obj.plugin_id,
                    'exe_dict': exe_dict.copy(),
                    'input_args': job_obj.input_args,
                    'unique_plugin_id': plugin_dict['unique_plugin_id'],
                    'sequence_id': plugin_dict['sequence_id'] if 'sequence_id' in plugin_dict else None
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
                    self.make_input_component(inp,inp_idx, file_input_idx,sequence = sequence)
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

    def make_input_component(self, input_dict, input_index, file_input_index, sequence):
        
        input_desc_column = [
            dbc.Row(html.H6(input_dict['label'])),
            dbc.Row(html.P(input_dict['description'])),
            dcc.Store(
                id = {'type': 'dsa-plugin-plugin-input-info','index': input_index} if not sequence else {'type': 'dsa-plugin-sequence-input-info','index': input_index},
                data = json.dumps(input_dict),
                storage_type = 'memory'
            )
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

            #TODO: Replace this with a real region/geometry selector
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.Input(
                            type = 'text',
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            maxLength = 1000,
                            disabled = input_dict['disabled'],
                            id = {'type': 'dsa-plugin-input','index': input_index} if not sequence else {'type': 'dsa-plugin-sequence-input','index': input_index},
                            style = {'width': '100%'}
                        )
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
                            channel = input_dict['channel'] if 'channel' in input_dict else 'input',
                            value = input_dict['default'] if 'default' in input_dict else "",
                            component_index = input_index,
                            file_selector_index = file_input_index[0],
                            disabled = input_dict['disabled'],
                            sequence = sequence
                        )
                    ], md = 7)
                ]),
                html.Hr()
            ])      

            file_input_index[0]+=1

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
                        dbc.Input(
                            type = 'text' if input_dict['type']=='string' else 'number',
                            value = input_dict['default'] if not input_dict['default'] is None else [],
                            maxLength = 1000,
                            disabled = input_dict['disabled'],
                            #min = input_dict['constraints']['min'] if not input_dict['constraints'] is None else [],
                            #max = input_dict['constraints']['max'] if not input_dict['constraints'] is None else [],
                            #step = input_dict['constraints']['step'] if not input_dict['constraints'] is None else [],
                            id = {'type': 'dsa-plugin-input','index': input_index} if not sequence else {'type': 'dsa-plugin-sequence-input','index': input_index},
                            style = {'width': '100%'}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])

        return input_component

    def make_file_component(self, select_type: str, channel:str, value: Union[str,dict], component_index:int, file_selector_index: int, disabled:bool,sequence:bool=False):
        
        if type(value)==dict:
            if all([i in value for i in ['name','_id']]):
                selector_value = value['name']
                input_value = value['_id']
            elif 'value' in value:
                selector_value = value['value']
                input_value = value['value']
            elif all([i in value for i in ['fileName','folderId']]):
                selector_value = value['fileName']
                input_value = json.dumps(value)
        else:
            selector_value = value
            input_value = value
    
        file_component = html.Div([
            dcc.Store(
                id = {'type': 'dsa-plugin-resource-selector-info','index': file_selector_index},
                data = json.dumps({
                    'type': select_type,
                    'channel': channel,
                    'component_index': component_index,
                    'file_component_index': file_selector_index
                }),
                storage_type='memory'
            ),
            dbc.InputGroup([
                dbc.InputGroupText(
                    f'{select_type}: '
                ),
                dbc.Input(
                    id = {'type': 'dsa-plugin-resource-selector-input','index': file_selector_index},
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
                    id = {'type': 'dsa-plugin-resource-selector-open-modal','index': file_selector_index} if not sequence else {'type': 'dsa-plugin-sequence-resource-selector-open-modal','index': component_index},
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

        if type(session_data)==str:
            session_data = json.loads(session_data)
        user_external_token = self.get_user_external_token(session_data)

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
                    unique_plugin_id = uuid.uuid4().hex[:24]
                    p_component = self.load_plugin(
                        plugin_dict = p | {'unique_plugin_id': unique_plugin_id},
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
                    sequence_id = uuid.uuid4().hex[:24]
                    
                    sequence_components = []
                    plugin_identifiers = []
                    for j_idx,j in enumerate(p):
                        unique_plugin_id = uuid.uuid4().hex[:24]

                        j_component = self.load_plugin(
                            plugin_dict = j | {'sequence_id': sequence_id, 'unique_plugin_id': unique_plugin_id},
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
                        plugin_identifiers.append(unique_plugin_id)
                    
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
                                    dcc.Store(
                                        id = {'type': 'dsa-plugin-sequence-sequence-info','index': sequence_count},
                                        data = json.dumps({'_id': sequence_id, 'plugins': plugin_identifiers}),
                                        storage_type='memory'
                                    ),
                                    html.Div(
                                        id = {'type': 'dsa-plugin-sequence-submit-status-div','index': sequence_count},
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

        self.resource_selector.update_layout(session_data,use_prefix=False)

        layout = html.Div([
            dbc.Card([
                dbc.Modal(
                    id = {'type': 'dsa-plugin-resource-selector-modal','index': 0},
                    centered = True,
                    is_open = False,
                    size = 'xl',
                    className = None,
                    children = [
                        self.resource_selector.blueprint.embed(self.blueprint)
                    ]
                ),
                dbc.CardHeader(self.title),
                dbc.CardBody([
                    dbc.Row(
                        'Below are separate input components for running a desired set of plugins. Individual plugins can be executed independently while plugins that are part of a Sequence are submitted all at once.'
                    ),
                    html.Hr(),
                    html.Div(
                        id = {'type': 'dsa-plugin-plugin-parent-div','index': 0},
                        children = dmc.Accordion(
                            children = plugin_components
                        )
                    )
                ])
            ])
        ],style = {'maxHeight': '90vh','overflow': 'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix=f'{self.component_prefix}', escape = lambda input_id: self.prefix_escape(input_id)).transform_layout(layout)

        return layout

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
                State({'type': 'dsa-plugin-plugin-input-info','index': ALL},'data'),
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
                State({'type': 'dsa-plugin-sequence-sequence-info','index': MATCH},'data'),
                State({'type': 'dsa-plugin-sequence-plugin-info-store','index': ALL},'data'),
                State({'type': 'dsa-plugin-sequence-input','index': ALL},'value'),
                State({'type': 'dsa-plugin-sequence-input-info','index': ALL},'data'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-sequence-submit-status-div','index': MATCH},'children'),
                Output({'type': 'dsa-plugin-sequence-submit-button','index': MATCH},'disabled')
            ],
            prevent_initial_call = True
        )(self.submit_sequence)

        # Callback for opening the resource selector modal with information
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-resource-selector-open-modal','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-plugin-resource-selector-info','index': ALL},'data'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-plugin-resource-selector-modal','index': ALL},'is_open'),
                Output({'type': 'dsa-plugin-resource-selector-modal','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.open_resource_selector)

        # Callback for retrieving selected resource information
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-resource-selector-modal','index': ALL},'is_open')
            ],
            [
                State({'type': 'anchor-dsa-resource-selector-selected-resources','index': ALL},'data'),
            ],
            [
                Output({'type': 'dsa-plugin-resource-selector-input','index': ALL},'value'),
                Output({'type': 'dsa-plugin-input','index': ALL},'value')
            ],
            prevent_initial_call = True
        )(self.retrieve_resource_selection)

        # Callback for creating a wildcard input
        """
        self.blueprint.callback(
            [
                Input({'type': 'dsa-plugin-wildcard-icon','index': ALL},'n_clicks')
            ],
            [
                State({'type': '','index': },'')
            ],
            [
                Output({'type': '', 'index': },'')
            ],
            prevent_initial_call = True
        )(self.create_wildcard_input)

        """

    def post_process_plugin_inputs(self, plugin_inputs, plugin_input_info):

        processed_inputs = []
        error_inputs = []
        for p_input, p_info in zip(plugin_inputs,plugin_input_info):
            # None type inputs are replaced with default if one is available
            if not p_input is None:
                if p_info['type'] in ['file','directory','image'] and p_info['channel']=='output':
                    if '"' in p_input or "'" in p_input:
                        p_input = json.loads(p_input.replace("'",'"'))
                    if type(p_input)==list:
                        p_input = p_input[0]
                    if 'channel' in p_info:
                        if p_info['channel']=='output':
                            # This needs a _name and _folder argument
                            if type(p_input)==dict:
                                processed_inputs.extend([
                                    {
                                        'name': p_info['name'],
                                        'value':p_input['fileName']
                                    },
                                    {
                                        'name': p_info['name']+'_folder',
                                        'value':p_input['folderId']
                                    }
                                ])

                            else:
                                error_inputs.append(p_info['name'])
                        else:
                            if type(p_input)==str:
                                processed_inputs.append({
                                    'name': p_info['name'],
                                    'value':p_input
                                })
                            else:
                                error_inputs.append(p_info['name'])

                    else:
                        if type(p_input)==str:
                            processed_inputs.append({
                                'name': p_info['name'],
                                'value':p_input
                            })
                        else:
                            error_inputs.append(p_info['name'])

                elif p_info['type'] in ['region','geometry','point']:
                    
                    if p_info['type']=='region':
                        if not all([j in p_input for j in ['[',']']]):
                            fixed_region = p_input.replace(' ','').split(',')
                        else:
                            fixed_region = p_input.replace('[','').replace(']','').replace(' ','').split(',')

                        try:
                            fixed_region = [float(i) for i in fixed_region]
                            processed_inputs.append({
                                'name': p_info['name'],
                                'value':json.dumps(fixed_region)
                            })
                        except ValueError:
                            error_inputs.append(p_info['name'])

                    else:
                        error_inputs.append(p_info['name'])

                elif 'vector' in p_info['type']:
                    
                    fixed_vector = p_input.replace('[','').replace(']','').replace(' ','').split(',')
                    if not 'string' in p_info['type']:
                        try:
                            if any([i in p_info['type'] for i in ['float','double']]):
                                fixed_vector = [float(i) for i in fixed_vector]
                            elif 'integer' in p_info['type']:
                                fixed_vector = [int(i) for i in fixed_vector]
                        except ValueError:
                            error_inputs.append(p_info['name'])

                    processed_inputs.append({
                        'name': p_info['name'],
                        'value':json.dumps(fixed_vector)
                    })

                else:
                    processed_inputs.append({
                        'name': p_info['name'],
                        'value': p_input
                    })

        return processed_inputs, error_inputs

    def submit_plugin(self, clicked, plugin_info, plugin_inputs,plugin_input_info, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)

        user_external_token = self.get_user_external_token(session_data)

        plugin_info = [json.loads(p_info) for p_info in plugin_info]
        all_plugin_input_info = [json.loads(i_info) for i_info in plugin_input_info]

        selected_plugin = plugin_info[ctx.triggered_id['index']]
        
        selected_plugin_inputs = []
        selected_plugin_inputs_info = []
        for p,p_info in zip(plugin_inputs,all_plugin_input_info):
            if p_info['unique_plugin_id']==selected_plugin['unique_plugin_id']:
                selected_plugin_inputs.append(p)
                selected_plugin_inputs_info.append(p_info)

        processed_inputs_dict, error_inputs = self.post_process_plugin_inputs(selected_plugin_inputs,selected_plugin_inputs_info)

        if len(selected_plugin['input_args'])>len(plugin_inputs):
            # Mismatch in input length
            status_div = dbc.Alert('Missing plugin inputs!',color='warning')
            button_disable = False
            return status_div, button_disable

        if len(error_inputs)>0:
            status_div = dbc.Alert(f'Incorrect input types for: {error_inputs}',color='warning')
            button_disable = False
            return status_div, button_disable

        job_dict = {
            'plugin_id': selected_plugin['_id'],
            'input_args': processed_inputs_dict
        }

        # function incorporated from girder-job-sequence
        job_obj = from_dict(self.handler.gc,job_dict)
        job_start_response = job_obj.start()

        if job_start_response.status_code==200:
            status_div = dbc.Alert('Plugin successfully submitted!',color='success')
            button_disable = True
        else:
            status_div = dbc.Alert(f'Error submitting plugin: {selected_plugin["_id"]}',color = 'danger')
            print(job_start_response.content)
            button_disable = False

        return status_div, button_disable

    def submit_sequence(self, clicked, sequence_info, sequence_plugins_info, sequence_plugin_inputs, sequence_plugin_inputs_info, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)

        user_external_token = self.get_user_external_token(session_data)
        # Getting information on this sequence
        sequence_info = json.loads(sequence_info)
        # Getting information on plugins in this sequence
        all_sequence_plugins_info = [json.loads(i) for i in sequence_plugins_info]
        sequence_plugin_inputs_info = [json.loads(i) for i in sequence_plugin_inputs_info]

        selected_sequence_plugins_info = [i for i in all_sequence_plugins_info if i['sequence_id']==sequence_info['_id'] and i['unique_plugin_id'] in sequence_info['plugins']]
        selected_sequence_plugins_ids = [i['unique_plugin_id'] for i in selected_sequence_plugins_info]
        sequence_job_list = []
        sequence_inputs_error_list = []
        for plugin_id in sequence_info['plugins']:
            plugin_info = selected_sequence_plugins_info[selected_sequence_plugins_ids.index(plugin_id)]

            plugin_inputs = []
            plugin_inputs_info = []
            for s,s_info in zip(sequence_plugin_inputs, sequence_plugin_inputs_info):
                if s_info['unique_plugin_id']==plugin_id:
                    plugin_inputs.append(s)
                    plugin_inputs_info.append(s_info)

            processed_plugin_inputs, error_inputs = self.post_process_plugin_inputs(plugin_inputs,plugin_inputs_info)
            sequence_inputs_error_list.extend(error_inputs)
            
            plugin_dict = {
                'plugin_id': plugin_info['_id'],
                'input_args': processed_plugin_inputs
            }
            sequence_job_list.append(plugin_dict)
    
        if len(sequence_inputs_error_list) > 0:
            status_div = dbc.Alert(f'Incorrect input types for: {sequence_inputs_error_list}',color='warning')
            button_disable = False
            return status_div, button_disable

        sequence_obj = from_list(self.handler.gc,sequence_job_list)

        # Start job sequence thread
        job_seq_thread = threading.Thread(
            target = sequence_obj.start, 
            name = f'fusion_tools_job_sequence_{sequence_obj.id}',
            kwargs = {
                "cancel_on_error": True
            },
            daemon=True
        )
        job_seq_thread.start()

        status_div = dbc.Alert(f'Sequence {ctx.triggered_id["index"]+1} Submitted',color='success')
        button_disable = True
        return status_div, button_disable

    def open_resource_selector(self, clicked, selector_info, session_data):
        
        if any(clicked):
            opened = True
            selector_info = json.loads(selector_info[ctx.triggered_id['index']])
            session_data = json.loads(session_data)

            selector_children = self.resource_selector.update_layout(
                session_data = session_data,
                use_prefix = True,
                selector_type = selector_info['type'] if not selector_info['type']=='image' else 'item',
                select_count = 1,
                source_channel = selector_info['channel'],
                source_index = {
                    'component_index': selector_info['component_index'],
                    'file_component_index': selector_info['file_component_index']
                }
            )

            return [opened], [selector_children]

        else:
            raise exceptions.PreventUpdate
    
    def retrieve_resource_selection(self, modal_opened, selected_data):

        modal_opened = get_pattern_matching_value(modal_opened)
        selected_data = get_pattern_matching_value(selected_data)
        if selected_data and not modal_opened:
            selected_data = json.loads(selected_data)
            update_index = selected_data['source_component_index']
            selector_val = ','.join([i['Name'] for i in selected_data['resource_list']])
            input_val = json.dumps([i['_id'] if '_id' in i else i for i in selected_data['resource_list']])

            new_selector_vals = [no_update if not idx==update_index['file_component_index'] else selector_val for idx in range(len(ctx.outputs_list[0]))]
            new_input_vals = [no_update if not idx==update_index['component_index'] else input_val for idx in range(len(ctx.outputs_list[1]))]

            return new_selector_vals, new_input_vals
        else:
            raise exceptions.PreventUpdate

    def create_wildcard_input(self):
        pass





class DSAPluginRunner(DSATool):
    """Handler for DSAPluginRunner component, letting users specify input arguments to plugins to run on connected DSA instance.

    :param DSATool: Class for components that integrate with DSA.
    :type DSATool: None
    """

    title = 'DSA Plugin Runner'
    description = 'Select a plugin to run on the cloud!'

    def __init__(self,
                 handler: None
                 ):
        
        super().__init__()
        self.handler = handler

    def load(self, component_prefix: int):
        
        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}', escape = lambda input_id: self.prefix_escape(input_id)),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

        # Adding DSAPluginGroup object to PluginRunner
        self.plugin_inputs_handler = DSAPluginGroup(
            handler = self.handler
        )
        self.plugin_inputs_handler.load(self.component_prefix)
    
    def update_layout(self, session_data:dict, use_prefix: bool):
        
        if type(session_data)==str:
            session_data = json.loads(session_data)

        user_external_token = self.get_user_external_token(session_data)
        plugin_list = self.handler.list_plugins(user_token = user_external_token)
        docker_list = sorted(list(set([i['image'] for i in plugin_list])))

        if not use_prefix:
            self.plugin_inputs_handler.blueprint.layout = self.plugin_inputs_handler.update_layout(session_data,False)

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        html.H3(self.title)
                    ),
                    html.Hr(),
                    dbc.Row(
                        self.description
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': i, 'value': i}
                                    for i in docker_list
                                ],
                                value = [],
                                multi = False,
                                placeholder = 'Docker Image containing Plugin',
                                id = {'type': 'dsa-plugin-runner-docker-drop','index': 0}
                            )],
                            md = 6
                        ),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = False,
                                placeholder = 'Plugin Name',
                                id = {'type': 'dsa-plugin-runner-cli-drop','index': 0}
                            )
                        ],
                        md = 6)
                    ]),
                    html.Div(
                        id = {'type': 'dsa-plugin-runner-inputs-div','index': 0},
                        children = [
                            self.plugin_inputs_handler.update_layout(session_data,False) if use_prefix else self.plugin_inputs_handler.blueprint.embed(self.blueprint)
                        ]
                    )
                ])
            ])
        ])

        if use_prefix:
            PrefixIdTransform(prefix=f'{self.component_prefix}', escape = lambda input_id: self.prefix_escape(input_id)).transform_layout(layout)

        return layout

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
                Output({'type': 'dsa-plugin-runner-inputs-div','index': ALL},'children')
            ],
            prevent_initial_call=True
        )(self.populate_plugin_inputs)

    def update_cli_options(self, docker_select,session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        docker_select = get_pattern_matching_value(docker_select)
        session_data = json.loads(session_data)

        user_external_token = self.get_user_external_token(session_data)

        plugin_list = self.handler.list_plugins(user_token=user_external_token)
        included_cli = sorted([i['name'] for i in plugin_list if i['image']==docker_select])

        return [included_cli]
    
    def populate_plugin_inputs(self, cli_select, docker_select,session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        docker_select = get_pattern_matching_value(docker_select)
        cli_select = get_pattern_matching_value(cli_select)
        plugin_components = self.plugin_inputs_handler.update_layout(
            session_data = session_data,
            use_prefix = True,
            plugin_groups = {
                'image': docker_select,
                'name': cli_select
            }
        )

        return [plugin_components]




class DSAPluginProgress(DSATool):
    """Handler for DSAPluginProgress component, letting users check the progress of currently running or previously run plugins as well as cancellation of running plugins.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """

    title = 'DSA Plugin Progress'
    description = 'Monitor the progress of currently running plugins.'

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

    def generate_plugin_table(self, session_data:dict, offset:int, limit: int, next_clicks:int, prev_clicks:int, use_prefix:bool):
        
        user_external_token = self.get_user_external_token(session_data)
        user_external_id = self.get_user_external_id(session_data)

        # Getting all jobs for this user:
        user_jobs = self.handler.get_user_jobs(
            user_id = user_external_id,
            user_token = user_external_token,
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

        table_rows = []
        if len(user_jobs)>0:
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
                        'You have exceeded all of the jobs for this user!'
                    ])
                )
            else:
                table_rows.append(
                    dmc.Tr([
                        'You have not run any jobs yet!'
                    ])
                )

        if len(table_rows)==0:
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
        
        if 'user' in session_data:
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
                        html.H3(self.title)
                    ),
                    html.Hr(),
                    dbc.Row(
                        self.description
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

        user_external_token = self.get_user_external_token(session_data)

        if 'dsa-plugin-progress-get-logs' in ctx.triggered_id['type']:
            row_clicked = ctx.triggered_id['index']
            job_id = table_rows[row_clicked][5]['props']['children']

            job_logs = self.handler.get_specific_job(
                job_id = job_id,
                user_token = user_external_token
            )

            job_logs_div = html.Div(
                [
                    html.Div([html.P(i) for i in line.split('\n')])
                    for line in job_logs.get('log',[])
                ],
                style = {'maxHeight': '20vh','overflow': 'scroll'}
            )

        elif 'dsa-plugin-progress-cancel-job' in ctx.triggered_id['type']:
            row_clicked = ctx.triggered_id['index']
            job_id = table_rows[row_clicked][5]['props']['children']

            cancel_response = self.handler.cancel_job(
                job_id = job_id,
                user_token = user_external_token
            )

            job_logs_div = html.Div(
                'Cancel request sent! Close and re-open to see updated status'
            )


        return [job_logs_div]
    


