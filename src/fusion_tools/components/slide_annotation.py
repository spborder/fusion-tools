"""
Components for annotation of entire slides by users

"""

import os
import sys
import json
import geojson
import geopandas as gpd
import numpy as np
import pandas as pd
import textwrap
import re
import uuid
import threading
import zipfile
from shutil import rmtree
from copy import deepcopy

from typing_extensions import Union
from shapely.geometry import box, shape
import plotly.express as px
import plotly.graph_objects as go
from umap import UMAP

from PIL import Image, ImageOps

from io import BytesIO
import requests

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

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import (
    find_intersecting, 
    extract_geojson_properties, 
    process_filters_queries,
    detect_histomics,
    histomics_to_geojson,
    export_annotations
)
from fusion_tools.utils.images import get_feature_image, write_ome_tiff, format_intersecting_masks
from fusion_tools.utils.stats import get_label_statistics, run_wilcox_rank_sum
from fusion_tools import Tool, MultiTool

from fusion_tools.handler.dsa_handler import DSAHandler


class SlideAnnotationSchema:
    """Specification for SlideAnnotation schema

    .. code-block:: json

    {
        "dsa_url": "optional",
        "name": "required",
        "description": "optional",
        "users": ["optional"],
        "admins": ["optional"],
        "annotations": [
            {
                "name": "Example Text Label",
                "description": "",
                "type": "text",
                "roi": True,
                "editable": True
            },
            {
                "name": "Example Numeric Label",
                "description": "",
                "type": "numeric",
                "min": 0,
                "max": 100,
                "roi": False,
                "editable": True
            },
            {
                "name": "Example Options Label",
                "description": "",
                "type": "options",
                "options": [
                    "option 1",
                    "option 2",
                    "option 3"
                ],
                "multi": False,
                "roi": False,
                "editable": True
            }
        ]
    }

    """
    def __init__(self,
                 schema_data: dict):
        
        self.schema_data = schema_data

        # Checking dictionary for acceptable keys and validity
        allowed_keys = ["dsa_url", "name","description","users","admins","annotations","slides"]
        allowed_annotation_keys = ["name","description","type","options","multi","roi","editable","min","max"]

        allowed_key_vals = {
            "type": ["text","numeric","options","roi"],
            "editable": [True, False, "admins"],
            "multi": [True, False],
        }

    def to_dict(self):
        return self.schema_data


class SlideAnnotation(MultiTool):
    """Component used for assigning labels to slides, allows for importing other schema

    :param MultiTool: General class for tool which works on multiple slides at once
    :type MultiTool: None
    """
    def __init__(self,
                 handler: Union[None,DSAHandler] = None,
                 preload_schema: Union[None, str, dict, list, SlideAnnotationSchema] = None
                ):

        super().__init__()

        self.handler = handler
        self.preload_schema = preload_schema

        self.schemas = []

        if not self.preload_schema is None:
            local_schemas = self.load_local_schema(self.preload_schema)
        else:
            local_schemas = []
        
        if not self.handler is None:
            cloud_schemas = self.load_cloud_schema()
        else:
            cloud_schemas = []
        
        self.schemas = local_schemas+cloud_schemas

    def __str__(self):
        return 'Slide Annotation'
    
    def load(self, component_prefix: int):

        self.component_prefix = component_prefix
        self.title = 'Slide Annotation'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def get_callbacks(self):
        
        #TODO: Remaining callbacks to implement:
        # Callback for creating/updating annotation schema

        # Optional: Callback for inviting user to existing annotation schema
        # Optional: Callback for admin panel indicating other user's progress

        self.blueprint.callback(
            [
                Input({'type': 'slide-select-drop','index': ALL},'value')
            ],
            [
                State({'type': 'slide-annotation-schema-drop','index': ALL},'value'),
                State({'type': 'slide-annotation-input-info','index': ALL},'data'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'slide-annotation-current-slide-div','index': ALL},'children'),
                Output({'type': 'slide-annotation-input','index': ALL},'value'),
                Output({'type': 'slide-annotation-input-info','index': ALL},'data'),
                Output({'type': 'slide-annotation-roi-input','index': ALL},'color')
            ]
        )(self.update_slide)

        self.blueprint.callback(
            [
                Input({'type':'slide-annotation-schema-drop','index': ALL},'value')
            ],
            [
                State({'type': 'slide-select-drop','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'slide-annotation-schema-parent-div','index':ALL},'children'),
                Output({'type': 'slide-annotation-download-button','index': ALL},'disabled'),
            ]
        )(self.update_schema)

        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-schema-refresh-icon','index': ALL},'n_clicks')
            ],
            [
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'slide-annotation-schema-drop','index': ALL},'options')
            ]
        )(self.refresh_schemas)

        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-edit-input','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'slide-annotation-input-info','index': ALL},'data')
            ],
            [
                Output({'type': 'slide-annotation-modal','index': ALL},'is_open'),
                Output({'type': 'slide-annotation-modal','index': ALL},'children')
            ]
        )(self.open_edit_modal)

        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-roi-input','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'slide-annotation-input-info','index': ALL},'data'),
                State({'type': 'map-tile-layer','index': ALL},'url'),
                State({'type': 'map-tile-layer','index': ALL},'tileSize')
            ],
            [
                Output({'type': 'slide-annotation-modal','index': ALL},'is_open'),
                Output({'type': 'slide-annotation-modal','index': ALL},'children')
            ]
        )(self.open_roi_modal)

        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-submit-labels','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'slide-annotation-input','index': ALL},'value'),
                State({'type': 'slide-annotation-input-info','index': ALL},'data'),
                State({'type': 'slide-annotation-schema-drop','index':ALL},'value'),
                State({'type': 'map-slide-information','index': ALL},'data'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'slide-annotation-output-parent','index':ALL},'children'),
                Output({'type': 'slide-annotation-download-button','index': ALL},'disabled'),
                Output('anchor-vis-store','data')
            ]
        )(self.submit_labels)

        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-roi-done-button','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'slide-annotation-edit-control','index': ALL},'geojson'),
                State({'type': 'slide-annotation-input-info','index': ALL},'data'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ],
            [
                Output({'type': 'slide-annotation-input-info','index': ALL},'data'),
                Output({'type': 'slide-annotation-modal','index': ALL},'is_open'),
                Output({'type': 'slide-annotation-roi-input','index': ALL},'color')
            ]
        )(self.submit_roi)

        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-download-button','index': ALL},'n_clicks')
            ],
            [
                State({'type':'slide-annotation-schema-drop','index': ALL},'value'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'slide-annotation-download-data','index': ALL},'data')
            ]
        )(self.download_annotations)


    def update_layout(self, session_data:dict, use_prefix:bool):

        # Components needed:
        # - Available Schema dropdown (shows existing schemas and New Schema)
        #   - Add refresh button for checking for cloud schema
        # - Current Slide info (shows name of current slide, id, any currently applied labels to that slide)
        #   - If this slide isn't added yet, have a button to "Add to Annotation Session" which reveals the annotation components
        #   - Underneath will be all schema components (rows of labeling components and "Submit" and "Clear" buttons at the bottom)
        # - Other slides labeled
        #   - If any others are added
        # - Download session data
        #   - Two files, one that is session metadata (schema) and the other which includes applied slide labels

        # Getting slide-annotation data from session 
        slide_annotation_data = session_data.get('data',{}).get('slide-annotation')
        if not slide_annotation_data is None:
            # Loading schemas from session data
            pass

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        dbc.Col(
                            html.H3('Slide Annotation')
                        )
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Col(
                            'Used for annotating whole slides following pre-specified schema'
                        )
                    ),
                    html.Hr(),
                    dbc.Modal(
                        id = {'type': 'slide-annotation-modal','index':0},
                        children = [],
                        is_open = False,
                        size = 'xl'
                    ),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label(
                                'Select Annotation Schema: '
                            ),
                            md = 4
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                options = [
                                    {
                                        'label': n.schema_data['name'],
                                        'value': n.schema_data['name']
                                    }
                                    for n in self.schemas
                                ],
                                value = [],
                                multi = False,
                                id = {'type': 'slide-annotation-schema-drop','index': 0}
                            ),
                            md = 6
                        ),
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-rotate fa-2x',
                                    n_clicks = 0,
                                    id = {'type': 'slide-annotation-schema-refresh-icon','index': 0}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'slide-annotation-schema-refresh-icon','index': 0},
                                children = 'Click to refresh available schema'
                            )
                        ])
                    ]),
                    html.Hr(),
                    html.Div(
                        id = {'type': 'slide-annotation-schema-parent-div','index': 0},
                        children = [
                            'Select a schema to get started!'
                        ]
                    ),
                    html.Div(
                        children = [
                            dbc.Button(
                                'Download Annotations',
                                className = 'd-grid col-12 mx-auto',
                                color = 'success',
                                disabled = True,
                                n_clicks = 0,
                                id = {'type': 'slide-annotation-download-button','index': 0}
                            ),
                            dcc.Download(
                                id = {'type': 'slide-annotation-download-data','index': 0}
                            )
                        ],
                        style = {'marginTop': '5px'}
                    )
                ])
            ])
        ])

        if use_prefix:
            PrefixIdTransform(prefix = self.component_prefix).transform_layout(layout)

        return layout

    def gen_layout(self, session_data:dict):

        self.blueprint.layout = self.update_layout(session_data, use_prefix = False)

    def load_local_schema(self, schema):
        """Adding/preloading component with annotation schemas
        
        :param schema: Filepath, data, or object containing information describing the new schema
        :type schema: Union[str, list, dict, SlideAnnotationSchema]
        """
        
        if type(schema)==str:
            # Attempting to load schema from filepath
            with open(schema,'r') as f:
                schema = json.load(f)
                f.close()

        if type(schema)==dict:
            new_schema = [SlideAnnotationSchema(
                schema_data = schema
            )]
        
        elif type(schema)==list:
            new_schema = [
                SlideAnnotationSchema(
                    schema_data = s
                )
                for s in schema
            ]
        
        elif type(schema)==SlideAnnotationSchema:
            new_schema = [schema]

        else:
            new_schema = []
        
        return new_schema

    def load_cloud_schema(self):
        """Checking linked DSA instance for annotation session collection
        """
        cloud_schemas = []


        return cloud_schemas
    
    def refresh_schemas(self, clicked, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        #TODO: check linked cloud instance for any new schemas added
        new_schema_options = [
            {
                'label': i.schema_data['name'],
                'value': i.schema_data['name']
            }
            for i in self.schemas
        ]

        new_schema_options += [
            {
                'label': 'New Schema',
                'value': 'New Schema'
            }
        ]

        return [new_schema_options]

    def update_slide(self, new_slide_index, schema_val, current_input_infos, session_data):
        

        if not any([i['value'] or i['value']==0 for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)
        new_slide = session_data['current'][get_pattern_matching_value(new_slide_index)]
        schema_val = get_pattern_matching_value(schema_val)

        new_slide_div = html.Div(
            children = [
                html.H5(f'Labeling for: {new_slide["name"]}')
            ]
        )

        # Checking if this slide has any labels        
        previous_labels = session_data.get('data',{}).get('slide-annotation',{}).get(schema_val,None)
        current_input_infos = [json.loads(i) for i in current_input_infos]

        if not previous_labels is None:
            slide_names = [i['Slide Name'] for i in previous_labels]
            if new_slide['name'] in slide_names:
                prev_input_vals = previous_labels[slide_names.index(new_slide['name'])]

                load_input_vals = [v for k,v in prev_input_vals.items() if not k in ['Slide Name','Slide ID'] and not '_ROI' in k]
                load_input_infos = [no_update if not i['roi'] else i | {'roi': prev_input_vals.get(f'{l}_ROI',True)} for i,l in zip(current_input_infos,[i for i in list(prev_input_vals.keys()) if not i in ['Slide Name','Slide ID']])]
                load_roi_input_colors = [no_update if not type(i['roi'])==dict else 'success' for i,l in zip(current_input_infos,[i for i in list(prev_input_vals.keys()) if not i in ['Slide Name','Slide ID']])]
            else:
                load_input_vals = [[] for i in range(len(ctx.outputs_list[1]))]
                load_input_infos = [no_update if not i['roi'] else i | {'roi': True} for i in current_input_infos]
                load_roi_input_colors = ['primary' if i['roi'] else 'secondary' for i in current_input_infos]
        else:
            load_input_vals = [[] for i in range(len(ctx.outputs_list[1]))]
            load_input_infos = [no_update if not i['roi'] else i | {'roi': True} for i in current_input_infos]
            load_roi_input_colors = ['primary' if i['roi'] else 'secondary' for i in current_input_infos]

        return [new_slide_div], load_input_vals, [json.dumps(i) if type(i)==dict else i for i in load_input_infos], load_roi_input_colors
    
    def update_schema(self, new_schema_val, current_slide_index, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        if not get_pattern_matching_value(current_slide_index) is None:
            current_slide = session_data['current'][get_pattern_matching_value(current_slide_index)]['name']
        else:
            current_slide = None

        new_schema_val = get_pattern_matching_value(new_schema_val)
        new_ann_components = self.make_annotation_components(new_schema_val, current_slide, session_data)

        # Checking if there is any data in the session for this schema
        schema_data = session_data.get('data',{}).get('slide-annotation',{}).get(new_schema_val)
        if not schema_data is None:
            disable_download_button = False
        else:
            disable_download_button = True

        return [new_ann_components], [disable_download_button]

    def make_annotation_components(self, schema_key, slide_name, session_data):

        if not schema_key in [i.schema_data['name'] for i in self.schemas]:
            return f'Schema: {schema_key} Not Found!'
        
        schema_index = [i.schema_data['name'] for i in self.schemas].index(schema_key)
        schema_info = self.schemas[schema_index].schema_data

        # Check if this schema has any data already in the session
        if 'slide-annotation' in session_data['data']:
            if schema_key in session_data['data']['slide-annotation']:
                schema_table = self.make_schema_label_table(session_data,schema_key)
                schema_data = session_data['data']['slide-annotation'][schema_key]
            else:
                schema_table = 'No labels added yet!'
                schema_data = None
        else:
            schema_table = 'No labels added yet!'
            schema_data = None

        if not schema_data is None:
            slide_names = [i['Slide Name'] for i in schema_data]
            if not slide_name is None:
                if slide_name in slide_names:
                    # First two values are Slide Name and Slide ID
                    slide_input_vals = schema_data[slide_names.index(slide_name)]
                else:
                    slide_input_vals = None
            else:
                slide_input_vals = None
        else:
            slide_input_vals = None


        schema_div = html.Div([
            dbc.Card([
                dbc.CardHeader(html.H4(schema_key)),
                dbc.CardBody([
                    dbc.Row(
                        schema_info.get('description')
                    ),
                    html.Hr(),
                    html.Div(
                        id = {'type': 'slide-annotation-current-slide-div','index': 0},
                        children = [
                            html.H5(f'Labeling for: {slide_name}') if not slide_name is None else ''
                        ]
                    ),
                    html.Div(
                        children = [
                            self.make_input_component(i,idx, slide_input_vals)
                            for idx,i in enumerate(schema_info.get('annotations',[]))
                        ]
                    ),
                    dbc.Row([
                        dbc.Button(
                            'Submit Labels',
                            className = 'd-grid col-12 mx-auto',
                            id = {'type': 'slide-annotation-submit-labels','index': 0},
                            n_clicks = 0,
                            color = 'primary',
                            disabled = False
                        )
                    ]),
                    html.Div(
                        id = {'type': 'slide-annotation-output-parent','index': 0},
                        children = [schema_table],
                        style = {
                            'marginTop': '10px',
                            'marginBottom': '10px',
                            'maxHeight': '20vh',
                            'overflow': 'scroll'
                        }
                    )
                ])
            ])
        ])

        PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(schema_div)

        return [schema_div]

    def make_input_component(self, input_spec, input_index, slide_input_vals):

        
        roi_input_color = 'secondary' if not input_spec.get('roi',False) else 'primary'
        use_val = []
        if not slide_input_vals is None:
            if input_spec.get('roi',False):
                if f"{input_spec['name']}_ROI" in slide_input_vals:
                    slide_input_roi = slide_input_vals.get(f"{input_spec['name']}_ROI")
                    if type(slide_input_roi)==dict:
                        input_spec['roi'] = slide_input_roi
                        roi_input_color = 'success'
                    else:
                        roi_input_color = 'primary'
                else:
                    roi_input_color = 'primary'
            
            if slide_input_vals.get(input_spec['name'],False):
                use_val = slide_input_vals.get(input_spec['name'])
            else:
                use_val = []

        input_desc_column = [
            dbc.Row(html.H6(input_spec['name'])),
            dbc.Row(html.P(input_spec['description'])),
            dcc.Store(
                id = {'type': 'slide-annotation-input-info','index': input_index},
                data = json.dumps(input_spec),
                storage_type = 'memory'
            )
        ]

        edit_button = dbc.Button(
            children = [
                html.A(
                    html.I(
                        className = 'fa-solid fa-pen-to-square'
                    ),
                ),
                dbc.Tooltip(
                    target = {'type': 'slide-annotation-edit-input','index': input_index},
                    children = 'Edit Input Properties'
                )
            ],
            id = {'type': 'slide-annotation-edit-input','index': input_index},
            color = 'primary' if input_spec.get('editable',False) else 'secondary',
            n_clicks = 0,
            disabled = not input_spec.get('editable',False) 
        ) 

        roi_button = dbc.Button(
            children = [
                html.A(
                    html.I(
                        className = 'fa-solid fa-draw-polygon'
                    ),
                ),
                dbc.Tooltip(
                    target = {'type': 'slide-annotation-roi-input','index': input_index},
                    children = 'Draw ROI'
                )
            ],
            id = {'type': 'slide-annotation-roi-input','index': input_index},
            color = roi_input_color,
            n_clicks = 0,
            disabled= roi_input_color=='secondary'
        ) 

        if input_spec['type']=='text':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.Input(
                                type = 'text',
                                value = use_val,
                                id = {'type': 'slide-annotation-input','index': input_index},
                            ),
                            roi_button,
                            edit_button                           
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
                            value = use_val,
                            id = {'type': 'slide-annotation-input','index': input_index}
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
                                value = use_val,
                                id = {'type': 'slide-annotation-input','index': input_index},
                            ),
                            roi_button,
                            edit_button                            
                        ])

                    ],md=7)
                ]),
                html.Hr()
            ])

        elif input_spec['type']=='options':
            #TODO: Find some workaround for the "multi" selection, all the className CSS options with dcc.Dropdown() didn't work here
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.Select(
                                options = input_spec['options'],
                                value = use_val,
                                id = {'type': 'slide-annotation-input','index': input_index}
                            ),
                            roi_button,
                            edit_button
                        ])
                    ],md=7)
                ]),
                html.Hr()
            ])

        return input_component

    def open_edit_modal(self, clicked, input_info):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        input_info = json.loads(get_pattern_matching_value(input_info))
        
        return [True], [json.dumps(input_info,indent=4)]
    
    def open_roi_modal(self, clicked, input_info, tile_url, tile_size):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        tile_url = get_pattern_matching_value(tile_url)
        tile_size = get_pattern_matching_value(tile_size)

        if any([i is None for i in [tile_url, tile_size]]):
            raise exceptions.PreventUpdate
        
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
                                    id = {'type': f'{self.component_prefix}-slide-annotation-edit-control','index': 0}
                                )
                            ]
                        )
                    ],
                    style = {'height': '40vh','width': '80%','margin': 'auto','display': 'inline-block'}
                ),
                dbc.Button(
                    'Done!',
                    className = 'd-grid col-12 mx-auto',
                    color = 'success',
                    n_clicks = 0,
                    id = {'type': f'{self.component_prefix}-slide-annotation-roi-done-button','index': 0}
                )
            ], style = {'padding': '10px 10px 10px 10px'})
        ]

        return [True], modal_children

    def edit_schema(self):
        pass

    def submit_labels(self, submit_clicked, input_vals, input_infos, schema_name, slide_information, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)
        schema_name = get_pattern_matching_value(schema_name)
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        # If a slide hasn't been loaded yet
        if slide_information is None:
            raise exceptions.PreventUpdate
        elif len(list(slide_information.keys()))==0:
            raise exceptions.PreventUpdate

        input_infos = [json.loads(i) for i in input_infos]

        slide_annotation_data = session_data.get('data',{}).get('slide-annotation',{}).get(schema_name)
        this_slide_dict = {
            'Slide Name': slide_information['name'],
            'Slide ID': slide_information['metadata_url'].split('/')[-1]
        }

        this_slide_dict = this_slide_dict | {info['name']: val for info,val in zip(input_infos,input_vals)}
        if any([i['roi'] for i in input_infos]):
            for i in input_infos:
                if i['roi']:
                    this_slide_dict = this_slide_dict | {f'{i["name"]}_ROI': json.dumps(i['roi'])}

        if not slide_annotation_data is None:
            # If there is already recorded data for that schema
            # Checking if this slide is already present 
            current_ids = [i['Slide ID'] for i in slide_annotation_data]
            if this_slide_dict['Slide ID'] in current_ids:
                slide_annotation_data[current_ids.index(this_slide_dict['Slide ID'])] = this_slide_dict
            else:
                slide_annotation_data.append(this_slide_dict)
        else:
            # Initializing annotation schema
            if 'slide-annotation' in session_data['data']:
                session_data['data']['slide-annotation'][schema_name] = [this_slide_dict]
            else:
                session_data['data']['slide-annotation'] = {
                    schema_name: [this_slide_dict]
                }

        ann_schema_table = self.make_schema_label_table(session_data,schema_name)
        disable_download_button = False

        return [ann_schema_table], [disable_download_button], json.dumps(session_data)
    
    def make_schema_label_table(self, session_data, schema_name):

        schema_data = session_data.get('data',{}).get('slide-annotation',{}).get(schema_name)
        if not schema_data is None:
            ann_schema_df = pd.DataFrame.from_records(schema_data)

            ann_schema_table = dash_table.DataTable(
                id = {'type':f'{self.component_prefix}-slide-annotation-schema-table','index': 0},
                columns = [{'name':i,'id':i,'deletable':False,'selectable':True} for i in ann_schema_df.columns],
                data = ann_schema_df.to_dict('records'),
                fixed_columns={ 'headers': True, 'data': 1 },
                style_table={'minWidth': '100%'},
                style_cell={
                    # all three widths are needed
                    'minWidth': '250px', 'width': '250px', 'maxWidth': '250px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                },
                tooltip_data = [
                    {
                        column: {'value': str(value),'type':'markdown'}
                        for column,value in row.items()
                    } for row in ann_schema_df.to_dict('records')
                ],
                tooltip_duration = None
            )
        else:
            ann_schema_table = html.Div()

        return ann_schema_table

    def submit_roi(self, done_clicked, edit_geojson, input_info, slide_information):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        edit_geojson = get_pattern_matching_value(edit_geojson)

        n_inputs = len(input_info)
        input_info = json.loads(input_info[ctx.triggered_id['index']])

        slide_information = json.loads(get_pattern_matching_value(slide_information))
        scaled_geojson = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),edit_geojson)

        input_info['roi'] = scaled_geojson

        update_infos = [no_update if not idx==ctx.triggered_id['index'] else json.dumps(input_info) for idx in range(n_inputs)]
        modal_open = [False]
        roi_button_color = [no_update if not idx==ctx.triggered_id['index'] else 'success' for idx in range(n_inputs)]

        return update_infos, modal_open, roi_button_color

    def download_annotations(self, button_clicked, schema_name, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        schema_name = get_pattern_matching_value(schema_name)
        session_data = json.loads(session_data)

        annotation_data = session_data.get('data',{}).get('slide-annotation',{}).get(schema_name)
        if not annotation_data is None:
            annotation_df = pd.DataFrame.from_records(annotation_data)
            
            # Transforming the schema name so that it's a valid filename
            schema_save_name = re.sub(r'[^\w_.)( -]', '', schema_name)
            return [dcc.send_data_frame(annotation_df.to_csv,f'{schema_save_name}.csv')]
        else:
            return [no_update]

