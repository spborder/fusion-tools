"""

Components related to multi-level annotation of data in a SlideMap

"""


import os
import json
import numpy as np
import pandas as pd

import uuid
from copy import deepcopy


from typing_extensions import Union
from shapely.geometry import box, shape
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go

from io import BytesIO
from PIL import Image, ImageOps, ImageColor
import requests
import time
import geojson

import asyncio

from skimage.measure import label

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table, ClientsideFunction
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
from dash_extensions.javascript import Namespace, assign

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import (
    find_intersecting, extract_geojson_properties, 
    path_to_mask, process_filters_queries,
    path_to_indices, indices_to_path
)
from fusion_tools import asyncio_db_loop
from fusion_tools.components.base import Tool, MultiTool, BaseSchema, Handler


class AnnotationSchema(BaseSchema):
    """Annotation schema that can be ingested by all annotation components in FUSION
    """
    def __init__(self,
                 schema: str,
                 name: str = "FUSION Annotation Session",
                 description: str = "",
                 user_spec: Union[dict,None] = None,
                 annotations: Union[list,dict] = []
                 ):
        """Constructor method for AnnotationSchema in FUSION

        :param schema: One of "single", "bulk", "slide" where single = FeatureAnnotation, bulk = BulkLabels, and slide = SlideAnnotation
        :type schema: str
        :param name: Name that this annotation session will appear as (a unique id will be assigned on initialization), defaults to "FUSION Annotation Session"
        :type name: str, optional
        :param description: Optional text description to include for this annotation task., defaults to ""
        :type description: str, optional
        :param user_spec: Dictionary with two keys: users and admins. Each key contains a list of user login names or ids., defaults to None
        :type user_spec: Union[dict,None], optional
        :param annotations: List of different annotations for this schema. Keys for each include name, description, type, and type-specific keys, defaults to []
        :type annotations: Union[list,dict], optional

        Available annotation types available for each schema are:
            - FeatureAnnotation:
                - "class"
                    - color: str, rgba(0-255,0-255,0-255,0.0-1.0) format
                - "text"
                    - maxLength: int = 1000
                - "numeric"
                    - min
                    - max
                - "options"
                    - options: list = [], list of strings for each option in a dropdown
                - "radio"
                    - values: list = [], list of values to assign for exclusive labels
                - "checklist"
                    - values: list = [], list of values to assign for multiple labels
                - Each annotation type can also have a "pinned" kwarg to pull that annotation out of the dropdown menu
            - BulkLabels:
                - "exclusive"
                - "inclusive"
                - "unlabeled"
            - SlideAnnotation:
                - (same as FeatureAnnotation)
                - "roi"
                - Each annotation in a SlideAnnotation schema may also have "roi":bool as an additional keyword to enable manual ROIs for any label (roi types ignore this parameter)
        """

        self.schema = schema
        self.name = name
        self.description = description
        self.user_spec = user_spec
        self.annotations = annotations

        for a in self.annotations:
            if a.get('id') is None:
                a['id'] = uuid.uuid4().hex[:24]

        self.id = uuid.uuid4().hex[:24]
    
    def add_annotation(self, annotation_dict: dict):
        """Add annotation to AnnotationSchema

        :param annotation_dict: See schema description for more details on what can be added
        :type annotation_dict: dict
        """

        if annotation_dict.get('id') is None:
            annotation_dict['id'] = uuid.uuid4().hex[:24]

        self.annotations.append(annotation_dict)

    def add_user(self, user_dict:Union[dict,str], admin:bool = False):
        """Add a new user to AnnotationSchema

        :param user_dict: User info (login, _id) or just login name to add to schema
        :type user_dict: Union[dict,str]
        :param admin: Whether this user is added as an admin to the schema or not, defaults to False
        :type admin: bool, optional
        """
        if admin:
            self.user_spec['admins'].append(user_dict)
        else:
            self.user_spec['users'].append(user_dict)
    
    def export_data(self, database, user: dict, include_users: Union[list,None] = None):
        pass


#TODO: Data storage method
# Local (files, database), cloud (DSA,?), custom

class AnnotationSession:
    """Component for organizing multiple types of AnnotationSchemas
    """
    title = 'Annotation Session'
    description = 'Component for organizing and interacting with multiple AnnotationSchemas'

    def __init__(self,
                 schemas: Union[list,AnnotationSchema,None] = None,
                 editable: bool = False):
        
        self.schemas = schemas
        self.editable = editable

    def __str__(self):
        return self.title
    
    def load(self, component_prefix: int):

        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        # Add callbacks here
        self.get_callbacks()

    def gen_layout(self, session_data: dict):

        self.blueprint.layout = self.update_layout(session_data, use_prefix = False)

    def update_layout(self, sesion_data: dict, use_prefix: bool):

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
                    html.Hr(),
                    dbc.Row([])
                ])
            ])
        ])

        if use_prefix:
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(layout)

        return layout

    def get_callbacks(self):
        pass



class FeatureAnnotation(Tool):
    """Enables annotation (drawing) on top of structures in the SlideMap using a separate interface.

    :param Tool: General Class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    title = "Feature Annotation"
    description = 'Used for annotating (drawing) and labeling individual structures in the SlideMap'
    
    annotation_types = ["class","text","numeric","options","radio","checklist"]
    annotation_descriptions = [
        "Hand-drawn annotation on top of structures.",
        "Free text label applied to a structure.",
        "Numeric value assigned to a structure.",
        "Dropdown menu selection from list of possible options (one value permitted).",
        "Filled in circle used for selecting between two or more values (one value permitted).",
        "Set of selectable items for assigning multiple values to a single structure (multiple values permitted)."
    ]

    def __init__(self,
                 editable: bool = False,
                 annotations: Union[list,dict,None,AnnotationSchema] = None,
                 user_spec: Union[dict,None] = None):
        """Constructor method
        
        :param annotations: Annotations schema as specified in AnnotationSchema
        :type annotations: Union[list,dict,None], optional
        """
        super().__init__()

        # Overruling inherited session_update prop
        self.session_update = True

        self.editable = editable
        self.annotations = annotations
        self.user_spec = user_spec

        # Making sure every annotation has a unique id
        if isinstance(self.annotations,AnnotationSchema):
            if not self.user_spec is None:
                self.user_spec = self.user_spec | self.annotations.user_spec

            self.annotations = self.annotations.annotations

        elif type(self.annotations)==dict:
            if self.annotations.get('id') is None:
                self.annotations['id'] = uuid.uuid4().hex[:24]

            self.annotations = [self.annotations]
        elif type(self.annotations)==list:
            for a in self.annotations:
                if a.get('id') is None:
                    a['id'] = uuid.uuid4().hex[:24]
        
        elif self.annotations is None:
            self.annotations = []
    
    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        # Add callbacks here
        self.get_namespace()
        self.get_callbacks()
        self.feature_annotation_callbacks()

    def get_scale_factors(self, image_metadata: dict):
        """Function used to initialize scaling factors applied to GeoJSON annotations to project annotations into the SlideMap CRS (coordinate reference system)

        :return: x and y (horizontal and vertical) scale factors applied to each coordinate in incoming annotations
        :rtype: float
        """

        base_dims = [
            image_metadata['sizeX']/(2**(image_metadata['levels']-1)),
            image_metadata['sizeY']/(2**(image_metadata['levels']-1))
        ]

        #x_scale = (base_dims[0]*(240/image_metadata['tileHeight'])) / image_metadata['sizeX']
        #y_scale = -((base_dims[1]*(240/image_metadata['tileHeight'])) / image_metadata['sizeY'])

        x_scale = base_dims[0] / image_metadata['sizeX']
        y_scale = -(base_dims[1]) / image_metadata['sizeY']


        return x_scale, y_scale

    def check_annotation_list(self, session_data):

        feature_annotation_session_data = session_data.get('data',{}).get('feature-annotation')

        annotations_list = self.annotations
        if not feature_annotation_session_data is None:
            current_names = [i.get('name') for i in annotations_list]

            # Adding new labels/colors from session_data (non-overlapping)
            annotations_list += [
                i for i in feature_annotation_session_data.get('annotations',[])
                if not i.get('name') in current_names
            ]
            current_names = [i.get('name') for i in annotations_list]

            # Updating colors based on user selections (overlapping)
            overlap_names = [i for i in feature_annotation_session_data.get('annotations',[]) if i.get('name') in current_names]
            for o in overlap_names:
                annotations_list[current_names.index(o.get('name'))] = o
        else:
            current_names = [i.get('name') for i in annotations_list]

        return annotations_list, current_names

    def update_layout(self, session_data:dict, use_prefix:bool):
        """Generating layout for component
        """

        feature_annotation_session_data = session_data.get('data',{}).get('feature-annotation')

        annotations_list = self.annotations
        if not feature_annotation_session_data is None:
            current_names = [i.get('name') for i in annotations_list]

            # Adding new labels/colors from session_data (non-overlapping)
            annotations_list += [
                i for i in feature_annotation_session_data.get('annotations',[])
                if not i.get('name') in current_names
            ]
            current_names = [i.get('name') for i in annotations_list]

            # Updating colors based on user selections (overlapping)
            overlap_names = [i for i in feature_annotation_session_data.get('annotations',[]) if i.get('name') in current_names]
            for o in overlap_names:
                annotations_list[current_names.index(o.get('name'))] = o

        # Adding non-pinned values to the main dropdown menu
        dropdown_vals = [
            {
                'label': html.Div([
                    i.get('name')
                ]),
                'value': i.get('name')
            }
            for idx,i in enumerate(annotations_list)
            if not i.get('pinned',False)
        ]

        pinned_vals = [
            [i,idx] for idx,i in enumerate(annotations_list) if i.get('pinned',False)
        ]

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
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Select structure: ',html_for = {'type': 'feature-annotation-structure-drop','index': 0})
                        ], md = 3),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = False,
                                placeholder = "Structure",
                                id = {'type': 'feature-annotation-structure-drop','index': 0},
                                style = {'width': '100%'}
                            )
                        ],md =7),
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-rotate fa-2x',
                                    n_clicks = 0,
                                    id = {'type': 'feature-annotation-refresh-icon','index': 0}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'feature-annotation-refresh-icon','index': 0},
                                children = 'Click to refresh available structures'
                            )
                        ],md = 2,align='center'),
                        dcc.Store(
                            id = {'type': 'feature-annotation-current-structures','index': 0},
                            storage_type='memory',
                            data = json.dumps({})
                        ),
                        dcc.Store(
                            id = {'type': 'feature-annotation-slide-information','index': 0},
                            storage_type = 'memory',
                            data = json.dumps({})
                        )
                    ],style = {'marginBottom': '10px'},align='center'),
                    dbc.Row([
                        dbc.Progress(
                            id = {'type': 'feature-annotation-progress','index': 0},
                            style = {'marginBottom':'5px','width': '100%'},
                        )
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Row([
                                html.Div(
                                    dcc.Loading(
                                        dcc.Graph(
                                            id = {'type': 'feature-annotation-figure','index': 0},
                                            figure = go.Figure(
                                                layout = {
                                                    'margin': {'l':0,'r':0,'t':0,'b':0},
                                                    'xaxis': {'showticklabels': False,'showgrid': False},
                                                    'yaxis': {'showticklabels': False, 'showgrid': False},
                                                    'dragmode': 'drawclosedpath'
                                                }
                                            ),
                                            config = {
                                                'modeBarButtonsToAdd': [
                                                    'drawopenpath',
                                                    'drawclosedpath',
                                                    'eraseshape'
                                                ]
                                            }
                                        )
                                    )
                                )
                            ]),
                            html.Div(
                                id = {'type': 'feature-annotation-buttons-div','index': 0},
                                children = [
                                    dcc.Loading(
                                        dbc.Row([
                                            dbc.Col([
                                                dbc.Button(
                                                    'Previous',
                                                    className = 'd-grid col-12 mx-auto',
                                                    n_clicks = 0,
                                                    disabled = True,
                                                    id = {'type': 'feature-annotation-previous','index': 0}
                                                )
                                            ],md = 4),
                                            dbc.Col([
                                                dcc.Input(
                                                    value = [],
                                                    disabled = True,
                                                    type = 'number',
                                                    debounce = True,
                                                    step = 1,
                                                    min = 1,
                                                    id = {'type': 'feature-annotation-index-input','index': 0},
                                                    style = {'width': '100%','height': '100%', 'text-align': 'center', 'font-size': '25','font-weight': 'bold'}
                                                )
                                            ],md = 4),
                                            dbc.Col([
                                                dbc.Button(
                                                    'Next',
                                                    className = 'd-grid col-12 mx-auto',
                                                    n_clicks = 0,
                                                    disabled = True,
                                                    id = {'type': 'feature-annotation-next','index': 0}
                                                )
                                            ],md = 4)
                                        ],align='center')
                                    )
                                ],
                                style = {'marginTop':'10px'}
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Annotation Options')
                        ])
                    ],style = {'marginTop': '5px'}),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Annotations: ',html_for = {'type': 'feature-annotation-drop','index': 0})
                        ],md = 2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = dropdown_vals,
                                value = [],
                                multi = False,
                                placeholder = 'Annotation',
                                id = {'type': 'feature-annotation-drop','index': 0}
                            )
                        ], md = 8),
                        dbc.Col([
                            html.A(
                                children = [
                                    html.I(
                                        className = 'bi bi-pin-angle-fill h3',
                                    )
                                ],
                                n_clicks = 0,
                                id = {'type': 'feature-annotation-pin-icon','index': 0},
                                style = {'float': 'right'}
                            ),
                            dbc.Tooltip(
                                target = {'type': 'feature-annotation-pin-icon','index': 0},
                                children = ['Pin annotation item below!']
                            )
                        ], md = 'auto'),
                        dbc.Col([
                            html.A(
                                children = [
                                    html.I(
                                        className = 'bi bi-plus-circle-fill h3'
                                    )
                                ],
                                n_clicks = 0,
                                id = {'type': 'feature-annotation-add-new-icon','index': 0},
                                style = {'float': 'right'}
                            ),
                            dbc.Tooltip(
                                target = {'type': 'feature-annotation-add-new-icon','index': 0},
                                children = ['Add new annotation!']
                            )
                        ],md = 'auto') if self.editable else html.Div()
                    ],align = 'center'),
                    dbc.Modal(
                        id = {'type': 'feature-annotation-add-modal','index': 0},
                        children = [],
                        is_open = False,
                        size = 'xl'
                    ),
                    dbc.Row([
                        html.Div(
                            children = [],
                            id = {'type': 'feature-annotation-annotation-parent-div','index': 0}
                        )
                    ]),
                    dcc.Store(
                        id = {'type': 'feature-annotation-store','index': 0},
                        data = json.dumps({}),
                        storage_type='memory'
                    ),
                    dbc.Row([
                        html.Div(
                            children = [
                                self.generate_pinned_components(i[0],i[1])
                                for i in pinned_vals
                            ],
                            id = {'type': 'feature-annotation-pinned-parent-div','index': 0}
                        )
                    ]),
                    html.Hr(),
                    dbc.Accordion(
                        start_collapsed = True,
                        id = {'type': 'feature-annotation-extra-options-accordion','index': 0},
                        children = [
                            dbc.AccordionItem(
                                title = 'Region Options',
                                item_id='region-options',
                                children = [
                                    dbc.Row([
                                        dmc.Switch(
                                            id = {'type':'feature-annotation-grab-viewport','index': 0},
                                            size = 'lg',
                                            onLabel = 'ON',
                                            offLabel = 'OFF',
                                            checked = False,
                                            label = 'Grab structures in Viewport',
                                            description = 'Select whether or not to only grab structures in the current viewport.'
                                        )
                                    ]),
                                    dbc.Row([
                                        dbc.Col(
                                            dbc.Label('Bounding Box Padding:'),
                                            md = 4
                                        ),
                                        dbc.Col(
                                            dcc.Input(
                                                type = 'number',
                                                value = 50,
                                                id = {'type': 'feature-annotation-bbox-padding','index': 0},
                                                style = {'width': '100%'}
                                            ),
                                            md = 8
                                        )
                                    ],style = {'marginTop':'5px','marginBottom':'5px'}),
                                ]
                            ),
                            dbc.AccordionItem(
                                title = 'Export Annotations',
                                item_id = 'export-annotations',
                                children = [
                                    html.Div(
                                        id = {'type': 'feature-annotation-export-annotations-div','index': 0},
                                        children = []
                                    )
                                ]
                            )
                        ]
                    )
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow': 'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(layout)

        return layout

    def gen_layout(self, session_data:dict):

        self.blueprint.layout = self.update_layout(session_data,use_prefix=False)

    def get_callbacks(self):
        """Initializing callbacks and adding to DashBlueprint
        """

        # Updating with new slide
        self.blueprint.callback(
            [
                Input({'type': 'slide-select-drop','index':ALL},'value')
            ],
            [
                Output({'type': 'feature-annotation-slide-information','index':ALL},'data'),
                Output({'type': 'feature-annotation-figure','index': ALL},'figure'),
                Output({'type': 'feature-annotation-next','index': ALL},'disabled'),
                Output({'type': 'feature-annotation-previous','index': ALL},'disabled'),
                Output({'type': 'feature-annotation-index-input','index': ALL},'disabled')
            ],
            [
                State('anchor-vis-store','data')
            ]
        )(self.update_slide)

        #TODO: Add the "show un-annotated only" option here somewhere
        # Updating which structures are available in the dropdown menu
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-refresh-icon','index': ALL},'n_clicks'),
                Input({'type': 'feature-overlay','index':ALL},'name'),
            ],
            [
                Output({'type': 'feature-annotation-structure-drop','index': ALL},'options'),
                Output({'type': 'feature-annotation-current-structures','index': ALL},'data'),
                Output({'type': 'feature-annotation-progress','index': ALL},'value'),
                Output({'type': 'feature-annotation-progress','index': ALL},'label'),
                Output({'type': 'feature-annotation-figure','index': ALL},'figure')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'slide-map','index':ALL},'bounds'),
                State({'type': 'feature-annotation-bbox-padding','index': ALL},'value'),
                State({'type': 'feature-annotation-slide-information','index': ALL},'data'),
                State({'type': 'vis-layout-tabs','index': ALL},'active_tab'),
                State({'type': 'feature-annotation-grab-viewport','index':ALL},'checked')
            ]
        )(self.update_structure_options)

        # Updating which structure is in the annotation figure
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-structure-drop','index': ALL},'value'),
                Input({'type': 'feature-annotation-previous','index': ALL},'n_clicks'),
                Input({'type': 'feature-annotation-next','index': ALL},'n_clicks'),
                Input({'type': 'feature-annotation-index-input','index': ALL},'value')
            ],
            [
                Output({'type': 'feature-annotation-figure','index': ALL},'figure'),
                Output({'type':'feature-annotation-current-structures','index': ALL},'data'),
                Output({'type': 'feature-annotation-progress','index': ALL},'value'),
                Output({'type': 'feature-annotation-progress','index': ALL},'label'),
                Output({'type': 'feature-annotation-annotation-parent-div','index': ALL},'children'),
                Output({'type': 'feature-annotation-pinned-parent-div','index': ALL},'children'),
                Output({'type': 'feature-annotation-store','index': ALL},'data'),
                Output({'type': 'map-marker-div','index': ALL},'children'),
                Output({'type': 'feature-annotation-index-input','index': ALL},'value')
            ],
            [
                State({'type': 'feature-annotation-current-structures','index': ALL},'data'),
                State({'type':'feature-annotation-slide-information','index':ALL},'data'),
                State({'type': 'feature-annotation-drop','index': ALL},'value'),
                State('anchor-vis-store','data')
            ]
        )(self.update_structure)

        # Callback for pinning/unpinning an annotation type
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-pin-icon','index': ALL},'n_clicks'),
                Input({'type': 'feature-annotation-unpin-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-annotation-parent-div','index': ALL},'children'),
                Output({'type': 'feature-annotation-drop','index': ALL},'options'),
                Output({'type': 'feature-annotation-pinned-parent-div','index': ALL},'children'),
                Output('anchor-vis-store','data')
            ],
            [
                State({'type': 'feature-annotation-drop','index': ALL},'value'),
                State({'type': 'feature-annotation-drop','index': ALL},'options'),
                State({'type': 'feature-annotation-pinned-parent-div','index': ALL},'children'),
                State('anchor-vis-store','data')
            ]
        )(self.update_pinned)

        # Callback for creating annotation component when selected from the dropdown menu
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'feature-annotation-annotation-parent-div','index': ALL},'children')
            ],
            [
                State({'type': 'feature-annotation-store','index': ALL},'data'),
                State('anchor-vis-store','data')
            ]
        )(self.update_annotation_component)

        # Callback for grabbing annotations as they are input/added for a given structure
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-input','index': ALL},'value'),
                Input({'type': 'feature-annotation-figure','index': ALL},'relayoutData')
            ],
            [
                Output({'type': 'feature-annotation-store','index': ALL},'data')
            ],
            [
                State({'type': 'feature-annotation-store','index': ALL},'data'),
                State({'type': 'feature-annotation-input-info','index': ALL},'data'),
                State({'type': 'feature-annotation-figure','index':ALL},'figure')
            ]
        )(self.update_annotation)

        # Callback for new class annotation
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-annotate-new-class','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-figure','index': ALL},'figure')
            ],
            [
                State('anchor-vis-store','data')
            ]
        )(self.new_class_annotation)

        # Opening the add annotation modal
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-add-new-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-add-modal','index': ALL},'is_open'),
                Output({'type': 'feature-annotation-add-modal','index': ALL},'children')
            ]
        )(self.open_add_modal)

        # Update annotation type description
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-new-type-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'feature-annotation-type-description','index': ALL},'children')
            ]
        )(self.update_type_description)

        # Populating new annotation type options
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-new-type-submit','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-new-type-options-div','index': ALL},'children'),
                Output({'type': 'feature-annotation-new-submit','index': ALL},'disabled')
            ],
            [
                State({'type': 'feature-annotation-new-type-drop','index': ALL},'value')
            ]
        )(self.populate_type_options)

        # Adding/deleting new annotation option/value
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-new-add-option','index': ALL},'n_clicks'),
                Input({'type': 'feature-annotation-new-remove-option','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-new-add-option-div','index': ALL},'children'),
                Output({'type': 'feature-annotation-new-option-title','index': ALL},'children')
            ],
            [
                State({'type': 'feature-annotation-new-add-option-div','index': ALL},'children')
            ]
        )(self.update_type_options)

        # Adding new annotation type to available components
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-new-submit','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-add-modal','index': ALL},'is_open'),
                Output({'type': 'feature-annotation-drop','index': ALL},'options'),
                Output('anchor-vis-store','data')
            ],
            [
                State({'type': 'feature-annotation-new-type-drop','index':ALL},'value'),
                State({'type': 'feature-annotation-new-name','index': ALL},'value'),
                State({'type': 'feature-annotation-new-option','index': ALL},'value'),
                State('anchor-vis-store','data')
            ]
        )(self.submit_new_annotation_type)

        # Populating export accordion tab
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-extra-options-accordion','index': ALL},'active_item')
            ],
            [
                Output({'type': 'feature-annotation-export-annotations-div','index': ALL},'children')
            ],
            [
                State('anchor-vis-store','data')
            ]
        )(self.populate_export_data)

        # Exporting annotation data (different options for admin/user)
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-export-annotation-data','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-export-download','index': ALL},'data')
            ],
            [
                State({'type': 'feature-annotation-export-session-table','index': ALL},'selected_rows'),
                State({'type': 'feature-annotation-export-users-table','index': ALL},'selected_rows'),
                State('anchor-vis-store','data')
            ]
        )(self.export_annotation_data)

    def feature_annotation_callbacks(self):

        self.blueprint.clientside_callback(
            """
            function(structure_options, slide_annotations, bbox_padding, get_viewport, slide_information){
                
                if (bbox_padding[0]==undefined){
                    throw window.dash_clientside.PreventUpdate;
                } else if (slide_annotations[0]==undefined || slide_annotations[0]==='{}'){
                    throw window.dash_clientside.PreventUpdate;
                } else if (slide_information[0]==undefined){
                    throw window.dash_clientside.PreventUpdate;
                } else if (get_viewport[0]){
                    throw window.dash_clientside.PreventUpdate;
                }

                const annotations_array = JSON.parse(slide_annotations[0]);
                slide_information = JSON.parse(slide_information[0]);
                bbox_padding = bbox_padding[0] * slide_information.x_scale;

                const getBBox = (coords, padding = 0) => {
                    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
                    for (const [x, y] of coords) {
                        if (x < minX) minX = x;
                        if (y < minY) minY = y;
                        if (x > maxX) maxX = x;
                        if (y > maxY) maxY = y;
                    }
                    return [
                        minX - padding,
                        minY - padding,
                        maxX + padding, 
                        maxY + padding
                    ];
                };

                const computeBBoxes = (featureCollection, padding = 0) =>
                    Array.isArray(featureCollection?.features)
                        ? featureCollection.features
                            .filter(f => f.geometry?.type === 'Polygon' && Array.isArray(f.geometry.coordinates?.[0]))
                            .map(f => getBBox(f.geometry.coordinates[0], padding))
                        : [];
                
                const current_structure_bbox = annotations_array.map(featureCollection => {
                    const fc_name = featureCollection.properties.name;
                    return {
                        'name': fc_name,
                        'index': 0,
                        'bboxes': computeBBoxes(featureCollection, bbox_padding),
                        'ids': featureCollection.features.map(f => f.properties._id)
                    };
                });
            
                return[JSON.stringify(current_structure_bbox)];
            }
            """,
            [
                Input({'type':'feature-annotation-structure-drop','index': ALL},'options'),
                Input({'type': 'map-annotations-store','index': ALL},'data'),

            ],
            [
                Output({'type': 'feature-annotation-current-structures','index': ALL},'data')
            ],
            [
                State({'type': 'feature-annotation-bbox-padding','index': ALL},'value'),
                State({'type': 'feature-annotation-grab-viewport','index': ALL},'checked'),
                State({'type': 'feature-annotation-slide-information','index': ALL},'data')
            ]
        )

    def get_namespace(self):
        """Adding JavaScript functions to the FeatureAnnotation Namespace
        """
        self.js_namespace = Namespace(
            "fusionTools","featureAnnotation"
        )

        self.js_namespace.add(
            name = 'removeMarker',
            src = """
                function(e,ctx){
                    e.target.removeLayer(e.layer._leaflet_id);
                    ctx.data.features.splice(ctx.data.features.indexOf(e.layer.feature),1);
                }
            """
        )

        self.js_namespace.add(
            name = 'tooltipMarker',
            src = 'function(feature,layer,ctx){layer.bindTooltip("Double-click to remove")}'
        )

        self.js_namespace.add(
            name = "markerRender",
            src = """
                function(feature,latlng,context) {
                    marker = L.marker(latlng, {
                        title: "FeatureAnnotation Marker",
                        alt: "FeatureAnnotation Marker",
                        riseOnHover: true,
                        draggable: false,
                    });

                    return marker;
                }
            """
        )

        self.js_namespace.dump(
            assets_folder = self.assets_folder
        )

    def update_slide(self, slide_selection,vis_data):

        if not any([i['value'] or i['value']==0 for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        vis_data = json.loads(vis_data)
        slide_data = vis_data['current'][get_pattern_matching_value(slide_selection)]
        new_slide_data = {}
        new_slide_data['regions_url'] = slide_data['regions_url']
        new_metadata = requests.get(slide_data['image_metadata_url']).json()
        new_slide_data['x_scale'], new_slide_data['y_scale'] = self.get_scale_factors(new_metadata)
        new_slide_data['name'] = slide_data['name']

        new_slide_data = json.dumps(new_slide_data)
        new_figure = go.Figure()

        return [new_slide_data], [new_figure], [False], [False], [False]

    def generate_pinned_components(self, pinned:dict, pin_index: int, use_prefix:bool = False):
        """Function for generating pinned component

        :param pinned: Dictionary containing information on the component to be pinned
        :type pinned: dict
        :param pin_index: Index to use for annotation components
        :type pin_index: int
        :param use_prefix: Whether or not to use prefix (mostly True), defaults to False
        :type use_prefix: bool, optional
        """
        pinned_component = html.Div([
            dbc.Row([
                dbc.Col(
                    children = self.generate_annotation_component(pinned.get('name'), [pinned], pin_index),
                    md = 11
                ),
                dbc.Col([
                    html.A(
                        n_clicks = 0,
                        id = {'type': 'feature-annotation-unpin-icon','index':pin_index},
                        children = [
                            html.I(
                                className = 'bi bi-pin-angle h4'
                            )
                        ]
                    ),
                    dbc.Tooltip(
                        target = {'type': 'feature-annotation-unpin-icon','index': pin_index},
                        children = [
                            'Click to un-pin this item'
                        ]
                    )
                ])
            ])
        ],style = {'marginBottom':'5px','marginTop':'5px'})

        if use_prefix:
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(pinned_component)

        return pinned_component

    def generate_annotation_component(self, component_val:str, annotation_list: list, component_index: int):
        
        all_names = [i.get('name') for i in annotation_list]

        if component_val in all_names:
            component_info = annotation_list[all_names.index(component_val)]
            if component_info.get('type','') in self.annotation_types:

                if component_info.get('type')=='class':
                    annotation_component = html.Div([
                        dbc.Row([
                            dbc.Col(
                                children = [
                                    dbc.InputGroup([
                                        dbc.InputGroupText(
                                            component_info.get('name'),
                                            className = 'd-grid col-3'
                                        ),
                                        dbc.Button(
                                            'New Annotation',
                                            n_clicks = 0,
                                            id = {'type': 'feature-annotation-annotate-new-class','index': component_index},
                                            className = 'd-grid gap-0 col-9'
                                        )
                                    ],style = {'width': '100%'}),
                                    component_info.get('description',''),
                                    dcc.Store(
                                        id = {'type': 'feature-annotation-input-info','index': component_index},
                                        data = json.dumps(component_info),
                                        storage_type='memory'
                                    )
                                ],md=12
                            )
                        ],align='center')
                    ],style = {'marginTop':'5px'})
                elif component_info.get('type')=='text':
                    annotation_component = html.Div([
                        dbc.Row([
                            dbc.Col([
                                dbc.InputGroup([
                                    dbc.InputGroupText(component_info.get('name')),
                                    dbc.Input(
                                        type = 'text',
                                        value = component_info.get('value',''),
                                        id = {'type': 'feature-annotation-input','index': component_index}
                                    )
                                ],style = {'width': '100%'}),
                                component_info.get('description',''),
                                dcc.Store(
                                    id = {'type': 'feature-annotation-input-info','index': component_index},
                                    data = json.dumps(component_info),
                                    storage_type='memory'
                                )
                            ])
                        ])
                    ],style = {'marginTop':'5px'})
                elif component_info.get('type')=='options':
                    annotation_component = html.Div([
                        dbc.Row([
                            dbc.Col([
                                dbc.InputGroup([
                                    dbc.InputGroupText(component_info.get('name')),
                                    dbc.Select(
                                        options = component_info.get('options'),
                                        value = component_info.get('value',[]),
                                        id = {'type': 'feature-annotation-input','index': component_index}
                                    )
                                ],style = {'width': '100%'}),
                                component_info.get('description',''),
                                dcc.Store(
                                    id = {'type': 'feature-annotation-input-info','index': component_index},
                                    data = json.dumps(component_info),
                                    storage_type='memory'
                                )
                            ])
                        ])
                    ],style = {'marginTop':'5px'})
                elif component_info.get('type')=='numeric':
                    annotation_component = html.Div([
                        dbc.Row([
                            dbc.Col([
                                dbc.InputGroup([
                                    dbc.InputGroupText(component_info.get('name')),
                                    dbc.Input(
                                        type = 'number',
                                        value = component_info.get('value',[]),
                                        id = {'type': 'feature-annotation-input','index': component_index}
                                    )
                                ],style = {'width': '100%'}),
                                component_info.get('description',''),
                                dcc.Store(
                                    id = {'type': 'feature-annotation-input-info','index': component_index},
                                    data = json.dumps(component_info),
                                    storage_type='memory'
                                )
                            ])
                        ])
                    ],style = {'marginTop':'5px'})

                elif component_info.get('type')=='checklist':
                    annotation_component = html.Div([
                        dbc.Row([
                            dbc.Col([
                                dbc.InputGroup([
                                    dbc.InputGroupText(component_info.get('name')),
                                    dbc.Checklist(
                                        options = component_info.get('values'),
                                        value = component_info.get('value',[]),
                                        id = {'type': 'feature-annotation-input','index': component_index}
                                    )
                                ],style = {'width': '100%'}),
                                component_info.get('description',''),
                                dcc.Store(
                                    id = {'type': 'feature-annotation-input-info','index': component_index},
                                    data = json.dumps(component_info),
                                    storage_type='memory'
                                )
                            ])
                        ])
                    ],style = {'marginTop':'5px'})

                elif component_info.get('type')=='radio':
                    annotation_component = html.Div([
                        dbc.Row([
                            dbc.Col([
                                dbc.InputGroup([
                                    dbc.InputGroupText(component_info.get('name')),
                                    dbc.RadioItems(
                                        options = component_info.get('values'),
                                        value = component_info.get('value',[]),
                                        id = {'type': 'feature-annotation-input','index': component_index}
                                    )
                                ],style = {'width': '100%'}),
                                component_info.get('description',''),
                                dcc.Store(
                                    id = {'type': 'feature-annotation-input-info','index': component_index},
                                    data = json.dumps(component_info),
                                    storage_type='memory'
                                )
                            ])
                        ])
                    ],style = {'marginTop':'5px'})
        
                return annotation_component
            else:
                return html.Div()
        else:
            return html.Div()

    def update_structure_options(self,refresh_clicked, overlay_names, current_features, slide_bounds, bbox_padding, slide_information, active_tab, get_viewport):
        """Updating the structure options based on updated slide bounds

        :param slide_bounds: Current slide bounds
        :type slide_bounds: list
        :param current_features: Current set of GeoJSON FeatureCollections
        :type current_features: list
        :param active_tab: Active tab in vis-tools
        :type active_tab: list
        :return: Updated structure dropdown options and bounding box data
        :rtype: tuple
        """

        active_tab = get_pattern_matching_value(active_tab)
        progress_value = 0
        progress_label = '0%'
        new_figure = go.Figure()

        if not active_tab is None:
            if not active_tab == 'feature-annotation':
                raise exceptions.PreventUpdate
        else:
            raise exceptions.PreventUpdate
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        get_viewport = get_pattern_matching_value(get_viewport)

        structure_options = overlay_names
        structure_bboxes = {}
        if get_viewport:
            slide_map_bounds = get_pattern_matching_value(slide_bounds)
            if slide_map_bounds is None:
                raise exceptions.PreventUpdate
            
            if not slide_map_bounds is None:
                slide_map_box = box(slide_map_bounds[0][1],slide_map_bounds[0][0],slide_map_bounds[1][1],slide_map_bounds[1][0])
            else:
                slide_map_box = None
                
            bbox_padding = get_pattern_matching_value(bbox_padding)
            current_features = json.loads(get_pattern_matching_value(current_features))
            slide_information = json.loads(get_pattern_matching_value(slide_information))
            x_scale = slide_information['x_scale']
            y_scale = slide_information['y_scale']

            for g in current_features:
                if get_viewport:
                    intersecting_shapes, intersecting_properties = find_intersecting(g,slide_map_box)
                else:
                    intersecting_shapes = g
                if len(intersecting_shapes['features'])>0:

                    structure_bboxes[g['properties']['name']] = [
                        list(shape(f['geometry']).buffer(bbox_padding*x_scale).bounds) for f in intersecting_shapes['features']
                    ]
                    structure_bboxes[f'{g["properties"]["name"]}_index'] = 0

        new_structure_bboxes = json.dumps(structure_bboxes)

        return [structure_options], [new_structure_bboxes], [progress_value], [progress_label], [new_figure]

    @asyncio_db_loop
    def check_database(self, table_name: str = 'annotation', structure_id:Union[str,list,None] = None, user_id:Union[str,list,None] = None, session_id:Union[str,list,None] = None):
        """Check if a user(s) has any annotations for one or more structures

        :param structure_id: String uuid or list of uuids for structures
        :type structure_id: Union[str,list,None], optional
        :param user_id: String uuid or list of uuids for users
        :type user_id: Union[str,list,None], optional
        :param session_id: String uuid or list of uuids for sessions
        :type session_id: Union[str,list,None], optional
        """

        filters = {}
        #TODO: If the SlideMap instance is not using caching, structures are not present

        if not structure_id is None:
            filters = filters | {'structure': {'id': structure_id}}
        
        if not user_id is None:
            filters = filters | {'user': {'id': user_id}}
        
        if not session_id is None:
            filters = filters | {'session': {'id': session_id}}


        loop = asyncio.get_event_loop()
        db_annotations = loop.run_until_complete(
            asyncio.gather(
                self.database.search(
                    search_kwargs = {
                        'type': table_name,
                        'filters': filters
                    }
                )
            )
        )

        return db_annotations

    def update_structure(self, structure_drop_value, prev_click, next_click, structure_index_input, current_structure_data, slide_information, annotation_val, session_data):
        """Updating the current structure figure based on selections

        :param structure_drop_value: Structure name selected from dropdown menu
        :type structure_drop_value: list
        :param prev_click: Number of times Previous was clicked
        :type prev_click: list
        :param next_click: Number of times Next was clicked
        :type next_click: list
        :param structure_index_input: Index input value
        :type structure_index_input: list
        :param current_structure_data: Bounding box/id/etc. information for each structure
        :type current_structure_data: list
        :param slide_information: Information for the current slide (x_scale, y_scale used)
        :type slide_information: list
        :param annotation_val: Main annotation value selected
        :type annotation_val: list
        :param session_data: Visualization session data
        :type session_data: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        structure_drop_value = get_pattern_matching_value(structure_drop_value)
        current_structure_data = json.loads(get_pattern_matching_value(current_structure_data))
        structure_index_input = get_pattern_matching_value(structure_index_input)
        slide_information = json.loads(get_pattern_matching_value(slide_information))
        annotation_val = get_pattern_matching_value(annotation_val)
        session_data = json.loads(session_data)
        progress_value = 0
        progress_label = '0%'

        structure_names = [i['name'] for i in current_structure_data]

        if structure_drop_value is None or not structure_drop_value in structure_names:
            raise exceptions.PreventUpdate
        
        structure_index = structure_names.index(structure_drop_value)
        current_feature_index = current_structure_data[structure_index]['index']

        prev_bbox = current_structure_data[structure_index]['bboxes'][current_feature_index]
        prev_id = current_structure_data[structure_index]['ids'][current_feature_index]

        if 'feature-annotation-structure-drop' in ctx.triggered_id['type']:
            # Getting a new structure (not updating index):
            current_structure_region = current_structure_data[structure_index]['bboxes'][current_feature_index]
            current_structure_id = current_structure_data[structure_index]['ids'][current_feature_index]

        elif 'feature-annotation-previous' in ctx.triggered_id['type']:
            # Going to previous structure
            if current_feature_index==0:
                current_feature_index = len(current_structure_data[structure_index]['bboxes'])-1
            else:
                current_feature_index -= 1
            
            current_structure_region = current_structure_data[structure_index]['bboxes'][current_feature_index]
            current_structure_id = current_structure_data[structure_index]['ids'][current_feature_index]

            progress_value = round(100*((current_feature_index+1) / len(current_structure_data[structure_index]['bboxes'])))
            progress_label = f'{progress_value}%'

        elif 'feature-annotation-next' in ctx.triggered_id['type']:
            # Going to next structure
            if current_feature_index==len(current_structure_data[structure_index]['bboxes'])-1:
                current_feature_index = 0
            else:
                current_feature_index += 1

            current_structure_region = current_structure_data[structure_index]['bboxes'][current_feature_index]
            current_structure_id = current_structure_data[structure_index]['ids'][current_feature_index]

            progress_value = round(100*((current_feature_index+1) / len(current_structure_data[structure_index]['bboxes'])))
            progress_label = f'{progress_value}%'

        elif 'feature-annotation-index-input' in ctx.triggered_id['type']:
            # Going to structure at this number
            if structure_index_input<0:
                structure_index_input = 1
            elif structure_index_input>len(current_structure_data[structure_index]['bboxes']):
                structure_index_input = len(current_structure_data[structure_index]['bboxes'])
            
            # Structure index input starts at 1 (0 interpreted as False)
            current_feature_index = structure_index_input - 1
            current_structure_region = current_structure_data[structure_index]['bboxes'][current_feature_index]
            current_structure_id = current_structure_data[structure_index]['ids'][current_feature_index]

            progress_value = round(100*((current_feature_index+1) / len(current_structure_data[structure_index]['bboxes'])))
            progress_label = f'{progress_value}%'

            
        current_structure_data[structure_index]['index'] = current_feature_index

        # Pulling out the desired region:
        image_region, marker_centroid = self.get_structure_region(current_structure_region, slide_information)
        image_figure = go.Figure(px.imshow(np.array(image_region)))
        image_figure.update_layout(
            {
                'margin': {'l':0,'r':0,'t':0,'b':0},
                'xaxis':{'showticklabels':False,'showgrid':False},
                'yaxis':{'showticklabels':False,'showgrid':False},
                'dragmode':'drawclosedpath',
            }
        )

        new_markers_div = [
            dl.GeoJSON(
                data = {
                    'type': 'FeatureCollection',
                    'features': [
                        {
                            'type': 'Feature',
                            'geometry': {
                                'type': 'Point',
                                'coordinates': marker_centroid
                            },
                            'properties': {
                                'name': 'featureAnnotation Marker',
                                '_id': uuid.uuid4().hex[:24]
                            }
                        }
                    ]
                },
                pointToLayer=self.js_namespace("markerRender"),
                onEachFeature = self.js_namespace("tooltipMarker"),
                id = {'type': f'{self.component_prefix}-feature-annotation-markers','index': 0},
                eventHandlers = {
                    'dblclick': self.js_namespace('removeMarker')
                }
            )
        ]

        # Saving current annotation values to the database
        new_anns = self.check_database(
            structure_id = current_structure_id,
            user_id = session_data.get('user',{}).get('_id'),
            session_id = session_data.get('session',{}).get('id')
        )
        
        if len(new_anns[0])==0:
            updated_annotation_store = json.dumps(
                {
                    'id': uuid.uuid4().hex[:24],
                    'user': session_data.get('user',{}).get('_id'),
                    'session': session_data.get('session',{}).get('id'),
                    'structure': current_structure_id,
                    'data': []
                }
            )
        else:
            # datetime isn't JSON serializable
            last_update = new_anns[0][0].pop('updated')
            updated_annotation_store = json.dumps(new_anns[0][0])
        

        # Updating with current annotation values for selected annotation (from dropdown) and pinned annotation components
        annotations_list, current_names = self.check_annotation_list(session_data)
        if not len(new_anns[0])==0:
            prev_ann_values = new_anns[0][0]['data']
            layout_shape_list = []
            for p in prev_ann_values:
                annotations_list[current_names.index(p.get('name'))]['value'] = p.get('value')
                if p.get('type')=='class':
                    for s in p.get('shapes',[]):
                        path_string = indices_to_path(s)
                        line_color = p.get('color')
                        if 'a' in line_color:
                            fill_color = line_color.replace(line_color.split(',')[-1],'0.2)')
                        else:
                            fill_color = line_color.replace('(','a(').replace(')',',0.2)')
                        
                        layout_shape_list.append({
                            'path': path_string,
                            'line': {
                                'color': line_color
                            },
                            'fillcolor': fill_color
                        })

            if len(layout_shape_list)>0:
                image_figure.update_layout({
                    'shapes': layout_shape_list
                })

        if not annotation_val is None:
            main_ann_comp = self.generate_annotation_component(
                component_val = annotation_val,
                annotation_list = annotations_list,
                component_index=current_names.index(annotation_val)
            )
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(main_ann_comp)

            main_annotation_val = [main_ann_comp]
        else:
            main_annotation_val = [no_update]

        pinned_annotation_vals = [
            self.generate_pinned_components(
                pinned = p_o,
                pin_index=p_o_idx,
                use_prefix = True
            )
            for p_o_idx,p_o in enumerate(annotations_list)
            if p_o.get('pinned',False)
        ]

        if len(pinned_annotation_vals)==0:
            pinned_annotation_vals = no_update

        return [image_figure], [json.dumps(current_structure_data)], [progress_value], [progress_label], main_annotation_val, [pinned_annotation_vals], [updated_annotation_store], new_markers_div, [current_feature_index+1]

    def update_annotation(self,annotation_inputs, annotation_classes, current_annotation_data, input_infos, feature_figure):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_annotation_data = json.loads(get_pattern_matching_value(current_annotation_data))
        input_infos = [json.loads(i) for i in input_infos]
        
        if len(list(current_annotation_data.keys()))>0:
            # Processing annotation input components
            current_ann_ids = [i.get('id') for i in current_annotation_data['data']]
            non_class_inputs = [i for i in input_infos if not i.get('type')=='class']
            for info, ann in zip(non_class_inputs,annotation_inputs):
                if type(ann)==list:
                    if len(ann)==0:
                        continue
                
                elif type(ann)==str:
                    if ann=='':
                        continue

                if info.get('id') in current_ann_ids:
                    current_annotation_data['data'][current_ann_ids.index(info.get('id'))] = info | {'value': ann}
                else:
                    current_annotation_data['data'].append(info | {'value': ann})

            # Processing class inputs from figure.layout.shapes
            current_class_colors = [i.get('color') for i in current_annotation_data['data'] if i.get('type')=='class']
            available_class_colors = [i.get('color') for i in self.annotations if i.get('type')=='class']
            input_class_info = [i for i in input_infos if i.get('type')=='class']
            input_class_color = [i.get('color') for i in input_infos if i.get('type')=='class']
            
            feature_figure = get_pattern_matching_value(feature_figure)
            if not feature_figure is None:
                layout_data = feature_figure.get('layout')
                if 'shapes' in layout_data:
                    # Getting all unique annotated shape colors:
                    shape_colors = list(set([i.get('line',{}).get('color') for i in layout_data['shapes'] if 'path' in i]))
                    for s in shape_colors:
                        # Skip colors not in schema
                        if not s in available_class_colors:
                            print(f'{s} not in {available_class_colors}')
                            continue
                        all_class_shapes = [i.get('path') for i in layout_data['shapes'] if i.get('line',{}).get('color','')==s]
                        all_class_shapes = [i for i in all_class_shapes if not i is None]
                        
                        class_shape_indices = []
                        for a in all_class_shapes:
                            path_indices = path_to_indices(a)
                            class_shape_indices.append(path_indices.tolist())
                        
                        if s in current_class_colors:
                            current_annotation_data['data'][current_class_colors.index(s)] = current_annotation_data['data'][current_class_colors.index(s)] | {'shapes': class_shape_indices}
                        else:
                            current_annotation_data['data'].append(
                                input_class_info[input_class_color.index(s)] | {'shapes': class_shape_indices}
                            )

            #print(f'len(current_annotation_data["data"]): {len(current_annotation_data["data"])}')
            if len(current_annotation_data['data'])>0:
                db_dict = deepcopy(current_annotation_data)
                ann_id = db_dict.pop('id')
                get_create_result = self.database.get_create(
                    table_name = 'annotation',
                    inst_id = ann_id,
                    kwargs = db_dict
                )

        return [json.dumps(current_annotation_data)]

    def update_annotation_component(self, annotation_val,annotation_data, session_data):
        

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        annotation_data = json.loads(get_pattern_matching_value(annotation_data))
        annotation_val = get_pattern_matching_value(annotation_val)
        if annotation_val is None:
            return [html.Div()]

        annotations_list, current_names = self.check_annotation_list(session_data)
        if len(list(annotation_data.keys()))>0:
            if not len(annotation_data['data'])==0:
                for p in annotation_data['data']:
                    annotations_list[current_names.index(p.get('name'))]['value'] = p.get('value')

        new_annotation_component = self.generate_annotation_component(
            component_val = annotation_val,
            annotation_list = annotations_list,
            component_index = current_names.index(annotation_val)
        )

        PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(new_annotation_component)

        return [new_annotation_component]

    def extract_pinned_name(self, component_dict):

        pinned_names = ()
        if type(component_dict)==list:
            for c in component_dict:
                if type(c)==dict:
                    for key,value in c.items():
                        if key=='children':
                            if type(value) in [list,dict]:
                                pinned_names += self.extract_pinned_name(value)
                            elif type(value) == str:
                                pinned_names += (value,)
                        elif key=='props':
                            pinned_names += self.extract_pinned_name(value)
                elif type(c)==list:
                    pinned_names += self.extract_pinned_name(c)
                elif type(c)==str:
                    pinned_names += (c, )
                
        elif type(component_dict)==dict:
            for key,value in component_dict.items():
                if key=='children':
                    if type(value) in [list,dict]:
                        pinned_names+=self.extract_pinned_name(value)
                    elif type(value)==str:
                        pinned_names += (value,)
                elif key=='props':
                    pinned_names += self.extract_pinned_name(value)
        
        return pinned_names

    def update_pinned(self, pin_click, unpin_click, annotation_value, annotation_options, pinned_items, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        current_annotation = get_pattern_matching_value(annotation_value)
        session_data = json.loads(session_data)

        feature_annotation_session_data = session_data.get('data',{}).get('feature-annotation')

        annotations_list = self.annotations
        if not feature_annotation_session_data is None:
            current_names = [i.get('name') for i in annotations_list]

            # Adding new labels/colors from session_data (non-overlapping)
            annotations_list += [
                i for i in feature_annotation_session_data.get('annotations',[])
                if not i.get('name') in current_names
            ]
            current_names = [i.get('name') for i in annotations_list]

            # Updating colors based on user selections (overlapping)
            overlap_names = [i for i in feature_annotation_session_data.get('annotations',[]) if i.get('name') in current_names]
            for o in overlap_names:
                annotations_list[current_names.index(o.get('name'))] = o
        else:
            current_names = [i.get('name') for i in annotations_list]

        pinned_list = self.extract_pinned_name(get_pattern_matching_value(pinned_items))
        current_pinned_list = [i for i in pinned_list if i in current_names]
        if not get_pattern_matching_value(annotation_options) is None:
            current_dropdown_list = [i.get('value') for i in get_pattern_matching_value(annotation_options)]
        else:
            current_dropdown_list = []

        if 'feature-annotation-pin-icon' in ctx.triggered_id['type']:
            if current_annotation is None:
                raise exceptions.PreventUpdate

            # Pinning the selected annotation
            pinned_annotations = Patch()
            pinned_annotations.append(
                self.generate_pinned_components(
                    pinned = annotations_list[current_names.index(current_annotation)],
                    pin_index = current_names.index(current_annotation),
                    use_prefix = True
                )
            )

            ann_drop = Patch()
            del ann_drop[current_dropdown_list.index(current_annotation)]

            annotations_list[current_names.index(current_annotation)]['pinned'] = True

            # Only clearing the parent div children when pinning the current annotation
            ann_parent_div = html.Div()
        
        elif 'feature-annotation-unpin-icon' in ctx.triggered_id['type']:
            # Removing pinned annotation from pinned list and adding it back to the dropdown
            pinned_annotations = Patch()
            del pinned_annotations[current_pinned_list.index(current_names[ctx.triggered_id['index']])]

            ann_drop = Patch()
            ann_drop.append(
                {
                    'label': current_names[ctx.triggered_id['index']], 
                    'value': current_names[ctx.triggered_id['index']]
                }
            )

            annotations_list[current_names.index(current_names[ctx.triggered_id['index']])]['pinned'] = False

            # Not updating the annotation parent div when removing a pinned annotation
            ann_parent_div = no_update

        if 'feature-annotation' in session_data['data']:
            session_data['data']['feature-annotation']['annotations'] = annotations_list
        else:
            session_data['data']['feature-annotation'] = {
                'annotations': annotations_list
            }
        
        
        return [ann_parent_div], [ann_drop], [pinned_annotations], json.dumps(session_data)

    def get_structure_region(self, structure_bbox:list, slide_information: dict, scale:bool = True):
        """Using the tile server "regions_url" property to pull out a specific region of tissue

        :param structure_bbox: List of minx, miny, maxx, maxy coordinates
        :type structure_bbox: list
        :param scale: Whether or not to scale the bbox values to slide coordinates
        :type scale: bool
        """

        # Converting structure bbox from map coordinates to slide-pixel coordinates
        if scale:
            slide_coordinates = [
                int(structure_bbox[0]/slide_information['x_scale']), 
                int(structure_bbox[3]/slide_information['y_scale']), 
                int(structure_bbox[2]/slide_information['x_scale']), 
                int(structure_bbox[1]/slide_information['y_scale'])
            ]
        else:
            slide_coordinates = structure_bbox

        # Finding centroid of coordinates for marker point
        marker_centroid = [
            (structure_bbox[0]+structure_bbox[2])/2, (structure_bbox[1]+structure_bbox[3])/2
        ]

        #TODO: Update this function for multi-frame images
        image_region = Image.open(
            BytesIO(
                requests.get(
                    slide_information['regions_url']+f'?left={slide_coordinates[0]}&top={slide_coordinates[1]}&right={slide_coordinates[2]}&bottom={slide_coordinates[3]}'
                ).content
            )
        )

        return image_region, marker_centroid
    
    def new_class_annotation(self, clicked, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        annotations_list, current_names = self.check_annotation_list(session_data)

        updated_figure = Patch()
        new_line_color = annotations_list[ctx.triggered_id['index']].get('color')
        if 'a' in new_line_color:
            new_fill_color = new_line_color.replace(new_line_color.split(',')[-1],'0.2)')
        else:
            new_fill_color = new_line_color.replace('(','a(').replace(')',',0.2)')

        updated_figure['layout']['newshape']['line']['color'] = new_line_color
        updated_figure['layout']['newshape']['fillcolor'] = new_fill_color
        
        return [updated_figure]       

    def open_add_modal(self, clicked):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        add_modal_children = html.Div(
            dbc.Card([
                html.H4('Add new annotation'),
                html.Hr(),
                html.P('Select a new annotation type below to get started.'),
                html.Hr(),
                dbc.Row([
                    dbc.InputGroup([
                        dbc.InputGroupText('Annotation Types: '),
                        dbc.Select(
                            id = {'type': 'feature-annotation-new-type-drop','index': 0},
                            value = [],
                            options = self.annotation_types
                        ),
                        dbc.Button(
                            'Select Type',
                            id = {'type': 'feature-annotation-new-type-submit','index': 0}
                        )
                    ]),
                    html.Div(
                        id = {'type': 'feature-annotation-type-description','index': 0},
                        children = []
                    ),
                    html.Hr()
                ]),
                dbc.Row(
                    html.Div(
                        id = {'type': 'feature-annotation-new-type-options-div','index': 0},
                        children = []
                    )
                ),
                dbc.Row(
                    dbc.Button(
                        'Add to Session!',
                        id = {'type': 'feature-annotation-new-submit','index': 0},
                        className = 'd-grid col-9 mx-auto',
                        n_clicks = 0,
                        disabled = True
                    )
                )
            ]),
            style = {'padding': '15px 15px 15px 15px'}
        )

        PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(add_modal_children)

        return [True], [add_modal_children]

    def update_type_description(self, annotation_type):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        annotation_type = get_pattern_matching_value(annotation_type)
        if not annotation_type is None:
            if annotation_type in self.annotation_types:
                type_description = self.annotation_descriptions[self.annotation_types.index(annotation_type)]
            else:
                type_description = ''
        else:
            type_description = ''

        return [type_description]
    
    def rgb2hex(self,r,g,b):
        return "#{:02x}{:02x}{:02x}".format(r,g,b)

    def hex2rgb(self,hexcode):
        return f"rgb({','.join([str(i) for i in ImageColor.getcolor(hexcode,'RGB')])})"
    
    def rgba2rgb(self, rgba_str):
        rgb_vals = rgba_str.replace('rgba(','').replace('}','').split(',')
        rgb_str = f'rgb({rgb_vals[0]},{rgb_vals[1]},{rgb_vals[2]})'

        return rgb_str
    
    def populate_type_options(self, clicked, annotation_type):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        annotation_type = get_pattern_matching_value(annotation_type)
        if annotation_type is None:
            raise exceptions.PreventUpdate
        
        # Name for all types
        # class = color, text = None, numeric = min&max options = options, radio = values, checklist = values
        name_input = dbc.InputGroup([
            dbc.InputGroupText("Name of Annotation: "),
            dbc.Input(
                id = {'type': 'feature-annotation-new-name','index': 0},
                value = '',
                type = 'text',
                placeholder='Annotation Name',
                maxLength = 1000
            )
        ])

        if annotation_type=='class':
            type_inputs = [
                dbc.InputGroup([
                    dbc.InputGroupText("Color for New Class: "),
                    dbc.Input(
                        id = {'type': 'feature-annotation-new-option','index': 0},
                        type = 'color',
                        value = "#7C7C7C",

                    )
                ])
            ]
        elif annotation_type=='text':
            type_inputs = []
        elif annotation_type=='numeric':
            type_inputs = [
                dbc.InputGroup([
                    dbc.InputGroupText('Minimum Value: '),
                    dbc.Input(
                        type = 'number',
                        id = {'type': 'feature-annotation-new-option','index': 0},
                        value = 0
                    )
                ]),
                dbc.InputGroup([
                    dbc.InputGroupText('Maximum Value: '),
                    dbc.Input(
                        type = 'number',
                        id = {'type': 'feature-annotation-new-option','index': 1},
                        value = 1
                    )
                ])
            ]
        
        elif annotation_type in ['options','radio','checklist']:
            type_inputs = [
                html.Div(
                    id = {'type': 'feature-annotation-new-add-option-div','index': 0},
                    children = [
                        dbc.InputGroup([
                            dbc.InputGroupText(
                                f'Option 1: ',
                                id = {'type': 'feature-annotation-new-option-title','index': 0}
                            ),
                            dbc.Input(
                                type = 'text',
                                maxLength = 1000,
                                placeholder='Option',
                                id = {'type': 'feature-annotation-new-option','index': 0}
                            ),
                            dbc.Button(
                                children = [
                                    html.I(
                                        className = 'bi bi-dash-circle-fill h4',
                                        id = {'type': 'feature-annotation-remove-new-option-icon','index': 0}
                                    ),
                                    dbc.Tooltip(
                                        children = 'Remove Option',
                                        target = {'type': 'feature-annotation-remove-new-option-icon','index': 0}
                                    )
                                ],
                                n_clicks = 0,
                                id = {'type': 'feature-annotation-new-remove-option','index': 0},
                                style = {'color': 'rgb(255,0,0)'}
                            )
                        ],style = {'marginTop': '10px','marginBottom':'10px'})
                    ]
                ),
                dbc.InputGroup([
                    dbc.Button(
                        'New Option',
                        n_clicks = 0,
                        id = {'type': 'feature-annotation-new-add-option','index': 0},
                        className = 'd-grid col-12 mx-auto'
                    )
                ],style = {'marginTop':'10px','marginBottom':'10px'})
            ]

        
        type_options_div = html.Div(
            [name_input]+type_inputs,
            style = {'width': '100%','marginTop':'10px','marginBottom':'10px'}
        )

        PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(type_options_div)

        return [type_options_div], [False]

    def update_type_options(self, add_clicked, rem_clicked, current_options):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        add_clicked = get_pattern_matching_value(add_clicked)

        current_names = self.extract_pinned_name(get_pattern_matching_value(current_options))
        current_names = [i for i in current_names if not 'Remove' in i]

        def new_option(idx_val):
            return dbc.InputGroup([
                dbc.InputGroupText(
                    f'Option {len(current_names)+1}: ',
                    id = {'type': f'{self.component_prefix}-feature-annotation-new-option-title','index': idx_val}
                ),
                dbc.Input(
                    id = {'type': f'{self.component_prefix}-feature-annotation-new-option','index': idx_val},
                    type = 'text',
                    maxLength = 1000,
                    placeholder='Option'
                ),
                dbc.Button(
                    children = [
                        html.I(
                            className = 'bi bi-dash-circle-fill h4',
                            id = {'type': f'{self.component_prefix}-feature-annotation-remove-new-option-icon','index':idx_val}
                        ),
                        dbc.Tooltip(
                            children = 'Remove Option',
                            target = {'type': f'{self.component_prefix}-feature-annotation-remove-new-option-icon','index':idx_val}
                        )
                    ],
                    n_clicks = 0,
                    id = {'type': f'{self.component_prefix}-feature-annotation-new-remove-option','index': idx_val},
                    style = {'color': 'rgb(255,0,0)'}
                )
            ],style = {'marginTop':'10px','marginBottom':'10px'})
        
        return_children = Patch()
        if 'add-option' in ctx.triggered_id['type']:
            # Adding a new option input component
            return_children.append(
                new_option(add_clicked)
            )
            return_names = [f'Option {idx+1}' for idx in range(len(ctx.outputs_list[1]))]

        elif 'remove-option' in ctx.triggered_id['type']:
            
            # Deleting the indicated option input component
            del return_children[rem_clicked.index(1)]

            return_names = []
            option_count = 1
            for o in rem_clicked:
                if o==0:
                    return_names.append(f'Option: {option_count}')
                    option_count +=1
                else:
                    # This one won't be seen because this component was deleted but needs to be returned still
                    return_names.append('removed')
        
        return [return_children],return_names

    def submit_new_annotation_type(self, submit_clicked, new_type, new_type_name, new_type_options, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        new_type = get_pattern_matching_value(new_type)
        new_type_name = get_pattern_matching_value(new_type_name)

        session_data = json.loads(session_data)
        
        if new_type is None or new_type_name is None:
            raise exceptions.PreventUpdate
        
        if any([i is None for i in new_type_options]):
            raise exceptions.PreventUpdate

        modal_open = False
        ann_drop = Patch()
        ann_drop.append(
            {
                'label': html.Div(new_type_name), 
                'value': new_type_name
            }
        )
        
        new_type_dict = {
            'name': new_type_name,
            'type': new_type
        }

        if new_type=='class':
            new_type_dict['color'] = self.hex2rgb(new_type_options[0])
        elif new_type=='text':
            pass
        elif new_type=='numeric':
            new_type_dict['min'] = new_type_options[0]
            new_type_dict['max'] = new_type_options[1]

        elif new_type=='options':
            # Only adding unique options
            new_type_dict['options'] = list(set(new_type_options))
        elif new_type=='radio':
            # Only adding unique values
            new_type_dict['values'] = list(set(new_type_options))
        elif new_type=='checklist':
            # Only adding unique values
            new_type_dict['values'] = list(set(new_type_options))
        
        if 'feature-annotation' in session_data.get('data'):
            current_session_annotations = session_data.get('data').get('feature-annotation',{}).get('annotations',[])
            current_session_annotations.append(new_type_dict)
        else:
            session_data['data']['feature-annotation'] = {
                'annotations': [new_type_dict]
            }
        

        return [modal_open], [ann_drop], json.dumps(session_data)

    def populate_export_data(self, active_accordion, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        active_accordion = get_pattern_matching_value(active_accordion)
        if not active_accordion=='export-annotations':
            return [html.Div()]

        else:
            session_data = json.loads(session_data)
            
            current_user = session_data.get('user',{}).get('login')
            user_status = 'guest'
            if not current_user is None:
                if not self.user_spec is None:
                    if current_user in self.user_spec.get('admins',[]):
                        user_status = 'admin'
                    elif current_user in self.user_spec.get('users',[]):
                        user_status = 'user'

            if user_status == 'guest':
                # This allows the user to export all annotations generated by them in this current session
                export_div_contents = html.Div([
                    dbc.Row([
                        html.H5("Guest User Export Enabled: ")
                    ]),
                    dbc.Row([
                        "As a Guest user, you can download all annotations made by you in the current session."
                    ]),
                    html.Hr(),
                    dbc.Button(
                        "Export Annotation Data",
                        className = 'd-grid col-12 mx-auto',
                        n_clicks = 0,
                        id = {'type': f'{self.component_prefix}-feature-annotation-export-annotation-data','index': 0}
                    ),
                    dcc.Download(
                        id = {'type': f'{self.component_prefix}-feature-annotation-export-download','index': 0}
                    )
                ])


            elif user_status == 'user':
                # This is a named member of the annotation session, they are able to download their annotations
                # from this and/or previous sessions
                user_session_list = self.check_database(
                    table_name = 'vis_session',
                    user_id = session_data.get('user').get('_id')
                )[0]
                print(user_session_list)

                user_session_dataframe = self.make_dash_table(
                    df = pd.DataFrame.from_records(user_session_list),
                    id = {'type': f'{self.component_prefix}-feature-annotation-export-session-table','index': 0}
                )

                export_div_contents = html.Div([
                    dbc.Row([
                        html.H5(f'Welcome back, {current_user}!')
                    ]),
                    dbc.Row([
                        'As a member of this annotation session, you can download all annotations made by you during this or in previous sessions.'
                    ]),
                    html.Hr(),
                    user_session_dataframe
                ])

            elif user_status=='admin':
                # This user can download any/all annotation data from different users/sessions
                all_users_list = self.check_database(
                    table_name='user'
                )[0]
                print(all_users_list)

                users_dataframe = self.make_dash_table(
                    df = pd.DataFrame.from_records(all_users_list),
                    id = {'type': f'{self.component_prefix}-feature-annotation-export-users-table','index': 0}
                )
                export_div_contents = html.Div([
                    dbc.Row([
                        html.H5(f'Welcome back, {current_user}!')
                    ]),
                    dbc.Row([
                        'As an administrator of this annotation session, you can download all annotations made by yourself or any other user.'
                    ]),
                    html.Hr(),
                    users_dataframe
                ])

            return [export_div_contents]
        
    def export_annotation_data(self, clicked, session_rows, user_rows,session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)
        current_user = session_data.get('user',{}).get('login')
        user_status = 'guest'
        if not current_user is None:
            if not self.user_spec is None:
                if current_user in self.user_spec.get('admins',[]):
                    user_status = 'admin'
                elif current_user in self.user_spec.get('users',[]):
                    user_status = 'user'
        
        if user_status=='guest':
            user_id_filter = session_data.get('user',{}).get('_id')
            session_id_filter = session_data.get('session',{}).get('id')
        elif user_status=='user':
            user_id_filter = session_data.get('user',{}).get('_id')
            # This filter is based on session row selections made by the user
            session_id_filter = []
        elif user_status=='admin':
            # This filter is based on user row selections made by the user
            user_id_filter = []
            # This filter is based on session row selections made by the user (populates with selected users)
            session_id_filter = []
        
        annotation_data = self.check_database(
            user_id = user_id_filter,
            session_id = session_id_filter
        )

        annotation_df = pd.DataFrame.from_records(annotation_data[0])

        return [dcc.send_data_frame(annotation_df.to_csv,"fusion_FeatureAnnotation_data.csv")]


#TODO: BulkLabels updates
# Integrate database for filtering structures (can spatial filters be added?)
# Adding annotations to database instead of local store
# Integrate annotation schema with user-spec
#   - Is there a way to pre-specify which labels/combinations are needed? Probably not.

class BulkLabels(Tool):
    """Add labels to many structures at the same time

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data
    :type Tool: None
    """

    title = 'Bulk Labels'
    description = 'Apply labels to structures based on several different inclusion and exclusion criteria.'

    def __init__(self,
                 ignore_list: list = [],
                 property_depth: int = 4):
        """Constructor method
        """

        super().__init__()
        self.ignore_list = ignore_list
        self.property_depth = property_depth

    def __str__(self):
        return self.title

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_namespace()
        self.get_callbacks()

    def get_scale_factors(self, image_metadata: dict):
        """Function used to initialize scaling factors applied to GeoJSON annotations to project annotations into the SlideMap CRS (coordinate reference system)

        :return: x and y (horizontal and vertical) scale factors applied to each coordinate in incoming annotations
        :rtype: float
        """

        base_dims = [
            image_metadata['sizeX']/(2**(image_metadata['levels']-1)),
            image_metadata['sizeY']/(2**(image_metadata['levels']-1))
        ]

        #x_scale = (base_dims[0]*(240/image_metadata['tileHeight'])) / image_metadata['sizeX']
        #y_scale = -((base_dims[1]*(240/image_metadata['tileHeight'])) / image_metadata['sizeY'])

        x_scale = base_dims[0] / image_metadata['sizeX']
        y_scale = -(base_dims[1]) / image_metadata['sizeY']


        return x_scale, y_scale

    def get_namespace(self):
        """Adding JavaScript functions to the BulkLabels Namespace
        """
        self.js_namespace = Namespace(
            "fusionTools","bulkLabels"
        )

        self.js_namespace.add(
            name = 'removeMarker',
            src = """
                function(e,ctx){
                    e.target.removeLayer(e.layer._leaflet_id);
                    ctx.data.features.splice(ctx.data.features.indexOf(e.layer.feature),1);
                }
            """
        )

        self.js_namespace.add(
            name = 'tooltipMarker',
            src = 'function(feature,layer,ctx){layer.bindTooltip("Double-click to remove")}'
        )

        self.js_namespace.add(
            name = "markerRender",
            src = """
                function(feature,latlng,context) {
                    marker = L.marker(latlng, {
                        title: "BulkLabels Marker",
                        alt: "BulkLabels Marker",
                        riseOnHover: true,
                        draggable: false,
                    });

                    return marker;
                }
            """
        )

        self.js_namespace.dump(
            assets_folder = self.assets_folder
        )

    def update_layout(self, session_data:dict, use_prefix:bool):
        """Generating layout for BulkLabels component

        :return: BulkLabels layout
        :rtype: html.Div
        """
        # Using .get method to get bulk-labels session data, if not present use default empty data with labels and labels_metadata keys
        bulk_labels_store_data = session_data.get('data',{}).get('bulk-labels',{'labels': [], 'labels_metadata': []})
        if len(bulk_labels_store_data['labels'])>0:
            label_table_div = self.make_label_table(bulk_labels_store_data['labels'],use_prefix = use_prefix)
        else:
            label_table_div = []

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
                        dbc.Col(
                            html.H5('Step 1: Where?'),
                            md = 9
                        ),
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-rotate fa-xl',
                                    n_clicks = 0,
                                    id = {'type': 'bulk-labels-refresh-icon','index': 0}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'bulk-labels-refresh-icon','index': 0},
                                children = 'Click to reset labeling components'
                            )
                        ],md = 3)
                    ],justify='left'),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Include',html_for = {'type': 'bulk-labels-include-structures','index': 0})
                        ],md = 3),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = True,
                                placeholder = 'Include Structures',
                                id = {'type': 'bulk-labels-include-structures','index': 0}
                            )
                        ],md = 9),
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'bulk-labels-spatial-query-div','index': 0},
                                children = []
                            )
                        ])
                    ],style={'marginTop':'10px'}),
                    dbc.Row([
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-map-location fa-xl',
                                    id = {'type': 'bulk-labels-spatial-query-icon','index': 0},
                                    n_clicks = 0,
                                    style = {'marginLeft': '50%'}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'bulk-labels-spatial-query-icon','index': 0},
                                children = 'Click to add a spatial query'
                            )
                        ])
                    ],style={'marginBottom': '10px','marginTop':'10px'}),
                    html.Hr(),
                    dbc.Row(
                        html.H5('Step 2: What?')
                    ),
                    html.Hr(),
                    dcc.Store(
                        id = {'type': 'bulk-labels-labels-store','index': 0},
                        storage_type = 'memory',
                        data = json.dumps(bulk_labels_store_data)
                    ),
                    dcc.Store(
                        id = {'type': 'bulk-labels-filter-data','index': 0},
                        storage_type = 'memory',
                        data = json.dumps({'Spatial': [], 'Filters': []})
                    ),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'bulk-labels-add-property-div','index': 0},
                                children = []
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-square-plus fa-xl',
                                    id = {'type': 'bulk-labels-add-property-icon','index': 0},
                                    n_clicks = 0,
                                    style = {'marginLeft': '50%'}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'bulk-labels-add-property-icon','index': 0},
                                children = 'Click to add a property filter'
                            )
                        ],align='center')
                    ],style = {'marginBottom': '10px'}),
                    dbc.Row([
                        dbc.Col(
                            dcc.Loading(dbc.Button(
                                'Update Structures',
                                n_clicks = 0,
                                id = {'type': 'bulk-labels-update-structures','index': 0},
                                className = 'd-grid col-12 mx-auto'
                            ))
                        )
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'bulk-labels-current-structures','index': 0},
                                children = []
                            )
                        ])
                    ],style = {'marginBottom': '10px'}),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            html.H5('Step 3: Kind?')
                        ],md = 4),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': 'Inclusive','value': 'in'},
                                    {'label': 'Exclusive', 'value': 'over'},
                                    {'label': 'Unlabeled', 'value': 'un'}
                                ],
                                value = 'in',
                                placeholder = 'Label Method',
                                multi = False,
                                id = {'type': 'bulk-labels-label-method','index': 0}
                            )
                        ],md = 8)
                    ],style={'marginBottom': '10px'}),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'bulk-labels-method-explanation','index': 0},
                            children = [
                                dcc.Markdown('*Inclusive*: Allow multiple labels of the same "type". Use if multiple values are possible for a single structure.')
                            ]
                        )
                    ],style = {'marginBottom':'10px'}),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            html.H5('Step 4: Label!')
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Label: ',html_for = {'type': 'bulk-labels-label-text','index': 0})
                        ],md = 2),
                        dbc.Col([
                            dcc.Input(
                                id = {'type': 'bulk-labels-label-type','index': 0},
                                value = [],
                                placeholder = 'Label Type',
                                disabled = True,
                                style = {'width': '100%'}
                            )
                        ],md = 5),
                        dbc.Col([
                            dcc.Textarea(
                                id = {'type': 'bulk-labels-label-text','index': 0},
                                value = [],
                                maxLength = 1000,
                                placeholder = 'Enter Label Here',
                                required=True,
                                style = {'width': '100%','height':'100px'},
                                disabled = True
                            )
                        ],md = 5)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Additional Rationale: ',html_for = {'type': 'bulk-labels-label-rationale','index': 0})
                        ],md = 3),
                        dbc.Col([
                            dcc.Textarea(
                                id = {'type': 'bulk-labels-label-rationale','index': 0},
                                value = [],
                                maxLength = 1000,
                                placeholder = 'Enter Additional Rationale Here',
                                style = {'width': '100%','height': '100px'},
                                disabled = True
                            )
                        ], md = 9)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Label Source: ',html_for = {'type': 'bulk-labels-label-source','index': 0})
                        ],md = 3),
                        dbc.Col([
                            dcc.Markdown(
                                '`Label Source Data`',
                                id = {'type': 'bulk-labels-label-source','index': 0},
                                style = {'width': '100%','maxHeight': '150px','overflow': 'scroll'}                            
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                'Apply Label!',
                                className = 'd-grid col-12 mx-auto',
                                n_clicks = 0,
                                id = {'type': 'bulk-labels-apply-labels','index': 0},
                                disabled = True
                            ),
                            dbc.Tooltip(
                                'Saves current label to labeling session but does not add label to structure-level data',
                                target = {'type': 'bulk-labels-apply-labels','index': 0}
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                'Download Labels!',
                                className = 'd-grid col-12 mx-auto',
                                n_clicks = 0,
                                id = {'type': 'bulk-labels-download-labels','index': 0},
                                disabled = True
                            ),
                            dbc.Tooltip(
                                'Downloads both individual labels as well as associated labeling metadata containing rationales for labels.',
                                target = {'type': 'bulk-labels-download-labels','index': 0}
                            ),
                            dcc.Download(
                                id = {'type':'bulk-labels-download-data','index': 0}
                            ),
                            dcc.Download(
                                id = {'type': 'bulk-labels-download-metadata','index': 0}
                            )
                        ])
                    ],style = {'marginTop': '10px'}),
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                'Add Labels to Structures',
                                id = {'type': 'bulk-labels-add-labels-to-structures','index': 0},
                                className = 'd-grid col-12 mx-auto',
                                n_clicks = 0,
                                disabled = True
                            ),
                            dbc.Tooltip(
                                'Adds current labels to structures for use in plotting, filtering, etc.',
                                target = {'type': 'bulk-labels-add-labels-to-structures','index': 0}
                            )
                        ])
                    ],style = {'marginTop': '10px'}),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'bulk-labels-label-stats-div','index': 0},
                                children = label_table_div
                            )
                        ])
                    ],style = {'marginTop': '10px'})
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow': 'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(layout)

        return layout

    def gen_layout(self, session_data:dict):

        self.blueprint.layout = self.update_layout(session_data,use_prefix=False)

    def get_callbacks(self):
        """Adding callbacks to DashBlueprint object
        """
        
        # Updating for new slide
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-info-store','index': ALL},'data')
            ],
            [
                Output({'type': 'bulk-labels-labels-store','index': ALL},'data'),
                Output({'type': 'bulk-labels-label-stats-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-spatial-query-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-add-property-div','index': ALL},'children')
            ]
        )(self.update_slide)

        # Adding spatial relationships 
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-spatial-query-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-remove-spatial-query-icon','index':ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-spatial-query-div','index': ALL},'children')
            ],
            [
                State({'type':'feature-overlay','index': ALL},'name')
            ]
        )(self.update_spatial_queries)

        # Updating inclusion/inclusion criteria
        self.blueprint.callback(
            [
                Input({'type':'bulk-labels-update-structures','index':ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-current-structures','index': ALL},'children'),
                Output({'type': 'map-marker-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-label-source','index': ALL},'children'),
                Output({'type': 'bulk-labels-label-type','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-label-text','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-label-rationale','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-apply-labels','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-download-labels','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-add-labels-to-structures','index': ALL},'disabled')
            ],
            [
                State({'type': 'bulk-labels-include-structures','index': ALL},'value'),
                State({'type': 'bulk-labels-filter-data','index': ALL},'data'),
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.update_label_structures)

        # Adding filtering data to a separate store:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-filter-selector','index': ALL},'value'),
                Input({'type': 'bulk-labels-spatial-query-drop','index': ALL},'value'),
                Input({'type': 'bulk-labels-spatial-query-structures','index': ALL},'value'),
                Input({'type': 'bulk-labels-spatial-query-nearest','index': ALL},'value'),
                Input({'type': 'bulk-labels-remove-spatial-query-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-remove-property-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-spatial-query-mod','index': ALL},'value'),
                Input({'type': 'bulk-labels-filter-property-mod','index': ALL},'value')
            ],
            [
                Output({'type': 'bulk-labels-filter-data', 'index': ALL},'data')
            ],
            [
                State({'type': 'bulk-labels-add-property-div','index': ALL},'children'),
                State({'type': 'bulk-labels-spatial-query-div','index':ALL},'children'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.update_filter_data)

        # Adding new property
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-add-property-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-remove-property-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-add-property-div','index': ALL},'children')
            ],
            [
                State({'type': 'map-annotations-info-store','index': ALL},'data')
            ]
        )(self.update_label_properties)

        # Updating property selector
        self.blueprint.callback(
            [
                Input({'type':'bulk-labels-filter-property-drop','index': MATCH},'value')
            ],
            [
                Output({'type':'bulk-labels-property-selector-div','index':MATCH},'children')
            ],
            [
                State({'type': 'map-annotations-info-store','index': ALL},'data')
            ]
        )(self.update_property_selector)

        # Updating spatial query definition:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-spatial-query-drop','index':MATCH},'value')
            ],
            [
                Output({'type': 'bulk-labels-spatial-query-definition','index': MATCH},'children')
            ]
        )(self.update_spatial_query_definition)

        # Applying labels to marked points:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-apply-labels','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-labels-store','index': ALL},'data'),
                Output({'type': 'bulk-labels-apply-labels','index': ALL},'color'),
                Output({'type': 'bulk-labels-label-stats-div','index': ALL},'children')
            ],
            [
                State({'type': 'bulk-labels-markers','index': ALL},'data'),
                State({'type': 'bulk-labels-labels-store','index': ALL},'data'),
                State({'type': 'bulk-labels-label-type','index': ALL},'value'),
                State({'type': 'bulk-labels-label-text','index': ALL},'value'),
                State({'type': 'bulk-labels-label-rationale','index': ALL},'value'),
                State({'type': 'bulk-labels-label-source','index': ALL},'children'),
                State({'type': 'bulk-labels-label-method','index': ALL},'value'),
                State({'type':'map-slide-information','index':ALL},'data')
            ]
        )(self.apply_labels)

        # Resetting everything:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-refresh-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type':'bulk-labels-include-structures','index': ALL},'value'),
                Output({'type': 'bulk-labels-spatial-query-div','index':ALL},'children'),
                Output({'type': 'bulk-labels-add-property-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-current-structures','index': ALL},'children'),
                Output({'type': 'bulk-labels-label-type','index': ALL},'value'),
                Output({'type': 'bulk-labels-label-type','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-label-text','index': ALL},'value'),
                Output({'type': 'bulk-labels-label-text','index':ALL},'disabled'),
                Output({'type': 'bulk-labels-label-rationale','index': ALL},'value'),
                Output({'type': 'bulk-labels-label-rationale','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-label-source','index': ALL},'children'),
                Output({'type': 'bulk-labels-apply-labels','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-include-structures','index':ALL},'options'),
                Output({'type': 'bulk-labels-spatial-query-structures','index':ALL},'options'),
                Output({'type': 'bulk-labels-apply-labels','index': ALL},'color'),
                Output({'type': 'map-marker-div','index': ALL},'children')
            ],
            [
                State({'type': 'feature-overlay','index':ALL},'name')
            ]
        )(self.refresh_labels)

        # Downloading labels
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-download-labels','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-download-data','index': ALL},'data'),
                Output({'type': 'bulk-labels-download-metadata','index': ALL},'data')
            ],
            [
                State({'type': 'bulk-labels-labels-store','index': ALL},'data')
            ]
        )(self.download_data)

        # Updating label method description
        self.blueprint.callback(
            [
                Input({'type':'bulk-labels-label-method','index': ALL},'value')
            ],
            [
                Output({'type': 'bulk-labels-method-explanation','index': ALL},'children')
            ]
        )(self.update_method_explanation)

        # Updating number of markers when one is removed:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-markers','index': ALL},'n_dblclicks')
            ],
            [
                Output({'type': 'bulk-labels-current-structures','index':ALL},'children')
            ],
            [
                State({'type': 'bulk-labels-markers','index': ALL},'data')
            ]
        )(self.update_structure_count)

        # Adding current labels to structure data
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-add-labels-to-structures','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'map-annotations-store','index': ALL},'data')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'bulk-labels-labels-store','index': ALL},'data')
            ]
        )(self.add_labels_to_structures)

        # Editing current labels by editing the label table
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-label-table','index': ALL},'data'),
            ],
            [
                Output({'type': 'bulk-labels-labels-store','index': ALL},'data')
            ],
            [
                State({'type': 'bulk-labels-labels-store','index': ALL},'data'),
            ]
        )(self.update_label_table)

    def update_slide(self, new_annotations_info: list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        new_labels_data = json.dumps({'labels': [], 'labels_metadata': []})
        new_label_stats_div = []
        new_spatial_query_div = []
        new_property_filter_div = []

        return [new_labels_data], [new_label_stats_div], [new_spatial_query_div],[new_property_filter_div]

    def update_method_explanation(self, method):
        """Updating explanation given for the selected label method

        :param method: Name of method selected
        :type method: list
        :return: Description of the labeling method selected
        :rtype: list
        """
        
        method = get_pattern_matching_value(method)
        method_types = {
            'in': '*Inclusive*: Allow multiple labels of the same "type". Use if multiple values are possible for a single structure.',
            'over': '*Exclusive*: Only one "label" for each label "type" is allowed. New labels will overwrite previous labels for the same "type".',
            'un': '*Unlabeled*: Only applies this label to structures without any label assigned to this label "type".'
        }

        if method:
            if method in method_types:
                return [dcc.Markdown(method_types[method])]
            else:
                return [dcc.Markdown('Select a method to get started.')]
        else:
            raise exceptions.PreventUpdate

    def update_spatial_query_definition(self, query_type):
        """Returning the definition for the selected spatial predicate type

        :param query_type: Name of spatial predicate
        :type query_type: str
        :return: Markdown string
        :rtype: dcc.Markdown
        """

        if query_type is None:
            raise exceptions.PreventUpdate
        if not type(query_type)==str:
            raise exceptions.PreventUpdate
        
        query_types = {
            'within': '''
            Returns `True` if the *boundary* and *interior* of the object intsect only with the *interior* of the other (not its *boundary* or *exterior*)
            ''',
            'intersects': '''
            Returns `True` if the *boundary* or *interior* of the object intersect in any way with those of the other.
            ''',
            'crosses': '''
            Returns `True` if the *interior* of the object intersects the *interior* of the other but does not contain it, and the dimension of the intersection is less than the dimension of the one or the other.
            ''',
            'contains': '''
            Returns `True` if no points of *other* lie in the exterior of the *object* and at least one point of the interior of *other* lies in the interior of *object*
            ''',
            'touches': '''
            Returns `True` if the objects have at least one point in common and their interiors do not intersect with any part of the other.
            ''',
            'overlaps': '''
            Returns `True` if the geometries have more than one but not all points in common, have the same dimension, and the intersection of the interiors of the geometries has the same dimension as the geometries themselves.
            ''',
            'nearest': '''
            Returns `True` if *other* is within `max_distance` of *object* 
            '''
        }

        if query_type in query_types:
            if query_type=='nearest':
                return [
                    dmc.NumberInput(
                        label = 'Pixel distance',
                        stepHoldDelay = 500,
                        stepHoldInterval=100,
                        value = 0,
                        step = 1,
                        min = 0,
                        style = {'width': '100%'},
                        id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-nearest','index':ctx.triggered_id['index']}
                    ), 
                    dcc.Markdown(
                        query_types[query_type]
                    )
                ]
            else:
                return [dcc.Markdown(query_types[query_type])]
        else:
            raise exceptions.PreventUpdate

    def update_spatial_queries(self, add_click, remove_click, structure_names):
        """Generating a new spatial query selector once the add/remove icons are clicked

        :param add_click: Add spatial query icon selected
        :type add_click: list
        :param remove_click: Delete spatial query icon selected
        :type remove_click: list
        :param structure_names: Names of current overlay structures
        :type structure_names: list
        :return: Spatial query selectors (two dropdown menus and delete icon)
        :rtype: tuple
        """
        
        queries_div = Patch()
        add_click = get_pattern_matching_value(add_click)

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        if 'bulk-labels-spatial-query-icon' in ctx.triggered_id['type']:

            def new_query_div():
                return html.Div([
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': html.Span('AND',style={'color': 'rgb(0,0,255)'}),'value': 'and'},
                                    {'label': html.Span('OR',style={'color': 'rgb(0,255,0)'}),'value': 'or'},
                                    {'label': html.Span('NOT',style={'color': 'rgb(255,0,0)'}),'value': 'not'}
                                ],
                                value = 'and',
                                placeholder='Modifier',
                                id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-mod','index': add_click}
                            )
                        ],md = 2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': 'intersects','value': 'intersects'},
                                    {'label': 'contains','value': 'contains'},
                                    {'label': 'within','value': 'within'},
                                    {'label': 'touches','value': 'touches'},
                                    {'label': 'crosses','value': 'crosses'},
                                    {'label': 'overlaps','value': 'overlaps'},
                                    {'label': 'nearest','value': 'nearest'}
                                ],
                                value = [],
                                multi= False,
                                id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-drop','index': add_click}
                            )
                        ],md = 3),
                        dbc.Col([
                            dcc.Dropdown(
                                options = structure_names,
                                value = [],
                                multi = False,
                                placeholder = 'Select structure',
                                id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-structures','index':add_click}
                            )
                        ],md=5),
                        dbc.Col([
                            html.A(
                                html.I(
                                    id = {'type': f'{self.component_prefix}-bulk-labels-remove-spatial-query-icon','index': add_click},
                                    n_clicks = 0,
                                    className = 'bi bi-x-circle-fill fa-2x',
                                    style = {'color': 'rgb(255,0,0)'}
                                )
                            )
                        ], md = 2)
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-definition','index': add_click},
                        children = []
                    )
                ])

            queries_div.append(new_query_div())

        elif 'bulk-labels-remove-spatial-query-icon' in ctx.triggered_id['type']:

            values_to_remove = []
            for i, val in enumerate(remove_click):
                if val:
                    values_to_remove.insert(0,i)

            for v in values_to_remove:
                del queries_div[v]

        
        return [queries_div]

    def parse_filter_divs(self, add_property_parent: list)->list:
        """Processing parent div object and extracting name and range for each property filter.

        :param add_property_parent: Parent div containing property filters
        :type add_property_parent: list
        :return: List of property filters (dicts with keys: name and range)
        :rtype: list
        """
        processed_filters = []
        if not add_property_parent is None:
            for div in add_property_parent:
                div_children = div['props']['children']
                filter_mod = div_children[0]['props']['children'][0]['props']['children'][0]['props']['value']
                #print(f'filter_mod: {filter_mod}')
                filter_name = div_children[0]['props']['children'][1]['props']['children'][0]['props']['value']
                #print(f'filter_name: {filter_name}')
                if 'props' in div_children[1]['props']['children']:
                    if 'value' in div_children[1]['props']['children']['props']:
                        filter_value = div_children[1]['props']['children']['props']['value']
                    else:
                        filter_value = div_children[1]['props']['children']['props']['children']['props']['value']
                    
                    #print(f'filter_value: {filter_value}')

                    if not any([i is None for i in [filter_mod,filter_name,filter_value]]):
                        processed_filters.append({
                            'mod': filter_mod,
                            'name': filter_name,
                            'range': filter_value
                        })

        return processed_filters

    def parse_spatial_divs(self, spatial_query_parent: list, slide_information:dict)->list:
        """Parsing through parent div containing all spatial queries and returning them in list form

        :param spatial_query_parent: Div containing spatial query child divs
        :type spatial_query_parent: list
        :return: Processed queries with keys "type", "structure", and "distance" (if "nearest" selected)
        :rtype: list
        """
        processed_queries = []
        x_scale = slide_information['x_scale']
        if not spatial_query_parent is None:
            for div in spatial_query_parent:
                div_children = div['props']['children'][0]['props']['children']

                query_mod = div_children[0]['props']['children'][0]['props']['value']
                #print(f'query_mod: {query_mod}')
                query_type = div_children[1]['props']['children'][0]['props']['value']
                #print(f'query_type: {query_type}')
                query_structure = div_children[2]['props']['children'][0]['props']['value']
                
                if not any([i is None for i in [query_mod,query_type,query_structure]]):
                    if not query_type=='nearest':
                        processed_queries.append({
                            'mod': query_mod,
                            'type': query_type,
                            'structure': query_structure
                        })
                    else:
                        distance_div = div['props']['children'][1]['props']['children']
                        if len(distance_div)>0:
                            if 'value' in distance_div[0]['props']:
                                query_distance = distance_div[0]['props']['value']
                                #print(f'query_distance: {query_distance}')
                                if not any([i is None for i in [query_mod,query_type,query_structure,query_distance]]):
                                    try:
                                        processed_queries.append({
                                            'mod': query_mod,
                                            'type': query_type,
                                            'structure': query_structure,
                                            'distance': query_distance*x_scale
                                        })
                                    except TypeError:
                                        continue

        return processed_queries

    def update_filter_data(self, property_filter, sp_query_type, sp_query_structure, sp_query_distance, remove_sq, remove_prop, spatial_mod,prop_mod,property_divs: list, spatial_divs: list, slide_information:list):

        property_divs = get_pattern_matching_value(property_divs)
        spatial_divs = get_pattern_matching_value(spatial_divs)

        slide_information = json.loads(get_pattern_matching_value(slide_information))
        processed_prop_filters = self.parse_filter_divs(property_divs)
        processed_spatial_filters = self.parse_spatial_divs(spatial_divs,slide_information)

        new_filter_data = json.dumps({
            "Spatial": processed_spatial_filters,
            "Filters": processed_prop_filters
        })

        return [new_filter_data]

    def update_label_structures(self, update_structures_click:list, include_structures:list, filter_data:list, current_features:list, slide_information:list):
        """Go through current structures and return all those that pass spatial and property filters.

        :param update_structures_click: Button clicked
        :type update_structures_click: list
        :param include_structures: List of structures to include in the final filtered GeoJSON
        :type include_structures: list
        :param filter_properties: List of property filters to apply to current GeoJSON
        :type filter_properties: list
        :param spatial_queries: List of spatial filters to apply to current GeoJSON
        :type spatial_queries: list
        :param current_features: Current structures in slide map
        :type current_features: list
        :return: Markers over structures that pass the spatial and property filters, count of structures, enabled label components
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        include_structures = get_pattern_matching_value(include_structures)
        current_features = json.loads(get_pattern_matching_value(current_features))

        slide_information = json.loads(get_pattern_matching_value(slide_information))

        filter_data = json.loads(get_pattern_matching_value(filter_data))

        #TODO: Replace this function to utilize the fusionDB
        # at least processing the property search criteria, not all spatial operations are available
        filtered_geojson, filtered_ref_list = process_filters_queries(filter_data["Filters"], filter_data["Spatial"], include_structures, current_features)

        new_structures_div = [
            dbc.Alert(
                f'{len(filtered_geojson["features"])} Structures Included!',
                color = 'success' if len(filtered_geojson['features'])>0 else 'danger'
            )
        ]
        
        new_markers_div = [
            dl.GeoJSON(
                data = {
                    'type': 'FeatureCollection',
                    'features': [
                        {
                            'type': 'Feature',
                            'geometry': {
                                'type': 'Point',
                                'coordinates': [
                                    (f['bbox'][0]+f['bbox'][2])/2,
                                    (f['bbox'][1]+f['bbox'][3])/2
                                ]
                            },
                            'properties': f_data | {'_id': f['properties']['_id']}
                        }
                        for f,f_data in zip(filtered_geojson['features'],filtered_ref_list)
                    ]
                },
                pointToLayer=self.js_namespace("markerRender"),
                onEachFeature = self.js_namespace("tooltipMarker"),
                id = {'type': f'{self.component_prefix}-bulk-labels-markers','index': 0},
                eventHandlers = {
                    'dblclick': self.js_namespace('removeMarker')
                }
            )
        ]

        new_labels_source = f'`{json.dumps({"Spatial": filter_data["Spatial"],"Filters": filter_data["Filters"]})}`'

        if len(filtered_geojson['features'])>0:
            labels_type_disabled = False
            labels_text_disabled = False
            labels_rationale_disabled = False
            labels_apply_button_disabled = False
            labels_download_button_disabled = False
            labels_add_to_structures_button_disabled = False
        else:
            labels_type_disabled = True
            labels_text_disabled = True
            labels_rationale_disabled = True
            labels_apply_button_disabled = True
            labels_download_button_disabled = True
            labels_add_to_structures_button_disabled = True


        return [new_structures_div], [new_markers_div], [new_labels_source], [labels_type_disabled], [labels_text_disabled], [labels_rationale_disabled], [labels_apply_button_disabled], [labels_download_button_disabled], [labels_add_to_structures_button_disabled]

    def update_label_properties(self, add_click:list, remove_click:list, annotations_info:list):
        """Adding/removing property filter dropdown

        :param add_click: Add property filter clicked
        :type add_click: list
        :param remove_click: Remove property filter clicked
        :type remove_click: list
        :return: Property filter dropdown and parent div of range selector
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        properties_div = Patch()
        add_click = get_pattern_matching_value(add_click)
        property_info = json.loads(get_pattern_matching_value(annotations_info))['property_info']

        if 'bulk-labels-add-property-icon' in ctx.triggered_id['type']:

            def new_property_div():
                return html.Div([
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': html.Span('AND',style={'color':'rgb(0,0,255)'}),'value': 'and'},
                                    {'label': html.Span('OR',style={'color': 'rgb(0,255,0)'}),'value': 'or'},
                                    {'label': html.Span('NOT',style={'color':'rgb(255,0,0)'}),'value': 'not'}
                                ],
                                value = 'and',
                                placeholder='Modifier',
                                id = {'type': f'{self.component_prefix}-bulk-labels-filter-property-mod','index': add_click}
                            )
                        ],md=2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = list(property_info.keys()),
                                value = [],
                                multi = False,
                                placeholder = 'Select property',
                                id = {'type': f'{self.component_prefix}-bulk-labels-filter-property-drop','index':add_click}
                            )
                        ],md=8),
                        dbc.Col([
                            html.A(
                                html.I(
                                    id = {'type': f'{self.component_prefix}-bulk-labels-remove-property-icon','index': add_click},
                                    n_clicks = 0,
                                    className = 'bi bi-x-circle-fill fa-2x',
                                    style = {'color': 'rgb(255,0,0)'}
                                )
                            )
                        ], md = 2)
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-bulk-labels-property-selector-div','index': add_click},
                        children = []
                    )
                ])

            properties_div.append(new_property_div())

        elif 'bulk-labels-remove-property-icon' in ctx.triggered_id['type']:

            values_to_remove = []
            for i, val in enumerate(remove_click):
                if val:
                    values_to_remove.insert(0,i)

            for v in values_to_remove:
                del properties_div[v]

        
        return [properties_div]

    def update_property_selector(self, property_value:str, annotations_info:list):
        """Updating property filter range selector

        :param property_value: Name of property to generate selector for
        :type property_value: str
        :param property_info: Dictionary containing range/unique values for each property
        :type property_info: list
        :return: Either a multi-dropdown for categorical properties or a RangeSlider for quantitative values
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        property_info = json.loads(get_pattern_matching_value(annotations_info))['property_info']
        property_values = property_info[property_value]

        if 'min' in property_values:
            # Used for numeric type filters
            values_selector = html.Div(
                dcc.RangeSlider(
                    id = {'type':f'{self.component_prefix}-bulk-labels-filter-selector','index': ctx.triggered_id['index']},
                    min = property_values['min'] - 0.01,
                    max = property_values['max'] + 0.01,
                    value = [property_values['min'], property_values['max']],
                    step = 0.01,
                    marks = None,
                    tooltip = {
                        'placement': 'bottom',
                        'always_visible': True
                    },
                    allowCross=True,
                    disabled = False
                ),
                style = {'display': 'inline-block','margin':'auto','width': '100%'}
            )

        elif 'unique' in property_values:
            values_selector = html.Div(
                dcc.Dropdown(
                    id = {'type': f'{self.component_prefix}-bulk-labels-filter-selector','index': ctx.triggered_id['index']},
                    options = property_values['unique'],
                    value = property_values['unique'] if len(property_values['unique'])<10 else [],
                    multi = True
                )
            )

        return values_selector 

    def search_labels(self, marker_features, current_labels, label_type, label_text, label_method):
        """Checking current labels and adding the new label based on label_method (inclusive, exclusive, or unlabeled).

        :param marker_features: GeoJSON Features for new markers
        :type marker_features: list
        :param current_labels: List of all current labels (dicts with keys: centroid, labels)
        :type current_labels: list
        :param label_type: String corresponding to the type for the new label
        :type label_type: str
        :param label_text: String corresponding to the new label to apply to each centroid
        :type label_text: str
        :param label_method: One of: in (inclusive, append new label to current regardless of type), over (exclusive, replace existing labels of same type), or un (unlabeled, only apply label to structures that do not have a label for this type)
        :type label_method: str
        :return: Updated set of labels, including original set
        :rtype: dict
        """
        if 'labels' in current_labels:
            current_centroids = [i['centroid'] for i in current_labels['labels']]
        else:
            current_labels['labels'] = []
            current_centroids = []

        for m_idx, m in enumerate(marker_features):
            m_centroid = list(m['geometry']['coordinates'])
            m_id = m['properties']['_id']
            if m_centroid in current_centroids:
                cent_idx = current_centroids.index(m_centroid)
                if label_method=='in':
                    # Adding inclusive label to current set of labels 
                    current_labels['labels'][cent_idx]['labels'].append(
                        {
                            'type': label_type,
                            'value': label_text
                        }
                    )
                elif label_method=='over':
                    if any([label_type==i['type'] for i in current_labels['labels'][cent_idx]['labels']]):
                        # Overruling label previously assigned for this "type"
                        current_labels['labels'][cent_idx]['labels'] = [i if not i['type']==label_type else {'type': label_type,'value': label_text} for i in current_labels['labels'][cent_idx]['labels']]
                    
                    else:
                        # Not previously labeled, nothing to overrule
                        current_labels['labels'][cent_idx]['labels'].append(
                            {
                                'type': label_type,
                                'value': label_text
                            }
                        )
                elif label_method=='un':
                    if not any([label_type==i['type'] for i in current_labels['labels'][cent_idx]['labels']]):
                        # Only adding this label if no other label of this "type" is added
                        current_labels['labels'][cent_idx]['labels'].append(
                            {
                                'type': label_type,
                                'value': label_text
                            }
                        )

            else:
                current_labels['labels'].append(
                    {
                        'centroid': m_centroid,
                        '_id': m_id,
                        'labels': [{
                            'type': label_type,
                            'value': label_text
                        }]
                    }
                )

        return current_labels

    def apply_labels(self, button_click, current_markers, current_data, label_type, label_text, label_rationale, label_source, label_method, slide_information):
        """Applying current label to marked structures

        :param button_click: Button clicked
        :type button_click: list
        :param current_markers: Current markers on the slide-map
        :type current_markers: list
        :param current_data: Current labels data
        :type current_data: list
        :param label_type: Type of label being added
        :type label_type: list
        :param label_text: Label being added to structures
        :type label_text: list
        :param label_rationale: Optional additional rationale to save with label decision
        :type label_rationale: list
        :param label_source: Property and spatial filters incorporated to generate markers
        :type label_source: list
        :param label_method: Method used to apply labels to structures
        :type label_method: list
        :param current_annotations: Current GeoJSON annotations on the slide map
        :type current_annotations: list
        :return: Updated labels data and annotations with label added as a property
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        label_type = get_pattern_matching_value(label_type)
        label_text = get_pattern_matching_value(label_text)
        label_method = get_pattern_matching_value(label_method)

        if label_text is None or label_type is None:
            raise exceptions.PreventUpdate

        label_rationale = get_pattern_matching_value(label_rationale)
        label_source = json.loads(get_pattern_matching_value(label_source).replace('`',''))
        current_data = json.loads(get_pattern_matching_value(current_data))
        current_markers = get_pattern_matching_value(current_markers)
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        scaled_markers = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),current_markers)
        
        labeled_items = self.search_labels(scaled_markers['features'], current_data, label_type, label_text, label_method)

        if 'labels' in current_data and 'labels_metadata' in current_data:
            current_data['labels'] = labeled_items['labels']
            current_data['labels_metadata'].append(
                {
                    'type': label_type,
                    'label': label_text,
                    'rationale': label_rationale,
                    'source': label_source
                }
            )
        else:
            current_data['labels'] = labeled_items['labels']
            current_data['labels_metadata'] = [
                {
                    'type': label_type,
                    'label': label_text,
                    'rationale': label_rationale,
                    'source': label_source
                }
            ]

        new_data = json.dumps(current_data)

        # Creating a table for count of unique labels:
        label_count_table = self.make_label_table(labeled_items)

        return [new_data], ['success'], [label_count_table]

    def make_label_table(self, labeled_items, use_prefix:bool = True):
        
        # Creating a table for count of unique labels:
        labels = []
        for l in labeled_items['labels']:
            for m in l['labels']:
                # Accounting for multiple values for the same "type"
                l_dict = {
                    'Label Type': m['type'],
                    'Value': m['value']
                }

                labels.append(l_dict)

        label_count_df = pd.DataFrame.from_records(labels).groupby(by='Label Type')
        label_counts = label_count_df.value_counts(['Value']).to_frame()
        label_counts.reset_index(inplace=True)
        label_counts.columns = ['Label Type','Label Value','Count']

        label_count_table = dash_table.DataTable(
            columns = [{'name':i,'id':i,'selectable':True} for i in label_counts],
            data = label_counts.to_dict('records'),
            editable=True,   
            row_deletable=True,                                     
            sort_mode='multi',
            sort_action = 'native',
            page_current=0,
            page_size=5,
            style_cell = {
                'overflow':'hidden',
                'textOverflow':'ellipsis',
                'maxWidth':0
            },
            tooltip_data = [
                {
                    column: {'value':str(value),'type':'markdown'}
                    for column, value in row.items()
                } for row in label_counts.to_dict('records')
            ],
            tooltip_duration = None,
            id = {'type': f'{self.component_prefix}-bulk-labels-label-table','index':0} if use_prefix else {'type': 'bulk-labels-label-table','index': 0}
        )

        return label_count_table

    def refresh_labels(self, refresh_click, structure_options):
        """Clear current label components and start over

        :param refresh_click: Refresh icon clicked
        :type refresh_click: list
        :param structure_options: Names of current overlay layers
        :type structure_options: list
        :return: Cleared labeling components
        :rtype: tuple
        """
        if refresh_click:

            include_structures = []
            spatial_queries = []
            add_property = []
            current_structures = []
            label_type = []
            type_disable = True
            label_text = []
            text_disable = True
            label_rationale = []
            rationale_disable = True
            label_source = '`Label Source`'
            apply_disable = True
            apply_style = 'primary'
            markers = []

            include_options = [{'label': i, 'value': i} for i in structure_options]
            if len(ctx.outputs_list[13])>0:
                spatial_queries_structures = [include_options for i in range(len(ctx.outputs_list[13]))]        
            else:
                spatial_queries_structures = []

            return [include_structures], [spatial_queries], [add_property], [current_structures],[label_type],[type_disable],[label_text], [text_disable], [label_rationale], [rationale_disable], [label_source], [apply_disable], [include_options], spatial_queries_structures, [apply_style], [markers]
        else:
            raise exceptions.PreventUpdate

    def download_data(self, button_click, label_data):
        """Download both the labels applied to the current session as well as the labeling metadata

        :param button_click: Download button clicked
        :type button_click: list
        :param label_data: Current label data and metadata
        :type label_data: list
        :return: Data sent to the two download components in the layout containing JSON formatted label data and metadata
        :rtype: tuple
        """
        if button_click:
            label_data = json.loads(get_pattern_matching_value(label_data))

            return [{'content': json.dumps(label_data['labels']),'filename': 'label_data.json'}], [{'content': json.dumps(label_data['labels_metadata']), 'filename': 'label_metadata.json'}]
        else:
            raise exceptions.PreventUpdate

    def update_structure_count(self, marker_dblclicked,marker_geo):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        marker_geo = get_pattern_matching_value(marker_geo)
        new_structure_count_children = [
            dbc.Alert(
                f'{len(marker_geo["features"])} Structures Included!',
                color = 'success' if len(marker_geo["features"])>0 else 'danger'
            )
        ]

        return new_structure_count_children
    
    def add_labels_to_structures(self, button_click, current_annotations, current_labels):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_annotations = json.loads(get_pattern_matching_value(current_annotations))
        current_labels = json.loads(get_pattern_matching_value(current_labels))

        label_ids = [i['_id'] for i in current_labels['labels']]
        for c in current_annotations:
            feature_ids = [i['properties']['_id'] for i in c['features']]
            id_intersect = list(set(label_ids) & set(feature_ids))
            if len(id_intersect)>0:
                for id in id_intersect:
                    feature_label = current_labels['labels'][label_ids.index(id)]
                    c['features'][feature_ids.index(id)]['properties'] = c['features'][feature_ids.index(id)]['properties'] | feature_label

        updated_annotations = json.dumps(current_annotations)

        return [updated_annotations]

    def update_label_table(self, table_data, current_labels):
        
        table_data = get_pattern_matching_value(table_data)
        current_labels = json.loads(get_pattern_matching_value(current_labels))
        if not table_data is None:
            included_label_types = sorted(list(set([i['Label Type'] for i in table_data])))
            current_label_types = sorted(list(set([i['type'] for i in current_labels['labels_metadata']])))
            
            included_label_values = []
            current_label_values = []
            for t in included_label_types:
                included_label_values.extend(sorted([i['Label Value'] for i in table_data if i['Label Type']==t]))
                current_label_values.extend(sorted([i['label'] for i in current_labels['labels_metadata'] if i['type']==t]))

            # Removing not-included label from labels and label metadata
            if not included_label_types==current_label_types or not included_label_values==current_label_values:
                # If the len of included_label_types does not equal the len of current_label_types then there has been a type deletion
                deletion = False
                replation = False
                if not len(included_label_types)==len(current_label_types):
                    # This would be a deletion of one label type/value
                    #print(f'type deletion: {included_label_types}, {current_label_types}')
                    deletion = True
                    replation = False
                else:
                    # If the len of the types are the same length then check if they contain the same values:
                    if not included_label_types==current_label_types:
                        # This is a type replation
                        #print(f'type replation: {included_label_types}, {current_label_types}')
                        deletion = False
                        replation = {'type': [i for i in included_label_types if not i in current_label_types][0]}

                    else:
                        # In this case there is most likely a value replation
                        if not included_label_values==current_label_values and len(included_label_values)==len(current_label_values):
                            #print(f'value replation: {included_label_values}, {current_label_values}')
                            deletion = False
                            replation = {'value': [i for i in included_label_values if not i in current_label_values][0]}
                        elif not len(included_label_values)==len(current_label_values):
                            # This is a deletion
                            deletion = True
                            replation = False

                for l_idx,l in enumerate(current_labels['labels']):
                    for l_m_idx,l_m in enumerate(l['labels']):
                        if not l_m['type'] in included_label_types:
                            if deletion:
                                del current_labels['labels'][l_idx]['labels'][l_m_idx]
                            elif replation:
                                current_labels['labels'][l_idx]['labels'][l_m_idx]['type'] = replation['type']
                        else:
                            if not l_m['value'] in included_label_values:
                                if deletion:
                                    del current_labels['labels'][l_idx]['labels'][l_m_idx]
                                elif replation:
                                    current_labels['labels'][l_idx]['labels'][l_m_idx]['value'] = replation['value']

                    if len(l['labels'])==0:
                        del current_labels['labels'][l_idx]
                
                if deletion:
                    current_labels['labels_metadata'] = [i for i in current_labels['labels_metadata'] if i['label'] in included_label_values and i['type'] in included_label_types]
                elif replation:
                    if 'type' in replation:
                        current_labels['labels_metadata'] = [i if i['type'] in included_label_types else i | replation for i in current_labels['labels_metadata']]
                    elif 'value' in replation:
                        current_labels['labels_metadata'] = [i if i['label'] in included_label_values else i | {'label': replation['value']} for i in current_labels['labels_metadata']]
                
                updated_labels = json.dumps(current_labels)
            else:
                raise exceptions.PreventUpdate
        else:
            updated_labels = json.dumps({})

        return [updated_labels]


#TODO: SlideAnnotation updates
# Integrate database for adding annotations to slides for multiple users 
# Annotation Schema for user-specs
#   - Extracting annotations for one/more users
# This could be efficiently made a standalone if annotations aren't needed (tiles)


class SlideAnnotation(MultiTool):
    """Component used for assigning labels to slides, allows for importing other schema

    :param MultiTool: General class for tool which works on multiple slides at once
    :type MultiTool: None
    """
    title = 'Slide Annotation'
    description = 'Used for annotating whole slides following pre-specified schema'

    annotation_types = ["roi","text","numeric","options","radio","checklist"]
    annotation_descriptions = [
        "Hand-drawn regions on a slide",
        "Free text label applied to a structure.",
        "Numeric value assigned to a structure.",
        "Dropdown menu selection from list of possible options (one value permitted).",
        "Filled in circle used for selecting between two or more values (one value permitted).",
        "Set of selectable items for assigning multiple values to a single structure (multiple values permitted)."
    ]

    def __init__(self,
                 handler: Union[None,Handler] = None,
                 preload_schema: Union[None, str, dict, list, AnnotationSchema] = None
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
        return self.title
    
    def load(self, component_prefix: int):

        self.component_prefix = component_prefix
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

        # Selecting a slide annotation schema from the initial list
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

        # Refreshing available schemas (TODO)
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

        # Opening the edit modal with options to edit individual annotations information
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

        # Updating the edit modal content based on selections
        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-edit-type-dropdown','index': ALL},'value')
            ],
            [
                State({'type': 'slide-annotation-edit-store','index': ALL},'data')
            ],
            [
                Output({'type': 'slide-annotation-edit-option-div','index': ALL},'children')
            ]
        )(self.update_edit_option_div)

        # Updating options based on whether remove or add was clicked
        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-edit-option-add','index': ALL},'n_clicks'),
                Input({'type': 'slide-annotation-edit-option-remove','index':ALL},'n_clicks')
            ],
            [
                State({'type': 'slide-annotation-edit-option','index': ALL},'id')
            ],
            [
                Output({'type': 'slide-annotation-edit-option-parent-div','index': ALL},'children')
            ]
        )(self.update_edit_options)

        self.blueprint.callback(
            [
                Input({'type': 'slide-annotation-remove-input','index': ALL},'n_clicks'),
                Input({'type': 'slide-annotation-edit-update-input','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'slide-annotation-edit-name-text','index': ALL},'value'),
                State({'type': 'slide-annotation-edit-description-text','index': ALL},'value'),
                State({'type': 'slide-annotation-edit-type-dropdown','index': ALL},'value'),
                State({'type': 'slide-annotation-edit-roi-dropdown','index': ALL},'value'),
                State({'type': 'slide-annotation-edit-editable-dropdown','index': ALL},'value'),
                State({'type': 'slide-annotation-edit-option','index': ALL},'value'),
                State({'type': 'slide-annotation-edit-store','index': ALL},'data'),
                State({'type': 'slide-annotation-schema-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'slide-annotation-modal','index': ALL},'is_open'),
                Output({'type': 'slide-annotation-schema-parent-div','index': ALL},'children'),
                Output({'type': 'slide-annotation-schema-drop','index': ALL},'value')
            ]
        )(self.update_edit)

        # Opening the ROI modal to add ROIs to the slide
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

        # Submitting input labels for a slide
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

        # Submitting a drawn ROI
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

        # Downloading annotations for the current session
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
                            html.H3(self.title)
                        )
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Col(
                            self.description
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
                                        'label': n.name,
                                        'value': n.name
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
            new_schema = [
                AnnotationSchema.from_dict(schema)
            ]
        
        elif type(schema)==list:
            new_schema = [
                AnnotationSchema.from_dict(s)
                for s in schema
            ]
        
        elif type(schema)==AnnotationSchema:
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

        if not schema_key in [i.name for i in self.schemas]:
            return f'Schema: {schema_key} Not Found!'
        
        schema_index = [i.name for i in self.schemas].index(schema_key)
        schema_info = self.schemas[schema_index]

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
                        schema_info.description
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
                            for idx,i in enumerate(schema_info.annotations)
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
            disabled= roi_input_color=='secondary' or input_spec['type']=='roi'
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

            level_names = input_spec.get('levels',['True','False'])
            if len(level_names)<2:
                level_names = ['True','False']

            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dcc.RadioItems(
                            options = [
                                {'label': level_names[0], 'value': 1},
                                {'label': level_names[1], 'value': 0}
                            ],
                            inline = True,
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

        elif input_spec['type']=='checklist':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.Checklist(
                                options = input_spec['options'],
                                value = use_val,
                                id = {'type': 'slide-annotation-input','index': iput_index}
                            ),
                            roi_button,
                            edit_button
                        ])
                    ],md=7)
                ]),
                html.Hr()
            ])

        elif input_spec['type']=='roi':
            input_component = html.Div([
                dbc.Row([
                    dbc.Col(input_desc_column,md=5),
                    dbc.Col([
                        dbc.InputGroup([
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

        if input_info.get('type','') in ['options','checklist']:
            options_div = html.Div(
                id = {'type':'slide-annotation-edit-option-div','index': 0},
                children = [
                    html.Div(
                        id = {'type':'slide-annotation-edit-option-parent-div','index': 0},
                        children = [
                            dbc.Row([
                                dbc.InputGroup([
                                    dbc.InputGroupText('Option: '),
                                    dbc.Input(
                                        type = 'text',
                                        value = o,
                                        id = {'type': 'slide-annotation-edit-option','index': o_idx}
                                    ),
                                    dbc.Button(
                                        children = [
                                            html.H4('X',style = {'color': 'rgb(0,0,0)'})
                                        ],
                                        id = {'type': 'slide-annotation-edit-option-remove','index': o_idx}
                                    )
                                ])
                            ],style = {'marginBottom':'5px'})
                            for o_idx,o in enumerate(input_info.get('options',[]))
                        ]                    
                    ),
                    dbc.Row(
                        children = [
                            dbc.Col(
                                html.A(
                                    html.I(
                                        className = 'bi bi-plus-circle-fill h3',
                                        style = {'color': 'rgb(0,255,0)'},
                                        n_clicks = len(input_info.get('options',[])),
                                        id = {'type': 'slide-annotation-edit-option-add','index': 0}
                                    )
                                ),
                                width = 'auto', align = 'center'
                            )
                        ],
                        align = 'center',justify='center'
                    ),
                    html.Hr()
                ]
            )
        else:
            options_div = html.Div(
                id = {'type':'slide-annotation-edit-option-div','index': 0},
                children = []
            )

        edit_modal_content = dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    html.H4(f"Editing: {input_info.get('name')}")
                ]),
                html.Hr(),
                dbc.Row([
                    dbc.Col(
                        html.H5('Name: '),
                        md = 3
                    ),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.Input(
                                type = 'text',
                                value = input_info.get('name',''),
                                id = {'type': 'slide-annotation-edit-name-text','index': 0}
                            )
                        ])
                    ], md = 9)
                ], style = {'marginBottom': '10px'}),
                dbc.Row([
                    dbc.Col(
                        html.H5('Description: '),
                        md = 3
                    ),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.Input(
                                type = 'text',
                                value = input_info.get('description',''),
                                id = {'type': 'slide-annotation-edit-description-text','index': 0}
                            )
                        ]),
                    ], md = 9)
                ], style = {'marginBottom': '10px'}),
                dbc.Row([
                    dbc.Col(
                        dbc.InputGroup([
                            dbc.InputGroupText('Type: '),
                            dbc.Select(
                                options = self.annotation_types,
                                value = input_info.get('type',[]),
                                id = {'type': 'slide-annotation-edit-type-dropdown','index': 0}
                            )
                        ])
                    )
                ], style = {'marginBottom': '10px'}),
                dbc.Row([
                    dbc.Col(
                        dbc.InputGroup([
                            dbc.InputGroupText('ROI: '),
                            dbc.Select(
                                options = [
                                    'True', 'False'
                                ],
                                value = 'True' if input_info.get('roi',False) else 'False',
                                id = {'type': 'slide-annotation-edit-roi-dropdown','index': 0}
                            )
                        ])
                    )
                ], style = {'marginBottom': '10px'}),
                dbc.Row([
                    dbc.Col(
                        dbc.InputGroup([
                            dbc.InputGroupText('Editable: '),
                            dbc.Select(
                                options = [
                                    'True', 'False'
                                ],
                                value = 'True' if input_info.get('editable',False) else 'False',
                                id = {'type': 'slide-annotation-edit-editable-dropdown','index': 0}
                            )
                        ])
                    )
                ], style = {'marginBottom': '10px'}),
                html.Hr(),
                options_div,
                dcc.Store(
                    id = {'type': 'slide-annotation-edit-store','index': 0},
                    data = json.dumps(input_info),
                    storage_type = 'memory'
                ),
                dbc.Row([
                    dbc.Col([
                        dbc.Button(
                            'Remove Annotation Input',
                            className = 'd-grid col-12 mx-auto',
                            color = 'danger',
                            id = {'type': 'slide-annotation-edit-remove-input','index': 0}
                        )
                    ],md=6),
                    dbc.Col([
                        dbc.Button(
                            'Update Annotation Input',
                            className = 'd-grid col-12 mx-auto',
                            color = 'success',
                            id = {'type': 'slide-annotation-edit-update-input','index': 0}
                        )
                    ])
                ])
            ])
        ])


        PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(edit_modal_content)

        
        return [True], [edit_modal_content]

    def update_edit_option_div(self, edit_value, input_info):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        input_info = json.loads(get_pattern_matching_value(input_info))
        edit_value = get_pattern_matching_value(edit_value)
        if edit_value in ['options','checklist','radio']:
            options_div = html.Div([
                html.Div(
                    id = {'type':'slide-annotation-edit-option-parent-div','index': 0},
                    children = [
                        dbc.Row([
                            dbc.InputGroup([
                                dbc.InputGroupText('Option: '),
                                dbc.Input(
                                    type = 'text',
                                    value = o,
                                    id = {'type': 'slide-annotation-edit-option','index': o_idx}
                                ),
                                dbc.Button(
                                    children = [
                                        html.H4('X',style = {'color': 'rgb(0,0,0)'})
                                    ],
                                    id = {'type': 'slide-annotation-edit-option-remove','index': o_idx}
                                )
                            ])
                        ],style = {'marginBottom':'5px'})
                        for o_idx,o in enumerate(input_info.get('options',[]))
                    ]                    
                ),
                dbc.Row(
                    children = [
                        dbc.Col(
                            html.A(
                                html.I(
                                    className = 'bi bi-plus-circle-fill h3',
                                    style = {'color': 'rgb(0,255,0)'},
                                    n_clicks = len(input_info.get('options',[])),
                                    id = {'type': 'slide-annotation-edit-option-add','index': 0}
                                )
                            ),
                            width = 'auto', align = 'center'
                        )
                    ],
                    align = 'center',justify='center'
                ),
                html.Hr()
            ])

            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(options_div)

            return [options_div]
        else:
            return [html.Div()]

    def update_edit_options(self, add_click,rem_click, option_ids):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        add_click = get_pattern_matching_value(add_click)

        options_parent = Patch()
        def make_new_option(click_idx):
            new_row =  dbc.Row([
                    dbc.InputGroup([
                        dbc.InputGroupText('Option: '),
                        dbc.Input(
                            type = 'text',
                            value = '',
                            id = {'type': 'slide-annotation-edit-option','index': click_idx}
                        ),
                        dbc.Button(
                            children = [
                                html.H4('X',style = {'color': 'rgb(0,0,0)'})
                            ],
                            id = {'type': 'slide-annotation-edit-option-remove','index': click_idx}
                        )
                    ])
                ],style = {'marginBottom':'5px'})

            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(new_row)

            return new_row

        if 'slide-annotation-edit-option-add' in ctx.triggered_id['type']:
        
            options_parent.append(make_new_option(add_click))
            
        elif 'slide-annotation-edit-option-remove' in ctx.triggered_id['type']:
            
            del options_parent[rem_click.index(1)]
        

        return [options_parent]

    def update_edit(self,remove_click, update_click, update_name, update_desc, update_type, update_roi, update_editable, update_options, edit_store, schema_name):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        update_name = get_pattern_matching_value(update_name)
        update_desc = get_pattern_matching_value(update_desc)
        update_type = get_pattern_matching_value(update_type)
        update_roi = get_pattern_matching_value(update_roi)
        update_editable = get_pattern_matching_value(update_editable)
        
        edit_store = json.loads(get_pattern_matching_value(edit_store))
        schema_name = get_pattern_matching_value(schema_name)

        available_schema_names = [
            i.name
            for i in self.schemas
        ]

        if schema_name in available_schema_names:
            current_schema = self.schemas[available_schema_names.index(schema_name)]

            schema_ann_names = [
                i.get('name') for i in current_schema.annotations
            ]

            update_ann = current_schema.annotations[schema_ann_names.index(edit_store.get('name'))]

            if 'slide-annotation-edit-remove-input' in ctx.triggered_id['type']:
                del current_schema.annotations[schema_ann_names.index(edit_store.get('name'))]
                
            elif 'slide-annotation-edit-update-input' in ctx.triggered_id['type']:

                update_ann = update_ann | {
                    'name': update_name,
                    'description': update_desc,
                    'type': update_type,
                    'roi': update_roi,
                    'editable': update_editable
                }

                if update_type in ['options','radio','checklist']:
                    update_ann['options'] = update_options
                
                current_schema.annotations[schema_ann_names.index(edit_store.get('name'))] = update_ann

        
        modal_open = False
        parent_div_children = html.Div()
        schema_drop_value = []

        return [modal_open], [parent_div_children], [modal_open]
        

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

        slide_id = slide_information['metadata_url'].split('/')[-1]
        if slide_id == 'metadata':
            slide_id = slide_information['metadata_url'].split('/')[-2]

        this_slide_dict = {
            'Slide Name': slide_information['name'],
            'Slide ID': slide_id
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






