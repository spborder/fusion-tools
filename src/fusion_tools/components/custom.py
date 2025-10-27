"""

Components which integrate custom functionality within a set structure

"""

import json
import geojson
import geopandas as gpd
import numpy as np

from typing_extensions import Union
from shapely.geometry import box, shape
import plotly.express as px
import plotly.graph_objects as go

from PIL import Image, ImageOps

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
from dash import dcc, callback, ctx, ALL, exceptions, no_update
import dash_bootstrap_components as dbc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform, BlockingCallbackTransform
from dash_extensions.javascript import Namespace, arrow_function

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value

from fusion_tools.utils.images import get_feature_image
from fusion_tools.components.base import Tool, MultiTool

import time


class FUSIONFunction:
    """Specification for a function supplied to FUSION for creation of a custom component
    """
    def __init__(self,
                title: str,
                description: str = '',
                urls: Union[str,list,None] = None,
                function =  None,
                function_type: str = 'structure',
                input_spec: Union[list,dict] = [],
                output_spec: Union[list,dict] = [],
                output_callbacks: Union[list,None] = None):
        """Constructor method

        :param title: Title to be used for this function in the layout
        :type title: str
        :param description: Description for this function to be incorporated into the layout, defaults to ''
        :type description: str, optional
        :param urls: Any associated URLs associated with this function that you would like displayed, defaults to None
        :type urls: Union[str,list,None], optional
        :param function: A lambda function or other callable which takes inputs specified in input_spec and outputs items in output_spec, defaults to None
        :type function: None, optional
        :param function_type: The "type" of function supplied. This defines what the function is meant to operate on. Choose one of "structure", "layer", "ROI", or "item"., defaults to 'structure'
        :type function_type: str, optional
        :param input_spec: List or dictionary specifying input parameter name, description, type (numeric, image, mask, annotation, string, boolean, options, region). Numeric types may have min and max kwargs. Options types have an "options" kwarg for list of options. defaults to []
        :type input_spec: Union[list,dict], optional
        :param output_spec: List or dictionary specifying outputs of the function and how they should be rendered. Includes name, description, and type (image, annotation, numeric, string, and function). Function outputs should include a function kwarg specifying a lambda/callable that takes the output and an integer index as input, defaults to []
        :type output_spec: Union[list,dict], optional
        :param output_callbacks: List of any callbacks to be used with generated components as a part of "function" output types. Include inputs, outputs, and function kwargs specifying the callback inputs, outputs, and what the callback function should be., defaults to None
        :type output_callbacks: Union[list,None], optional
        """

        
        self.title = title
        self.description = description
        self.urls = urls
        self.function = function
        self.function_type = function_type
        self.input_spec = input_spec
        self.output_spec = output_spec
        self.output_callbacks = output_callbacks

        # structure = function is run on an individual structure
        # ROI = function is run on a broad region of the image/annotations in that ROI
        assert function_type in ['structure', 'ROI', 'layer', 'item']

        if type(self.input_spec)==list:
            for i in self.input_spec:
                assert type(i)==dict
                # Description not required
                assert all([j in list(i.keys()) for j in ['name','type']])
                assert i.get('type') in ['numeric','image','annotation','mask','string','boolean','options','region']
        elif type(self.input_spec)==dict:
            assert all([j in self.input_spec.keys() for j in ['name','type']])
            assert self.input_spec.get('type') in ['numeric','image','annotation','mask','string','boolean','options','region']

        if type(self.output_spec)==list:
            for i in self.output_spec:
                assert type(i)==dict
                assert 'type' in i.keys()
        elif type(self.output_spec)==dict:
            assert 'type' in self.output_spec.keys()

        if not self.output_callbacks is None:
            if type(self.output_callbacks)==list:
                for o in self.output_callbacks:
                    assert all([j in o.keys() for j in ['inputs','outputs','function']])

            elif type(self.output_callbacks)==dict:
                assert all([j in self.output_callbacks.keys() for j in ['inputs','outputs','function']])


class CustomFunction(Tool):
    """
    Component which can be used for deploying/sharing custom Python functions executed on annotations/images
    """
    title = 'Custom Function'
    description = ''

    def __init__(self,
                 title = 'Custom Function',
                 description = '',
                 custom_function: Union[list,FUSIONFunction,None] = None
                 ):
        """Constructor method

        :param title: A title to use for this component, defaults to 'Custom Function'
        :type title: str, optional
        :param description: A description to use for this component, defaults to ''
        :type description: str, optional
        :param custom_function: One or more FUSIONFunctions to include in this component, defaults to None
        :type custom_function: Union[list,FUSIONFunction,None], optional
        """
        
        super().__init__()
        self.title = title
        self.description = description

        if not type(custom_function)==list:
            self.custom_function = [custom_function]
        else:
            self.custom_function = custom_function
    
    def load(self, component_prefix:int):

        self.component_prefix = component_prefix
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()
        self.output_callbacks()

    def output_callbacks(self):
        """Registering callbacks passed by users to the layout
        """
        for c in self.custom_function:
            if c.output_callbacks is not None:
                for callback in c.output_callbacks:
                    self.blueprint.callback(
                        inputs = callback.get('inputs')+callback.get('states',[]),
                        output = callback.get('outputs'),
                    )(callback.get('function'))

    def get_callbacks(self):
        
        # Populating function inputs
        self.blueprint.callback(
            [
                Input({'type': 'custom-function-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'custom-function-function-div','index': ALL},'children')
            ]
        )(self.get_function_layout)

        # Running function with specified inputs
        self.blueprint.callback(
            [
                Input({'type': 'custom-function-run','index': ALL},'n_clicks'),
            ],
            [
                Output({'type': 'custom-function-output-div','index': ALL},'children'),
                Output({'type': 'custom-function-output-data-store','index': ALL},'data')
            ],
            [
                State({'type': 'custom-function-drop','index': ALL},'value'),
                State({'type': 'custom-function-input','index': ALL},'value'),
                State({'type': 'custom-function-input-info','index': ALL},'data'),
                State({'type': 'custom-function-structure-drop','index': ALL},'value'),
                State({'type': 'custom-function-structure-number','index': ALL},'value'),
                State({'type': 'custom-function-main-roi-store','index': ALL},'data'),
                State({'type': 'map-slide-information','index': ALL},'data'),
                State({'type': 'feature-overlay','index': ALL},'name'),
                State('anchor-vis-store','data')
            ]
        )(self.run_function)

        self.blueprint.callback(
            [
                Input({'type': 'custom-function-download-button','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'custom-function-output-data-store','index': ALL},'data')
            ],
            [
                Output({'type': 'custom-function-download-data','index': ALL},'data')
            ]
        )(self.download_data)

        # Updating available structure names
        self.blueprint.callback(
            [
                Input({'type': 'custom-function-refresh-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'custom-function-structure-drop','index': ALL},'options')
            ],
            [
                State({'type': 'feature-overlay','index':ALL},'name')
            ]
        )(self.update_structures)

        #TODO: Downloading derived data
        # Open region selection modal
        self.blueprint.callback(
            [
                Input({'type': 'custom-function-roi-input','index': ALL},'n_clicks'),
                Input({'type':'custom-function-main-roi','index': ALL},'n_clicks'),
                Input({'type': 'custom-function-view-annotations','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'map-tile-layer','index': ALL},'url'),
                State({'type': 'map-tile-layer','index': ALL},'tileSize'),
                State({'type': 'map-slide-information','index': ALL},'data'),
                State({'type': 'custom-function-output-annotation-store','index': ALL},'data')
            ],
            [
                Output({'type': 'custom-function-modal','index': ALL},'is_open'),
                Output({'type': 'custom-function-modal','index': ALL},'children')
            ]
        )(self.open_roi_modal)

        # Collecting region selection
        self.blueprint.callback(
            [
                Input({'type': 'custom-function-roi-done-button','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'custom-function-edit-control','index': ALL},'geojson'),
                State({'type': 'custom-function-input-info','index': ALL},'data'),
                State({'type': 'custom-function-main-roi-store','index': ALL},'data'),
                State({'type': 'custom-function-roi-trigger','index': ALL},'data'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ],
            [
                Output({'type': 'custom-function-input-info','index': ALL},'data'),
                Output({'type': 'custom-function-main-roi-store','index': ALL},'data'),
                Output({'type': 'custom-function-modal','index': ALL},'is_open'),
                Output({'type': 'custom-function-roi-input','index': ALL},'color'),
                Output({'type': 'custom-function-main-roi','index': ALL},'color')
            ]
        )(self.submit_roi)

    def update_layout(self, session_data:dict, use_prefix:bool):
        """Initializing layout for component
        """
        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        dbc.Col(
                            html.H3(self.title)
                        )
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Col(
                            self.description
                        )
                    ),
                    dbc.Modal(
                        id = {'type': 'custom-function-modal','index': 0},
                        is_open = False,
                        size = 'xl',
                        children = []
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(dbc.Label('Select a function: '),md = 2),
                        dbc.Col(
                            dcc.Dropdown(
                                id = {'type': 'custom-function-drop','index': 0},
                                options = [
                                    {
                                        'label': i.title,
                                        'value': i.title
                                    }
                                    for i in self.custom_function
                                ],
                                value = [],
                                multi = False
                            ),
                            md = 10
                        )
                    ]),
                    html.Hr(),
                    html.Div(
                        id = {'type': 'custom-function-function-div','index': 0},
                        children = []
                    )
                ])
            ])
        ])

        if use_prefix:
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(layout)

        return layout
    
    def get_function_layout(self, function_selection):
        """Generating input components for the selected function

        :param function_selection: Title attribute for one of the passed functions
        :type function_selection: list
        """
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        all_titles = [i.title for i in self.custom_function]
        function_title = get_pattern_matching_value(function_selection)
        
        if function_title in all_titles:
            function_info = self.custom_function[all_titles.index(function_title)]
        else:
            raise exceptions.PreventUpdate


        if function_info.function_type=='layer':
            #TODO: Add an All checkbox or something instead of putting in the number
            function_type_components = html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label('Structure: '),md = 3),
                    dbc.Col(
                        dcc.Dropdown(
                            options = [],
                            value = [],
                            id = {'type': 'custom-function-structure-drop','index': 0},
                            multi = True
                        ),
                        md = 7
                    ),
                    dbc.Col([
                        html.A(
                            html.I(
                                className = 'fa-solid fa-rotate fa-xl',
                                n_clicks = 0,
                                id = {'type': 'custom-function-refresh-icon','index': 0}
                            )
                        ),
                        dbc.Tooltip(
                            target = {'type': 'custom-function-refresh-icon','index': 0},
                            children = 'Click to reset labeling components'
                        )
                    ],md=2)
                ],style = {'marginBottom':'5px'}),
                html.Hr(),
                dbc.Row([
                    dbc.Col(
                        dbc.InputGroup([
                            dbc.InputGroupText('Number of Structures:'),
                            dbc.Input(
                                id = {'type': 'custom-function-structure-number','index': 0},
                                type = 'number',
                                min = 0
                            )
                        ])
                    )
                ],style = {'marginBottom':'5px'})
            ])

        elif function_info.function_type=='structure':
            function_type_components = html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label('Structure: '),md = 3),
                    dbc.Col(
                        dcc.Dropdown(
                            options = [],
                            value = [],
                            id = {'type': 'custom-function-structure-drop','index': 0},
                            multi = True
                        ),
                        md = 7
                    ),
                    dbc.Col([
                        html.A(
                            html.I(
                                className = 'fa-solid fa-rotate fa-xl',
                                n_clicks = 0,
                                id = {'type': 'custom-function-refresh-icon','index': 0}
                            )
                        ),
                        dbc.Tooltip(
                            target = {'type': 'custom-function-refresh-icon','index': 0},
                            children = 'Click to reset labeling components'
                        )
                    ],md=2)
                ],style = {'marginBottom':'5px'}),
                html.Hr()
            ])
        elif function_info.function_type=='ROI':
            roi_button = dbc.Button(
                children = [
                    html.A(
                        html.I(
                            className = 'fa-solid fa-draw-polygon'
                        ),
                    ),
                    dbc.Tooltip(
                        target = {'type': 'custom-function-main-roi','index': 0},
                        children = 'Draw ROI'
                    ),
                    dcc.Store(
                        id = {'type': 'custom-function-main-roi-store','index': 0},
                        data = json.dumps({}),
                        storage_type = 'memory'
                    )
                ],
                id = {'type': 'custom-function-main-roi','index': 0},
                color = 'primary',
                n_clicks = 0,
            ) 

            function_type_components = html.Div([
                dbc.Row([
                    dbc.Col(
                        dbc.InputGroup([
                            dbc.InputGroupText('Select ROI to run function on: '),
                            roi_button
                        ],size = 'lg'),
                    )
                ],align='center',justify='center')
            ],style = {'marginBottom':'5px','width': '100%'})

        elif function_info.function_type=='item':
            function_type_components = html.Div([
                html.H5('Running on current slide')            
            ])

        function_layout = html.Div([
            dbc.Row(
                dbc.Col(
                    html.H3(function_info.title)
                )
            ),
            html.Hr(),
            dbc.Row(
                dbc.Col(
                    function_info.description
                )
            ),
            html.Hr(),
            dbc.Row(
                function_type_components,
            ),
            dbc.Row([
                self.make_input_component(i,idx)
                for idx,i in enumerate(function_info.input_spec)
            ],style = {'maxHeight':'50vh','overflow': 'scroll'}
            ),
            dbc.Row(
                dbc.Button(
                    'Run it!',
                    id = {'type': 'custom-function-run','index': 0},
                    className = 'd-grid col-12 mx-auto',
                    color = 'primary',
                    n_clicks = 0
                ),
                style = {'marginTop': '5px','marginBottom':'5px'}
            ),
            html.Hr(),
            dbc.Row([
                html.Div(
                    id = {'type': 'custom-function-output-div','index': 0},
                    children = []
                )
            ]),
            html.Hr(),
            dbc.Row([
                dcc.Store(
                    id = {'type': 'custom-function-output-data-store','index': 0},
                    data = json.dumps({}),
                    storage_type = 'memory'
                ),
                dbc.Button(
                    'Download Results',
                    id = {'type': 'custom-function-download-button','index': 0},
                    color = 'success',
                    className = 'd-grid col-12 mx-auto',
                    n_clicks = 0
                ),
                dcc.Download(
                    id = {'type': 'custom-function-download-data','index': 0}
                )
            ])
        ])

        PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(function_layout)


        return [function_layout]

    def make_input_component(self, input_spec, input_index):
        """Making an input component based on provided input_specs
        """
        input_desc_column = [
            dbc.Row(html.H6(input_spec.get('name'))),
            dbc.Row(html.P(input_spec.get('description'))),
            dcc.Store(
                id = {'type': 'custom-function-input-info','index': input_index},
                data = json.dumps(input_spec),
                storage_type = 'memory'
            ) if not input_spec['type'] in ['image','mask','annotation'] else None
        ]

        if input_spec['type']=='text':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.Input(
                                type = 'text',
                                id = {'type': 'custom-function-input','index': input_index},
                            ),                       
                        ])
                    ],md=7)
                ]),
                html.Hr()
            ])
        
        elif input_spec['type']=='boolean':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dcc.RadioItems(
                            options = [
                                {'label': 'True', 'value': 1},
                                {'label': 'False', 'value': 0}
                            ],
                            id = {'type': 'custom-function-input','index': input_index}
                        )
                    ],md=7)
                ])
            ])

        elif input_spec['type']=='numeric':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.Input(
                                type = 'number',
                                id = {'type': 'custom-function-input','index': input_index},
                            )                       
                        ])
                    ],md=7)
                ]),
                html.Hr()
            ])

        elif input_spec['type']=='options':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.Select(
                                options = input_spec['options'],
                                id = {'type': 'custom-function-input','index': input_index}
                            ),
                        ])
                    ],md=7)
                ]),
                html.Hr()
            ])

        elif input_spec['type'] in ['image','mask','annotation']:

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText(f'{input_spec["type"]} passed as input to function')
                        ])
                    ],md=7)
                ]),
                html.Hr()
            ])

        elif input_spec['type']=='region':

            roi_button = dbc.Button(
                children = [
                    html.A(
                        html.I(
                            className = 'fa-solid fa-draw-polygon'
                        ),
                    ),
                    dbc.Tooltip(
                        target = {'type': 'custom-function-roi-input','index': input_index},
                        children = 'Draw ROI'
                    )
                ],
                id = {'type': 'custom-function-roi-input','index': input_index},
                color = 'primary',
                n_clicks = 0,
            ) 

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText('Select Region: '),
                            roi_button
                        ])
                    ],md=7)
                ]),
                html.Hr()
            ])


        return input_component

    def make_output(self, output, output_spec,output_index):
        
        output_desc_column = [
            dbc.Row(html.H6(output_spec.get('name'))),
            dbc.Row(html.P(output_spec.get('description'))),
        ]

        if output_spec['type']=='image':
            
            if type(output)==list:
                image_dims = [i.shape if type(i)==np.ndarray else np.array(i).shape for i in output]
                max_height = max([i[0] for i in image_dims])
                max_width = max([i[1] for i in image_dims])

                modded_images = []
                for img in output:
                    if type(img)==np.ndarray:
                        img = Image.fromarray(img)                    
                    
                    img_width, img_height = img.size
                    
                    delta_width = max_width - img_width
                    delta_height = max_height - img_height

                    pad_width = delta_width // 2
                    pad_height = delta_height //2

                    mod_img = np.array(
                        ImageOps.expand(
                            img,
                            border = (
                                pad_width,
                                pad_height,
                                delta_width - pad_width,
                                delta_height - pad_height
                            ),
                            fill = 0
                        )
                    )
                    modded_images.append(mod_img)

                image_data = px.imshow(np.stack(modded_images,axis=0),animation_frame=0,binary_string=True)

            else:
                if type(output)==np.ndarray:
                    image_data = px.imshow(Image.fromarray(output))
                else:
                    image_data = px.imshow(output)

            image_data.update_layout(
                margin = {'t':0,'b':0,'l':0,'r':0}
            )
            
            output_component = html.Div([
                dbc.Row([
                    dbc.Col(output_desc_column,md=5),
                    dbc.Col([
                        dcc.Graph(
                            figure = go.Figure(
                                image_data
                            )
                        )
                    ],md = 7)
                ]),
                html.Hr()
            ])

        elif output_spec['type']=='numeric':

            if type(output)==list:
                number_output = f'Click "Download" to download array. shapes: {[o.shape for o in output if type(o)==np.ndarray]}'
            elif type(output)==np.ndarray:
                number_output = f'Click "Download" to download array. shape: {output.shape}'
            elif type(output) in [int,float,bool]:
                number_output = output
            
            output_component = html.Div([
                dbc.Row([
                    dbc.Col(output_desc_column,md=5),
                    dbc.Col(
                        html.H5(str(number_output)),
                        md = 7
                    )
                ])
            ])
        elif output_spec['type']=='annotation':
            #TODO: This output type should enable visualization of the generated annotations relative to the whole slide
            annotations_view_component = html.Div([
                dbc.Button(
                    'View Annotations',
                    n_clicks = 0,
                    className = 'd-grid col-12 mx-auto',
                    color = 'secondary',
                    id = {'type': 'custom-function-view-annotations','index': 0}
                ),
                dcc.Store(
                    id = {'type': 'custom-function-output-annotation-store','index': 0},
                    data = json.dumps(output),
                    storage_type = 'memory'
                )
            ])
            
            output_component = html.Div([
                dbc.Row([
                    dbc.Col(output_desc_column,md=5),
                    dbc.Col(
                        annotations_view_component,
                        md = 7
                    )
                ])
            ])

        elif output_spec['type']=='string':

            output_component = html.Div([
                dbc.Row([
                    dbc.Col(output_desc_column,md=5),
                    dbc.Col(
                        html.H5(output),
                        md = 7
                    )
                ])
            ])

        elif output_spec['type']=='function':
            # This is for if you want to return a component or execute some other function when generating output
            try:
                output_component = output_spec['function'](output=output,output_index=output_index)

                if output_component is None:
                    output_component = dbc.Alert('Output function called successfully!',color='success')
                else:
                    PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(output_component)

            except Exception as e:
                output_component = dbc.Alert(f'Output function failed!: {e}',color='danger')


        return output_component

    def update_structures(self, clicked, overlay_names):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        overlay_names = [
            {
                'label': i,
                'value': i
            }
            for i in overlay_names
        ]

        return [overlay_names]

    def get_feature_image(self, feature, slide_information, return_mask = False, return_image = True, frame_index = None, frame_colors = None):
        
        # Scaling feature geometry to original slide CRS (skipping this)
        #feature = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),feature)
        
        if return_image and not return_mask:
            feature_mask = None
            feature_image = get_feature_image(
                feature,
                slide_information['regions_url'],
                return_mask = return_mask,
                return_image = return_image,
                frame_index = frame_index,
                frame_colors = frame_colors
            )
        elif return_image and return_mask:
            feature_image, feature_mask = get_feature_image(
                feature,
                slide_information['regions_url'],
                return_mask = return_mask,
                return_image = return_image,
                frame_index = frame_index,
                frame_colors = frame_colors
            )
        elif return_mask and not return_image:
            feature_image = None
            feature_mask = get_feature_image(
                feature,
                slide_information['regions_url'],
                return_mask = return_mask,
                return_image = return_image,
                frame_index = frame_index,
                frame_colors = frame_colors
            )

        return feature_image, feature_mask

    def open_roi_modal(self, clicked, main_clicked, view_clicked, tile_url, tile_size, map_slide_information,output_anns):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        tile_url = get_pattern_matching_value(tile_url)
        tile_size = get_pattern_matching_value(tile_size)

        if any([i is None for i in [tile_url, tile_size]]):
            raise exceptions.PreventUpdate
        
        if not 'custom-function-view-annotations' in ctx.triggered_id['type']:
            modal_children = [
                html.Div([
                    dl.Map(
                        crs = 'Simple',
                        center = [-120,120],
                        zoom = 0,
                        children = [
                            dl.TileLayer(
                                url = tile_url,
                                tileSize=tile_size
                            ),
                            dl.FeatureGroup(
                                children = [
                                    dl.EditControl(
                                        id = {'type': f'{self.component_prefix}-custom-function-edit-control','index': 0}
                                    )
                                ]
                            )
                        ],
                        style = {'height': '40vh','width': '100%','margin': 'auto','display': 'inline-block'}
                    ),
                    dbc.Button(
                        'Done!',
                        className = 'd-grid col-12 mx-auto',
                        color = 'success',
                        n_clicks = 0,
                        id = {'type': f'{self.component_prefix}-custom-function-roi-done-button','index': 0}
                    ),
                    dcc.Store(
                        id = {'type': f'{self.component_prefix}-custom-function-roi-trigger','index': 0},
                        data = json.dumps(
                            {
                                'main': 'main' in ctx.triggered_id['type']
                            }
                        ),
                        storage_type='memory'
                    )
                ], style = {'padding': '10px 10px 10px 10px'})
            ]

        else:

            output_anns = [json.loads(i) for i in output_anns]
            scaled_geojson = [geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]*slide_information['x_scale'],c[1]*slide_information['y_scale']),g),o) for o in output_anns]
            ann_names = [
                o.get('properties',{}).get('name',f'Layer {o_idx+1}')
                for o_idx,o in enuemrate(output_anns)
            ]

            modal_children = [
                html.Div([
                    dl.Map(
                        crs = 'Simple',
                        center = [-120,120],
                        zoom = 0,
                        children = [
                            dl.TileLayer(
                                url = tile_url,
                                tileSize=tile_size
                            ),
                            dl.LayersControl(
                                children = [
                                    dl.Overlay(
                                        dl.LayerGroup(
                                            dl.GeoJSON(
                                                data = o_ann,
                                                format = 'geojson',
                                                options = {
                                                    'style': self.js_namespace('featureStyle')
                                                },
                                                hideout = {
                                                    'lineColor': {
                                                        k: '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255))
                                                        for k in ann_names
                                                    }
                                                },
                                                hoverStyle = arrow_function(
                                                    {
                                                        'weight': 5,
                                                        'color': '#9caf00',
                                                        'dashArray': ''
                                                    }
                                                ),
                                                zoomToBounds = True
                                            )
                                        ),
                                        name = ann_name,
                                        checked = True
                                    )
                                    for o_ann,ann_name in zip(scaled_geojson,ann_names)
                                ]
                            )
                        ],
                        style = {'height': '40vh','width': '100%','margin': 'auto','display': 'inline-block'}
                    ),
                ], style = {'padding': '10px 10px 10px 10px'})
            ]


        return [True], modal_children

    def submit_roi(self, done_clicked, edit_geojson, input_info, main_info, trigger_data, slide_information):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        edit_geojson = get_pattern_matching_value(edit_geojson)
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        trigger_data = json.loads(get_pattern_matching_value(trigger_data))
        if trigger_data['main']:

            update_infos = [no_update]*len(ctx.outputs_list[0])
            roi_button_color = [no_update]*len(ctx.outputs_list[3])
            main_info = json.loads(get_pattern_matching_value(main_info))
            main_updated_info = main_info.copy()
            scaled_geojson = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),edit_geojson)
            main_updated_info['roi'] = scaled_geojson
            main_updated_info = [json.dumps(main_updated_info)]
            main_button_color = ['success']
            modal_open = [False]

        else:

            main_updated_info = [no_update]
            main_button_color = [no_update]

            n_inputs = len(input_info)
            input_info = json.loads(input_info[ctx.triggered_id['index']])

            scaled_geojson = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),edit_geojson)

            input_info['roi'] = scaled_geojson

            update_infos = [no_update if not idx==ctx.triggered_id['index'] else json.dumps(input_info) for idx in range(n_inputs)]
            modal_open = [False]
            roi_button_color = [no_update if not idx==ctx.triggered_id['index'] else 'success' for idx in range(n_inputs)]

        return update_infos, main_updated_info, modal_open, roi_button_color, main_button_color

    def run_function(self, clicked, function_name, function_inputs, function_input_info, structure_names, structure_number, main_roi_store, current_slide_information, overlay_names, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        function_name = get_pattern_matching_value(function_name)
        all_function_names = [i.title for i in self.custom_function]
        function_info = self.custom_function[all_function_names.index(function_name)]

        # Used in structure and layer type function types
        structure_names = get_pattern_matching_value(structure_names)

        # Used only in layer function types
        structure_number = get_pattern_matching_value(structure_number)
        current_slide_information = json.loads(get_pattern_matching_value(current_slide_information))
        session_data = json.loads(session_data)

        # Assigning kwarg vals from input components
        kwarg_inputs = {}
        for i_spec, i_val in zip(function_input_info,function_inputs):
            i_spec = json.loads(i_spec)
            if not i_spec['type']=='region':
                kwarg_inputs[i_spec['name']] = i_val
            else:
                kwarg_inputs[i_spec['name']] = i_spec['roi']

        all_input_names = [i['name'] for i in function_info.input_spec]
        all_input_types = [i['type'] for i in function_info.input_spec]

        if function_info.function_type=='layer':
            # For functions which are called on a whole layer
            # Getting the layer id
            slide_annotation_metadata = current_slide_information.get('annotation_metadata')
            slide_annotation_names = [
                i.get('name') for i in slide_annotation_metadata
            ]            
            layer_id = slide_annotation_metadata[slide_annotation_names.index(structure_names)]['_id']
            structure_generator = self.database.get_structure_generator(layer_id = layer_id)

            function_output = []
            for f in structure_generator:
                if any([i in all_input_types for i in ['image','mask']]):
                    f_img, f_mask = self.get_feature_image(
                        feature = {'type': 'Feature', 'geometry': f.geom, 'properties': {'id': f.id} | f.properties},
                        slide_information = current_slide_information,
                        return_mask = 'mask' in all_input_types,
                        return_image = 'image' in all_input_types
                    )
                    if not f_img is None:
                        kwarg_inputs[all_input_names[all_input_types.index('image')]] = f_img
                    
                    if not f_mask is None:
                        kwarg_inputs[all_input_names[all_input_types.index('mask')]] = f_mask

                if 'annotation' in all_input_types:
                    kwarg_inputs[all_input_names[all_input_types.index('annotation')]] = {'type': 'Feature', 'geometry': f.geom, 'properties': {'id': f.id} | f.properties}

                function_output.extend(function_info.function(**kwarg_inputs))

        elif function_info.function_type=='structure':
            # For functions which are called on each structure/feature individually
            # Getting the layer id
            slide_annotation_metadata = current_slide_information.get('annotation_metadata')
            slide_annotation_names = [
                i.get('name') for i in slide_annotation_metadata
            ]            
            layer_id = slide_annotation_metadata[slide_annotation_names.index(structure_names)]['_id']
            structure_generator = self.database.get_structure_generator(layer_id = layer_id)


            function_output = []
            for f in structure_generator:
                if any([i in all_input_types for i in ['image','mask']]):
                    f_img, f_mask = self.get_feature_image(
                        feature = {'type': 'Feature', 'geometry': f.geom, 'properties': {'id': f.id} | f.properties},
                        slide_information = current_slide_information,
                        return_mask = 'mask' in all_input_types,
                        return_image = 'image' in all_input_types
                    )
                    if not f_img is None:
                        kwarg_inputs[all_input_names[all_input_types.index('image')]] = f_img
                    
                    if not f_mask is None:
                        kwarg_inputs[all_input_names[all_input_types.index('mask')]] = f_mask

                if 'annotation' in all_input_types:
                    kwarg_inputs[all_input_names[all_input_types.index('annotation')]] = {'type': 'Feature', 'geometry': f.geom, 'properties': {'id': f.id} | f.properties}

                function_output.extend(function_info.function(**kwarg_inputs))
                break

        elif function_info.function_type=='ROI':

            main_roi = json.loads(get_pattern_matching_value(main_roi_store))['roi']         
            main_gdf = gpd.GeoDataFrame.from_features(main_roi['features'])
            main_bounds = main_gdf.total_bounds   
            # for ROI-level functions
            if 'annotation' in all_input_types:
                scaled_intersecting_anns = []

                slide_annotation_metadata = current_slide_information.get('annotation_metadata')
                for s in slide_annotation_metadata:
                    intersecting_structure_ids = self.database.get_structures_in_bbox(
                        bbox = main_bounds,
                        item_id = current_slide_information.get('id'),
                        layer_id = s.get('_id')
                    )

                    if len(intersecting_structure_ids)>0:
                        structure_generator = self.database.get_structure_generator(
                            structure_id = intersecting_structure_ids
                        )

                        intersecting_in_layer = {
                            'type': 'FeatureCollection',
                            'features': [
                                {
                                    'type': 'Feature',
                                    'geometry': geojson.utils.map_geometries(
                                        lambda g: geojson.utils.map_tuples(lambda c: (c[0]-main_bounds[0],c[1] - main_bounds[1]),g),
                                        f.geom
                                    ),
                                    'properties': {'id': f.id} | f.properties
                                }
                                for f in structure_generator
                            ],
                            'properties': {
                                'id': s.get('_id'),
                                'name': s.get('name')
                            }
                        }

                        scaled_intersecting_anns.append(s_geo)

                kwarg_inputs[all_input_names[all_input_types.index('annotation')]] = scaled_intersecting_anns
            
            if 'image' in all_input_types:
                roi_img, _ = self.get_feature_image(
                    feature = main_roi['features'][0],
                    slide_information = current_slide_information,
                    return_mask = False,
                    return_image = True
                )

                kwarg_inputs[all_input_names[all_input_types.index('image')]] = roi_img
            
            function_output = function_info.function(**kwarg_inputs)
        
        if not type(function_output)==tuple and not type(function_output)==list:
            function_output = [function_output]
        elif type(function_output)==tuple:
            function_output = [function_output]

        output_children = []
        output_content = []
        for o_idx, (output,spec) in enumerate(zip(function_output,function_info.output_spec)):
            output_children.append(
                self.make_output(output,spec,o_idx)
            )

            #Adding outputs to the output_content list
            # available types include string, numeric, annotation, image, and function
            if spec.type in ['string','numeric','annotation']:
                if spec.type=='numeric':
                    if type(output)==np.ndarray:
                        output_content.append(output.tolist())
                    else:
                        output_content.append(output)
                else:
                    output_content.append(output)
            elif spec.type=='image':
                output_content.append(
                    f'/tmp/image_output_{o_idx}.png'
                )

            elif spec.type=='function':
                output_content.append(
                    'function-output'
                )
            
        #TODO: Specifying output data here depending on what the function output is

        output_data = json.dumps({
            'content': output_content,
            'filename': f'{function_info.title}_output.json'
        })


        return [output_children], [output_data]

    def download_data(self, clicked, data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        data = json.loads(get_pattern_matching_value(data))

        # Checking if any images or function outputs are present
        img_present = any(['.png' in i for i in data.get('content')])
        func_present = any(['function-output'==i for i in data.get('content')])

        #TODO: Currently this method for downloading data only works for string/numeric output types
        # Need some kind of dynamic method for storing/re-generating output to save for image/function types
        if not img_present and not func_present:
            return [{'content': json.dumps(data.get('content'),indent=4),'filename': data.get('filename')}]
        
        else:
            raise exceptions.PreventUpdate







