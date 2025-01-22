"""Components related to DSA Plugins
"""

import requests
import json
import numpy as np
import lxml.etree as ET

from typing_extensions import Union

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

from fusion_tools.handler import DSATool

class DSAPluginRunner(DSATool):
    """Handler for DSAPluginRunner component, letting users specify input arguments to plugins to run on connected DSA instance.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self,
                 handler: None
                 ):
        
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
                        if type(in_arg['default']) in [int,float,str]:
                            exe_input['default'] = in_arg['default']
                        elif type(in_arg['default'])==dict:
                            # Defining input from uploaded file item/file ID (#TODO: Define input from previous plugin output)
                            if in_arg['default']['type']=='input_file':
                                input_file_arg = in_arg['default']['name']
                                input_file_arg_idx = [i['name'] for i in plugin_dict['input_files']].index(input_file_arg)

                            elif in_arg['default']['type']=='input_annotation':
                                pass

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
                        dbc.Row(html.P(input_dict['description']))
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
                        dbc.Row(html.P(input_dict['description']))
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
                        dbc.Row(html.P(input_dict['description']))
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
                        dbc.Row(html.P(input_dict['description']))
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
                        dbc.Row(html.P(input_dict['description']))
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
    
    def find_upload_resource_id(self, ):
        pass

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


























