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
                "roi": True
            },
            {
                "name": "Example Numeric Label",
                "description": "",
                "type": "numeric",
                "min": 0,
                "max": 100,
                "roi": False
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
                "roi": False
            }
        ]
    }

    """
    def __init__(self,
                 schema_data: dict):
        
        self.schema_data = schema_data

        # Checking dictionary for acceptable keys and validity



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

        # Callback for updating the current slide
        # Callback for selecting existing annotation schema (cloud or local)
        # Callback for creating/updating annotation schema
        # Callback for adding new label (text, numeric, button, (Optional: ROI))
        # Callback for downloading annotation data

        # Optional: Callback for inviting user to existing annotation schema
        # Optional: Callback for admin panel indicating other user's progress

        self.blueprint.callback(
            [
                Input({'type': 'slide-select-drop','index': ALL},'value')
            ],
            [
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'slide-annotation-current-slide-div','index': ALL},'children')
            ]
        )(self.update_slide)

        self.blueprint.callback(
            [
                Input({'type':'slide-annotation-schema-drop','index': ALL},'value')
            ],
            [
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'slide-annotation-schema-parent-div','index':ALL},'children')
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
                'label': i['name'],
                'value': i['name']
            }
            for i in self.schemas
        ]

        return [new_schema_options]

    def update_slide(self, new_slide_index, session_data):
        

        if not any([i['value'] or i['value']==0 for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)
        new_slide = session_data['current'][get_pattern_matching_value(new_slide_index)]

        new_slide_div = html.Div(
            children = [
                html.h5(f'Labeling for: {new_slide["name"]}')
            ]
        )

        return [new_slide_div]
    
    def update_schema(self, new_schema_val, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        new_schema_val = get_pattern_matching_value(new_schema_val)

        new_ann_components = self.make_annotation_components(new_schema_val)

        return [new_ann_components]

    def make_annotation_components(self, schema_key):

        if not schema_key in [i.schema_data['name'] for i in self.schemas]:
            return f'Schema: {schema_key} Not Found!'
        
        schema_index = [i.schema_data['name'] for i in self.schemas].index(schema_key)
        schema_info = self.schemas[schema_index].schema_data
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
                        children = []
                    ),
                    html.Div(
                        children = [
                            self.make_input_component(i,idx)
                            for idx,i in enumerate(schema_info.get('annotations',[]))
                        ]
                    )
                ])
            ])
        ])

        PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(schema_div)

        return [schema_div]

    def make_input_component(self, input_spec, input_index):

        input_desc_column = [
            dbc.Row(html.H6(input_spec['name'])),
            dbc.Row(html.P(input_spec['description'])),
            dcc.Store(
                id = {'type': 'slide-annotation-input-info','index': input_index},
                data = json.dumps(input_spec),
                storage_type = 'memory'
            )
        ]

        if input_spec['type']=='text':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.Input(
                            type = 'text',
                            id = {'type': 'slide-annotation-input','index': input_index},
                            style = {'width': '100%'}
                        )
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
                        dbc.Input(
                            type = 'number',
                            id = {'type': 'slide-annotation-input','index': input_index},
                            style = {'width': '100%'}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])

        elif input_spec['type']=='options':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dcc.Checklist(
                            options = input_spec['options'],
                            id = {'type': 'slide-annotation-input','index': input_index},
                            style = {'width': '100%'}
                        )
                    ],md=7)
                ]),
                html.Hr()
            ])

        return input_component

    def add_label(self):
        pass

    def download_annotations(self):
        pass


