"""
Visualization tools which can be linked to SlideMap components (but don't have to be)

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
    

class OverlayOptions(Tool):
    """OverlayOptions Tool which enables editing overlay visualization properties including line color, fill color, and filters.

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self,
                 ignore_list: list = ["_id", "_index"],
                 property_depth: int = 4
                 ):
        """Constructor method

        :param geojson_anns: Individual or list of GeoJSON formatted annotations.
        :type geojson_anns: Union[list,dict]
        :param reference_object: Path to larger object containing information on GeoJSON features, defaults to None
        :type reference_object: Union[str,None], optional
        :param ignore_list: List of properties to exclude from visualization. These can include any internal or private properties that are not desired to be viewed by the user or used for filtering/overlay colors., defaults to []
        :type ignore_list: list, optional
        :param property_depth: Depth at which to search for nested properties. Properties which are nested further than this will be ignored.
        :type property_depth: int, optional
        """

        super().__init__()
        self.ignore_list = ignore_list
        self.property_depth = property_depth
    
    def __str__(self):
        return 'Overlay Options'
        
    def load(self,component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Overlay Options'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.js_namespace = Namespace("fusionTools","slideMap")

        # Add callbacks here
        self.get_callbacks()

    def gen_layout(self, session_data:dict):
        """Generating OverlayOptions layout, added to DashBlueprint() object to be embedded in larger layout.
        """

        adv_colormaps = [
            'Custom Palettes',
            'blue->red',
            'white->black',
            'Sequential Palettes',
            'OrRd', 'PuBu', 'BuPu', 
            'Oranges', 'BuGn', 'YlOrBr', 
            'YlGn', 'Reds', 'RdPu', 
            'Greens', 'YlGnBu', 'Purples', 
            'GnBu', 'Greys', 'YlOrRd', 
            'PuRd', 'Blues', 'PuBuGn', 
            'Diverging Palettes',
            'Viridis', 'Spectral', 'RdYlGn', 
            'RdBu', 'PiYG', 'PRGn', 'RdYlBu', 
            'BrBG', 'RdGy', 'PuOr', 
            'Qualitative Palettes',
            'Set2', 'Accent', 'Set1', 
            'Set3', 'Dark2', 'Paired', 
            'Pastel2', 'Pastel1',
        ]

        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Overlay Options')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Select options below to adjust overlay color, transparency, and line color for structures on your slide.'
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label(
                                'Select Overlay Property: ',
                                html_for = {'type': 'overlay-drop','index': 0}
                            ),
                            md = 3
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = False,
                                id = {'type': 'overlay-drop','index': 0}
                            ),
                            md = 9
                        )
                    ]),
                    html.Div(
                        dcc.Store(
                            id = {'type': 'overlay-property-info','index':0},
                            data = json.dumps({}),
                            storage_type='memory'
                        )
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label(
                                'Adjust Overlay Transparency: ',
                                html_for = {'type': 'overlay-trans-slider','index': 0}
                            ),
                            md = 3
                        ),
                        dbc.Col(
                            dcc.Slider(
                                min = 0,
                                max = 100,
                                step = 10,
                                value = 50,
                                id = {'type': 'overlay-trans-slider','index': 0}
                            )
                        )
                    ]),
                    html.Hr(),
                    dbc.Row([
                        dbc.Label('Filter Structures: ',html_for = {'type': 'add-filter-parent','index': 0}),
                        html.Div('Click the icon below to add a filter.')
                    ]),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'add-filter-parent','index': 0},
                            children = []
                        )
                    ],align='center'),
                    dbc.Row([
                        dbc.Col([
                            html.Div([
                                html.A(
                                    html.I(
                                        className = 'bi bi-filter-circle fa-2x',
                                        n_clicks = 0,
                                        id = {'type': 'add-filter-butt','index': 0},
                                    )
                                ),
                                dbc.Tooltip(
                                    target = {'type': 'add-filter-butt','index': 0},
                                    children = 'Click to add a filter'
                                )
                            ])
                        ],md = 2),
                        dbc.Col([
                            html.Div([
                                html.A(
                                    html.I(
                                        className = 'fa-solid fa-layer-group fa-2x',
                                        n_clicks = 0,
                                        id = {'type': 'create-layer-from-filter','index': 0},
                                    )
                                ),
                                dbc.Tooltip(
                                    target = {'type': 'create-layer-from-filter','index': 0},
                                    children = 'Create new layer from filters'
                                )
                            ])
                        ],md = 2)
                    ],align='center', justify='center'),
                    html.Hr(),
                    dbc.Row(
                        dbc.Label('Update Structure Boundary Color',html_for = {'type': 'feature-lineColor-opts','index': 0})
                    ),
                    dbc.Row([
                        dbc.Tabs(
                            id = {'type': 'feature-lineColor-opts','index': 0},
                            children = []
                        )
                    ],style = {'marginBottom':'10px'}),
                    dbc.Row([
                        dbc.Accordion(
                            id = {'type':'adv-overlay-accordion','index': 0},
                            start_collapsed = True,
                            children = [
                                dbc.AccordionItem(
                                    title = dcc.Markdown('*Advanced Overlay Options*'),
                                    children = [
                                        dbc.Card([
                                            dbc.CardBody([
                                                html.Div([
                                                    dbc.InputGroup([
                                                        dbc.Input(
                                                            id = {'type': 'adv-overlay-colorbar-width','index': 0},
                                                            placeholder = 'Colorbar Width',
                                                            type = 'number',
                                                            value = 300,
                                                            min = 0,
                                                            max = 1000,
                                                            step = 50
                                                        ),
                                                        dbc.InputGroupText(
                                                            'pixels'
                                                        )
                                                    ]),
                                                    dbc.FormText(
                                                        'Width of colorbar'
                                                    ),
                                                    html.Hr(),
                                                    dbc.Select(
                                                        id = {'type': 'adv-overlay-colormap','index': 0},
                                                        placeholder = 'Select colormap options',
                                                        options = [
                                                            {'label': i, 'value': i, 'disabled': ' ' in i}
                                                            for i in adv_colormaps
                                                        ],
                                                        value = 'blue->red'
                                                    )
                                                ]),
                                                html.Div(
                                                    children = [
                                                        dbc.Button(
                                                            'Update Overlays!',
                                                            className = 'd-grid col-12 mx-auto',
                                                            id = {'type': 'adv-overlay-butt','index': 0},
                                                            n_clicks = 0
                                                        )
                                                    ],
                                                    style = {'marginTop':'10px'}
                                                )
                                            ])
                                        ])
                                    ]
                                ),
                                dbc.AccordionItem(
                                    title = dcc.Markdown('*Manual ROI Options*'),
                                    children = [
                                        dbc.Card([
                                            dbc.CardBody([
                                                # Whether to separate structures or not
                                                # Whether to summarize or not
                                                dmc.Switch(
                                                    size = 'lg',
                                                    radius = 'lg',
                                                    label = 'Separate Intersecting Structures',
                                                    onLabel="ON",
                                                    offLabel="OFF",
                                                    description = "Separates aggregated properties by which structure they are derived from",
                                                    id = {'type': 'manual-roi-separate-switch','index':0}
                                                ),
                                                html.Hr(),
                                                dmc.Switch(
                                                    size = 'lg',
                                                    radius = 'lg',
                                                    label = "Summarize Aggregated Properties",
                                                    onLabel = "ON",
                                                    offLabel = "OFF",
                                                    description = "Whether to report summaries of aggregated properties or just the MEAN",
                                                    id = {'type': 'manual-roi-summarize-switch','index': 0}
                                                )
                                            ])
                                        ])
                                    ]
                                ),
                                dbc.AccordionItem(
                                    title = dcc.Markdown('*Export Layers*'),
                                    children = [
                                        dbc.Card([
                                            dbc.CardBody([
                                                html.Div([
                                                    dbc.Button(
                                                        'Export Current Layers',
                                                        id = {'type': 'export-current-layers','index': 0},
                                                        n_clicks = 0,
                                                        className = 'd-grid col-12 mx-auto'
                                                    ),
                                                    dcc.Download(
                                                        id = {'type': 'export-current-layers-data','index': 0}
                                                    )
                                                ])
                                            ])
                                        ])
                                    ]
                                )
                            ]
                        )
                    ])
                ])
            )
        ],style = {'maxHeight': '100vh','overflow':'scroll'})

        self.blueprint.layout = layout

    def get_callbacks(self):
        """Initializing callbacks for OverlayOptions Tool
        """

        # Updating for new slide selection:
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-info-store','index': ALL},'data')
            ],
            [
                Output({'type': 'overlay-drop','index': ALL},'options'),
                Output({'type': 'overlay-property-info','index': ALL},'data'),
                Output({'type': 'add-filter-parent','index': ALL},'children'),
                Output({'type': 'feature-lineColor-opts','index': ALL},'children')
            ]
        )(self.update_slide)

        # Updating overlay color, transparency, line color, and filter
        self.blueprint.callback(
            [
                Input({'type': 'overlay-drop','index': ALL},'value'),
                Input({'type':'overlay-trans-slider','index': ALL},'value'),
                Input({'type':'feature-lineColor-butt','index': ALL},'n_clicks'),
                Input({'type': 'add-filter-parent','index': ALL},'children'),
                Input({'type':'add-filter-selector','index': ALL},'value'),
                Input({'type':'delete-filter','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-bounds','index': ALL},'hideout'),
                Output({'type': 'map-colorbar-div','index': ALL},'children')
            ],
            [
                State({'type': 'overlay-drop','index': ALL},'value'),
                State({'type': 'overlay-trans-slider','index': ALL},'value'),
                State({'type': 'overlay-property-info','index': ALL},'data'),
                State({'type': 'feature-lineColor','index': ALL},'value'),
                State({'type': 'feature-overlay','index': ALL},'name'),
                State({'type': 'adv-overlay-colormap','index': ALL},'value'),
                State({'type': 'feature-bounds','index': ALL},'hideout')
            ]
        )(self.update_overlays)

        # Updating overlays based on additional options
        self.blueprint.callback(
            [
                Input({'type':'adv-overlay-butt','index': ALL},'n_clicks')
            ],
            [
                Output({'type':'feature-bounds','index': ALL},'hideout'),
                Output({'type': 'map-colorbar-div','index': ALL},'children')
            ],
            [
                State({'type': 'adv-overlay-colorbar-width','index': ALL},'value'),
                State({'type': 'adv-overlay-colormap','index': ALL},'value'),
                State({'type': 'feature-bounds','index': ALL},'hideout')
            ]
        )(self.adv_update_overlays)

        # Adding filters
        self.blueprint.callback(
            [
                Output({'type': 'add-filter-parent','index': ALL},'children',allow_duplicate=True)
            ],
            [
                Input({'type': 'add-filter-butt','index': ALL},'n_clicks'),
                Input({'type': 'delete-filter','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'overlay-property-info','index': ALL},'data'),
                State({'type': 'overlay-drop','index': ALL},'options')
            ]
        )(self.add_filter)

        # Changing the filter selector based on dropdown selection
        self.blueprint.callback(
            [
                Input({'type': 'add-filter-drop','index': MATCH},'value')
            ],
            [
                Output({'type': 'add-filter-selector-div','index': MATCH},'children')
            ],
            [
                State({'type': 'overlay-property-info','index': ALL},'data')
            ]
        )(self.update_filter_selector)

        # Opening create layer options from filter (if any filters are specified)
        self.blueprint.callback(
            [
                Input({'type':'create-layer-from-filter','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'map-layers-control','index': ALL},'children'),
                Output({'type': 'map-annotations-store','index': ALL},'data')
            ],
            [
                State({'type': 'add-filter-parent','index': ALL},'children'),
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'feature-overlay','index': ALL},'name'),
                State({'type': 'feature-lineColor','index': ALL},'value'),
                State({'type': 'adv-overlay-colormap','index': ALL},'value'),
            ]
        )(self.create_layer_from_filter)

        # Adding new structures to the line color selector
        self.blueprint.callback(
            [
                Input({'type': 'feature-overlay','index':ALL},'name')
            ],
            [
                Output({'type': 'feature-lineColor-opts','index': ALL},'children')
            ]
        )(self.add_structure_line_color)

        # Exporting current layers
        self.blueprint.callback(
            [
                Input({'type': 'export-current-layers','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'export-current-layers-data','index': ALL},'data')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'map-slide-information','index':ALL},'data')
            ]
        )(self.export_layers)

    def update_slide(self, new_annotations_info:list):
        
        if not any([i['value'] for i in ctx.triggered]):
            return [[]], [json.dumps({})], [[]], [[]]

        new_annotations_info = json.loads(get_pattern_matching_value(new_annotations_info))
        overlay_options = new_annotations_info['available_properties']
        feature_names = new_annotations_info['feature_names']
        overlay_info = new_annotations_info['property_info']

        drop_options = [
            {
                'label': i,
                'value': i
            }
            for i in overlay_options
        ]

        property_info = json.dumps(overlay_info)
        filter_children = []
        feature_lineColor_children = [
            dbc.Tab(
                children = [
                    dmc.ColorPicker(
                        id = {'type': f'{self.component_prefix}-feature-lineColor','index': f_idx},
                        format = 'hex',
                        value = '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255)),
                        fullWidth=True
                    ),
                    dbc.Button(
                        id = {'type': f'{self.component_prefix}-feature-lineColor-butt','index': f_idx},
                        children = ['Update Boundary Color'],
                        className = 'd-grid col-12 mx-auto',
                        n_clicks = 0
                    )
                ],
                label = f
            )
            for f_idx, f in enumerate(feature_names)
        ]

        return [drop_options], [property_info],[filter_children], [feature_lineColor_children]
 
    def add_filter(self, add_filter_click, delete_filter_click,overlay_info_state,overlay_options):
        """Adding a new filter to apply to GeoJSON features

        :param add_filter_click: Add filter icon clicked
        :type add_filter_click: _type_
        :param delete_filter_click: Delete filter icon (x) clicked
        :type delete_filter_click: _type_
        :param overlay_info_state: Summary information on properties for GeoJSON features
        :type overlay_info_state: _type_
        :raises exceptions.PreventUpdate: Stop callback execution
        :raises exceptions.PreventUpdate: No information provided for GeoJSON properties, cancels adding new filter.
        :return: List of current filters applied to GeoJSON features
        :rtype: list
        """
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        add_filter_click = get_pattern_matching_value(add_filter_click)
        overlay_options = get_pattern_matching_value(overlay_options)
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))
        #TODO: See if these can be added as an "OR" or "AND" to get more specific filtering 
        if len(list(overlay_info_state.keys()))==0:
            raise exceptions.PreventUpdate

        active_filters = Patch()
        if 'delete-filter' in ctx.triggered_id['type']:

            values_to_remove = []
            for i,val in enumerate(delete_filter_click):
                if val:
                    values_to_remove.insert(0,i)
            
            for v in values_to_remove:
                del active_filters[v]

        elif 'add-filter-butt' in ctx.triggered_id['type']:
            
            # Initializing dropdown value 
            overlayBounds = overlay_info_state[overlay_options[0]['label']]
            if 'min' in overlayBounds:
                # Used for numeric filtering
                values_selector = html.Div(
                    dcc.RangeSlider(
                        id = {'type': f'{self.component_prefix}-add-filter-selector','index': add_filter_click},
                        min = overlayBounds['min']-0.01,
                        max = overlayBounds['max']+0.01,
                        value = [overlayBounds['min'],overlayBounds['max']],
                        step = 0.01,
                        marks = None,
                        tooltip = {'placement':'bottom','always_visible': True},
                        allowCross = True,
                        disabled = False
                    ),
                    id = {'type': f'{self.component_prefix}-add-filter-selector-div','index': add_filter_click},
                    style = {'display': 'inline-block','margin': 'auto','width': '100%'}
                )
            elif 'unique' in overlayBounds:
                # Used for categorical filtering
                values_selector = html.Div(
                    dcc.Dropdown(
                        id = {'type':f'{self.component_prefix}-add-filter-selector','index': add_filter_click},
                        options = overlayBounds['unique'],
                        value = overlayBounds['unique'],
                        multi = True
                    ),
                    id = {'type': f'{self.component_prefix}-add-filter-selector-div','index': add_filter_click}
                )
            
            def new_filter_item():
                return html.Div([
                    dbc.Row([
                        dbc.Col(
                            dcc.Dropdown(
                                options = overlay_options,
                                value = overlay_options[0],
                                placeholder = 'Select property to filter structures',
                                id = {'type': f'{self.component_prefix}-add-filter-drop','index': add_filter_click}
                            ),
                            md = 10
                        ),
                        dbc.Col([
                            html.I(
                                id = {'type': f'{self.component_prefix}-delete-filter','index': add_filter_click},
                                n_clicks = 0,
                                className = 'bi bi-x-circle-fill fa-2x',
                                style = {'color': 'rgb(255,0,0)'}
                            ),
                            dbc.Tooltip(
                                target = {'type': f'{self.component_prefix}-delete-filter','index': add_filter_click},
                                children = 'Delete this filter'
                            )
                            ],
                            md = 2
                        )
                    ],align='center'),
                    values_selector
                ])
            
            active_filters.append(new_filter_item())

        return [active_filters]
    
    def update_filter_selector(self, add_filter_value, overlay_info_state):
        """Updating the filter selector (either a RangeSlider or Dropdown component depending on property type)


        :param add_filter_value: Selected property to be used for filters.
        :type add_filter_value: str
        :param overlay_info_state: Current information on GeoJSON feature properties (contains "min" and "max" for numeric properties and "unique" for categorical properties)
        :type overlay_info_state: list
        :raises exceptions.PreventUpdate: Stop callback execution
        :return: Filter selector. Either a dropdown menu for categorical properties or a dcc.RangeSlider for selecting a range of values between the minimum and maximum for that property
        :rtype: _type_
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))
        overlayBounds = overlay_info_state[add_filter_value]
        if 'min' in overlayBounds:
            # Used for numeric filtering
            values_selector = dcc.RangeSlider(
                id = {'type': f'{self.component_prefix}-add-filter-selector','index': ctx.triggered_id['index']},
                min = overlayBounds['min']-0.01,
                max = overlayBounds['max']+0.01,
                value = [overlayBounds['min'],overlayBounds['max']],
                step = 0.01,
                marks = None,
                tooltip = {'placement':'bottom','always_visible': True},
                allowCross = True,
                disabled = False
            )
        
        elif 'unique' in overlayBounds:
            # Used for categorical filtering
            values_selector = dcc.Dropdown(
                id = {'type':f'{self.component_prefix}-add-filter-selector','index': ctx.triggered_id['index']},
                options = overlayBounds['unique'],
                value = overlayBounds['unique'],
                multi = True
            )

        return values_selector

    def parse_added_filters(self, add_filter_parent:list)->list:
        """Getting all filter values from parent div


        :param add_filter_parent: List of dictionaries containing component information from dynamically added filters.
        :type add_filter_parent: list
        :return: List of filter values to apply to current GeoJSON features.
        :rtype: list
        """
        processed_filters = []

        if not add_filter_parent is None:
            for div in add_filter_parent:
                div_children = div['props']['children']
                filter_name = div_children[0]['props']['children'][0]['props']['children']['props']['value']

                if 'value' in div_children[1]['props']['children']['props']:
                    filter_value = div_children[1]['props']['children']['props']['value']
                else:
                    filter_value = div_children[1]['props']['children']['props']['children']['props']['value']

                processed_filters.append({
                    'name': filter_name,
                    'range': filter_value
                })

        return processed_filters

    def update_overlays(self, overlay_value, transp_value, lineColor_butt, filter_parent, filter_value, delete_filter, overlay_state, transp_state, overlay_info_state, lineColor_state, overlay_names, colormap_val, current_hideout):
        """Update overlay transparency and color based on property selection

        Adding new values to the "hideout" property of the GeoJSON layers triggers the featureStyle Namespace function

        :param overlay_value: Value to use as a basis for generating colors (range of colors for numeric properties and list of colors for categorical properties)
        :type overlay_value: list
        :param transp_value: Transparency value for each feature.
        :type transp_value: list
        :param lineColor_butt: Whether the button to update the lineColor property was clicked.
        :type lineColor_butt: list
        :param filter_parent: Parent Div containing filter information
        :type filter_parent: list
        :param filter_value: Whether the callback is triggered by a new filter value being selected
        :type filter_value: list
        :param delete_filter: Whether the callback is triggered by a filter being deleted
        :type delete_filter: list
        :param overlay_state: State of overlay dropdown if not triggered by new overlay value selection
        :type overlay_state: list
        :param transp_state: State of transparency slider if not triggered by transparency slider adjustment
        :type transp_state: list
        :param overlay_info_state: Information on overlay properties for current GeoJSON features
        :type overlay_info_state: list
        :param lineColor_state: Current selected lineColors to apply to current GeoJSON features
        :type lineColor_state: list
        :param colormap_val: Current colormap applied to overlays,
        :type colormap_val: list
        :param current_hideout: Current hideout properties assigned to each GeoJSON layer
        :type current_hideout: list
        :return: List of dictionaries added to the GeoJSONs' "hideout" property (used by Namespace functions) and a colorbar based on overlay value.
        :rtype: tuple
        """

        overlay_value = get_pattern_matching_value(overlay_value)
        transp_value = get_pattern_matching_value(transp_value)
        overlay_state = get_pattern_matching_value(overlay_state)
        transp_state = get_pattern_matching_value(transp_state)
        colormap_val = get_pattern_matching_value(colormap_val)
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))

        if 'overlay-drop' in ctx.triggered_id['type']:
            use_overlay_value = overlay_value
            use_transp_value = transp_state
        else:
            if type(overlay_state)==list:
                if len(overlay_state)==0:
                    use_overlay_value = None
                else:
                    use_overlay_value = overlay_state[0]
            else:
                use_overlay_value = overlay_state

        if 'overlay-trans-slider' in ctx.triggered_id['type']:
            use_transp_value = transp_value
        else:
            use_transp_value = transp_state

        if any([i in ctx.triggered_id['type'] for i in ['add-filter-parent', 'add-filter-selector','delete-filter']]):
            use_overlay_value = overlay_state
            use_transp_value = transp_state

        if 'feature-lineColor-butt' in ctx.triggered_id['type']:
            use_overlay_value = overlay_state
            use_transp_value = transp_state


        if not use_overlay_value is None:
            overlay_prop = {
                'name': use_overlay_value,
            }
        else:
            overlay_prop = {
                'name': None,
            }

        if not use_transp_value is None:
            fillOpacity = use_transp_value/100
        else:
            fillOpacity = 0.5

        if not use_overlay_value is None:
            overlay_bounds = overlay_info_state[use_overlay_value]
        else:
            overlay_bounds = {}

        lineColor = {
            i: j
            for i,j in zip(overlay_names, lineColor_state)
        }
        
        color_bar_style = {
            'visibility':'visible',
            'background':'white',
            'background':'rgba(255,255,255,0.8)',
            'box-shadow':'0 0 15px rgba(0,0,0,0.2)',
            'border-radius':'10px',
            'width': '400px',
            'padding':'0px 0px 0px 25px'
        }

        if 'min' in overlay_bounds:
            colorbar = [dl.Colorbar(
                colorscale = colormap_val if not '->' in colormap_val else colormap_val.split('->'),
                width = 300,
                height = 15,
                position = 'bottomleft',
                id = f'colorbar{np.random.randint(0,100)}',
                style = color_bar_style,
                tooltip=True
            )]
        elif 'unique' in overlay_bounds:
            colorbar = [dlx.categorical_colorbar(
                categories = overlay_bounds['unique'],
                colorscale = colormap_val if not '->' in colormap_val else colormap_val.split('->'),
                style = color_bar_style,
                position = 'bottomleft',
                id = f'colorbar{np.random.randint(0,100)}',
                width = 300,
                height = 15
            )]

        else:
            colorbar = [no_update]

        # Grabbing all filter values from the parent div
        filterVals = self.parse_added_filters(get_pattern_matching_value(filter_parent))

        geojson_hideout = [
            j | {
                'overlayBounds': overlay_bounds,
                'overlayProp': overlay_prop,
                'fillOpacity': fillOpacity,
                'lineColor': lineColor,
                'filterVals': filterVals,
            }
            for i,j in zip(range(len(ctx.outputs_list[0])),current_hideout)
        ]

        return geojson_hideout, colorbar

    def adv_update_overlays(self, butt_click: list, colorbar_width:list, colormap_val:list, current_feature_hideout:list):
        """Update some additional properties of the overlays and display.

        :param butt_click: Button clicked to update overlay properties 
        :type butt_click: list
        :param colorbar_width: Width of colorbar in pixels
        :type colorbar_width: list
        :param colormap_val: Colormap option to pass to chroma
        :type colormap_val: list
        :param current_feature_hideout: Current hideout properties for all structures
        :type current_feature_hideout: list
        :return: Updated colorbar width, line width, and colormap
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]) or len(current_feature_hideout)==0:
            raise exceptions.PreventUpdate

        new_hideout = [no_update]*len(ctx.outputs_list[1])

        colorbar_width = get_pattern_matching_value(colorbar_width)
        colormap_val = get_pattern_matching_value(colormap_val)

        # Updating colorbar width and colormap:
        overlay_bounds = current_feature_hideout[0]['overlayBounds']

        if not colorbar_width==0:
            color_bar_style = {
                'visibility':'visible',
                'background':'white',
                'background':'rgba(255,255,255,0.8)',
                'box-shadow':'0 0 15px rgba(0,0,0,0.2)',
                'border-radius':'10px',
                'width': f'{colorbar_width+100}px',
                'padding':'0px 0px 0px 25px'
            }

            if 'min' in overlay_bounds:
                colorbar_div_children = [dl.Colorbar(
                    colorscale = colormap_val,
                    width = colorbar_width,
                    height = 15,
                    position = 'bottomleft',
                    id = f'{self.component_prefix}-colorbar{np.random.randint(0,100)}',
                    style = color_bar_style,
                    tooltip=True
                )]
            elif 'unique' in overlay_bounds:
                colorbar_div_children = [dlx.categorical_colorbar(
                    categories = overlay_bounds['unique'],
                    colorscale = colormap_val,
                    style = color_bar_style,
                    position = 'bottomleft',
                    id = f'{self.component_prefix}-colorbar{np.random.randint(0,100)}',
                    width = colorbar_width,
                    height = 15
                )]

            else:
                colorbar_div_children = [no_update]
        else:
            colorbar_div_children = [html.Div()]

        # Updating line width:
        new_hideout = [i | {'colorMap': colormap_val} for i in current_feature_hideout]

        return new_hideout, colorbar_div_children

    def create_layer_from_filter(self, icon_click:list, current_filters:list, current_annotations:list, current_overlay_names:list, line_colors: list, colormap: list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_filters = get_pattern_matching_value(current_filters)
        colormap = get_pattern_matching_value(colormap)

        if not current_filters is None:
            filter_list = self.parse_added_filters(current_filters)
            if len(filter_list)>0:

                current_annotations = json.loads(get_pattern_matching_value(current_annotations))
                filtered_geojson, filter_reference_list = process_filters_queries(filter_list,[],['all'],current_annotations)
                filtered_geojson['properties'] = {
                    'name': f'Filtered {len([i for i in current_overlay_names if "Filtered" in i])}',
                    '_id': uuid.uuid4().hex[:24]
                }

                line_colors_dict = {
                    i:j
                    for i,j in zip(current_overlay_names,line_colors)
                }
                line_colors_dict[filtered_geojson['properties']['name']] = '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255))

                for f in filtered_geojson['features']:
                    f['properties']['name'] = filtered_geojson['properties']['name']

                if len(filtered_geojson['features'])>0:
                    new_children = Patch()
                    new_children.append(
                        dl.Overlay(
                            dl.LayerGroup(
                                dl.GeoJSON(
                                    data = filtered_geojson,
                                    id = {'type': f'{self.component_prefix}-feature-bounds','index': len(current_overlay_names)+1},
                                    options = {
                                        'style': self.js_namespace("featureStyle")
                                    },
                                    filter = self.js_namespace('featureFilter'),
                                    hideout = {
                                        'overlayBounds': {},
                                        'overlayProp': {},
                                        'fillOpacity': 0.5,
                                        'lineColor': line_colors_dict,
                                        'filterVals': [],
                                        'colorMap': colormap
                                    },
                                    hoverStyle = arrow_function(
                                        {
                                            'weight': 5,
                                            'color': '#9caf00',
                                            'dashArray': ''
                                        }
                                    ),
                                    zoomToBounds=False,
                                    children = [
                                        dl.Popup(
                                            id = {'type': f'{self.component_prefix}-feature-popup','index': len(current_overlay_names)+1},
                                            autoPan = False,
                                        )
                                    ]
                                )
                            ),
                            name = filtered_geojson['properties']['name'], checked = True, id = {'type': f'{self.component_prefix}-feature-overlay','index': len(current_overlay_names)}
                        )
                    )

                    current_annotations.append(filtered_geojson)

                    return [new_children], [json.dumps(current_annotations)]
                else:
                    raise exceptions.PreventUpdate
            else:
                raise exceptions.PreventUpdate
        else:
            raise exceptions.PreventUpdate

    def add_structure_line_color(self, overlay_names:list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        line_color_tabs = Patch()
        line_color_tabs.append(
            dbc.Tab(
                children = [
                    dmc.ColorPicker(
                        id = {'type': f'{self.component_prefix}-feature-lineColor','index': len(overlay_names)},
                        format = 'hex',
                        value = '#FFFFFF',
                        fullWidth=True
                    ),
                    dbc.Button(
                        id = {'type': f'{self.component_prefix}-feature-lineColor-butt','index': len(overlay_names)},
                        children = ['Update Boundary Color'],
                        className = 'd-grid col-12 mx-auto',
                        n_clicks = 0
                    )
                ],
                label = overlay_names[-1]
            )
        )

        return [line_color_tabs]

    def export_layers(self, button_click, current_layers,slide_information):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        # Scaling annotations:
        current_layers = json.loads(get_pattern_matching_value(current_layers))
        scaled_layers = []
        for c in current_layers:
            scaled_layer = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),c)
            scaled_layers.append(scaled_layer)
        
        string_layers = json.dumps(scaled_layers)
        
        return [{'content': string_layers,'filename': 'fusion-tools-current-layers.json'}]

class PropertyViewer(Tool):
    """PropertyViewer Tool which allows users to view distribution of properties across the current viewport of the SlideMap

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data
    :type Tool: None
    """
    def __init__(self,
                 ignore_list: list = [],
                 property_depth: int = 6
                 ):
        """Constructor method

        :param ignore_list: List of properties not to make available to this component., defaults to []
        :type ignore_list: list, optional
        :param property_depth: Depth at which to search for nested properties. Properties nested further than this value will be ignored.
        :type property_depth: int, optional
        """
        
        super().__init__()
        self.ignore_list = ignore_list
        self.property_depth = property_depth   

    def __str__(self):
        return 'Property Viewer'

    def load(self, component_prefix: int):

        self.component_prefix = component_prefix

        self.title = 'Property Viewer'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()   

    def gen_layout(self, session_data:dict):
        """Generating layout for PropertyViewer Tool

        :return: Layout added to DashBlueprint() object to be embedded in larger layout
        :rtype: dash.html.Div.Div
        """
        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Property Viewer')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Pan around on the slide to view select properties across regions of interest'
                    ),
                    html.Hr(),
                    html.Div(
                        dmc.Switch(
                            id = {'type':'property-viewer-update','index': 0},
                            size = 'lg',
                            onLabel = 'ON',
                            offLabel = 'OFF',
                            checked = True,
                            label = 'Update Property Viewer',
                            description = 'Select whether or not to update values when panning around in the image'
                        )
                    ),
                    html.Hr(),
                    html.Div(
                        id = {'type': 'property-viewer-parent','index': 0},
                        children = [
                            'Move around to initialize property viewer.'
                        ]
                    ),
                    html.Div(
                        dcc.Store(
                            id = {'type': 'property-viewer-available-properties','index': 0},
                            storage_type='memory',
                            data = json.dumps({})
                        )
                    ),
                    html.Div(
                        dcc.Store(
                            id = {'type': 'property-viewer-property-info','index': 0},
                            storage_type = 'memory',
                            data = json.dumps({})
                        )
                    ),
                    html.Div(
                        dcc.Store(
                            id = {'type':'property-viewer-data','index':0},
                            storage_type='memory',
                            data = json.dumps({})
                        )
                    )
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow':'scroll'})

        self.blueprint.layout = layout

    def get_callbacks(self):
        """Initializing callbacks for PropertyViewer Tool
        """

        # Updating for a new slide:
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-info-store','index': ALL},'data')
            ],
            [
                Output({'type': 'property-viewer-available-properties','index': ALL},'data'),
                Output({'type': 'property-viewer-property-info','index': ALL},'data'),
                Output({'type': 'property-viewer-parent','index':ALL},'children'),
                Output({'type': 'property-viewer-data','index': ALL},'data')
            ]
        )(self.update_slide)

        # Updating when panning in SlideMap-like object
        self.blueprint.callback(
            [
                Input({'type': 'slide-map','index': ALL},'bounds'),
                Input({'type': 'property-view-type','index': ALL},'value'),
                Input({'type': 'property-view-subtype','index': ALL},'value'),
                Input({'type': 'property-view-butt','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'property-viewer-parent','index': ALL},'children'),
                Output({'type': 'property-viewer-data','index': ALL},'data')
            ],
            [
                State({'type': 'vis-layout-tabs','index': ALL},'active_tab'),
                State({'type': 'property-viewer-data','index': ALL},'data'),
                State({'type': 'property-viewer-update','index': ALL},'checked'),
                State({'type':'property-view-subtype-parent','index':ALL},'children'),
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'property-viewer-available-properties','index': ALL},'data')
            ]
        )(self.update_property_viewer)

    def update_slide(self, new_annotations_info: list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        new_annotations_info = json.loads(get_pattern_matching_value(new_annotations_info))
        new_available_properties = new_annotations_info['available_properties']
        new_property_info = new_annotations_info['property_info']

        new_available_properties = json.dumps(new_available_properties)
        new_property_info = json.dumps(new_property_info)
        new_property_viewer_children = []
        new_property_viewer_info = json.dumps({})

        return [new_available_properties], [new_property_info], [new_property_viewer_children], [new_property_viewer_info]

    def update_property_viewer(self,slide_map_bounds, view_type_value, view_subtype_value, view_butt_click, active_tab, current_property_data, update_viewer, current_subtype_children, current_geojson, available_properties):
        """Updating visualization of properties within the current viewport


        :param slide_map_bounds: Current viewport boundaries
        :type slide_map_bounds: list
        :param view_type_value: Property to view across each GeoJSON object
        :type view_type_value: list
        :param view_subtype_value: If a subtype is available for the view type, what it's value is. This is present for nested (dictionary) properties.
        :type view_subtype_value: list
        :param view_butt_click: Whether the callback is triggered by update plot button
        :type view_butt_click: list
        :param active_tab: Which tool tab is currently in view. Prevents update if the current tab isn't "property-viewer"
        :type active_tab: list
        :param current_property_data: Data used in current set of plots
        :type current_property_data: list
        :param update_viewer: Switch value for whether or not to update the plots based on panning around in the SlideMap
        :type update_viewer: list
        :param current_subtype_children: Parent container of all sub-type dropdown divs.
        :type current_subtype_children: list
        :param current_geojson: Current set of GeoJSON features and their properties
        :type current_geojson: list
        :raises exceptions.PreventUpdate: Stop callback execution
        :return: List of PropertyViewer tabs (separated by structure) and data used in plots
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        update_viewer = get_pattern_matching_value(update_viewer)
        active_tab = get_pattern_matching_value(active_tab)

        if not active_tab is None:
            if not active_tab=='property-viewer':
                raise exceptions.PreventUpdate
        else:
            raise exceptions.PreventUpdate
        
        slide_map_bounds = get_pattern_matching_value(slide_map_bounds)
        view_type_value = get_pattern_matching_value(view_type_value)
        current_property_data = json.loads(get_pattern_matching_value(current_property_data))
        current_subtype_children = get_pattern_matching_value(current_subtype_children)

        current_geojson = json.loads(get_pattern_matching_value(current_geojson))
        current_available_properties = json.loads(get_pattern_matching_value(available_properties))

        if 'slide-map' in ctx.triggered_id['type']:
            # Only update the region info when this is checked
            if update_viewer:
                current_property_data['bounds'] = slide_map_bounds

        elif 'property-view-type' in ctx.triggered_id['type']:
            view_subtype_value = []

        current_property_data['update_view'] = update_viewer
        current_property_data['property'] = view_type_value
        current_property_data['sub_property'] = view_subtype_value
        plot_components = self.generate_plot_tabs(current_property_data, current_geojson)

        # Checking if a selected property has sub-properties
        main_properties = list(set([i if not '-->' in i else i.split(' --> ')[0] for i in current_available_properties]))

        if any([i in ctx.triggered_id['type'] for i in ['property-view-type','property-view-subtype']]):
            # Making new subtype children to correspond to new property selection
            sub_dropdowns = []
            if 'property-view-type' in ctx.triggered_id['type']:
                if not view_type_value is None:
                    child_properties = [i for i in current_available_properties if i.split(' --> ')[0]==view_type_value]
                    n_levels = max(list(set([len(i.split(' --> ')) for i in child_properties])))

                    if n_levels>0:
                        for i in range(1,n_levels):
                            if i==1:
                                sub_drop = []
                                for j in child_properties:
                                    if len(j.split(' --> '))>i and not j.split(' --> ')[i] in sub_drop:
                                        sub_drop.append(j.split(' --> ')[i])

                                if i==n_levels-1:
                                    sub_drop = ['All'] + sub_drop

                                sub_dropdowns.append(
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Label(f'Sub-Property: {i}: ',html_for = {'type': f'{self.component_prefix}-property-view-subtype','index': i-1})
                                        ],md = 4),
                                        dbc.Col([
                                            dcc.Dropdown(
                                                options = sub_drop,
                                                value = [],
                                                multi = False,
                                                id = {'type': f'{self.component_prefix}-property-view-subtype','index': i-1},
                                                placeholder = f'Sub-Property: {i}',
                                                disabled = False
                                            )
                                        ])
                                    ])
                                )

                            else:

                                sub_dropdowns.append(
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Label(f'Sub-Property: {i}: ',html_for={'type': f'{self.component_prefix}-property-view-subtype','index': i-1})
                                        ],md = 4),
                                        dbc.Col([
                                            dcc.Dropdown(
                                                options = [],
                                                value = [],
                                                multi = False,
                                                id = {'type': f'{self.component_prefix}-property-view-subtype','index': i-1},
                                                placeholder = f'Sub-Property: {i}',
                                                disabled = True
                                            )
                                        ],md = 8)
                                    ])
                                )


            elif 'property-view-subtype' in ctx.triggered_id['type']:
                if not view_type_value is None:
                    child_properties = [i for i in current_available_properties if i.split(' --> ')[0]==view_type_value]
                    n_levels = max(list(set([len(i.split(' --> ')) for i in child_properties])))

                    view_subtype_value = [view_subtype_value[i] if i <= ctx.triggered_id['index'] else [] for i in range(len(view_subtype_value))]
                    prev_value = view_type_value
                    for sub_idx, sub in enumerate(view_subtype_value):
                        if type(sub)==str:
                            new_options = list(set([i.split(' --> ')[sub_idx+1] for i in child_properties if len(i.split(' --> '))>(sub_idx+1) and i.split(' --> ')[sub_idx]==prev_value]))

                            if sub_idx+1==n_levels-1:
                                new_options = ['All']+new_options

                            sub_dropdowns.append(
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label(f'Sub-Property: {sub_idx+1}: ',html_for = {f'{self.component_prefix}-type': 'property-view-subtype','index': sub_idx})
                                    ],md = 4),
                                    dbc.Col([
                                        dcc.Dropdown(
                                            options = new_options,
                                            value = view_subtype_value[sub_idx],
                                            placeholder = f'Sub-Property: {sub_idx+1}',
                                            disabled = False,
                                            id = {'type': f'{self.component_prefix}-property-view-subtype','index': sub_idx}
                                        )
                                    ])
                                ])
                            )

                            prev_value = sub
                        else:
                            if sub_idx<=ctx.triggered_id['index']+1:
                                new_options = list(set([i.split(' --> ')[sub_idx+1] for i in child_properties if len(i.split(' --> '))>(sub_idx+1) and i.split(' --> ')[sub_idx]==prev_value]))

                                if sub_idx+1==n_levels-1:
                                    new_options = ['All'] + new_options
                                
                                sub_dropdowns.append(
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Label(f'Sub-Property: {sub_idx+1}: ',html_for = {'type': f'{self.component_prefix}-property-view-subtype','index': sub_idx})
                                        ],md = 4),
                                        dbc.Col([
                                            dcc.Dropdown(
                                                options = new_options,
                                                value = view_subtype_value[sub_idx],
                                                placeholder = f'Sub-Property: {sub_idx+1}',
                                                disabled = False,
                                                id = {'type': f'{self.component_prefix}-property-view-subtype','index': sub_idx}
                                            )
                                        ])
                                    ])
                                )
                            else:
                                sub_dropdowns.append(
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Label(f'Sub-Property: {sub_idx+1}: ',html_for = {'type': f'{self.component_prefix}-property-view-subtype','index': sub_idx})
                                        ],md = 4),
                                        dbc.Col([
                                            dcc.Dropdown(
                                                options = [],
                                                value = [],
                                                placeholder = f'Sub-Property: {sub_idx+1}',
                                                disabled = True,
                                                id = {'type': f'{self.component_prefix}-property-view-subtype','index': sub_idx}
                                            )
                                        ])
                                    ])
                                )

            current_subtype_children = html.Div(sub_dropdowns)

        return_div = html.Div([
            dbc.Row([
                dbc.Col(
                    dbc.Label('Select a Property: ',html_for = {'type': f'{self.component_prefix}-property-view-type','index': 0}),
                    md = 3
                ),
                dbc.Col(
                    dcc.Dropdown(
                        options = main_properties,
                        value = view_type_value if not view_type_value is None else [],
                        placeholder = 'Property',
                        multi = False,
                        id = {'type': f'{self.component_prefix}-property-view-type','index': 0}
                    )
                )
            ]),
            dbc.Row([
                dbc.Col(
                    html.Div(
                        id = {'type': f'{self.component_prefix}-property-view-subtype-parent','index': 0},
                        children = [
                            current_subtype_children
                        ] if not type(current_subtype_children)==list else current_subtype_children
                    )
                )
            ]),
            html.Hr(),
            dbc.Row([
                plot_components
            ],style = {'maxHeight': '100vh','width': '100%'})
        ])

        updated_view_data = json.dumps(current_property_data)

        return [return_div], [updated_view_data]

    def generate_plot_tabs(self, current_property_data, current_features):
        """Generating tabs for each structure containing plot of selected value.

        :param current_property_data: Data stored for current viewport and property value selection
        :type current_property_data: dict
        :param current_features: Current GeoJSON features
        :type current_features: list
        :return: Tabs object containing a tab for each structure with a plot of the selected property value
        :rtype: dbc.Tabs
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        if len(current_features)==0:
            raise exceptions.PreventUpdate

        current_bounds_bounds = current_property_data['bounds']
        current_bounds_box = box(current_bounds_bounds[0][1],current_bounds_bounds[0][0],current_bounds_bounds[1][1],current_bounds_bounds[1][0])

        plot_tabs_children = []
        for g_idx, g in enumerate(current_features):
            
            if current_property_data['update_view']:
                intersecting_shapes,intersecting_properties = find_intersecting(g,current_bounds_box)
                current_property_data[g['properties']['_id']] = {
                    "geometry": intersecting_shapes,
                    "properties": intersecting_properties.to_dict('records')
                }
            else:
                if g['properties']['_id'] in current_property_data:
                    intersecting_properties = pd.DataFrame.from_records(current_property_data[g['properties']['_id']]['properties'])
                    intersecting_shapes = current_property_data[g['properties']['_id']]['geometry']
                else:
                    intersecting_properties = pd.DataFrame()
                    intersecting_shapes = {}
            
            g_count = len(intersecting_shapes['features'])
            if not current_property_data['property'] is None:
                if current_property_data['property'] in intersecting_properties:
                    if any([i in str(intersecting_properties[current_property_data['property']].dtype) for i in ["int","float"]]):
                        # This generates a histogram (all quantitative feature)
                        g_plot = html.Div(
                            dcc.Graph(
                                figure = px.histogram(
                                    data_frame = intersecting_properties,
                                    x = current_property_data['property'],
                                    title = f'Histogram of {current_property_data["property"]} in {g["properties"]["name"]}'
                                )
                            ),
                            style = {'width': '100%'}
                        )
                    elif intersecting_properties[current_property_data['property']].dtype == 'object':
                        column_type = list(set([type(i) for i in intersecting_properties[current_property_data['property']].tolist()]))

                        if len(column_type)==1:
                            if column_type[0]==str:
                                g_plot = html.Div(
                                    dcc.Graph(
                                        figure = px.histogram(
                                            data_frame = intersecting_properties,
                                            x = current_property_data['property'],
                                            title = f'Histogram of {current_property_data["property"]} in {g["properties"]["name"]}'
                                        )
                                    ),
                                    style = {'width': '100%'}
                                )
                            elif column_type[0]==dict:
                                sub_property_df = pd.DataFrame.from_records(intersecting_properties[current_property_data['property']].tolist()) 
                                if 'sub_property' in current_property_data and not sub_property_df.empty:
                                    if len(current_property_data['sub_property'])==1:
                                        if not current_property_data['sub_property']==['All']:
                                            if current_property_data['sub_property'][0] in sub_property_df:
                                                g_plot = html.Div(
                                                        dcc.Graph(
                                                            figure = go.Figure(
                                                                px.histogram(
                                                                    data_frame = sub_property_df,
                                                                    x = current_property_data['sub_property'][0],
                                                                    title = f'Histogram of {current_property_data["sub_property"][0]} in {g["properties"]["name"]}'
                                                                )
                                                            )
                                                        ),
                                                        style = {'width': '100%'}
                                                    )
                                            else:
                                                g_plot = f'{current_property_data["sub_property"]} is not in {current_property_data["property"]}'
                                        else:
                                            # Making the pie chart data
                                            column_dtypes = [str(i) for i in sub_property_df.dtypes]
                                            if all([any([i in j for i in ['int','float']]) for j in column_dtypes]):
                                                # This would be all numeric
                                                pie_chart_data = sub_property_df.sum(axis=0).to_dict()
                                            else:
                                                # This would have some un-numeric
                                                pie_chart_data = sub_property_df.value_counts().to_dict()

                                            pie_chart_list = []
                                            for key,val in pie_chart_data.items():
                                                pie_chart_list.append({
                                                    'Label': key, 'Total': val
                                                })
                                                                                        
                                            g_plot = html.Div(
                                                dcc.Graph(
                                                    figure = go.Figure(
                                                        px.pie(
                                                            data_frame = pd.DataFrame.from_records(pie_chart_list),
                                                            values = 'Total',
                                                            names = 'Label'
                                                        )
                                                    )
                                                )
                                            )

                                    elif len(current_property_data['sub_property'])>1:
                                        for sp in current_property_data['sub_property'][:-1]:

                                            if type(sp)==str and not sub_property_df.empty:
                                                if sp in sub_property_df:
                                                    sub_property_df = pd.DataFrame.from_records([i for i in sub_property_df[sp].tolist() if type(i)==dict])                                               
                                                
                                                elif sp=='All':
                                                    continue
                                                
                                                else:
                                                    sub_property_df = pd.DataFrame()
                                            else:
                                                sub_property_df = pd.DataFrame()

                                        if not sub_property_df.empty:
                                            if not current_property_data['sub_property'][-1]=='All':
                                                if type(current_property_data['sub_property'][-1])==str:
                                                    if current_property_data['sub_property'][-1] in sub_property_df:
                                                        g_plot = html.Div(
                                                                dcc.Graph(
                                                                    figure = go.Figure(
                                                                        px.histogram(
                                                                            data_frame = sub_property_df,
                                                                            x = current_property_data['sub_property'][-1],
                                                                            title = f'Histogram of {current_property_data["sub_property"]} in {g["properties"]["name"]}'
                                                                        )
                                                                    )
                                                                ),
                                                                style = {'width': '100%'}
                                                            )
                                                    else:
                                                        g_plot = f'{current_property_data["sub_property"]} is not in {current_property_data["property"]}'
                                                else:
                                                    g_plot = f'Select a sub-property within {current_property_data["sub_property"][-2]}'
                                            else:
                                                # Making the pie chart data
                                                column_dtypes = [str(i) for i in sub_property_df.dtypes]
                                                if all([any([i in j for i in ['int','float']]) for j in column_dtypes]):
                                                    # This would be all numeric
                                                    pie_chart_data = sub_property_df.sum(axis=0).to_dict()
                                                else:
                                                    # This would have some un-numeric
                                                    pie_chart_data = sub_property_df.value_counts().to_dict()

                                                pie_chart_list = []
                                                for key,val in pie_chart_data.items():
                                                    pie_chart_list.append({
                                                        'Label': key, 'Total': val
                                                    })
                                                
                                                g_plot = html.Div(
                                                    dcc.Graph(
                                                        figure = go.Figure(
                                                            px.pie(
                                                                data_frame = pd.DataFrame.from_records(pie_chart_list),
                                                                values = 'Total',
                                                                names = 'Label'
                                                            )
                                                        )
                                                    ),
                                                    style = {'width': '100%'}
                                                )
                                        
                                        else:
                                            g_plot = f'{current_property_data["sub_property"]} is not in {current_property_data["property"]}'

                                    else:
                                        g_plot = f'Select a sub-property within {current_property_data["property"]}'

                                else:
                                    g_plot = f'Select a sub-property within {current_property_data["property"]}'

                            else:
                                g_plot = f'Not implemented for type: {column_type}'

                        elif len(column_type)>1:
                            g_plot = f'Uh oh! Mixed dtypes: {column_type}'

                        else:
                            g_plot = f'Uh oh! column type: {column_type}'
                    else:
                        g_plot = f'Uh oh! column dtype is: {intersecting_properties[current_property_data["property"]].dtype}'
                else:
                    g_plot = f'Uh oh! {current_property_data["property"]} is not in {g["properties"]["name"]} with id: {g["properties"]["_id"]}'
            else:
                g_plot = 'Select a property to view'

            plot_tabs_children.append(
                dbc.Tab(
                    g_plot,
                    tab_id = g['properties']['_id'],
                    label = f"{g['properties']['name']} ({g_count})"
                )
            )

        plot_tabs = dbc.Tabs(
            plot_tabs_children,
            active_tab = current_features[0]['properties']['_id'],
            id = {'type': f'{self.component_prefix}-property-viewer-tabs','index': 0}
        )

        return plot_tabs

class PropertyPlotter(Tool):
    """PropertyPlotter Tool which enables more detailed selection of properties across the entire tissue. 
    Allows for generation of violin plots, scatter plots, and UMAP plots.

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self,
                 ignore_list: list = [],
                 property_depth: int = 6
                 ):
        """Constructor method

        :param geojson_list: Individual or list of GeoJSON formatted annotations
        :type geojson_list: Union[dict,list]
        :param reference_object: Path to external reference object containing information on each GeoJSON feature, defaults to None
        :type reference_object: Union[str,None], optional
        :param ignore_list: List of properties to not include in this component, defaults to []
        :type ignore_list: list, optional
        :param property_depth: Depth at which to search for nested properties. Properties nested further than this will be ignored.
        :type property_depth: int, optional
        """
        
        super().__init__()
        self.ignore_list = ignore_list
        self.property_depth = property_depth

    def __str__(self):
        return 'Property Plotter'

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Property Plotter'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )        
        
        self.get_callbacks()

    def get_namespace(self):
        """Adding JavaScript functions to the PropertyPlotter Namespace
        """
        # Same kind of marker-related functions as in BulkLabels
        self.js_namespace = Namespace(
            "fusionTools","propertyPlotter"
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
            src='function(feature,layer,ctx){layer.bindTooltip("Double-click to remove")}'
        )

        self.js_namespace.add(
            name = "markerRender",
            src = """
                function(feature,latlng,context) {
                    marker = L.marker(latlng, {
                        title: "PropertyPlotter Marker",
                        alt: "PropertyPlotter Marker",
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

    def generate_property_dict(self, available_properties, title: str = 'Features'):
        all_properties = {
            'title': title,
            'key': '0',
            'children': []
        }

        def add_prop_level(level_children, prop, index_list):
            new_keys = {}
            if len(level_children)==0:
                if not prop[0] in self.ignore_list:
                    new_key = f'{"-".join(index_list)}-0'
                    p_dict = {
                        'title': prop[0],
                        'key': new_key,
                        'children': []
                    }
                    l_dict = p_dict['children']
                    if len(prop)==1:
                        new_keys[new_key] = prop[0]
                    for p_idx,p in enumerate(prop[1:]):
                        if not p in self.ignore_list:
                            new_key = f'{"-".join(index_list+["0"]*(p_idx+2))}'
                            l_dict.append({
                                'title': p,
                                'key': new_key,
                                'children': []
                            })
                            l_dict = l_dict[0]['children']

                            new_keys[new_key] = ' --> '.join(prop[:p_idx+2])

                    level_children.append(p_dict)
            else:
                for p_idx,p in enumerate(prop):
                    if not p in self.ignore_list:
                        if any([p==i['title'] for i in level_children]):
                            title_idx = [i['title'] for i in level_children].index(p)
                            level_children = level_children[title_idx]['children']
                            index_list.append(str(title_idx))
                        else:
                            new_key = f'{"-".join(index_list)}-{len(level_children)}'
                            other_children = len(level_children)
                            level_children.append({
                                'title': p,
                                'key': new_key,
                                'children': []
                            })
                            level_children = level_children[-1]['children']
                            index_list.append(str(other_children))
                            if p_idx==len(prop)-1:
                                new_keys[new_key] = ' --> '.join(prop[:p_idx+1])
            
            return new_keys
        
        list_levels = [i.split(' --> ') if '-->' in i else [i] for i in available_properties]
        unique_levels = list(set([len(i) for i in list_levels]))
        sorted_level_idxes = np.argsort(unique_levels)[::-1]
        property_keys = {}
        for s in sorted_level_idxes:
            depth_count = unique_levels[s]
            props_with_level = [i for i in list_levels if len(i)==depth_count]
            for p in props_with_level:
                feature_children = all_properties['children']
                property_keys = property_keys | add_prop_level(feature_children,p,['0'])


        return all_properties, property_keys

    def get_callbacks(self):
        """Initializing callbacks for PropertyPlotter Tool
        """
        
        # Updating for a new slide:
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-info-store','index':ALL},'data')
            ],
            [
                Output({'type': 'property-list','index': ALL},'data'),
                Output({'type': 'label-list','index': ALL},'options'),
                Output({'type': 'property-graph','index': ALL},'figure'),
                Output({'type': 'property-graph-tabs-div','index': ALL},'children'),
                Output({'type': 'property-plotter-keys','index': ALL},'data')
            ]
        )(self.update_slide)

        # Updating plot based on selected properties and labels
        self.blueprint.callback(
            [
                Input({'type':'property-plotter-butt','index':ALL},'n_clicks')
            ],
            [
                Output({'type': 'property-graph','index': ALL},'figure'),
                Output({'type': 'property-graph-tabs-div','index': ALL},'children'),
                Output({'type': 'property-plotter-store','index': ALL},'data')
            ],
            [
                State({'type': 'property-list','index': ALL},'checked'),
                State({'type': 'label-list','index': ALL},'value'),
                State({'type': 'property-plotter-keys','index':ALL},'data'),
                State({'type': 'map-annotations-store','index':ALL},'data'),
                State({'type': 'property-plotter-store','index': ALL},'data')
            ]
        )(self.update_property_graph)
        
        # Updating selected data info after circling points in plot
        self.blueprint.callback(
            [
                Input({'type': 'property-graph','index': ALL},'selectedData')
            ],
            [
                Output({'type': 'property-graph-selected-div','index': ALL},'children'),
                Output({'type': 'map-marker-div','index': ALL},'children'),
                Output({'type': 'property-plotter-store','index':ALL},'data')
            ],
            [
                State({'type': 'property-plotter-store','index': ALL},'data'),
                State({'type':'label-list','index': ALL},'options')
            ]
        )(self.select_data_from_plot)

        # Clearing markers
        self.blueprint.callback(
            [
                Input({'type':'selected-marker-delete','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'map-marker-div','index': ALL},'children'),
                Output({'type': 'property-plotter-store','index': ALL},'data'),
                Output({'type': 'property-graph-selected-div','index': ALL},'children')
            ],
            [
                State({'type': 'property-plotter-store','index': ALL},'data'),
                State({'type': 'label-list','index':ALL},'options')
            ]
        )(self.remove_marker_label)

        # Updating sub-plot
        self.blueprint.callback(
            [
                Input({'type': 'selected-sub-butt','index': ALL},'n_clicks'),
                Input({'type': 'selected-sub-markers','index': ALL},'n_clicks')
            ],
            [
                Output({'type':'selected-sub-div','index': ALL},'children')
            ],
            [
                State({'type': 'selected-sub-drop','index': ALL},'value'),
                State({'type': 'property-plotter-store','index': ALL},'data'),
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'label-list','index': ALL},'value')
            ]
        )(self.update_sub_div)

        # Selecting points in selected data:
        self.blueprint.callback(
            [
                Input({'type': 'property-sub-graph','index': ALL},'selectedData')
            ],
            [
                Output({'type': 'map-marker-div','index': ALL},'children')
            ]
        )(self.sub_select_data)

    def update_slide(self, new_annotations_info:list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        new_annotations_info = json.loads(get_pattern_matching_value(new_annotations_info))
        new_available_properties = new_annotations_info['available_properties']

        new_property_dict, new_property_keys = self.generate_property_dict(new_available_properties)
        new_figure = go.Figure()
        new_graph_tabs_children = []
        new_property_keys = json.dumps(new_property_keys)

        return [new_property_dict], [new_available_properties], [new_figure], [new_graph_tabs_children], [new_property_keys]
        
    def gen_layout(self, session_data:dict):
        """Generating layout for PropertyPlotter Tool

        :return: Layout for PropertyPlotter DashBlueprint object to be embedded in larger layouts
        :rtype: dash.html.Div.Div
        """
        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        html.H3('Property Plotter')
                    ]),
                    html.Hr(),
                    dbc.Row(
                        'Select one or a combination of properties to generate a plot.'
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Label('Select properties below: ',html_for = {'type':'property-list-card','index': 0})
                    ),
                    html.Div(
                        dcc.Store(
                            id = {'type': 'property-plotter-store','index': 0},
                            data = json.dumps({}),
                            storage_type = 'memory'
                        )
                    ),
                    html.Div(
                        dcc.Store(
                            id = {'type':'property-plotter-keys','index': 0},
                            data = json.dumps({}),
                            storage_type = 'memory'
                        )
                    ),
                    dbc.Row(
                        dbc.Card(
                            id = {'type': 'property-list-card','index': 0},
                            children = [
                                html.Div(
                                    id = {'type': 'property-list-div','index': 0},
                                    children = [
                                        dta.TreeView(
                                            id = {'type': 'property-list','index': 0},
                                            multiple = True,
                                            checkable = True,
                                            checked = [],
                                            selected = [],
                                            expanded = [],
                                            data = {}
                                        )
                                    ],
                                    style = {'maxHeight': '250px','overflow':'scroll'}
                                )
                            ]
                        )
                    ),
                    dbc.Row(
                        children = [
                            dbc.Label('Label for points: ',html_for = {'type':'label-list','index': 0}),
                            dcc.Dropdown(
                                id = {'type': 'label-list','index': 0},
                                placeholder = 'Select a label',
                                multi = False,
                                options = []
                            )
                        ]
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Button(
                            'Generate Plot!',
                            id = {'type': 'property-plotter-butt','index': 0},
                            n_clicks = 0,
                            className = 'd-grid col-12 mx-auto'
                        )
                    ),
                    dbc.Row([
                        html.Div(
                            dcc.Loading(
                                dcc.Graph(
                                    id = {'type': 'property-graph','index': 0},
                                    figure = go.Figure()
                                )
                            ),
                            style = {'width': '100%'}
                        )
                    ]),
                    html.Hr(),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'property-graph-tabs-div','index': 0},
                            children = []
                        )
                    ])
                ])
            ])
        ],style={'maxHeight': '100vh','overflow':'scroll'})

        self.blueprint.layout = layout

    def update_property_graph(self, plot_butt_click, property_list, label_list, property_keys, current_features, current_plot_data):
        """Updating plot based on selected properties, label(s)

        :param plot_butt_click: Whether this callback is triggered by the plot button being clicked
        :type plot_butt_click: list
        :param property_list: List of properties to incorporate in the generated plot
        :type property_list: list
        :param label_list: List of properties to use as labels in the generated plot
        :type label_list: list
        :param current_features: Current set of GeoJSON features 
        :type current_features: list
        :param current_plot_data: Data present in the current plot.
        :type current_plot_data: list
        :raises exceptions.PreventUpdate: Stop callback execution because no properties are selected
        :raises exceptions.PreventUpdate: Stop callback execution because no properties are selected
        :return: Generated plot figure and new plot data
        :rtype: tuple
        """
        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))

        property_list = get_pattern_matching_value(property_list)
        label_names = get_pattern_matching_value(label_list)
        
        current_features = json.loads(get_pattern_matching_value(current_features))
        property_keys = json.loads(get_pattern_matching_value(property_keys))

        # Don't do anything if not given properties
        if property_list is None:
            raise exceptions.PreventUpdate
        elif type(property_list)==list:
            if len(property_list)==0:
                raise exceptions.PreventUpdate

        property_names = [property_keys[i] for i in property_list if i in property_keys]
            
        extracted_data = self.extract_data_from_features(current_features, property_names, label_names)
        current_plot_data['data'] = extracted_data

        data_df = pd.DataFrame.from_records(extracted_data).dropna(subset=property_names,how = 'all')
        data_df.reset_index(inplace=True,drop=True)
        if len(property_names)==1:
            # Single feature visualization
            plot_figure = self.gen_violin_plot(
                data_df = data_df,
                label_col = label_names,
                property_column = property_names[0],
                customdata_columns=['bbox','point_info']
            )

        elif len(property_names)>1:
            # Multi-feature visualization
            if len(property_names)>2:
                umap_cols = self.gen_umap_cols(
                    data_df = data_df,
                    property_columns = property_names
                )

                before_cols = data_df.columns.tolist()
                plot_cols = umap_cols.columns.tolist()

                data_df = pd.concat([data_df,umap_cols],axis=1,ignore_index=True).fillna(0)
                data_df.columns = before_cols + plot_cols

            elif len(property_names)==2:
                plot_cols = property_names

            plot_figure = self.gen_scatter_plot(
                data_df = data_df,
                plot_cols = plot_cols,
                label_col = label_names,
                customdata_cols = ['bbox','point_info']
            )

        current_plot_data = json.dumps(current_plot_data)

        property_graph_tabs_div = self.make_property_plot_tabs(data_df,label_names,property_names,['bbox','point_info'])

        return [plot_figure], [property_graph_tabs_div], [current_plot_data]

    def extract_property(self, feature: dict, properties:list, labels:list)->dict:
        """Extracting list of properties and labels from a single feature in a GeoJSON FeatureCollection

        :param feature: One Feature in GeoJSON FeatureCollection
        :type feature: dict
        :param properties: List of property names to extract
        :type properties: list
        :param labels: List of properties used as labels to extract
        :type labels: list
        :return: Dictionary of properties and labels for a single Feature
        :rtype: dict
        """

        f_dict = {}
        for p in properties:
            if '-->' not in p:
                if p in feature['properties']:
                    if not type(feature['properties'][p])==dict:
                        try:
                            f_dict[p] = float(feature['properties'][p])
                        except ValueError:
                            f_dict[p] = feature['properties'][p]
            else:
                split_p = p.split(' --> ')
                f_props = feature['properties'].copy()
                for sp in split_p:
                    if not f_props is None and not type(f_props)==float:
                        if sp in f_props:
                            f_props = f_props[sp]
                        else:
                            f_props = None
                    else:
                        f_props = None

                if not type(f_props)==dict and not f_props is None:
                    try:
                        f_dict[p] = float(f_props)
                    except ValueError:
                        f_dict[p] = f_props

        if not labels is None:
            if type(labels)==list:
                for l in labels:
                    if not '-->' in l:
                        if l in feature['properties']:
                            f_dict[l] = feature['properties'][l]
                    else:
                        l_parts = l.split(' --> ')
                        f_props_copy = feature['properties'].copy()
                        for l in l_parts:
                            if l in f_props_copy:
                                f_props_copy = f_props_copy[l]
                            else:
                                f_props_copy = 0
                                break    
                        
                        try:
                            f_dict[l] = float(f_props_copy)
                        except ValueError:
                            f_dict[l] = f_props_copy


            elif type(labels)==str:
                if not '-->' in labels:
                    if labels in feature['properties']:
                        try:
                            f_dict[labels] = float(feature['properties'][labels])
                        except ValueError:
                            f_dict[labels] = feature['properties'][labels]
                else:
                    l_parts = labels.split(' --> ')
                    f_props_copy = feature['properties'].copy()
                    for l in l_parts:
                        if l in f_props_copy:
                            f_props_copy = f_props_copy[l]
                        else:
                            f_props_copy = 0
                            break
                    try:
                        f_dict[labels] = float(f_props_copy)
                    except ValueError:
                        f_dict[labels] = f_props_copy

        # Getting bounding box info
        f_bbox = list(shape(feature['geometry']).bounds)
        f_dict['bbox'] = f_bbox

        return f_dict

    def extract_data_from_features(self, geo_list:list, properties:list, labels:list, filter_list: Union[list,None] = None)->list:
        """Iterate through properties and extract data based on selection


        :param geo_list: List of current GeoJSON features 
        :type geo_list: list
        :param properties: List of properties to use in the current plot
        :type properties: list
        :param labels: List of labels to use in the current plot (should just be one element)
        :type labels: list
        :param filter_list: List of dictionaries containing g_idx and f_idx corresponding to the layers and features to extract data from
        :param filter_list: Union[list,None], optional
        :return: Extracted data to use for the plot
        :rtype: list
        """
        extract_data = []
        if filter_list is None:
            for g_idx, g in enumerate(geo_list):
                for f_idx, f in enumerate(g['features']):
                    
                    f_dict = self.extract_property(f, properties, labels)
                    f_dict['point_info'] = {'g_idx': g_idx, 'f_idx': f_idx}

                    extract_data.append(f_dict)

        else:
            unique_gs = list(set([i['g_idx'] for i in filter_list]))
            fs_for_gs = [[i['f_idx'] for i in filter_list if i['g_idx']==g] for g in unique_gs]

            for f_list,g in zip(fs_for_gs,unique_gs):
                for f in f_list:

                    f_dict = self.extract_property(geo_list[g]['features'][f], properties, labels)
                    f_dict['point_info'] = {'g_idx': g, 'f_idx': f}

                    extract_data.append(f_dict)

        return extract_data

    def gen_violin_plot(self, data_df:pd.DataFrame, label_col: Union[str,None], property_column: str, customdata_columns:list):
        """Generating a violin plot using provided data, property columns, and customdata


        :param data_df: Extracted data from current GeoJSON features
        :type data_df: pd.DataFrame
        :param label_col: Name of column to use for label
        :type label_col: Union[str,None]
        :param property_column: Name of column to use for property (y-axis) value
        :type property_column: str
        :param customdata_columns: Names of columns to use for customdata (accessible from clickData and selectedData)
        :type customdata_columns: list
        :return: Figure containing violin plot data
        :rtype: go.Figure
        """
        figure = go.Figure(
            data = go.Violin(
                x = None if label_col is None else data_df[label_col],
                y = data_df[property_column],
                customdata = data_df[customdata_columns] if not customdata_columns is None else None,
                points = 'all',
                pointpos=0,
                spanmode='hard'
            )
        )
        
        figure.update_layout(
            legend = dict(
                orientation='h',
                y = 0,
                yanchor='top',
                xanchor='left'
            ),
            title = '<br>'.join(
                textwrap.wrap(
                    f'{property_column}',
                    width=80
                )
            ),
            yaxis_title = dict(
                text = '<br>'.join(
                    textwrap.wrap(
                        f'{property_column}',
                        width=80
                    )
                ),
                font = dict(size = 10)
            ),
            xaxis_title = dict(
                text = '<br>'.join(
                    textwrap.wrap(
                        label_col,
                        width=80
                    )
                ) if not label_col is None else 'Group',
                font = dict(size = 10)
            ),
            margin = {'r':0,'b':25}
        )

        return figure

    def gen_scatter_plot(self, data_df:pd.DataFrame, plot_cols:list, label_col:Union[str,None], customdata_cols:list):
        """Generating a 2D scatter plot using provided data


        :param data_df: Extracted data from current GeoJSON features
        :type data_df: pd.DataFrame
        :param plot_cols: Names of columns containing properties for the scatter plot
        :type plot_cols: list
        :param label_cols: Name of column to use to label markers.
        :type label_cols: Union[str,None]
        :param customdata_cols: Names of columns to use for customdata on plot
        :type customdata_cols: list
        :return: Scatter plot figure
        :rtype: go.Figure
        """
        if not label_col is None:
            figure = go.Figure(
                data = px.scatter(
                    data_frame=data_df,
                    x = plot_cols[0],
                    y = plot_cols[1],
                    color = label_col,
                    custom_data = customdata_cols,
                    title = '<br>'.join(
                        textwrap.wrap(
                            f'Scatter plot of {plot_cols[0]} and {plot_cols[1]} labeled by {label_col}',
                            width = 60
                            )
                        )
                )
            )
            if not data_df[label_col].dtype == np.number:
                figure.update_layout(
                    legend = dict(
                        orientation='h',
                        y = 0,
                        yanchor='top',
                        xanchor='left'
                    ),
                    margin = {'r':0,'b':25}
                )
            else:

                custom_data_idx = [i for i in range(data_df.shape[1]) if data_df.columns.tolist()[i] in customdata_cols]
                figure = go.Figure(
                    go.Scatter(
                        x = data_df[plot_cols[0]].values,
                        y = data_df[plot_cols[1]].values,
                        customdata = data_df.iloc[:,custom_data_idx].to_dict('records'),
                        mode = 'markers',
                        marker = {
                            'color': data_df[label_col].values,
                            'colorbar':{
                                'title': label_col
                            },
                            'colorscale':'jet'
                        },
                        text = data_df[label_col].values,
                        hovertemplate = "label: %{text}"

                    )
                )

        else:

            figure = go.Figure(
                data = px.scatter(
                    data_frame=data_df,
                    x = plot_cols[0],
                    y = plot_cols[1],
                    color = None,
                    custom_data = customdata_cols,
                    title = '<br>'.join(
                        textwrap.wrap(
                            f'Scatter plot of {plot_cols[0]} and {plot_cols[1]}',
                            width = 60
                            )
                        )
                )
            )

        return figure

    def gen_umap_cols(self, data_df:pd.DataFrame, property_columns: list)->pd.DataFrame:
        """Scale and run UMAP for dimensionality reduction


        :param data_df: Extracted data from current GeoJSON features
        :type data_df: pd.DataFrame
        :param property_columns: Names of columns containing properties for UMAP plot
        :type property_columns: list
        :return: Dataframe containing colunns named UMAP1 and UMAP2
        :rtype: pd.DataFrame
        """
        quant_data = data_df.loc[:,[i for i in property_columns if i in data_df.columns]].fillna(0)
        for p in property_columns:
            quant_data[p] = pd.to_numeric(quant_data[p],errors='coerce')
        quant_data = quant_data.values
        feature_data_means = np.nanmean(quant_data,axis=0)
        feature_data_stds = np.nanstd(quant_data,axis=0)

        scaled_data = (quant_data-feature_data_means)/feature_data_stds
        scaled_data[np.isnan(scaled_data)] = 0.0
        scaled_data[~np.isfinite(scaled_data)] = 0.0
        umap_reducer = UMAP()
        embeddings = umap_reducer.fit_transform(scaled_data)
        umap_df = pd.DataFrame(data = embeddings, columns = ['UMAP1','UMAP2']).fillna(0)

        umap_df.columns = ['UMAP1','UMAP2']
        umap_df.reset_index(drop=True, inplace=True)

        return umap_df

    def gen_selected_div(self, n_markers: int, available_properties):
        """Generate a new property-graph-selected-div after changing the number of markers

        :param n_markers: New number of markers
        :type n_markers: int
        """

        new_selected_div = [
            html.Div([
                html.H3(f'Selected Samples: {n_markers}'),
                html.Hr(),
                dbc.Row([
                    dbc.Col(
                        dbc.Label('Select property for sub-plot: ',html_for = {'type': f'{self.component_prefix}-selected-sub-drop','index':0}),
                        md = 3
                    ),
                    dbc.Col(
                        dcc.Dropdown(
                            options = available_properties,
                            value = [],
                            id = {'type': f'{self.component_prefix}-selected-sub-drop','index': 0},
                            multi = True
                        ),
                        md = 9
                    )
                ],align='center',style = {'marginBottom': '10px'}),
                dbc.Row(
                    dbc.Button(
                        'Update Sub-Plot',
                        className = 'd-grid col-12 mx-auto',
                        n_clicks = 0,
                        id = {'type': f'{self.component_prefix}-selected-sub-butt','index': 0},
                        color = 'primary'
                    ),
                    style = {'marginBottom': '10px'}
                ),
                html.B(),
                dbc.Row(
                    dbc.Button(
                        'See Selected Marker Features',
                        className = 'd-grid col-12 mx-auto',
                        n_clicks=0,
                        id = {'type': f'{self.component_prefix}-selected-sub-markers','index':0},
                        color = 'secondary'
                    ),
                    style = {'marginBottom': '10px'}
                ),
                dbc.Row(
                    html.Div(
                        id = {'type': f'{self.component_prefix}-selected-sub-div','index': 0},
                        children = 0
                    )
                )
            ])
        ]

        return new_selected_div

    def select_data_from_plot(self, selected_data, current_plot_data, available_properties):
        """Updating selected data tab based on selection in primary graph


        :param selected_data: Selected data points in the current plot
        :type selected_data: list
        :param current_plot_data: Data used to generate the current plot
        :type current_plot_data: list
        :raises exceptions.PreventUpdate: Stop callback execution because there is no selected data
        :raises exceptions.PreventUpdate: Stop callback execution because there is no selected data
        :return: Selected data description div, markers to add to the map, updated current plot data
        :rtype: tuple
        """

        property_graph_selected_div = [no_update]*len(ctx.outputs_list[0])
        
        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))
        selected_data = get_pattern_matching_value(selected_data)
        available_properties = get_pattern_matching_value(available_properties)

        if selected_data is None:
            raise exceptions.PreventUpdate
        if type(selected_data)==list:
            if len(selected_data)==0:
                raise exceptions.PreventUpdate

        #TODO: This should be updated to return a GeoJSON of points with indications of which structures are selected
        map_marker_geojson = {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [
                            [
                                (p['customdata'][0][0]+p['customdata'][0][2])/2,
                                (p['customdata'][0][1]+p['customdata'][0][3])/2
                            ][::-1]
                        ]
                    },
                    'properties': {

                    }
                }
                for p_idx, p in enumerate(selected_data['points'])
            ]
        }


        map_marker = []
        for p_idx,p in enumerate(selected_data['points']):
            map_marker.append(
                dl.Marker(
                    position = [
                        (p['customdata'][0][0]+p['customdata'][0][2])/2,
                        (p['customdata'][0][1]+p['customdata'][0][3])/2
                    ][::-1],
                    children = [
                        dl.Popup(
                            dbc.Button(
                                'Clear Marker',
                                color = 'danger',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-selected-marker-delete','index': p_idx}
                            ),
                            id = {'type': f'{self.component_prefix}-selected-marker-popup','index': p_idx}
                        ),
                        html.Div(
                            children = [
                                json.dumps(p['customdata'][1])
                            ],
                            id = {'type': f'{self.component_prefix}-selected-marker-index','index': p_idx},
                            style = {'display': 'none'}
                        )
                    ]
                )
            )

        current_plot_data['selected'] = selected_data
        current_plot_data = [json.dumps(current_plot_data)]

        # Update property_graph_selected_div
        property_graph_selected_div = self.gen_selected_div(len(map_marker), available_properties)

        return property_graph_selected_div, [map_marker], current_plot_data

    def make_property_plot_tabs(self, data_df:pd.DataFrame, label_col: Union[str,None],property_cols: list, customdata_cols:list)->list:
        """Generate property plot description tabs

        :param data_df: Current data used to generate the plot
        :type data_df: pd.DataFrame
        :param label_col: Column of data_df used to label points in the plot.
        :type label_col: Union[str,None]
        :param property_cols: Column(s) of data_df plotted in the plot.
        :type property_cols: list
        :param customdata_cols: Column(s) used in the "customdata" field of points in the plot
        :type customdata_cols: list
        :return: List of tabs including summary statistics, clustering options, selected data options
        :rtype: list
        """
        # Property summary tab
        property_summary_children = []
        if not label_col is None:
            unique_labels = [i for i in data_df[label_col].unique().tolist() if type(i)==str]
            for u_idx, u in enumerate(unique_labels):
                label_data = data_df[data_df[label_col].astype(str).str.match(u)].loc[:,[i for i in property_cols if i in data_df]]
                summary = label_data.describe().round(decimals=4)
                summary.reset_index(inplace=True,drop=False)

                property_summary_children.extend([
                    html.H3(f'Samples labeled: {u}'),
                    html.Hr(),
                    dash_table.DataTable(
                        id = {'type': f'{self.component_prefix}-property-summary-table','index': u_idx},
                        columns = [{'name': i, 'id': i, 'deletable': False, 'selectable': True} for i in summary.columns],
                        data = summary.to_dict('records'),
                        editable = False,
                        style_cell = {
                            'overflowX': 'auto'
                        },
                        tooltip_data = [
                            {
                                column: {'value': str(value),'type': 'markdown'}
                                for column,value in row.items()
                            } for row in summary.to_dict('records')
                        ],
                        tooltip_duration = None,
                        style_data_conditional = [
                            {
                                'if': {
                                    'column_id': 'index'
                                },
                                'width': '35%'
                            }
                        ]
                    ),
                    html.Hr()
                ])

        else:
            label_data = data_df.loc[:,[i for i in property_cols if i in data_df]]
            summary = label_data.describe().round(decimals=4)
            summary.reset_index(inplace=True,drop=False)

            property_summary_children.extend([
                html.H3('All Samples'),
                html.Hr(),
                dash_table.DataTable(
                    id = {'type': f'{self.component_prefix}-property-summary-table','index': 0},
                    columns = [{'name': i, 'id': i, 'deletable': False, 'selectable': True} for i in summary.columns],
                    data = summary.to_dict('records'),
                    editable = False,
                    style_cell = {
                        'overflowX': 'auto'
                    },
                    tooltip_data = [
                        {
                            column: {'value': str(value),'type': 'markdown'}
                            for column,value in row.items()
                        } for row in summary.to_dict('records')
                    ],
                    tooltip_duration = None,
                    style_data_conditional = [
                        {
                            'if': {
                                'column_id': 'index'
                            },
                            'width': '35%'
                        }
                    ]
                ),
                html.Hr()
            ])

        property_summary_tab = dbc.Tab(
            id = {'type': f'{self.component_prefix}-property-summary-tab','index': 0},
            children = property_summary_children,
            tab_id = 'property-summary',
            label = 'Property Summary'
        )

        # Property statistics
        label_stats_children = []
        if data_df.shape[0]>1:
            if not label_col is None:
                unique_labels = data_df[label_col].unique().tolist()
                if len(unique_labels)>1:
                    if any([i>1 for i in list(data_df[label_col].value_counts().to_dict().values())]):

                        p_value, results = get_label_statistics(
                            data_df = data_df.loc[:,[i for i in data_df if not i in customdata_cols]],
                            label_col=label_col
                        )

                        if len(property_cols)==1:
                            if len(unique_labels)==2:
                                if p_value<0.05:
                                    significance = dbc.Alert('Statistically significant (p<0.05)',color='success')
                                else:
                                    significance = dbc.Alert('Not statistically significant (p>=0.05)',color='warning')
                                
                                label_stats_children.extend([
                                    significance,
                                    html.Hr(),
                                    html.Div([
                                        html.A('Statistical Test: t-Test',href='https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html',target='_blank'),
                                        html.P('Tests null hypothesis that two independent samples have identical mean values. Assumes equal variance within groups.')
                                    ]),
                                    html.Div(
                                        dash_table.DataTable(
                                            id = {'type': f'{self.component_prefix}-property-stats-table','index': 0},
                                            columns = [
                                                {'name': i, 'id': i}
                                                for i in results.columns
                                            ],
                                            data = results.to_dict('records'),
                                            style_cell = {
                                                'overflow': 'hidden',
                                                'textOverflow': 'ellipsis',
                                                'maxWidth': 0
                                            },
                                            tooltip_data = [
                                                {
                                                    column: {'value': str(value), 'type': 'markdown'}
                                                    for column, value in row.items()
                                                } for row in results.to_dict('records')
                                            ],
                                            tooltip_duration = None
                                        ) if type(results)==pd.DataFrame else []
                                    )
                                ])
                        
                            elif len(unique_labels)>2:

                                if p_value<0.05:
                                    significance = dbc.Alert('Statistically significant! (p<0.05)',color='success')
                                else:
                                    significance = dbc.Alert('Not statistically significant (p>=0.05)',color='warning')
                                
                                label_stats_children.extend([
                                    significance,
                                    html.Hr(),
                                    html.Div([
                                        html.A('Statistical Test: One-Way ANOVA',href='https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.f_oneway.html',target='_blank'),
                                        html.P('Tests null hypothesis that two or more groups have the same population mean. Assumes independent samples from normal, homoscedastic (equal standard deviation) populations')
                                    ]),
                                    html.Div(
                                        dash_table.DataTable(
                                            id = {'type': f'{self.component_prefix}-property-stats-table','index':0},
                                            columns = [
                                                {'name': i, 'id': i}
                                                for i in results['anova'].columns
                                            ],
                                            data = results['anova'].to_dict('records'),
                                            style_cell = {
                                                'overflow': 'hidden',
                                                'textOverflow': 'ellipsis',
                                                'maxWidth': 0
                                            },
                                            tooltip_data = [
                                                {
                                                    column: {'value': str(value),'type': 'markdown'}
                                                    for column, value in row.items()
                                                } for row in results['anova'].to_dict('records')
                                            ],
                                            tooltip_duration = None
                                        )
                                    ),
                                    html.Hr(),
                                    html.Div([
                                        html.A("Statistical Test: Tukey's HSD",href='https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.tukey_hsd.html',target='_blank'),
                                        html.P('Post hoc test for pairwise comparison of means from different groups. Assumes independent samples from normal, equal (finite) variance populations')
                                    ]),
                                    html.Div(
                                        dash_table.DataTable(
                                            id = {'type': f'{self.component_prefix}-property-stats-tukey','index': 0},
                                            columns = [
                                                {'name': i,'id': i}
                                                for i in results['tukey'].columns
                                            ],
                                            data = results['tukey'].to_dict('records'),
                                            style_cell = {
                                                'overflow': 'hidden',
                                                'textOverflow': 'ellipsis',
                                                'maxWidth': 0
                                            },
                                            tooltip_data = [
                                                {
                                                    column: {'value': str(value), 'type': 'markdown'}
                                                    for column, value in row.items()
                                                } for row in results['tukey'].to_dict('records')
                                            ],
                                            tooltip_duration = None,
                                            style_data_conditional = [
                                                {
                                                    'if': {
                                                        'column_id': 'Comparison'
                                                    },
                                                    'width': '35%'
                                                },
                                                {
                                                    'if': {
                                                        'filter_query': '{p-value} <0.05',
                                                        'column_id': 'p-value'
                                                    },
                                                    'backgroundColor': 'green',
                                                    'color': 'white'
                                                },
                                                {
                                                    'if': {
                                                        'filter_query': '{p-value} >=0.05',
                                                        'column_id': 'p-value'
                                                    },
                                                    'backgroundColor': 'tomato',
                                                    'color': 'white'
                                                }
                                            ]
                                        )
                                    )
                                ])

                            else:

                                label_stats_children.append(
                                    dbc.Alert('Only one unique label present!',color = 'warning')
                                )

                        elif len(property_cols)==2:
                            if any([i<0.05 for i in p_value]):
                                significance = dbc.Alert('Statistical significance found!',color='success')
                            else:
                                significance = dbc.Alert('No statistical significance',color='warning')
                            
                            label_stats_children.extend([
                                significance,
                                html.Hr(),
                                html.Div([
                                    html.A('Statistical Test: Pearson Correlation Coefficient (r)',href='https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mstats.pearsonr.html',target='_blank'),
                                    html.P('Measures the linear relationship between two datasets. Assumes normally distributed data.')
                                ]),
                                html.Div(
                                    dash_table.DataTable(
                                        id=f'{self.component_prefix}-pearson-table',
                                        columns = [{'name':i,'id':i} for i in results.columns],
                                        data = results.to_dict('records'),
                                        style_cell = {
                                            'overflow':'hidden',
                                            'textOverflow':'ellipsis',
                                            'maxWidth':0
                                        },
                                        tooltip_data = [
                                            {
                                                column: {'value':str(value),'type':'markdown'}
                                                for column,value in row.items()
                                            } for row in results.to_dict('records')
                                        ],
                                        tooltip_duration = None,
                                        style_data_conditional = [
                                            {
                                                'if': {
                                                    'filter_query': '{p-value} <0.05',
                                                    'column_id':'p-value',
                                                },
                                                'backgroundColor':'green',
                                                'color':'white'
                                            },
                                            {
                                                'if':{
                                                    'filter_query': '{p-value} >= 0.05',
                                                    'column_id':'p-value'
                                                },
                                                'backgroundColor':'tomato',
                                                'color':'white'
                                            }
                                        ]
                                    )
                                )
                            ])

                        elif len(property_cols)>2:
                            
                            overall_silhouette = results['overall_silhouette']
                            if overall_silhouette>=-1 and overall_silhouette<=-0.5:
                                silhouette_alert = dbc.Alert(f'Overall Silhouette Score: {overall_silhouette}',color='danger')
                            elif overall_silhouette>-0.5 and overall_silhouette<=0.5:
                                silhouette_alert = dbc.Alert(f'Overall Silhouette Score: {overall_silhouette}',color = 'primary')
                            elif overall_silhouette>0.5 and overall_silhouette<=1:
                                silhouette_alert = dbc.Alert(f'Overall Silhouette Score: {overall_silhouette}',color = 'success')
                            else:
                                silhouette_alert = dbc.Alert(f'Weird value: {overall_silhouette}')

                            label_stats_children.extend([
                                silhouette_alert,
                                html.Div([
                                    html.A('Clustering Metric: Silhouette Coefficient',href='https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html#sklearn.metrics.silhouette_score',target='_blank'),
                                    html.P('Quantifies density of distribution for each sample. Values closer to 1 indicate high class clustering. Values closer to 0 indicate mixed clustering between classes. Values closer to -1 indicate highly dispersed distribution for a class.')
                                ]),
                                html.Div(
                                    dash_table.DataTable(
                                        id=f'{self.component_prefix}-silhouette-table',
                                        columns = [{'name':i,'id':i} for i in results['samples_silhouette'].columns],
                                        data = results['samples_silhouette'].to_dict('records'),
                                        style_cell = {
                                            'overflow':'hidden',
                                            'textOverflow':'ellipsis',
                                            'maxWidth':0
                                        },
                                        tooltip_data = [
                                            {
                                                column: {'value':str(value),'type':'markdown'}
                                                for column,value in row.items()
                                            } for row in results['samples_silhouette'].to_dict('records')
                                        ],
                                        tooltip_duration = None,
                                        style_data_conditional = [
                                            {
                                                'if': {
                                                    'filter_query': '{Silhouette Score}>0',
                                                    'column_id':'Silhouette Score',
                                                },
                                                'backgroundColor':'green',
                                                'color':'white'
                                            },
                                            {
                                                'if':{
                                                    'filter_query': '{Silhouette Score}<0',
                                                    'column_id':'Silhouette Score'
                                                },
                                                'backgroundColor':'tomato',
                                                'color':'white'
                                            }
                                        ]
                                    )
                                )
                            ])
                    else:
                        label_stats_children.append(
                            dbc.Alert(f'Only one of each label type present!',color='warning')
                        )
                else:
                    label_stats_children.append(
                        dbc.Alert(f'Only one label present! ({unique_labels[0]})',color='warning')
                    )
            else:
                label_stats_children.append(
                    dbc.Alert('No labels assigned to the plot!',color='warning')
                )
        else:
            label_stats_children.append(
                dbc.Alert('Only one sample present!',color='warning')
            )

        label_stats_tab = dbc.Tab(
            id = {'type': f'{self.component_prefix}-property-stats-tab','index': 0},
            children = label_stats_children,
            tab_id = 'property-stats',
            label = 'Property Statistics'
        )

        selected_data_tab = dbc.Tab(
            id = {'type': f'{self.component_prefix}-property-selected-data-tab','index': 0},
            children = html.Div(
                id = {'type': f'{self.component_prefix}-property-graph-selected-div','index': 0},
                children = ['Select data points in the plot to get started!']
            ),
            tab_id = 'property-selected-data',
            label = 'Selected Data'
        )

        property_plot_tabs = dbc.Tabs(
            id = {'type': f'{self.component_prefix}-property-plot-tabs','index': 0},
            children = [
                property_summary_tab,
                label_stats_tab,
                selected_data_tab
            ],
            active_tab = 'property-summary'
        )

        return property_plot_tabs

    def remove_marker_label(self, delete_click, current_plot_data, available_properties):
        """Remove marker from selected feature

        :param delete_click: Clear marker button clicked
        :type delete_click: list
        :param current_plot_data: Current data for plot
        :type current_plot_data: list
        :return: Updating current markers on SlideMap, current plot data, and property-graph-selected-div
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))
        available_properties = get_pattern_matching_value(available_properties)
        n_marked = len(current_plot_data['selected']['points'])

        patched_list = Patch()
        values_to_remove = np.where(delete_click)[0].tolist()
        for v in values_to_remove:
            del patched_list[v]
            del current_plot_data['selected']['points'][v]
        
        current_plot_data = [json.dumps(current_plot_data)]
        new_selected_div = self.gen_selected_div(n_marked-1, available_properties)

        return [patched_list], current_plot_data, new_selected_div

    def update_sub_div(self, plot_butt_clicked, marker_butt_clicked, sub_plot_value, current_plot_data, current_features, current_labels):
        """Updating the property-graph-selected-div based on selection of either a property to plot a sub-plot of or whether the marker properties button was clicked

        :param plot_butt_clicked: Update sub-plot button was clicked
        :type plot_butt_clicked: list
        :param marker_butt_clicked: Get marker features for selected samples clicked
        :type marker_butt_clicked: list
        :param current_plot_data: Current data in the plot
        :type current_plot_data: list
        :param current_features: Current set of GeoJSON FeatureCollections on the SlideMap
        :type current_features: list
        :param current_labels: Current labels applied to the main plot
        :type current_labels: list
        :return: Updated children of the selected-property-graph-div including either sub-plot or table of marker features
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))
        sub_plot_value = get_pattern_matching_value(sub_plot_value)
        current_labels = get_pattern_matching_value(current_labels)
        sub_div_content = []

        current_features = json.loads(get_pattern_matching_value(current_features))

        if 'selected-sub-butt' in ctx.triggered_id['type']:
            if not sub_plot_value is None:

                if type(sub_plot_value)==str:
                    sub_plot_value = [sub_plot_value]
                if type(sub_plot_value[0])==list:
                    sub_plot_value = sub_plot_value[0]

                # Pulling selected data points from current plot_data
                current_selected = current_plot_data['selected']['points']
                
                selected_data = self.extract_data_from_features(
                    geo_list=current_features,
                    properties = sub_plot_value,
                    labels = current_labels,
                    filter_list = [i['customdata'][1] for i in current_selected]
                )

                if len(selected_data)>0:
                    data_df = pd.DataFrame.from_records(selected_data).dropna(subset = sub_plot_value, how='all')
                    data_df.reset_index(inplace=True,drop=True)

                    if len(sub_plot_value)==1:
                        sub_plot_figure = self.gen_violin_plot(
                            data_df = data_df,
                            label_col = current_labels,
                            property_column = sub_plot_value[0],
                            customdata_columns = ['bbox','point_info']
                        )
                    elif len(sub_plot_value)==2:
                        sub_plot_figure = self.gen_scatter_plot(
                            data_df = data_df,
                            plot_cols = sub_plot_value,
                            label_col = current_labels,
                            customdata_cols = ['bbox','point_info']
                        )

                    elif len(sub_plot_value)>2:
                        umap_cols = self.gen_umap_cols(
                            data_df = data_df,
                            property_columns = sub_plot_value
                        )

                        before_cols = data_df.columns.tolist()
                        plot_cols = umap_cols.columns.tolist()

                        data_df = pd.concat([data_df,umap_cols],axis=1,ignore_index=True).fillna(0)
                        data_df.columns = before_cols + plot_cols

                        sub_plot_figure = self.gen_scatter_plot(
                            data_df = data_df,
                            plot_cols = ['UMAP1','UMAP2'],
                            label_col = current_labels,
                            customdata_cols = ['bbox','point_info']
                        )


                    sub_div_content = dcc.Graph(
                        id = {'type': f'{self.component_prefix}-property-sub-graph','index': 0},
                        figure = sub_plot_figure
                    )
                else:
                    sub_div_content = dbc.Alert(
                        f'Property: {sub_plot_value} not found in selected points!',
                        color = 'warning'
                    )

        elif 'selected-sub-markers' in ctx.triggered_id['type']:
            current_selected = current_plot_data['selected']['points']

            selected_data = self.extract_data_from_features(
                geo_list = current_features,
                properties = current_labels,
                labels = current_labels,
                filter_list = [i['customdata'][1] for i in current_selected]
            )

            selected_data = pd.DataFrame.from_records(selected_data)
            wilcox_results = run_wilcox_rank_sum(
                data_df = selected_data,
                label_col= current_labels
            )

            wilcox_df = pd.DataFrame.from_records(wilcox_results)

            if not wilcox_df.empty:
                
                #TODO: Sorting columns using 'native' does not work for exponents. Ignores exponent part.
                sub_div_content = dash_table.DataTable(
                    id = {'type': f'{self.component_prefix}-property-sub-wilcox','index': 0},
                    #sort_mode = 'multi',
                    #sort_action = 'native',
                    filter_action = 'native',
                    columns = [
                        {'name': i, 'id': i}
                        if not 'p Value' in i or 'statistic' in i else
                        {'name': i,'id': i, 'type': 'numeric', 'format': Format(precision=3,scheme=Scheme.decimal_or_exponent)}
                        for i in wilcox_df.columns
                    ],
                    data = wilcox_df.to_dict('records'),
                    style_cell = {
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                        'maxWidth': 0
                    },
                    tooltip_data = [
                        {
                            column: {'value': str(value), 'type': 'markdown'}
                            for column, value in row.items()
                        } for row in wilcox_df.to_dict('records')
                    ],
                    tooltip_duration = None,
                    style_data_conditional=[
                        {
                            'if': {
                                'filter_query': '{p Value Adjusted} <0.05',
                                'column_id': 'p Value Adjusted'
                            },
                            'backgroundColor': 'tomato',
                            'color': 'white'
                        },
                        {
                            'if': {
                                'filter_query': '{p Value Adjusted} >=0.05',
                                'column_id': 'p Value Adjusted'
                            },
                            'backgroundColor': 'lightblue',
                            'color': 'white'
                        }
                    ]
                )
            else:
                sub_div_content = dbc.Alert(
                    'No significant values found!',
                    color = 'warning'
                )


        return [sub_div_content]

    def sub_select_data(self, sub_selected_data):
        """Updating the markers on the map according to selected data in the sub-plot

        :param sub_selected_data: Selected points in the sub-plot
        :type sub_selected_data: list
        :param current_plot_data: Plot data in the main-plot
        :type current_plot_data: list
        :param current_features: Current GeoJSON features on the map
        :type current_features: list
        :return: Updated list of markers applied to the map
        :rtype: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        sub_selected_data = get_pattern_matching_value(sub_selected_data)
        
        if sub_selected_data is None:
            raise exceptions.PreventUpdate
        if type(sub_selected_data)==list:
            if len(sub_selected_data)==0:
                raise exceptions.PreventUpdate

        map_marker = []
        for p_idx,p in enumerate(sub_selected_data['points']):
            map_marker.append(
                dl.Marker(
                    position = [
                        (p['customdata'][0][0]+p['customdata'][0][2])/2,
                        (p['customdata'][0][1]+p['customdata'][0][3])/2
                    ][::-1],
                    children = [
                        dl.Popup(
                            dbc.Button(
                                'Clear Marker',
                                color = 'danger',
                                n_clicks = 0,
                                id = {'type': f'{self.component_prefix}-selected-marker-delete','index': p_idx}
                            ),
                            id = {'type': f'{self.component_prefix}-selected-marker-popup','index': p_idx}
                        ),
                        html.Div(
                            children = [
                                json.dumps(p['customdata'][1])
                            ],
                            id = {'type': f'{self.component_prefix}-selected-marker-index','index': p_idx},
                            style = {'display':'none'}
                        )
                    ]
                )
            )
        
        map_marker_div = html.Div(
            map_marker
        )

        return [map_marker_div]

class HRAViewer(Tool):
    """HRAViewer Tool which enables hierarchy visualization for organs, cell types, biomarkers, and proteins in the Human Reference Atlas

    For more information on the Human Reference Atlas (HRA), see: https://humanatlas.io/

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self):
        """Constructor method
        """
        
        super().__init__()
        self.asct_b_version = 7

        self.asct_b_release = pd.read_csv(
            BytesIO(
                requests.get(
                    f'https://humanatlas.io/assets/table-data/asctb_release{self.asct_b_version}.csv'
                ).content
            )
        )

        self.organ_table_options = [
            {'label': f'{i} ASCT+B Table', 'value': i, 'disabled': False}
            for i in self.asct_b_release['Organ'].tolist()
        ]

    def __str__(self):
        return "HRA Viewer"

    def load(self, component_prefix: int):
        
        self.component_prefix = component_prefix
        self.title = 'HRA Viewer'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def gen_layout(self, session_data: dict):
        """Generate layout for HRA Viewer component
        """

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        dbc.Col(html.H3('Human Reference Atlas (HRA) Viewers'))
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Col('Select one of the embedded components below or select an organ to view the ASCT+B table for that organ')
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('HRA View Select: ',html_for = {'type': 'hra-viewer-drop','index': 0})
                        ],md=2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': 'FTU Explorer','value': 'FTU Explorer','disabled': False},
                                ] + self.organ_table_options,
                                value = [],
                                multi = False,
                                id = {'type': 'hra-viewer-drop','index': 0}
                            )
                        ], md = 10)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'hra-viewer-parent','index': 0},
                                children = [],
                            )
                        ])
                    ],align='center')
                ])
            ])
        ],style = {'width': '100%'})

        self.blueprint.layout = layout

    def get_callbacks(self):
        """Initializing callbacks and attaching to DashBlueprint
        """

        self.blueprint.callback(
            [
                Input({'type': 'hra-viewer-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'hra-viewer-parent','index': ALL},'children')
            ]
        )(self.update_hra_viewer)

    def get_organ_table(self, organ:str):
        """Grabbing ASCT+B Table for a specific organ

        :param organ: Name of organ to get table for
        :type organ: str
        """

        csv_path = self.asct_b_release[self.asct_b_release['Organ'].str.match(organ)]['csv'].values[0]
        
        new_table_request = requests.get(csv_path)

        if new_table_request.ok:
            new_table = pd.read_csv(
                BytesIO(
                    new_table_request.content
                ),
                skiprows=list(range(10))
            ).fillna('-')

            table_attribution = {}
            attribution_rows = pd.read_csv(
                BytesIO(
                    new_table_request.content
                )
            ).iloc[1:9,:2]
            table_attrib_list = ['authors','authors_orcs','reviewers','reviewers_orcs','publications','data_doi','date','version']
            for t_idx,t in enumerate(table_attrib_list):
                try:
                    table_attribution[t] = re.split('; |, ',attribution_rows.iloc[t_idx,:].values[1])
                except:
                    table_attribution[t] = 'Not provided'

        else:
            new_table = None
            table_attribution = None

        return new_table, table_attribution

    def update_hra_viewer(self, viewer_drop_value):
        """Updating the HRAViewer component based on selected view

        :param viewer_drop_value: Selected component from dropdown (one of FTU Explorer or {organ} ASCT+B Table)
        :type viewer_drop_value: list
        """
        """
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        """

        viewer_drop_value = get_pattern_matching_value(viewer_drop_value)

        if viewer_drop_value is None:
            raise exceptions.PreventUpdate

        viewer_children = no_update
        if viewer_drop_value=='FTU Explorer':

            viewer_children = html.Iframe(
                srcDoc = '''
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="utf-8" />
                        <title>FTU Ui Small Web Component</title>
                        <meta name="viewport" content="width=device-width, initial-scale=1" />
                        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&display=swap" rel="stylesheet" />
                        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet" />
                        <link
                        rel="stylesheet"
                        href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
                        />
                        <link href="https://cdn.humanatlas.io/ui/ftu-ui-small-wc/styles.css" rel="stylesheet" />
                        <script src="https://cdn.humanatlas.io/ui/ftu-ui-small-wc/wc.js" defer></script>
                    </head>
                    <body style="margin: 0">
                        <hra-ftu-ui-small
                        base-href="https://cdn.humanatlas.io/ui/ftu-ui-small-wc/"
                        selected-illustration="https://purl.humanatlas.io/2d-ftu/kidney-renal-corpuscle"
                        datasets="assets/TEMP/ftu-datasets.jsonld"
                        summaries="assets/TEMP/ftu-cell-summaries.jsonld"
                        >
                        </hra-ftu-ui-small>
                    </body>
                    </html>
                ''',
                style = {
                    'height': '1000px','width': '100%','overflow': 'scroll'
                }
            )
        
        if viewer_drop_value in self.asct_b_release['Organ'].tolist():
            
            organ_table, table_attribution = self.get_organ_table(viewer_drop_value)
            
            if not organ_table is None and not table_attribution is None:
                
                reviewers_and_authors = [
                    dbc.Row([
                        dbc.Col([
                            dbc.Label(
                                html.H4('Authors:'),
                                html_for={'type': f'{self.component_prefix}-hra-viewer-authors','index': 0}
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                dmc.AvatarGroup(
                                    id = {'type': f'{self.component_prefix}-hra-viewer-authors','index': 0},
                                    children = [
                                        html.A(
                                            dmc.Tooltip(
                                                dmc.Avatar(
                                                    ''.join([n[0] for n in name.split()]),
                                                    radius = 'xl',
                                                    size = 'lg',
                                                    color = f'rgb({np.random.randint(0,255)},{np.random.randint(0,255)},{np.random.randint(0,255)})'
                                                ),
                                                label = name,
                                                position = 'bottom'
                                            ),
                                            href = f'https://orcid.org/{orc_id}',
                                            target = '_blank'
                                        )
                                        for name,orc_id in zip(table_attribution['authors'], table_attribution['authors_orcs'])
                                    ]
                                )
                            )
                        ])
                    ],style={'marginBottom': '5px'},align='center'),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label(
                                html.H6(
                                    'Reviewers: '
                                ),
                                html_for={'type': f'{self.component_prefix}-hra-viewer-reviewers','index': 0}
                            )
                        )
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                dmc.AvatarGroup(
                                    id = {'type': f'{self.component_prefix}-hra-viewer-reviewers','index': 0},
                                    children = [
                                        html.A(
                                            dmc.Tooltip(
                                                dmc.Avatar(
                                                    ''.join([n[0] for n in name.split()]),
                                                    radius = 'xl',
                                                    size = 'md',
                                                    color = f'rgb({np.random.randint(0,255)},{np.random.randint(0,255)},{np.random.randint(0,255)})'
                                                ),
                                                label = name,
                                                position = 'bottom'
                                            ),
                                            href = f'https://orcid.org/{orc_id}',
                                            target = '_blank'
                                        )
                                        for name, orc_id in zip(table_attribution['reviewers'], table_attribution['reviewers_orcs'])
                                    ]
                                )
                            )]
                        )
                    ],style = {'marginBottom':'5px'})
                ]

                general_publications = dbc.Row([
                        dbc.Col(
                            'General Publication(s):',
                            md = 4
                        ),
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    children = [
                                        dbc.Row(
                                            dbc.Col(dmc.NavLink(
                                                label = p if 'https' in p else f'https://doi.org/{p.split("DOI:")[-1]}',
                                                href = p if 'https' in p else f'https://doi.org/{p.split("DOI:")[-1]}',
                                                target = '_blank'
                                            )),
                                            align='left'
                                        )
                                        if 'doi' in p.lower() else dbc.Row(p)
                                        for p in table_attribution['publications']
                                    ],
                                    style = {'maxHeight':'100px','overflow':'scroll'}
                                )
                                if not table_attribution['publications']=='Not Provided' else 'Not Provided'
                            ),
                            md = 8
                        )
                    ],align='center')
                
                organ_dash_table = [
                    dash_table.DataTable(
                        id = {'type':f'{self.component_prefix}-hra-viewer-table','index': 0},
                        columns = [{'name':i,'id':i,'deletable':False,'selectable':True} for i in organ_table.columns],
                        data = organ_table.to_dict('records'),
                        editable = False,
                        filter_action='native',
                        sort_action='native',
                        sort_mode='multi',
                        style_table = {
                            'overflowX': 'auto',
                            'maxWidth': '800px'
                        },
                        tooltip_data = [
                            {
                                column: {'value': str(value),'type':'markdown'}
                                for column,value in row.items()
                            } for row in organ_table.to_dict('records')
                        ],
                        tooltip_duration = None
                    )
                    ]
                
                data_doi = dbc.Row([
                        dbc.Col(
                            dmc.NavLink(
                                label = html.Div('Data DOI',style={'align':'center'}),
                                href = table_attribution['data_doi'],
                                target = '_blank'
                            ),
                            md = 12
                        )
                    ],align = 'center')
            


                viewer_children = dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.Div(reviewers_and_authors),
                            html.Hr(),
                            dbc.Row([
                                dbc.Col([
                                    html.Div(
                                        organ_dash_table,
                                        style = {'maxHeight': '500px','overflow': 'scroll','width': '100%'}
                                    )
                                ],md = 'auto')
                            ]),
                            html.Hr(),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label(
                                        html.H6('Table Data Sources:'),
                                        html_for={'type':f'{self.component_prefix}-hra-viewer-table-sources','index':0}
                                    )
                                ],md=12)
                            ]),
                            general_publications,
                            data_doi,
                            dbc.Row([
                                dbc.Col(
                                    dbc.Label('Date: ',html_for = {'type': f'{self.component_prefix}-hra-viewer-date','index': 0}),
                                    md = 4
                                ),
                                dbc.Col(
                                    table_attribution['date'],
                                    md = 8
                                )
                            ],align='center'),
                            dbc.Row([
                                dbc.Col(
                                    dbc.Label('Version Number: ',html_for = {'type':f'{self.component_prefix}-hra-viewer-version','index': 0}),
                                    md = 4
                                ),
                                dbc.Col(
                                    table_attribution['version'],
                                    md = 8
                                )
                            ],align='center')
                        ])
                    ],
                    width = True)
                ],style={'width':'100%'})

            else:
                viewer_children = dbc.Alert(f'Unable to get ASCT+B Table for {viewer_drop_value}',color='warning')

        return [viewer_children]

class DataExtractor(Tool):
    def __init__(self,
                 assets_folder_path:str = f'{os.getcwd()}/.fusion_assets/'):

        super().__init__()

        self.exportable_session_data = {
            'Slide Metadata':{
                'description': 'This is any information about the current slide including labels, preparation details, and image tile information.'
            },
            'Visualization Session':{
                'description': 'This is a record of your current Visualization Session which can be uploaded in the Dataset Builder page to reload.'
            }
        }

        self.download_folder = assets_folder_path+'downloads/'

        self.exportable_data = {
            'Properties':{
                'formats': ['CSV','XLSX','JSON'],
                'description': 'These are all per-structure properties and can include morphometrics, cell composition, channel intensity statistics, labels, etc.'
            },
            'Annotations':{
                'formats': ['Histomics (JSON)','GeoJSON','Aperio XML'],
                'description': 'These are the boundaries of selected structures. Different formats indicate the type of file generated and imported into another tool for visualization and analysis.'
            },
            'Images & Masks':{
                'formats': ['OME-TIFF'],
                'description': 'This will be a zip file containing combined images and masks for selected structures.'
            },
            'Images': {
                'formats': ['OME-TIFF','TIFF','PNG','JPG'],
                'description': 'This will be a zip file containing images of selected structures. Note: If this is a multi-frame image and OME-TIFF is not selected, images will be rendered in RGB according to the current colors in the map.'
            },
            'Masks': {
                'formats': ['OME-TIFF','TIFF','PNG','JPG'],
                'description': 'This will be a zip file containing masks of selected structures. Note: If a Manual ROI is selected, masks will include all intersecting structures as a separate label for each.'
            }
        }

    def __str__(self):
        return 'Data Extractor'

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Data Extractor'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}',escape = lambda input_id: self.prefix_escape(input_id)),
                MultiplexerTransform()
            ]
        )

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

    def gen_layout(self,session_data:dict):

        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Data Extractor')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Download select properties from indicated structures in the current slide.'
                    ),
                    html.Hr(),
                    html.Div([
                        dcc.Store(
                            id = {'type': 'data-extractor-store','index': 0},
                            storage_type = 'memory',
                            data = json.dumps({'selected_data': []})
                        ),
                        dbc.Modal(
                            id = {'type': 'data-extractor-download-modal','index': 0},
                            children = [],
                            is_open = False,
                            size = 'xl'
                        ),
                        dcc.Interval(
                            id = {'type': 'data-extractor-download-interval','index': 0},
                            disabled = True,
                            interval = 3000,
                            n_intervals = 0,
                            max_intervals=-1
                        )
                    ]),
                    dbc.Row([
                        dbc.Row([
                            dbc.Col(
                                html.H5('Download Session Data:'),
                                md = 5
                            ),
                            dbc.Col(
                                dcc.Dropdown(
                                    options = list(self.exportable_session_data.keys()),
                                    value = [],
                                    multi = False,
                                    placeholder = 'Select an option',
                                    id = {'type': 'data-extractor-session-data-drop','index': 0}
                                ),
                                md = 7
                            )
                        ]),
                        dbc.Row(
                            html.Div(
                                id = {'type': 'data-extractor-session-data-description','index': 0},
                                children = []
                            )
                        ),
                        dbc.Row(
                            dbc.Button(
                                'Download Session Data',
                                id = {'type': 'data-extractor-download-session-data','index': 0},
                                n_clicks = 0,
                                className = 'd-grid col-12 mx-auto',
                                color = 'primary',
                                disabled = True
                            )
                        )
                    ],style = {'marginBottom':'10px'}),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(
                            html.H5('Select which structures to extract data from.'),
                            md = 9
                        ),
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-rotate fa-xl',
                                    n_clicks = 0,
                                    id = {'type': 'data-extractor-refresh-icon','index': 0}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'data-extractor-refresh-icon','index': 0},
                                children = 'Click to refresh available structures'
                            )
                        ],md = 3)
                    ],justify='left'),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Current Structures:',html_for={'type':'data-extractor-current-structures-drop','index': 0})
                        ],md=3),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = True,
                                placeholder = 'Structures in Slide',
                                id = {'type': 'data-extractor-current-structures-drop','index': 0}
                            )
                        ],md=9)
                    ]),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            html.H5('Select what type of data you want to extract')
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label('Available Data:',html_for={'type': 'data-extractor-available-data-drop','index': 0}),
                            md = 3
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = True,
                                placeholder='Data',
                                id = {'type': 'data-extractor-available-data-drop','index':0}
                            ),
                            md = 9
                        )
                    ]),
                    html.Hr(),
                    html.Div(
                        id = {'type':'data-extractor-selected-data-parent','index': 0},
                        children = [
                            html.Div('Selected data descriptions will appear here')
                        ],
                        style = {'maxHeight': '100vh','overflow': 'scroll'}
                    ),
                    dbc.Row([
                        dcc.Loading([
                            dbc.Button(
                                'Download Selected Data',
                                className = 'd-grid col-12 mx-auto',
                                disabled = True,
                                color = 'primary',
                                id = {'type': 'data-extractor-download-button','index': 0}
                            ),
                            dcc.Download(
                                id = {'type': 'data-extractor-download','index': 0}
                            )
                        ])
                    ],style = {'marginTop':'10px'})
                ])
            )
        ])

        self.blueprint.layout = layout

    def get_callbacks(self):
        
        # Callback for updating current slide
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-info-store','index': ALL},'data')
            ],
            [
                Output({'type': 'data-extractor-current-structures-drop','index': ALL},'options'),
                Output({'type': 'data-extractor-available-data-drop','index': ALL},'options'),
                Output({'type': 'data-extractor-selected-data-parent','index': ALL},'children'),
                Output({'type': 'data-extractor-download-button','index': ALL},'disabled'),
                Output({'type':'data-extractor-store','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.update_slide)

        # Callback for the refresh button being pressed
        self.blueprint.callback(
            [
                Input({'type': 'data-extractor-refresh-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'data-extractor-current-structures-drop','index': ALL},'options'),
                Output({'type': 'data-extractor-available-data-drop','index': ALL},'options'),
                Output({'type': 'data-extractor-selected-data-parent','index': ALL},'children'),
                Output({'type': 'data-extractor-download-button','index': ALL},'disabled'),
                Output({'type': 'data-extractor-store','index': ALL},'data')
            ],
            [
                State({'type': 'feature-overlay','index': ALL},'name'),
                State({'type': 'map-marker-div','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.refresh_data)

        # Callback for selecting a session data item
        self.blueprint.callback(
            [
                Input({'type':'data-extractor-session-data-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'data-extractor-session-data-description','index': ALL},'children'),
                Output({'type': 'data-extractor-download-session-data','index': ALL},'disabled')
            ]
        )(self.update_session_data_description)

        # Callback for downloading session data item
        self.blueprint.callback(
            [
                Input({'type': 'data-extractor-download-session-data','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'data-extractor-session-data-drop','index': ALL},'value'),
                State({'type': 'map-slide-information','index':ALL},'data'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'data-extractor-download','index': ALL},'data')
            ]
        )(self.download_session_data)

        # Callback for updating selected data information and enabling download button
        self.blueprint.callback(
            [
                Input({'type': 'data-extractor-available-data-drop','index': ALL},'value')
            ],
            [
                State({'type': 'data-extractor-store','index': ALL},'data'),
                State({'type': 'map-slide-information','index': ALL},'data'),
                State({'type': 'channel-mixer-tab','index': ALL},'label')
            ],
            [
                Output({'type': 'data-extractor-selected-data-parent','index': ALL},'children'),
                Output({'type': 'data-extractor-download-button','index': ALL},'disabled'),
                Output({'type': 'data-extractor-store','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.update_data_info)

        # Disabling channel selection if 'Use ChannelMixer' is checked
        self.blueprint.callback(
            [
                Input({'type': 'data-extractor-channel-mix-switch','index': MATCH},'checked')
            ],
            [
                State({'type': 'channel-mixer-tab','index':ALL},'label')
            ],
            [
                Output({'type': 'data-extractor-selected-data-channels','index': MATCH},'disabled'),
                Output({'type': 'data-extractor-selected-data-channels','index': MATCH},'value')
            ],
            prevent_initial_call = True
        )(self.disable_channel_selector)

        # Callback for downloading selected data and clearing selections
        self.blueprint.callback(
            [
                Input({'type': 'data-extractor-download-button','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'data-extractor-download-interval','index': ALL},'disabled'),
                Output({'type': 'data-extractor-current-structures-drop','index': ALL},'value'),
                Output({'type': 'data-extractor-available-data-drop','index': ALL},'value'),
                Output({'type': 'data-extractor-selected-data-parent','index': ALL},'children'),
                Output({'type': 'data-extractor-download-button','index': ALL},'disabled'),
                Output({'type': 'data-extractor-store','index': ALL},'data')
            ],
            [
                State({'type': 'data-extractor-current-structures-drop','index': ALL},'value'),
                State({'type': 'data-extractor-available-data-drop','index': ALL},'value'),
                State({'type': 'data-extractor-selected-data-format','index': ALL},'value'),
                State({'type': 'map-annotations-store','index':ALL},'data'),
                State({'type': 'map-marker-div','index': ALL},'children'),
                State({'type': 'map-slide-information','index': ALL},'data'),
                State({'type': 'channel-mixer-tab','index': ALL},'label'),
                State({'type': 'channel-mixer-tab','index': ALL},'label_style'),
                State({'type': 'data-extractor-channel-mix-switch','index': ALL},'checked'),
                State({'type': 'data-extractor-selected-data-channels','index': ALL},'value'),
                State({'type': 'data-extractor-selected-data-masks','index': ALL},'value')
            ],
            prevent_initial_call = True
        )(self.start_download_data)

        self.blueprint.callback(
            [
                Input({'type': 'data-extractor-download-interval','index': ALL},'n_intervals')
            ],
            [
                State({'type': 'data-extractor-store','index': ALL},'data')
            ],
            [
                Output({'type': 'data-extractor-store','index': ALL},'data'),
                Output({'type':'data-extractor-download-interval','index': ALL},'disabled'),
                Output({'type': 'data-extractor-download-modal','index': ALL},'is_open'),
                Output({'type': 'data-extractor-download-modal','index':ALL},'children'),
                Output({'type': 'data-extractor-download-interval','index':ALL},'n_intervals'),
                Output({'type': 'data-extractor-download','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.update_download_data)
    
    def update_slide(self, new_annotations_info:list):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        new_annotations_info = json.loads(get_pattern_matching_value(new_annotations_info))
        new_structure_names = new_annotations_info['feature_names']

        available_structures_drop = [
            {'label': i, 'value': i, 'disabled': False}
            for i in new_structure_names
        ]
        if len(new_structure_names)>0:
            available_structures_drop += [{'label': 'Marked Structures','value': 'Marked Structures','disabled': True}]

        if len(available_structures_drop)>0:
            available_data_drop = [
                {'label': i, 'value': i, 'disabled': False}
                for i in self.exportable_data
            ]
        else:
            available_data_drop = []

        button_disabled = True
        new_data_extractor_store = json.dumps({'selected_data': []})

        return [available_structures_drop], [available_data_drop], [html.Div('Selected data descriptions will appear here')], [button_disabled], [new_data_extractor_store]

    def refresh_data(self, clicked, overlay_names, marker_div_children):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        marker_div_children = get_pattern_matching_value(marker_div_children)
        if not overlay_names is None:
            available_structures_drop = [
                {'label': i, 'value': i, 'disabled': False}
                for i in overlay_names
            ]
        else:
            available_structures_drop = []
        
        if not marker_div_children is None:
            available_structures_drop += [{'label': 'Marked Structures','value': 'Marked Structures','disabled': True if len(marker_div_children)==0 else False}]

        if not overlay_names is None or not marker_div_children is None:
            available_data_drop = [
                {'label': i, 'value': i, 'disabled': False}
                for i in self.exportable_data
            ]
        else:
            available_data_drop = []

        button_disabled = True

        new_data_extractor_store = json.dumps({'selected_data': []})

        return [available_structures_drop], [available_data_drop], [html.Div('Selected data descriptions will appear here')], [button_disabled],[new_data_extractor_store]

    def update_session_data_description(self, session_data_selection):
        
        if not any([i['value'] for i in ctx.triggered]):
            return ['Select a type of session data to see a description'], [True]
        
        session_data_selection = get_pattern_matching_value(session_data_selection)

        return [self.exportable_session_data[session_data_selection]['description']], [False]

    def download_session_data(self, clicked, session_data_selection, current_slide_info, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data_selection = get_pattern_matching_value(session_data_selection)
        current_slide_info = json.loads(get_pattern_matching_value(current_slide_info))
        session_data = json.loads(session_data)

        if session_data_selection == 'Slide Metadata':
            if 'tiles_url' in current_slide_info:
                slide_tile_url = current_slide_info['tiles_url']
                current_slide_tile_urls = [i['tiles_url'] for i in session_data['current']]
                slide_idx = current_slide_tile_urls.index(slide_tile_url)

                slide_metadata = requests.get(session_data['current'][slide_idx]['metadata_url']).json()

                download_content = {'content': json.dumps(slide_metadata,indent=4),'filename': 'slide_metadata.json'}
            else:
                raise exceptions.PreventUpdate
        elif session_data_selection == 'Visualization Session':
            download_content = {'content': json.dumps(session_data,indent=4),'filename': 'fusion_visualization_session.json'}

        return [download_content]

    def update_data_info(self, selected_data, data_extract_store, slide_info_store, channel_mix_frames):

        if not any([i['value'] for i in ctx.triggered]):
            return [html.Div('Selected data descriptions will appear here')], [True], [no_update]
        
        selected_data = get_pattern_matching_value(selected_data)
        current_selected_data = json.loads(get_pattern_matching_value(data_extract_store))['selected_data']
        slide_info = json.loads(get_pattern_matching_value(slide_info_store))['tiles_metadata']

        channel_mix_opt = not channel_mix_frames is None and not channel_mix_frames==[]        

        def make_new_info(data_type, slide_info, channel_mix_opt):
            data_type_index = list(self.exportable_data.keys()).index(data_type)

            # Checking if this info card should also have a channel selector
            if 'Images' in data_type and any([i in slide_info for i in ['frames','channels','channelmap']]):
                show_channels = True

                if 'channels' in slide_info:
                    channel_names = slide_info['channels']
                else:
                    channel_names = [f'Channel {i+1}' for i in range(len(slide_info['frames']))]

            else:
                show_channels = False
                channel_names = ['red','green','blue']

            if "Masks" in data_type:
                show_mask_opts = True
                mask_opts = ['Structure Only','Intersecting']
            else:
                show_mask_opts = False
                mask_opts = []

            return_card = dbc.Card([
                dbc.CardHeader(data_type),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col(
                            dbc.Label('Download Format: '),
                            md = 3
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                options = self.exportable_data[data_type]['formats'],
                                value = self.exportable_data[data_type]['formats'][0],
                                multi = False,
                                placeholder = 'Select a format',
                                id = {'type': f'{self.component_prefix}-data-extractor-selected-data-format','index': data_type_index}
                            ),
                            md = 9
                        )
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dmc.Switch(
                                label = 'Use ChannelMixer Colors',
                                checked = False,
                                description='Use colors selected in the ChannelMixer component, renders an RGB image.',
                                id = {'type': f'{self.component_prefix}-data-extractor-channel-mix-switch','index': data_type_index}
                            )
                        ])
                    ],style = {'display':'none'} if not channel_mix_opt else {}),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Channels to save: ')
                        ], md = 3),
                        dbc.Col(
                            dcc.Dropdown(
                                options = channel_names,
                                value = channel_names,
                                multi = True,
                                id = {'type': f'{self.component_prefix}-data-extractor-selected-data-channels','index': data_type_index}
                            ),
                            md = 9
                        )
                    ],style = {'display': 'none'} if not show_channels else {}
                    ),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Mask Options: ')
                        ],md=3),
                        dbc.Col(
                            dcc.Dropdown(
                                options = mask_opts,
                                value = mask_opts[0] if len(mask_opts)>0 else [],
                                multi = False,
                                id = {'type': f'{self.component_prefix}-data-extractor-selected-data-masks','index': data_type_index}
                            ),
                            md = 9
                        )
                    ],style = {'display': 'none'} if not show_mask_opts else {}
                    )
                ])
            ])

            return return_card

        # Which ones are in selected_data that aren't in current_selected_data
        if len(current_selected_data)>0 and len(selected_data)>0:
            new_selected = list(set(selected_data) - set(current_selected_data))
            info_return = Patch()
            if len(new_selected)>0:
                # Appending to the partial property update
                for n in new_selected:
                    info_return.append(make_new_info(n,slide_info,channel_mix_opt))

            else:
                # Removing some de-selected values
                removed_type = list(set(current_selected_data)-set(selected_data))
                rem_count = 0
                for r in removed_type:
                    del info_return[current_selected_data.index(r)-rem_count]
                    rem_count+=1

        elif len(current_selected_data)>0 and len(selected_data)==0:
            info_return = html.Div('Selected data descriptions will appear here')
        elif len(current_selected_data)==0 and len(selected_data)==1:
            info_return = Patch()
            info_return.append(make_new_info(selected_data[0],slide_info,channel_mix_opt))

        button_disabled = len(selected_data)==0
        selected_data_store = json.dumps({'selected_data': selected_data})
        
        return [info_return], [button_disabled], [selected_data_store]

    def disable_channel_selector(self, switched, channel_labels):

        if switched:
            return True, channel_labels
        return False, no_update

    def extract_marker_structures(self, markers_geojson, slide_annotations):

        marked_feature_list = []
        structure_names = [i['properties']['name'] for i in slide_annotations]
        for f in markers_geojson['features']:
            # Getting the info of which structure this marker is marking
            marked_name = f['properties']['name']
            marked_idx = f['properties']['feature_index']

            if marked_name in structure_names:
                marked_feature = slide_annotations[structure_names.index(marked_name)]['features'][marked_idx]
                marked_feature['properties']['name'] = f'Marked {marked_feature["properties"]["name"]}'
                marked_feature_list.append(marked_feature)

        return marked_feature_list

    def download_image_data(self, feature_list:list, x_scale:float, y_scale:float, tile_url:str='', save_masks:bool=False, image_opts:list = [], mask_opts:str = '',save_format:Union[str,list]='PNG', combine:bool=False, save_path:str=''):
        
        # Scaling coordinates of features back to the slide CRS
        if not mask_opts=='Intersecting':
            feature_collection = {
                'type': 'FeatureCollection',
                'features': feature_list
            }
            scaled_features = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/x_scale,c[1]/y_scale),g),feature_collection)

        else:
            # Creating the intersecting masks
            scaled_feature_list = []
            for geo in feature_list:
                if type(geo)==dict:
                    scaled_feature_list.append(geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/x_scale,c[1]/y_scale),g),deepcopy(geo)))
                elif type(geo)==list:
                    for h in geo:
                        scaled_feature_list.append(geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/x_scale,c[1]/y_scale),g),deepcopy(h)))

            mask_names = [i['properties']['name'] for i in feature_list[1]]

            intersecting_masks = format_intersecting_masks(
                scaled_feature_list[0],
                scaled_feature_list[1:],
                mask_format = 'one-hot-labels'
            )

            scaled_features = scaled_feature_list[0]

        channel_names = [i['name'] for i in image_opts]

        color_opts = None
        if any(['color' in i for i in image_opts]):
            color_opts = [
                [
                    int(i) for i in j['color'].replace('rgba(','').replace(')','').replace(' ','').split(',')[:-1]
                ]
                for j in image_opts
            ]

        if not color_opts is None:
            channel_names = ['red','green','blue']

        for f_idx,f in enumerate(scaled_features['features']):
            if save_masks:
                # This is for a normal tile_url grabbing an RGB image from a non-multi-frame image
                if not any(['frame' in i for i in image_opts]):
                    image, mask = get_feature_image(
                        feature=f,
                        tile_source = tile_url,
                        return_mask = save_masks
                    )
                else:
                    image, mask = get_feature_image(
                        feature = f,
                        tile_source = tile_url,
                        return_mask = save_masks,
                        frame_index = [i['frame'] for i in image_opts],
                        frame_colors=color_opts
                    )

                if combine and save_format=='OME-TIFF':
                    if mask_opts=='Structure Only':
                        combined_image_mask = np.vstack(
                            (
                                np.moveaxis(image,source=-1,destination=0),
                                mask[None,:,:]
                            )
                        )

                        write_ome_tiff(
                            combined_image_mask,
                            save_path+f'/Images & Masks/{f["properties"]["name"]}_{f_idx}.ome.tiff',
                            channel_names+[f['properties']['name']],
                            [1.0,1.0],
                            1.0
                        )
                    else:

                        image = np.moveaxis(image,source=-1,destination = 0)
                        mask = np.moveaxis(intersecting_masks[f_idx],source=-1,destination=0)
                        combined_image_mask = np.vstack(
                            (
                                image,
                                mask
                            )
                        )

                        write_ome_tiff(
                            combined_image_mask,
                            save_path+f'/Images & Masks/{f["properties"]["name"]}_{f_idx}.ome.tiff',
                            channel_names+mask_names,
                            [1.0,1.0],
                            1.0
                        )

                else:
                    img_save_format = save_format
                    mask_save_format = save_format

                    if os.path.exists(f'{save_path}/Images/'):
                        if img_save_format=='OME-TIFF':
                            image = np.moveaxis(image,source=-1,destination=0)

                            write_ome_tiff(
                                image,
                                save_path+f'/Images/{f["properties"]["name"]}_{f_idx}.ome.tiff',
                                channel_names,
                                [1.0,1.0],
                                1.0
                            )
                        elif img_save_format in ['TIFF','PNG','JPG']:
                            if len(np.shape(image))==2 or np.shape(image)[-1]==1 or np.shape(image)[-1]==3 or img_save_format=='TIFF':
                                image_save_path = f'{save_path}/Images/{f["properties"]["name"]}_{f_idx}.{save_format.lower()}'
                                Image.fromarray(image).save(image_save_path)
                            else:
                                image_save_path = f'{save_path}/Images/{f["properties"]["name"]}_{f_idx}.tiff'
                                Image.fromarray(image).save(image_save_path)
                                
                    if os.path.exists(f'{save_path}/Masks/'):
                        if mask_save_format == 'OME-TIFF':
                            if mask_opts=='Structure Only':
                                mask = np.moveaxis(mask,source=-1,destination=0)

                                write_ome_tiff(
                                    mask,
                                    save_path+f'/Masks/{f["properties"]["name"]}_{f_idx}.ome.tiff',
                                    [f["properties"]["name"]],
                                    [1.0,1.0],
                                    1.0
                                )

                            elif mask_opts=='Intersecting':
                                write_ome_tiff(
                                    intersecting_masks[f_idx],
                                    save_path+f'/Masks/{f["properties"]["name"]}_{f_idx}.ome.tiff',
                                    mask_names,
                                    [1.0,1.0],
                                    1.0                                
                                )

                        elif mask_save_format in ['TIFF','PNG','JPG']:
                            if mask_opts=='Structure Only':
                                save_mask = mask
                            elif mask_opts=='Intersecting':
                                save_mask = intersecting_masks[f_idx]

                            if len(np.shape(save_mask))==2 or np.shape(save_mask)[-1]==1 or np.shape(save_mask)[-1]==3 or mask_save_format=='TIFF':
                                # Apply some kind of artificial color if not grayscale or RGB
                                mask_save_path = f'{save_path}/Masks/{f["properties"]["name"]}_{f_idx}.{save_format.lower()}'
                                Image.fromarray(mask).save(mask_save_path)
                            else:
                                # Just overwriting and saving as TIFF anyways
                                mask_save_path = f'{save_path}/Masks/{f["properties"]["name"]}_{f_idx}.tiff'
                                Image.fromarray(mask).save(mask_save_path)

            else:
                
                if any(['frame' in i for i in image_opts]):
                    image = get_feature_image(
                        feature=f,
                        tile_source = tile_url,
                        return_mask = save_masks,
                        frame_index = [i['frame'] for i in image_opts],
                        frame_colors=color_opts
                    )
                else:
                    image = get_feature_image(
                        feature=f,
                        tile_source = tile_url,
                        return_mask = save_masks,
                    )

                img_save_format = save_format
                if img_save_format=='OME-TIFF':
                    write_ome_tiff(
                        image,
                        save_path+f'/Images/{f["properties"]["name"]}_{f_idx}.ome.tiff',
                        channel_names,
                        [1.0,1.0],
                        1.0
                    )
                elif img_save_format in ['TIFF','PNG','JPG']:

                    if len(np.shape(image))==2 or np.shape(image)[-1]==1 or np.shape(image)[-1]==3 or img_save_format=='TIFF':
                        image_save_path = f'{save_path}/Images/{f["properties"]["name"]}_{f_idx}.{save_format.lower()}'
                        Image.fromarray(image).save(image_save_path)
                    else:
                        image_save_path = f'{save_path}/Images/{f["properties"]["name"]}_{f_idx}.tiff'
                        Image.fromarray(image).save(image_save_path)

    def download_property_data(self, feature_list, save_format, save_path):
        
        # Making a dataframe from feature properties:
        property_list = []
        for f in feature_list:
            property_list.append(f['properties'])
        
        structure_name = f['properties']['name']
        property_df = pd.json_normalize(property_list)

        if save_format == 'CSV':
            property_df.to_csv(save_path+f'/{structure_name}_properties.csv')
        elif save_format == 'XLSX':
            with pd.ExcelWriter(save_path+f'/{structure_name}_properties.xlsx') as writer:
                property_df.to_excel(writer,engine='openpyxl')
                writer.close()
            
    def download_annotations(self, feature_list, x_scale, y_scale, save_format, save_path):
        
        feature_collection = {
            'type': 'FeatureCollection',
            'features': feature_list
        }
        structure_name = feature_list[0]['properties']['name']

        feature_collection = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/x_scale,c[1]/y_scale),g),feature_collection)
        feature_collection['properties'] = {
            'name': structure_name,
            '_id': uuid.uuid4().hex[:24]
        }

        if save_format=='Aperio XML':
            export_format = 'aperio'
            save_path = save_path + f'/{structure_name}.xml'

        elif save_format=='Histomics (JSON)':
            export_format = 'histomics'
            save_path = save_path +f'/{structure_name}.json'

        elif save_format == 'GeoJSON':
            export_format = 'geojson'
            save_path = save_path +f'/{structure_name}.json'
        
        export_annotations(
            feature_collection,
            format = export_format,
            save_path = save_path
        )

    def pick_download_type(self, download_info):

        if download_info['download_type']=='Properties':
            self.download_property_data(
                download_info['features'],
                download_info['format'],
                download_info['folder']
            )
        elif download_info['download_type'] in ['Images','Masks','Images & Masks']:
            self.download_image_data(
                download_info['features'],
                download_info['x_scale'],
                download_info['y_scale'],
                download_info['tile_url'],
                download_info['save_masks'],
                download_info['image_opts'],
                download_info['mask_opts'],
                download_info['format'],
                download_info['combine'],
                download_info['folder']
            )
        elif download_info['download_type'] == 'Annotations':
            self.download_annotations(
                download_info['features'],
                download_info['x_scale'], 
                download_info['y_scale'], 
                download_info['format'],
                download_info['folder']
            )

    def create_zip_file(self, base_path, output_file):
        
        # Writing temporary data to a zip file
        with zipfile.ZipFile(output_file,'w', zipfile.ZIP_DEFLATED) as zip:
            for path,subdirs,files in os.walk(base_path):
                extras_in_path = path.split('/downloads/')[0]+'/downloads/'
                for name in files:
                    if not 'zip' in name:
                        zip.write(os.path.join(path,name),os.path.join(path.replace(extras_in_path,''),name))
        
            zip.close()

    def start_download_data(self, clicked, selected_structures, selected_data, selected_data_formats, slide_annotations, slide_markers, slide_info, channel_mix_frames, channel_mix_colors, channel_mix_checked, selected_data_channels, selected_mask_options):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        interval_disabled = False
        new_values = []
        button_disabled = True
        selected_structures = get_pattern_matching_value(selected_structures)
        selected_data = get_pattern_matching_value(selected_data)
        slide_annotations = json.loads(get_pattern_matching_value(slide_annotations))
        slide_info = json.loads(get_pattern_matching_value(slide_info))
        slide_markers = get_pattern_matching_value(slide_markers)
        
        base_download_folder = uuid.uuid4().hex[:24]
        if not os.path.exists(self.download_folder+base_download_folder):
            os.makedirs(self.download_folder+base_download_folder)

        # Specifying which download threads to deploy
        download_thread_list = []
        layer_names = [i['properties']['name'] for i in slide_annotations]
        for s_idx, struct in enumerate(selected_structures):
            if struct in layer_names:
                struct_features = slide_annotations[layer_names.index(struct)]['features']
            elif struct == 'Marked Structures':
                if not slide_markers is None:
                    struct_features = []
                    for m in slide_markers:
                        struct_features.extend(self.extract_marker_structures(m['props']['data'],slide_annotations))

            for d_idx, (data,data_format,data_channels,data_masks,data_channel_mix) in enumerate(zip(selected_data,selected_data_formats, selected_data_channels, selected_mask_options, channel_mix_checked)):
                if data in ['Images','Masks','Images & Masks']:
                    if not os.path.exists(self.download_folder+base_download_folder+'/'+data):
                        os.makedirs(self.download_folder+base_download_folder+'/'+data)

                    if data_masks=='Intersecting':
                        struct_features = [{'type': 'FeatureCollection', 'features': struct_features}, slide_annotations]

                    if data_channel_mix:
                        image_opts = [
                            {
                                'frame': slide_info['tiles_metadata']['channels'].index(c_name),
                                'name': c_name,
                                'color': channel_mix_colors[c_idx]['color']
                            }
                            for c_idx,c_name in enumerate(channel_mix_frames)
                        ]
                    else:
                        if 'frames' in slide_info['tiles_metadata']:
                            image_opts = [
                                {
                                    'frame': slide_info['tiles_metadata']['channels'].index(c_name),
                                    'name': c_name,
                                }
                                for c_name in data_channels
                            ]
                        else:
                            image_opts = [
                                {
                                    'name': i
                                }
                                for i in ['red','green','blue']
                            ]

                    download_thread_list.append(
                        {
                            'download_type': data,
                            'structure':struct,
                            'x_scale': slide_info['x_scale'],
                            'y_scale': slide_info['y_scale'],
                            'format': data_format,
                            'folder': self.download_folder+base_download_folder,
                            'features': struct_features,
                            'tile_url': slide_info['tiles_url'].replace('zxy/{z}/{x}/{y}','region'),
                            'save_masks': 'Masks' in data,
                            'image_opts': image_opts,
                            'mask_opts': data_masks,
                            'combine': '&' in data,
                            '_id': uuid.uuid4().hex[:24]
                        }
                    )    
                else:
                    download_thread_list.append(
                        {
                            'download_type': data,
                            'structure': struct,
                            'x_scale': slide_info['x_scale'],
                            'y_scale': slide_info['y_scale'],
                            'format': data_format,
                            'folder': self.download_folder+base_download_folder,
                            'features': struct_features,
                            '_id': uuid.uuid4().hex[:24]
                        }
                    )

        download_data_store = json.dumps({
            'selected_data': [],
            'base_folder':self.download_folder+base_download_folder,
            'zip_file_path': self.download_folder+base_download_folder+'/fusion_download.zip',
            'download_tasks': download_thread_list,
            'current_task': download_thread_list[0]['_id'],
            'completed_tasks': []
        })

        new_thread = threading.Thread(
            target = self.pick_download_type,
            name = download_thread_list[0]['_id'],
            args = [download_thread_list[0]],
            daemon = True
        )
        new_thread.start()       

        return [interval_disabled], [new_values], [new_values], [html.Div('Selected data descriptions will appear here')], [button_disabled],[download_data_store]

    def update_download_data(self, new_interval, download_info_store):
        
        new_interval = get_pattern_matching_value(new_interval)
        download_info_store = json.loads(get_pattern_matching_value(download_info_store))

        current_threads = [i.name for i in threading.enumerate()]
        if not 'current_task' in download_info_store:
            raise exceptions.PreventUpdate
        
        if not download_info_store['current_task'] in current_threads:
            download_info_store['completed_tasks'].append(download_info_store['current_task'])
            
            if 'download_tasks' in download_info_store:
                if len(download_info_store['download_tasks'])==1:

                    if not os.path.exists(download_info_store['zip_file_path']):
                        # This means that the last download task was completed, now creating a zip-file of the results
                        zip_files_task = uuid.uuid4().hex[:24]
                        task_name = 'Creating Zip File'
                        download_info_store['current_task'] = zip_files_task
                        del download_info_store['download_tasks'][0]

                        download_progress = 99

                        interval_disabled = False
                        modal_open = True
                        new_n_intervals = no_update
                        download_data = no_update

                        new_thread = threading.Thread(
                            target = self.create_zip_file,
                            name = zip_files_task,
                            args = [download_info_store['base_folder'],download_info_store['zip_file_path']],
                            daemon=True
                        )
                        new_thread.start()
                    else:
                        task_name = 'Zip File Created'

                        download_progress = 99
                        interval_disabled = True
                        modal_open = False
                        new_n_intervals = no_update
                        download_data = dcc.send_file(download_info_store['zip_file_path'])

                elif len(download_info_store['download_tasks'])==0:
                    # This means that the zip file has finished being created
                    task_name = 'All Done!'
                    interval_disabled = False
                    modal_open = False
                    new_n_intervals = 0
                    download_data = dcc.send_file(download_info_store['zip_file_path'])
                    del download_info_store['download_tasks']

                    download_progress = 100

                elif len(download_info_store['download_tasks'])>1:
                    # This means there are still some download tasks remaining, move to the next one
                    interval_disabled = False
                    modal_open = True
                    new_n_intervals = no_update
                    download_data = no_update
                    del download_info_store['download_tasks'][0]

                    download_info_store['current_task'] = download_info_store['download_tasks'][0]['_id']

                    task_name = f'{download_info_store["download_tasks"][0]["structure"]} {download_info_store["download_tasks"][0]["download_type"]}'

                    new_thread = threading.Thread(
                        target = self.pick_download_type,
                        name = download_info_store['current_task'],
                        args = [download_info_store['download_tasks'][0]],
                        daemon=True
                    )
                    new_thread.start()
                    
                    n_complete = len(download_info_store['completed_tasks'])
                    n_remaining = len(download_info_store['download_tasks'])
                    download_progress = int(100*(n_complete/(n_complete+n_remaining)))

                modal_children = html.Div([
                    dbc.ModalHeader(html.H4(f'Download Progress')),
                    dbc.ModalBody([
                        html.Div(
                            html.H6(f'Working on: {task_name}')
                        ),
                        dbc.Progress(
                            value = download_progress,
                            label = f'{download_progress}%'
                        )
                    ])
                ])
            else:
                # Clearing the directory containing download
                download_path = download_info_store['base_folder']
                rmtree(download_path)

                # Continuing with the current download task
                interval_disabled = True
                modal_open = False
                modal_children = no_update
                new_n_intervals = no_update
                download_data = no_update

                del download_info_store['base_folder']
                del download_info_store['zip_file_path']
                del download_info_store['completed_tasks']
                del download_info_store['current_task']

        else:
            # Continuing with the current download task
            interval_disabled = False
            modal_open = True
            modal_children = no_update
            new_n_intervals = no_update
            download_data = no_update
       
        updated_download_info = json.dumps(download_info_store)

        return [updated_download_info],[interval_disabled], [modal_open], [modal_children], [new_n_intervals], [download_data]
        



class GlobalPropertyPlotter(MultiTool):
    def __init__(self,
                 ignore_list: list = [],
                 property_depth: int = 6,
                 preloaded_properties: Union[pd.DataFrame,None] = None,
                 structure_column: Union[str,None] = None,
                 slide_column: Union[str,None] = None,
                 bbox_columns: Union[list,str,None] = None,
                 nested_prop_sep: str = ' --> '
                 ):
        
        super().__init__()
        self.ignore_list = ignore_list
        self.property_depth = property_depth
        self.preloaded_properties = preloaded_properties
        self.structure_column = structure_column
        self.slide_column = slide_column
        self.bbox_columns = bbox_columns
        self.nested_prop_sep = nested_prop_sep

        if not self.preloaded_properties is None:
            self.preloaded_options = [i for i in self.preloaded_properties.columns.tolist() if not i in ignore_list]
            self.property_tree, self.property_keys = self.generate_property_dict(self.preloaded_options)

        else:
            self.preloaded_options = None

    def __str__(self):
        return "Global Property Plotter"

    def extract_all_properties(self, session_data):
        # This function would use the session data to extract annotations, properties, and format them in a reasonable way
        session_properties = pd.DataFrame()
        for s in session_data['current']:
            slide_name = s['name']
            annotations = requests.get(s['annotations_url']).json()
            
            # Checking if these are histomics formatted or GeoJSON formatted
            is_histomics = detect_histomics(annotations)
            if is_histomics:
                annotations = histomics_to_geojson(annotations)

            metadata = requests.get(s['metadata_url']).json()

            slide_properties = pd.DataFrame()
            for ann in annotations:
                ann_properties = pd.json_normalize([i['properties'] for i in ann['features']],sep=self.nested_prop_sep)
                ann_properties['Structure'] = [ann['properties']['name']]*ann_properties.shape[0]
                ann_properties['Slide Name'] = [slide_name]*ann_properties.shape[0]

                # Pulling out slide-level metadata
                if 'user' in metadata:
                    ann_properties = pd.concat([ann_properties,pd.DataFrame.from_records([metadata]*ann_properties.shape[0])],axis=1,ignore_index=True)

                bbox_list = []
                for f in ann['features']:
                    bbox = list(shape(f['geometry']).bounds)
                    bbox_list.append({'min_x':bbox[0],'min_y':bbox[1],'max_x':bbox[2],'max_y':bbox[3]})

                if len(bbox_list)>0:
                    ann_cols = ann_properties.columns.tolist()
                    ann_properties = pd.concat([ann_properties,pd.DataFrame.from_records(bbox_list)],axis=1,ignore_index=True)
                    ann_properties.columns = ann_cols+['min_x','min_y','max_x','max_y']

                if not ann_properties.empty:
                    if slide_properties.empty:
                        slide_properties = ann_properties
                    else:
                        slide_properties = pd.concat([slide_properties,ann_properties],axis=0,ignore_index=True)
                
            if session_properties.empty:
                session_properties = slide_properties
            else:
                session_properties = pd.concat([session_properties,slide_properties],axis=0,ignore_index=True)

        self.preloaded_properties = session_properties
        self.preloaded_options = session_properties.select_dtypes(exclude='object').columns.tolist()
        self.structure_column = 'Structure'
        self.slide_column = 'Slide Name'
        self.bbox_columns = ['min_x','min_y','max_x','max_y']

    def load(self, component_prefix: int):
        self.component_prefix = component_prefix

        self.title = 'Global Property Plotter'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )        
        
        self.get_callbacks()

    def __str__(self):
        return 'Global Property Plotter'

    def generate_property_dict(self, available_properties, title: str = 'Properties'):
        all_properties = {
            'title': title,
            'key': '0',
            'children': []
        }

        def add_prop_level(level_children, prop, index_list):
            new_keys = {}
            if len(level_children)==0:
                if not prop[0] in self.ignore_list:
                    new_key = f'{"-".join(index_list)}-0'
                    p_dict = {
                        'title': prop[0],
                        'key': new_key,
                        'children': []
                    }
                    l_dict = p_dict['children']
                    if len(prop)==1:
                        new_keys[new_key] = prop[0]
                    for p_idx,p in enumerate(prop[1:]):
                        if not p in self.ignore_list:
                            new_key = f'{"-".join(index_list+["0"]*(p_idx+2))}'
                            l_dict.append({
                                'title': p,
                                'key': new_key,
                                'children': []
                            })
                            l_dict = l_dict[0]['children']

                            new_keys[new_key] = self.nested_prop_sep.join(prop[:p_idx+2])

                    level_children.append(p_dict)
            else:
                for p_idx,p in enumerate(prop):
                    if not p in self.ignore_list:
                        if any([p==i['title'] for i in level_children]):
                            title_idx = [i['title'] for i in level_children].index(p)
                            level_children = level_children[title_idx]['children']
                            index_list.append(str(title_idx))
                        else:
                            new_key = f'{"-".join(index_list)}-{len(level_children)}'
                            other_children = len(level_children)
                            level_children.append({
                                'title': p,
                                'key': new_key,
                                'children': []
                            })
                            level_children = level_children[-1]['children']
                            index_list.append(str(other_children))
                            if p_idx==len(prop)-1:
                                new_keys[new_key] = self.nested_prop_sep.join(prop[:p_idx+1])
            
            return new_keys
        
        list_levels = [i.split(self.nested_prop_sep) if self.nested_prop_sep in i else [i] for i in available_properties]
        unique_levels = list(set([len(i) for i in list_levels]))
        sorted_level_idxes = np.argsort(unique_levels)[::-1]
        property_keys = {}
        for s in sorted_level_idxes:
            depth_count = unique_levels[s]
            props_with_level = [i for i in list_levels if len(i)==depth_count]
            for p in props_with_level:
                feature_children = all_properties['children']
                property_keys = property_keys | add_prop_level(feature_children,p,['0'])


        return all_properties, property_keys

    def extract_property_info(self):

        if not self.preloaded_properties is None:
            
            property_info = {}
            for p in self.preloaded_properties:
                if any([i in str(self.preloaded_properties[p].dtype).lower() for i in ['object','category','string']]):
                    property_info[p] = {
                        'unique': self.preloaded_properties[p].unique().tolist(),
                        'distinct': int(self.preloaded_properties[p].nunique())
                    }
                elif any([i in str(self.preloaded_properties[p].dtype).lower() for i in ['int','float','bool']]):
                    property_info[p] = {
                        'min': float(self.preloaded_properties[p].min()),
                        'max': float(self.preloaded_properties[p].max()),
                        'distinct': int(self.preloaded_properties[p].nunique())
                    }
                else:
                    print(f'property: {p} has dtype {self.preloaded_properties[p].dtype} which is not implemented!')

            return property_info
        else:
            return None

    def update_layout(self, session_data:dict, use_prefix:bool):
        
        
        if self.preloaded_properties is None:
            self.extract_all_properties(session_data)
            self.property_tree, self.property_keys = self.generate_property_dict(self.preloaded_options)

        property_info = self.extract_property_info()

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        html.H3('Global Property Plotter')
                    ]),
                    html.Hr(),
                    dbc.Row(
                        'Select one or a combination of properties to generate a plot.'
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Label('Select properties below: ',html_for = {'type': 'global-property-plotter-drop','index': 0}),
                        dmc.Switch(
                            id = {'type': 'global-property-plotter-drop-type','index': 0},
                            offLabel = 'Dropdown Menu',
                            onLabel = 'Tree View',
                            size = 'lg',
                            checked = False,
                            description = 'Select related properties in groups with "Tree View" or select properties individually with "Dropdown Menu"'
                        )
                    ]),
                    dcc.Store(
                        id = {'type': 'global-property-plotter-session-store','index': 0},
                        data = json.dumps(session_data),
                        storage_type = 'memory'
                    ),
                    dcc.Store(
                        id = {'type': 'global-property-plotter-property-info','index': 0},
                        data = json.dumps(property_info),
                        storage_type = 'memory'
                    ),
                    dbc.Row([
                        html.Div(
                            dcc.Dropdown(
                                options = [] if self.preloaded_options is None else self.preloaded_options,
                                value = [],
                                id = {'type': 'global-property-plotter-drop','index': 0},
                                multi = True,
                                placeholder = 'Properties'
                            ),
                            id = {'type': 'global-property-plotter-drop-div','index': 0}
                        )
                    ]),
                    html.Hr(),
                    dbc.Row(
                        dbc.Label('Select structures to include: ', html_for = {'type': 'global-property-plotter-structures','index': 0})
                    ),
                    dbc.Row([
                        dcc.Dropdown(
                            options = [] if self.structure_column is None or self.preloaded_properties is None else self.preloaded_properties[self.structure_column].unique().tolist(),
                            value = [],
                            id = {'type': 'global-property-plotter-structures','index': 0},
                            multi = True,
                            placeholder = 'Structures'
                        ),
                    ]),
                    html.Hr(),
                    dbc.Row([
                        dbc.Label('Select additional metadata filters: ',html_for = {'type': 'global-property-plotter-add-filter-parent','index': 0}),
                        html.Div('Click the icon below to add a filter.')
                    ]),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'global-property-plotter-add-filter-parent','index': 0},
                            children = []
                        )
                    ],align = 'center'),
                    dbc.Row([
                        dbc.Col([
                            html.Div([
                                html.A(
                                    html.I(
                                        className = 'bi bi-filter-circle fa-2x',
                                        n_clicks = 0,
                                        id = {'type': 'global-property-plotter-add-filter-butt','index': 0}
                                    )
                                ),
                                dbc.Tooltip(
                                    target = {'type': 'global-property-plotter-add-filter-butt','index': 0},
                                    children = 'Click to add a filter.'
                                )
                            ])
                        ])
                    ],align='center',justify='center'),
                    html.Hr(),
                    dbc.Row([
                        dbc.Label('Select a label to apply to points in the plot',html_for = {'type': 'global-property-plotter-label-drop','index': 0})
                    ]),
                    dbc.Row([
                        dcc.Dropdown(
                            options = [] if self.preloaded_properties is None else self.preloaded_properties.columns.tolist(),
                            value = [],
                            multi = False,
                            id = {'type': 'global-property-plotter-label-drop','index': 0},
                            placeholder = 'Label'
                        )
                    ],style = {'marginBottom':'10px'}),
                    dbc.Row([
                        dbc.Button(
                            'Generate Plot!',
                            id = {'type': 'global-property-plotter-plot-butt','index': 0},
                            n_clicks = 0,
                            className = 'd-grid col-12 mx-auto'
                        )
                    ],style = {'marginBottom': '10px'}),
                    dbc.Row([
                        dbc.Col([
                            dcc.Loading([
                                dcc.Store(
                                    id = {'type': 'global-property-plotter-store','index': 0},
                                    data = json.dumps({'property_names': [], 'structure_names': [], 'label_names': [], 'filters': [], 'data': []}),
                                    storage_type = 'memory'
                                ),
                                html.Div(
                                    id = {'type': 'global-property-plotter-plot-div','index': 0},
                                    children = []
                                )
                            ])
                        ],md = 6),
                        dbc.Col([
                            dcc.Loading(
                                html.Div(
                                    id = {'type': 'global-property-plotter-selected-div','index': 0},
                                    children = []
                                )
                            )
                        ],md=6)
                    ])
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow':'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(layout)

        return layout

    def gen_layout(self, session_data: dict):
        
        self.blueprint.layout = self.update_layout(session_data,use_prefix=False)

    def get_callbacks(self):
        
        #TODO: Callbacks
        # Callback for updating type of feature selector (either dropdown or tree)
        # Callback for running statistics
        # Callback for exporting plot data

        # Changing type of property selector (from dropdown to tree and back)
        self.blueprint.callback(
            [
                Input({'type': 'global-property-plotter-drop-type','index':ALL},'checked')
            ],
            [
                Output({'type': 'global-property-plotter-drop-div','index': ALL},'children')
            ]
        )(self.update_drop_type)

        # Updating filters
        self.blueprint.callback(
            [
                Input({'type': 'global-property-plotter-add-filter-butt','index': ALL},'n_clicks'),
                Input({'type': 'global-property-plotter-remove-property-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'global-property-plotter-add-filter-parent','index': ALL},'children')
            ],
            [
                State({'type': 'global-property-plotter-property-info','index': ALL},'data')
            ]
        )(self.update_filter_properties)

        # Updating filter property selector type based on selected property
        self.blueprint.callback(
            [
                Input({'type': 'global-property-plotter-filter-property-drop','index': MATCH},'value')
            ],
            [
                Output({'type': 'global-property-plotter-selector-div','index': MATCH},'children')
            ],
            [
                State({'type': 'global-property-plotter-property-info','index': ALL},'data')
            ]
        )(self.update_property_selector)

        # Updating store containing properties, structures, labels, and filters
        self.blueprint.callback(
            [
                Input({'type': 'global-property-plotter-drop','index': ALL},'value'),
                Input({'type': 'global-property-plotter-drop','index': ALL},'checked'),
                Input({'type': 'global-property-plotter-structures','index': ALL},'value'),
                Input({'type': 'global-property-plotter-label-drop','index': ALL},'value'),
                Input({'type': 'global-property-plotter-filter-property-mod','index': ALL},'value'),
                Input({'type': 'global-property-plotter-remove-property-icon','index': ALL},'n_clicks'),
                Input({'type': 'global-property-plotter-filter-selector','index': ALL},'value')
                
            ],
            [
                Output({'type': 'global-property-plotter-store','index': ALL},'data')
            ],
            [
                State({'type': 'global-property-plotter-add-filter-parent','index': ALL},'children'),
                State({'type': 'global-property-plotter-store','index': ALL},'data')
            ]
        )(self.update_properties_and_filters)

        # Generating plot of selected properties, structures, labels
        self.blueprint.callback(
            [
                Input({'type': 'global-property-plotter-plot-butt','index':ALL},'n_clicks')
            ],
            [
                Output({'type': 'global-property-plotter-store','index': ALL},'data'),
                Output({'type': 'global-property-plotter-plot-div','index': ALL},'children')
            ],
            [
                State({'type': 'global-property-plotter-store','index': ALL},'data')
            ]
        )(self.generate_plot)

        # Selecting points within the plot
        self.blueprint.callback(
            [
                Input({'type': 'global-property-plotter-plot','index': ALL},'selectedData'),
            ],
            [
                Output({'type': 'global-property-plotter-selected-div','index': ALL},'children')
            ],
            [
                State({'type': 'global-property-plotter-session-store','index':ALL},'data')
            ]
        )(self.select_data_from_plot)

    def update_drop_type(self, switch_switched):
        """Update the property selection mode (either dropdown menu or tree view)

        :param switch_switched: Switch selected
        :type switch_switched: list
        :return: New property selector component
        :rtype: list
        """

        switch_switched = get_pattern_matching_value(switch_switched)
        if switch_switched:
            # This is using the Tree View
            property_drop = dta.TreeView(
                id = {'type': f'{self.component_prefix}-global-property-plotter-drop','index': 0},
                multiple = True,
                checkable = True,
                checked = [],
                selected = [],
                expanded = [],
                data = self.property_tree
            )
        else:
            property_drop = dcc.Dropdown(
                options = [] if self.preloaded_options is None else self.preloaded_options,
                value = [],
                id = {'type': f'{self.component_prefix}-global-property-plotter-drop','index': 0},
                multi = True,
                placeholder = 'Properties'
            )

        return [property_drop]

    def update_properties_and_filters(self, property_selection, property_checked, structure_selection, label_selection, filter_prop_mod, filter_prop_remove, filter_prop_selector, property_divs,current_data):
        """Updating the properties, structures, and filters incorporated into the main plot

        :param property_selection: Properties selected for plotting
        :type property_selection: list
        :param property_checked: Properties selected from property tree view
        :type property_checked: list
        :param structure_selection: Structures selected to be plotted
        :type structure_selection: list
        :param label_selection: Label selected for the plot
        :type label_selection: list
        :param remove_prop: Remove property filter clicked
        :type remove_prop: list
        :param prop_mod: Modifier applied to property filter changed
        :type prop_mod: list
        :param property_divs: Children of property filter parent has been updated
        :type property_divs: list
        :param current_data: Contents of the global-property-store, updated by this plugin.
        :type current_data: list
        :return: Updated global-property-store object
        :rtype: list
        """
        
        current_data = json.loads(get_pattern_matching_value(current_data))
        property_divs = get_pattern_matching_value(property_divs)

        processed_prop_filters = self.parse_filter_divs(property_divs)

        current_data['filters'] = processed_prop_filters
        if not get_pattern_matching_value(property_selection) is None:
            current_data['property_names'] = get_pattern_matching_value(property_selection)
        elif not get_pattern_matching_value(property_checked) is None:
            current_data['property_names'] = [self.property_keys[i] for i in get_pattern_matching_value(property_checked) if i in self.property_keys]
        current_data['structure_names'] = get_pattern_matching_value(structure_selection)
        current_data['label_names'] = get_pattern_matching_value(label_selection)
        
        return [json.dumps(current_data)]

    def generate_plot(self, butt_click, current_data):
        """Generate a new plot based on selected properties

        :param butt_click: Generate Plot button clicked
        :type butt_click: list
        :param current_data: Dictionary containing current selected properties (in a list)
        :type current_data: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_data = json.loads(get_pattern_matching_value(current_data))
        property_names = current_data['property_names']
        structure_names = current_data['structure_names']
        label_names = current_data['label_names']
        filters = current_data['filters']

        if len(property_names)==0 | len(structure_names)==0:
            raise exceptions.PreventUpdate
        
        # Applying filters to the current data
        filtered_properties = pd.DataFrame()
        if not self.preloaded_properties is None:
            filtered_properties = self.preloaded_properties[self.preloaded_properties[self.structure_column].isin(structure_names)]

            include_list = [(False,)]*filtered_properties.shape[0]
            if len(filters)>0:
                for f in filters:
                    if f['name'] in filtered_properties:
                        if not filtered_properties[f['name']].dtype=='object':
                            structure_status = [f['range'][0]<=i and f['range'][1]>=i for i in filtered_properties[f['name']].tolist()]
                        else:
                            structure_status = [i in f['range'] for i in filtered_properties[f['name']].tolist()]

                        if f['mod']=='not':
                            structure_status = [not(i) for i in structure_status]

                        if f['mod'] in ['not','and']:
                            del_count = 0
                            for idx,i in enumerate(structure_status):
                                if not i:
                                    del include_list[idx-del_count]
                                    del_count+=1
                                else:
                                    include_list[idx-del_count]+=(True,)

                            filtered_properties = filtered_properties.loc[structure_status,:]
                        elif f['mod']=='or':
                            include_list = [i+(j,) for i,j in zip(include_list,structure_status)]

                filtered_properties = filtered_properties.loc[[any(i) for i in include_list]]
        else:
            #TODO: Grab the properties from the current visualization session or query them in some other way
            pass

        if filtered_properties.empty:
            raise exceptions.PreventUpdate
        else:
            current_data['data'] = filtered_properties.to_dict('records')

            if len(property_names)==1:
                plot_fig = self.gen_violin_plot(filtered_properties, label_names, property_names[0], [self.slide_column]+self.bbox_columns)
            elif len(property_names)==2:
                plot_fig = self.gen_scatter_plot(filtered_properties,property_names,None,[self.slide_column]+self.bbox_columns)
            elif len(property_names)>2:
                
                umap_columns = self.gen_umap_cols(filtered_properties,property_names)
                filtered_properties['UMAP1'] = umap_columns['UMAP1'].tolist()
                filtered_properties['UMAP2'] = umap_columns['UMAP2'].tolist()

                current_data['data'] = filtered_properties.to_dict('records')
 
                plot_fig = self.gen_scatter_plot(filtered_properties,['UMAP1','UMAP2'],label_names,[self.slide_column]+self.bbox_columns)

            return_fig = dcc.Graph(
                id = {'type': f'{self.component_prefix}-global-property-plotter-plot','index': 0},
                figure = plot_fig
            )

        return [json.dumps(current_data)],[return_fig]

    def gen_violin_plot(self, data_df:pd.DataFrame, label_col: Union[str,None], property_column: str, customdata_columns:list):
        """Generating a violin plot using provided data, property columns, and customdata


        :param data_df: Extracted data from current GeoJSON features
        :type data_df: pd.DataFrame
        :param label_col: Name of column to use for label
        :type label_col: Union[str,None]
        :param property_column: Name of column to use for property (y-axis) value
        :type property_column: str
        :param customdata_columns: Names of columns to use for customdata (accessible from clickData and selectedData)
        :type customdata_columns: list
        :return: Figure containing violin plot data
        :rtype: go.Figure
        """
        figure = go.Figure(
            data = go.Violin(
                x = None if label_col is None else data_df[label_col],
                y = data_df[property_column],
                customdata = data_df[customdata_columns] if not customdata_columns is None else None,
                points = 'all',
                pointpos=0,
                spanmode='hard'
            )
        )
        
        figure.update_layout(
            legend = dict(
                orientation='h',
                y = 0,
                yanchor='top',
                xanchor='left'
            ),
            title = '<br>'.join(
                textwrap.wrap(
                    f'{property_column}',
                    width=80
                )
            ),
            yaxis_title = dict(
                text = '<br>'.join(
                    textwrap.wrap(
                        f'{property_column}',
                        width=80
                    )
                ),
                font = dict(size = 10)
            ),
            xaxis_title = dict(
                text = '<br>'.join(
                    textwrap.wrap(
                        label_col,
                        width=80
                    )
                ) if not label_col is None else 'Group',
                font = dict(size = 10)
            ),
            margin = {'r':0,'b':25}
        )

        return figure

    def gen_scatter_plot(self, data_df:pd.DataFrame, plot_cols:list, label_col:Union[str,None], customdata_cols:list):
        """Generating a 2D scatter plot using provided data


        :param data_df: Extracted data from current GeoJSON features
        :type data_df: pd.DataFrame
        :param plot_cols: Names of columns containing properties for the scatter plot
        :type plot_cols: list
        :param label_cols: Name of column to use to label markers.
        :type label_cols: Union[str,None]
        :param customdata_cols: Names of columns to use for customdata on plot
        :type customdata_cols: list
        :return: Scatter plot figure
        :rtype: go.Figure
        """
        if not label_col is None:
            figure = go.Figure(
                data = px.scatter(
                    data_frame=data_df,
                    x = plot_cols[0],
                    y = plot_cols[1],
                    color = label_col,
                    custom_data = customdata_cols,
                    title = '<br>'.join(
                        textwrap.wrap(
                            f'Scatter plot of {plot_cols[0]} and {plot_cols[1]} labeled by {label_col}',
                            width = 60
                            )
                        )
                )
            )
            if not data_df[label_col].dtype == np.number:
                figure.update_layout(
                    legend = dict(
                        orientation='h',
                        y = 0,
                        yanchor='top',
                        xanchor='left'
                    ),
                    margin = {'r':0,'b':25}
                )
            else:

                custom_data_idx = [i for i in range(data_df.shape[1]) if data_df.columns.tolist()[i] in customdata_cols]
                figure = go.Figure(
                    go.Scatter(
                        x = data_df[plot_cols[0]].values,
                        y = data_df[plot_cols[1]].values,
                        customdata = data_df.iloc[:,custom_data_idx].to_dict('records'),
                        mode = 'markers',
                        marker = {
                            'color': data_df[label_col].values,
                            'colorbar':{
                                'title': label_col
                            },
                            'colorscale':'jet'
                        },
                        text = data_df[label_col].values,
                        hovertemplate = "label: %{text}"

                    )
                )

        else:

            figure = go.Figure(
                data = px.scatter(
                    data_frame=data_df,
                    x = plot_cols[0],
                    y = plot_cols[1],
                    color = None,
                    custom_data = customdata_cols,
                    title = '<br>'.join(
                        textwrap.wrap(
                            f'Scatter plot of {plot_cols[0]} and {plot_cols[1]}',
                            width = 60
                            )
                        )
                )
            )

        return figure

    def gen_umap_cols(self, data_df:pd.DataFrame, property_columns: list)->pd.DataFrame:
        """Scale and run UMAP for dimensionality reduction


        :param data_df: Extracted data from current GeoJSON features
        :type data_df: pd.DataFrame
        :param property_columns: Names of columns containing properties for UMAP plot
        :type property_columns: list
        :return: Dataframe containing colunns named UMAP1 and UMAP2
        :rtype: pd.DataFrame
        """
        quant_data = data_df.loc[:,[i for i in property_columns if i in data_df.columns]].fillna(0)
        for p in property_columns:
            quant_data[p] = pd.to_numeric(quant_data[p],errors='coerce')
        quant_data = quant_data.values
        feature_data_means = np.nanmean(quant_data,axis=0)
        feature_data_stds = np.nanstd(quant_data,axis=0)

        scaled_data = (quant_data-feature_data_means)/feature_data_stds
        scaled_data[np.isnan(scaled_data)] = 0.0
        scaled_data[~np.isfinite(scaled_data)] = 0.0
        umap_reducer = UMAP()
        embeddings = umap_reducer.fit_transform(scaled_data)
        umap_df = pd.DataFrame(data = embeddings, columns = ['UMAP1','UMAP2']).fillna(0)

        umap_df.columns = ['UMAP1','UMAP2']
        umap_df.reset_index(drop=True, inplace=True)

        return umap_df

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
                filter_name = div_children[0]['props']['children'][1]['props']['children'][0]['props']['value']
                if 'props' in div_children[1]['props']['children']:
                    if 'value' in div_children[1]['props']['children']['props']:
                        filter_value = div_children[1]['props']['children']['props']['value']
                    else:
                        filter_value = div_children[1]['props']['children']['props']['children']['props']['value']
                    
                    if not any([i is None for i in [filter_mod,filter_name,filter_value]]):
                        processed_filters.append({
                            'mod': filter_mod,
                            'name': filter_name,
                            'range': filter_value
                        })

        return processed_filters

    def update_property_selector(self, property_value:str, property_info:list):
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
        
        property_info = json.loads(get_pattern_matching_value(property_info))
        property_values = property_info[property_value]

        if 'min' in property_values:
            # Used for numeric type filters
            values_selector = html.Div(
                dcc.RangeSlider(
                    id = {'type':f'{self.component_prefix}-global-property-plotter-filter-selector','index': ctx.triggered_id['index']},
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
                    id = {'type': f'{self.component_prefix}-global-property-plotter-filter-selector','index': ctx.triggered_id['index']},
                    options = property_values['unique'],
                    value = property_values['unique'],
                    multi = True
                )
            )

        return values_selector 

    def update_filter_properties(self, add_click:list, remove_click:list, property_info:list):
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
        property_info = json.loads(get_pattern_matching_value(property_info))

        if 'global-property-plotter-add-filter-butt' in ctx.triggered_id['type']:

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
                                id = {'type': f'{self.component_prefix}-global-property-plotter-filter-property-mod','index': add_click}
                            )
                        ],md=2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = list(property_info.keys()),
                                value = [],
                                multi = False,
                                placeholder = 'Select property',
                                id = {'type': f'{self.component_prefix}-global-property-plotter-filter-property-drop','index':add_click}
                            )
                        ],md=8),
                        dbc.Col([
                            html.A(
                                html.I(
                                    id = {'type': f'{self.component_prefix}-global-property-plotter-remove-property-icon','index': add_click},
                                    n_clicks = 0,
                                    className = 'bi bi-x-circle-fill fa-2x',
                                    style = {'color': 'rgb(255,0,0)'}
                                )
                            )
                        ], md = 2)
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-global-property-plotter-selector-div','index': add_click},
                        children = []
                    )
                ])

            properties_div.append(new_property_div())

        elif 'global-property-plotter-remove-property-icon' in ctx.triggered_id['type']:

            values_to_remove = []
            for i, val in enumerate(remove_click):
                if val:
                    values_to_remove.insert(0,i)

            for v in values_to_remove:
                del properties_div[v]

        
        return [properties_div]
    
    def select_data_from_plot(self, selected_data, session_data):
        """Select point(s) from the plot and extract the image from that/those point(s)

        :param selected_data: Multiple points selected using either a box or lasso select
        :type selected_data: list
        :param session_data: Data for each slide in the current session
        :type session_data: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(get_pattern_matching_value(session_data))
        selected_data = get_pattern_matching_value(selected_data)

        session_names = [i['name'] for i in session_data['current']]
        selected_image_list = []
        selected_image = go.Figure()
        for s_idx,s in enumerate(selected_data['points']):
            if type(s['customdata'])==list:
                s_slide = s['customdata'][0]
                s_bbox = s['customdata'][1:]
            elif type(s['customdata'])==dict:
                s_custom = list(s['customdata'].values())
                s_slide = s_custom[0]
                s_bbox = s_custom[1:]

            if s_slide in session_names:
                image_region = Image.open(
                    BytesIO(
                        requests.get(
                            session_data['current'][session_names.index(s_slide)]['regions_url']+f'?top={s_bbox[1]}&left={s_bbox[0]}&bottom={s_bbox[3]}&right={s_bbox[2]}'
                        ).content
                    )
                )

                selected_image_list.append(image_region)

        if len(selected_image_list)==1:
            selected_image = go.Figure(
                data = px.imshow(selected_image_list[0]),
                layout = {'margin':{'t':0,'b':0,'l':0,'r':0}}
                )
        elif len(selected_image_list)>1:
            image_dims = [np.array(i).shape for i in selected_image_list]
            max_height = max([i[0] for i in image_dims])
            max_width = max([i[1] for i in image_dims])

            modded_images = []
            for img in selected_image_list:
                img_width, img_height = img.size
                delta_width = max_width - img_width
                delta_height = max_height - img_height

                pad_width = delta_width // 2
                pad_height = delta_height // 2

                mod_img = np.array(
                    ImageOps.expand(
                        img,
                        border = (
                            pad_width,
                            pad_height,
                            delta_width - pad_width,
                            delta_height - pad_height
                        ),
                        fill=0
                    )
                )
                modded_images.append(mod_img)

            selected_image = go.Figure(
                data = px.imshow(np.stack(modded_images,axis=0),animation_frame=0,binary_string=True),
                layout = {'margin':{'t':0,'b':0,'l':0,'r':0}}
                )
        else:
            selected_image = go.Figure()
            print(f'No images found')
            print(f'selected:{selected_data}')

        return [dcc.Graph(figure = selected_image)]



