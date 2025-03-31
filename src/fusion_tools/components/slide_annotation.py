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

        self.local_schemas = []
        self.cloud_schemas = []

        if not self.preload_schema is None:
            self.load_local_schema(self.preload_schema)
        
        if not self.handler is None:
            self.load_cloud_schema()

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

        # Callback for updating Visualization Session
        # Callback for updating the current slide
        # Callback for selecting existing annotation schema (cloud or local)
        # Callback for creating/updating annotation schema
        # Callback for adding new label (text, numeric, button, (Optional: ROI))
        # Callback for downloading annotation data

        # Optional: Callback for inviting user to existing annotation schema
        # Optional: Callback for admin panel indicating other user's progress

        pass

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
            new_schema = None
        
        if not new_schema is None:
            self.local_schemas.extend(new_schema)

    def load_cloud_schema(self):
        """Checking linked DSA instance for annotation session collection
        """
        pass

    def update_slide(self, new_slide_info):
        pass
    
    def update_schema(self):
        pass

    def add_label(self):
        pass

    def download_annotations(self):
        pass


