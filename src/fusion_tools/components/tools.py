"""

Visualization tools which can be linked to SlideMap components (but don't have to be)


"""

import os
import sys
import json
import numpy as np
import pandas as pd
import textwrap
import re

from typing_extensions import Union
from shapely.geometry import box, shape
import plotly.express as px
import plotly.graph_objects as go
from umap import UMAP

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
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import find_intersecting
from fusion_tools.utils.stats import get_label_statistics, run_wilcox_rank_sum



class Tool:
    """General class for interactive components that visualize, edit, or perform analyses on data.
    """
    pass

class OverlayOptions(Tool):
    """OverlayOptions Tool which enables editing overlay visualization properties including line color, fill color, and filters.

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self,
                 geojson_anns: Union[list,dict],
                 reference_object: Union[str,None] = None,
                 ignore_list: list = []
                 ):
        """Constructor method

        :param geojson_anns: Individual or list of GeoJSON formatted annotations.
        :type geojson_anns: Union[list,dict]
        :param reference_object: Path to larger object containing information on GeoJSON features, defaults to None
        :type reference_object: Union[str,None], optional
        :param ignore_list: List of properties to exclude from visualization. These can include any internal or private properties that are not desired to be viewed by the user or used for filtering/overlay colors., defaults to []
        :type ignore_list: list, optional
        """

        self.reference_object = reference_object
        self.overlay_options, self.feature_names, self.overlay_info = self.extract_overlay_options(geojson_anns, reference_object,ignore_list)
        
        self.title = 'Overlay Options'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        # Add callbacks here
        self.get_callbacks()

    def extract_overlay_options(self,geojson_anns: Union[list,dict],reference_object:Union[str,None],ignore_list:list):
        """Function to extract properties which are accessible for overlay and filters.

        :param geojson_anns: Individual or list of multiple GeoJSON formatted annotations applied to the current image.
        :type geojson_anns: Union[list,dict]
        :param reference_object: Path to external data container.
        :type reference_object: Union[str,None]
        :param ignore_list: List of properties to exclude from overlay generation and filtering.
        :type ignore_list: list
        :return: Properties extracted from GeoJSON objects, names for each structure, and summary information for each property
        :rtype: tuple
        """
        geojson_properties = []
        feature_names = []
        property_info = {}
        for ann in geojson_anns:
            feature_names.append(ann['properties']['name'])
            for f in ann['features']:
                f_props = list(f['properties'].keys())
                for p in f_props:
                    # Checking for sub-properties: (only going 1 level)
                    if type(f['properties'][p])==dict:
                        sub_props = []
                        for sup in list(f['properties'][p].keys()):
                            if not sup==p:
                                sub_prop_name = f'{p} --> {sup}'
                                sub_props.append(sub_prop_name)
                                
                                f_sup_val = f['properties'][p][sup]

                                if not sub_prop_name in property_info:
                                    if type(f_sup_val) in [int,float]:
                                        property_info[sub_prop_name] = {
                                            'min': f_sup_val,
                                            'max': f_sup_val,
                                            'distinct': 1
                                        }
                                    elif type(f_sup_val) in [str]:
                                        property_info[sub_prop_name] = {
                                            'unique': [f_sup_val],
                                            'distinct': 1
                                        }

                                else:
                                    if type(f_sup_val) in [int,float]:
                                        if f_sup_val < property_info[sub_prop_name]['min']:
                                            property_info[sub_prop_name]['min'] = f_sup_val
                                            property_info[sub_prop_name]['distinct']+=1

                                        if f_sup_val > property_info[sub_prop_name]['max']:
                                            property_info[sub_prop_name]['max'] = f_sup_val
                                            property_info[sub_prop_name]['distinct'] += 1

                                    elif type(f_sup_val) in [str]:
                                        if not f_sup_val in property_info[sub_prop_name]['unique']:
                                            property_info[sub_prop_name]['unique'].append(f_sup_val)
                                            property_info[sub_prop_name]['distinct']+=1

                                sub_props.append(sub_prop_name)
                    else:
                        sub_props = [p]

                        f_sup_val = f['properties'][p]

                        if not p in property_info:
                            if type(f_sup_val) in [int,float]:
                                property_info[p] = {
                                    'min': f_sup_val,
                                    'max': f_sup_val,
                                    'distinct': 1
                                }
                            else:
                                property_info[p] = {
                                    'unique': [f_sup_val],
                                    'distinct': 1
                                }
                        else:
                            if type(f_sup_val) in [int,float]:
                                if f_sup_val < property_info[p]['min']:
                                    property_info[p]['min'] = f_sup_val
                                    property_info[p]['distinct'] += 1
                                
                                elif f_sup_val > property_info[p]['max']:
                                    property_info[p]['max'] = f_sup_val
                                    property_info[p]['distinct']+=1

                            elif type(f_sup_val) in [str]:
                                if not f_sup_val in property_info[p]['unique']:
                                    property_info[p]['unique'].append(f_sup_val)
                                    property_info[p]['distinct']+=1

                    new_props = [i for i in sub_props if not i in geojson_properties and not i in ignore_list]
                    geojson_properties.extend(new_props)

        #TODO: After loading an experiment, reference the file here for additional properties
        
        geojson_properties = sorted(geojson_properties)

        return geojson_properties, feature_names, property_info

    def gen_layout(self):
        """Generating OverlayOptions layout, added to DashBlueprint() object to be embedded in larger layout.

        :return: OverlayOptions layout
        :rtype: dash.html.Div.Div
        """
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
                                options = [
                                    {'label': i, 'value': i}
                                    for i in self.overlay_options
                                ],
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
                            data = json.dumps(self.overlay_info),
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
                        ),
                        html.Div(
                            html.A(html.I(
                                className = 'bi bi-filter-circle fa-2x',
                                n_clicks = 0,
                                id = {'type': 'add-filter-butt','index': 0},
                                style = {'display': 'inline-block','position': 'relative','left': '45%','right':'50%'}
                            ))
                        )
                    ],align='center'),
                    html.Hr(),
                    dbc.Row(
                        dbc.Label('Update Structure Boundary Color',html_for = {'type': 'feature-lineColor-opts','index': 0})
                    ),
                    dbc.Row([
                        dbc.Tabs(
                            id = {'type': 'feature-lineColor-opts','index': 0},
                            children = [
                                dbc.Tab(
                                    children = [
                                        dmc.ColorPicker(
                                            id = {'type': 'feature-lineColor','index': f_idx},
                                            format = 'hex',
                                            value = '#FFFFFF',
                                            fullWidth=True
                                        ),
                                        dbc.Button(
                                            id = {'type': 'feature-lineColor-butt','index': f_idx},
                                            children = ['Update Boundary Color'],
                                            className = 'd-grid col-12 mx-auto',
                                            n_clicks = 0
                                        )
                                    ],
                                    label = f
                                )
                                for f_idx, f in enumerate(self.feature_names)
                            ]
                        )
                    ]),
                    dbc.Row([
                        dbc.Accordion(
                            id = {'type':'adv-overlay-accordion','index': 0},
                            start_collapsed = True,
                            children = [
                                dbc.AccordionItem(
                                    id = {'type':'adv-overlay-accordionitem','index':0},
                                    title = html.P('Advanced Overlay Options',style={'font-style':'italic'}),
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
                                                    dbc.InputGroup([
                                                        dbc.Input(
                                                            id = {'type': 'adv-overlay-line-width','index': 0},
                                                            placeholder = 'Line Width',
                                                            type = 'number',
                                                            value = 5,
                                                            min = 0,
                                                            max = 100,
                                                            step = 1
                                                        ),
                                                        dbc.InputGroupText(
                                                            'pixels'
                                                        )
                                                    ]),
                                                    dbc.FormText(
                                                        'Width of annotation boundary lines'
                                                    ),
                                                    html.Hr(),
                                                    dbc.Select(
                                                        id = {'type': 'adv-overlay-colormap','index': 0},
                                                        placeholder = 'Select colormap options',
                                                        options = [
                                                            {'label': '','value': '', 'disabled': False}
                                                        ]
                                                    )
                                                ]),
                                                html.Div(
                                                    dbc.Button(
                                                        'Update Overlays!',
                                                        className = 'd-grid col-12 mx-auto',
                                                        id = {'type': 'adv-overlay-butt','index': 0},
                                                        n_clicks = 0
                                                    )
                                                )
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

        return layout

    def get_callbacks(self):
        """Initializing callbacks for OverlayOptions Tool
        """
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
            ]
        )(self.update_overlays)

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
                State({'type': 'adv-overlay-line-width','index': ALL},'value'),
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
                State({'type': 'overlay-property-info','index': ALL},'data')
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

    def add_filter(self, add_filter_click, delete_filter_click,overlay_info_state):
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
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))

        if len(list(overlay_info_state.keys()))==0:
            raise exceptions.PreventUpdate

        active_filters = Patch()
        if ctx.triggered_id['type']=='delete-filter':

            values_to_remove = []
            for i,val in enumerate(delete_filter_click):
                if val:
                    values_to_remove.insert(0,i)
            
            for v in values_to_remove:
                del active_filters[v]

        elif ctx.triggered_id['type'] in ['add-filter-butt']:
            
            # Initializing dropdown value 
            overlayBounds = overlay_info_state[self.overlay_options[0]]
            if 'min' in overlayBounds:
                # Used for numeric filtering
                values_selector = html.Div(
                    dcc.RangeSlider(
                        id = {'type': 'add-filter-selector','index': add_filter_click},
                        min = overlayBounds['min']-0.01,
                        max = overlayBounds['max']+0.01,
                        value = [overlayBounds['min'],overlayBounds['max']],
                        step = 0.01,
                        marks = None,
                        tooltip = {'placement':'bottom','always_visible': True},
                        allowCross = True,
                        disabled = False
                    ),
                    id = {'type': 'add-filter-selector-div','index': add_filter_click},
                    style = {'display': 'inline-block','margin': 'auto','width': '100%'}
                )
            elif 'unique' in overlayBounds:
                # Used for categorical filtering
                values_selector = html.Div(
                    dcc.Dropdown(
                        id = {'type':'add-filter-selector','index': add_filter_click},
                        options = overlayBounds['unique'],
                        value = overlayBounds['unique'],
                        multi = True
                    ),
                    id = {'type': 'add-filter-selector-div','index': add_filter_click}
                )
            
            def new_filter_item():
                return html.Div([
                    dbc.Row([
                        dbc.Col(
                            dcc.Dropdown(
                                options = self.overlay_options,
                                value = self.overlay_options[0],
                                placeholder = 'Select property to filter structures',
                                id = {'type': 'add-filter-drop','index': add_filter_click}
                            ),
                            md = 10
                        ),
                        dbc.Col(
                            html.I(
                                id = {'type': 'delete-filter','index': add_filter_click},
                                n_clicks = 0,
                                className = 'bi bi-x-circle-fill fa-2x',
                                style = {'color': 'rgb(255,0,0)'}
                            ),
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
                id = {'type': 'add-filter-selector','index': ctx.triggered_id['index']},
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
                id = {'type':'add-filter-selector','index': ctx.triggered_id['index']},
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
                    'name': filter_name.split(' --> ')[0] if '-->' in filter_name else filter_name,
                    'value': filter_name.split(' --> ')[1] if '-->' in filter_name else None,
                    'range': filter_value
                })

        return processed_filters

    def update_overlays(self, overlay_value, transp_value, lineColor_butt, filter_parent, filter_value, delete_filter, overlay_state, transp_state, overlay_info_state, lineColor_state):
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
        :return: List of dictionaries added to the GeoJSONs' "hideout" property (used by Namespace functions) and a colorbar based on overlay value.
        :rtype: tuple
        """

        overlay_value = get_pattern_matching_value(overlay_value)
        transp_value = get_pattern_matching_value(transp_value)
        overlay_state = get_pattern_matching_value(overlay_state)
        transp_state = get_pattern_matching_value(transp_state)
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))

        if ctx.triggered_id['type']=='overlay-drop':
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

        if ctx.triggered_id['type']=='overlay-trans-slider':
            use_transp_value = transp_value
        else:
            use_transp_value = transp_state

        if ctx.triggered_id['type'] in ['add-filter-parent', 'add-filter-selector','delete-filter']:
            use_overlay_value = overlay_state
            use_transp_value = transp_state

        if ctx.triggered_id['type']=='feature-lineColor-butt':
            use_overlay_value = overlay_state
            use_transp_value = transp_state


        if not use_overlay_value is None:
            if '-->' in use_overlay_value:
                split_overlay_value = use_overlay_value.split(' --> ')

                overlay_prop = {
                    'name': split_overlay_value[0],
                    'value': split_overlay_value[1]
                }
            else:
                overlay_prop = {
                    'name': use_overlay_value,
                    'value': None
                }
        else:
            overlay_prop = {
                'name': None,
                'value': None
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
            for i,j in zip(self.feature_names, lineColor_state)
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
                colorscale = ['blue','red'],
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
                colorscale = ['blue','red'],
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
            {
                'overlayBounds': overlay_bounds,
                'overlayProp': overlay_prop,
                'fillOpacity': fillOpacity,
                'lineColor': lineColor,
                'filterVals': filterVals 
            }
            for i in range(len(ctx.outputs_list[0]))
        ]

        return geojson_hideout, colorbar

    def adv_update_overlays(self, butt_click: list, colorbar_width:list, line_width:list, colormap_val:list, current_feature_hideout:list):
        """Update some additional properties of the overlays and display.

        :param butt_click: Button clicked to update overlay properties 
        :type butt_click: list
        :param colorbar_width: Width of colorbar in pixels
        :type colorbar_width: list
        :param line_width: Width of structure boundaries in pixels
        :type line_width: list
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
        line_width = get_pattern_matching_value(line_width)
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
                    colorscale = ['blue','red'],
                    width = colorbar_width,
                    height = 15,
                    position = 'bottomleft',
                    id = f'colorbar{np.random.randint(0,100)}',
                    style = color_bar_style,
                    tooltip=True
                )]
            elif 'unique' in overlay_bounds:
                colorbar_div_children = [dlx.categorical_colorbar(
                    categories = overlay_bounds['unique'],
                    colorscale = ['blue','red'],
                    style = color_bar_style,
                    position = 'bottomleft',
                    id = f'colorbar{np.random.randint(0,100)}',
                    width = colorbar_width,
                    height = 15
                )]

            else:
                colorbar_div_children = [no_update]
        else:
            colorbar_div_children = [html.Div()]

        # Updating line width:
        new_hideout = [i | {'lineWidth': line_width} for i in current_feature_hideout]


        return new_hideout, colorbar_div_children

class PropertyViewer(Tool):
    """PropertyViewer Tool which allows users to view distribution of properties across the current viewport of the SlideMap

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data
    :type Tool: None
    """
    def __init__(self,
                 geojson_list: Union[dict,list],
                 reference_object: Union[str,None] = None,
                 ignore_list: list = []
                 ):
        """Constructor method

        :param geojson_list: Individual or list of GeoJSON formatted annotations.
        :type geojson_list: Union[dict,list]
        :param reference_object: Path to larger reference object containing information on GeoJSON features, defaults to None
        :type reference_object: Union[str,None], optional
        :param ignore_list: List of properties not to make available to this component., defaults to []
        :type ignore_list: list, optional
        """
        self.ignore_list = []
        self.reference_object = reference_object
        self.available_properties, self.feature_names = self.extract_overlay_options(geojson_list,reference_object,ignore_list)
    
        self.title = 'Property Viewer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()   
        
    def extract_overlay_options(self,geojson_anns:Union[list,dict],reference_object:Union[str,None],ignore_list:list)->tuple:
        """Extract all properties which can be used for overlays

        :param geojson_anns: Inividual or list of GeoJSON formatted annotations
        :type geojson_anns: Union[list,dict]
        :param reference_object: Path to external reference object containing information on GeoJSON features
        :type reference_object: Union[str,None]
        :param ignore_list: List of properties to not make available to this component.
        :type ignore_list: list
        :return: List of properties and names of structures
        :rtype: tuple
        """
        geojson_properties = []
        feature_names = []
        for ann in geojson_anns:
            feature_names.append(ann['properties']['name'])
            for f in ann['features']:
                f_props = list(f['properties'].keys())
                for p in f_props:
                    # Checking for sub-properties: (only going 1 level)
                    if type(f['properties'][p])==dict:
                            sub_props = [f'{p} --> {sp}' for sp in list(f['properties'][p].keys()) if not p==sp]
                    else:
                        sub_props = [p]
                    
                    geojson_properties.extend([i for i in sub_props if not i in geojson_properties and not i in ignore_list])

        #TODO: After loading an experiment, reference the file here for additional properties
        
        geojson_properties = sorted(geojson_properties)

        return geojson_properties, feature_names

    def gen_layout(self):
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
                            id = {'type':'property-viewer-data','index':0},
                            storage_type='memory',
                            data = json.dumps({})
                        )
                    )
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow':'scroll'})

        return layout

    def get_callbacks(self):
        """Initializing callbacks for PropertyViewer Tool
        """
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
                State({'type': 'feature-bounds','index': ALL},'data')
            ]
        )(self.update_property_viewer)

    def update_property_viewer(self,slide_map_bounds, view_type_value, view_subtype_value, view_butt_click, active_tab, current_property_data, update_viewer, current_geojson):
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
        :param current_geojson: Current set of GeoJSON features and their properties
        :type current_geojson: list
        :raises exceptions.PreventUpdate: Stop callback execution
        :return: List of PropertyViewer tabs (separated by structure) and data used in plots
        :rtype: tuple
        """

        update_viewer = get_pattern_matching_value(update_viewer)
        active_tab = get_pattern_matching_value(active_tab)

        if not active_tab is None:
            if not active_tab=='property-viewer':
                raise exceptions.PreventUpdate
        
        slide_map_bounds = get_pattern_matching_value(slide_map_bounds)
        view_type_value = get_pattern_matching_value(view_type_value)
        view_subtype_value = get_pattern_matching_value(view_subtype_value)
        current_property_data = json.loads(get_pattern_matching_value(current_property_data))

        if ctx.triggered_id['type']=='slide-map':
            # Only update the region info when this is checked
            if update_viewer:
                current_property_data['bounds'] = slide_map_bounds

        current_property_data['update_view'] = update_viewer
        current_property_data['property'] = view_type_value
        current_property_data['sub_property'] = view_subtype_value
        plot_components = self.generate_plot_tabs(current_property_data, current_geojson)

        # Checking if a selected property has sub-properties
        main_properties = list(set([i if not '-->' in i else i.split(' --> ')[0] for i in self.available_properties]))
        if not view_type_value is None:
            if view_type_value in list(set([i.split(' --> ')[0] for i in self.available_properties if '-->' in i])):
                sub_types = list(set([i.split(' --> ')[1] for i in [j for j in self.available_properties if view_type_value in j]]))
            else:
                sub_types = None
        else:
            sub_types = None

        return_div = html.Div([
            dbc.Row([
                dbc.Col(
                    dbc.Label('Select a Property: ',html_for = {'type': 'property-view-type','index': 0}),
                    md = 3
                ),
                dbc.Col(
                    dcc.Dropdown(
                        options = main_properties,
                        value = view_type_value if not view_type_value is None else [],
                        placeholder = 'Property',
                        multi = False,
                        id = {'type': 'property-view-type','index': 0}
                    )
                )
            ]),
            dbc.Row([
                dbc.Col(
                    dbc.Label('Select a Sub-Property: ',html_for = {'type': 'property-view-subtype','index': 0}),
                    md = 3
                ),
                dbc.Col(
                    dcc.Dropdown(
                        options = sub_types if not sub_types is None else [],
                        value = view_subtype_value if not view_subtype_value is None else [],
                        placeholder = 'Sub-Property',
                        multi = False,
                        id = {'type': 'property-view-subtype','index': 0},
                        disabled = not sub_types
                    )
                )
            ]),
            html.Hr(),
            dbc.Row([
                plot_components
            ],style = {'maxHeight': '100vh'})
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
                                sub_properties = sub_property_df.columns.tolist()
                                if 'sub_property' in current_property_data:
                                    if current_property_data['sub_property'] in sub_properties:
                                        g_plot = html.Div(
                                                dcc.Graph(
                                                    figure = go.Figure(
                                                        px.histogram(
                                                            data_frame = sub_property_df,
                                                            x = current_property_data['sub_property'],
                                                            title = f'Histogram of {current_property_data["sub_property"]} in {g["properties"]["name"]}'
                                                        )
                                                    )
                                                )
                                            )
                                    else:
                                        g_plot = f'{current_property_data["property"]} --> {current_property_data["sub_property"]} is not in {g["properties"]["name"]}'
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
            id = {'type': 'property-viewer-tabs','index': 0}
        )

        return plot_tabs

class PropertyPlotter(Tool):
    """PropertyPlotter Tool which enables more detailed selection of properties across the entire tissue. 
    Allows for generation of violin plots, scatter plots, and UMAP plots.

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self,
                 geojson_list: Union[dict,list],
                 reference_object: Union[str,None] = None,
                 ignore_list: list = []
                 ):
        """Constructor method

        :param geojson_list: Individual or list of GeoJSON formatted annotations
        :type geojson_list: Union[dict,list]
        :param reference_object: Path to external reference object containing information on each GeoJSON feature, defaults to None
        :type reference_object: Union[str,None], optional
        :param ignore_list: List of properties to not include in this component, defaults to []
        :type ignore_list: list, optional
        """
        self.reference_object = reference_object
        self.ignore_list = ignore_list
        self.available_properties, self.feature_names = self.extract_overlay_options(geojson_list,reference_object,ignore_list)

        self.generate_property_dict()

        self.title = 'Property Plotter'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def extract_overlay_options(self,geojson_anns:Union[list,dict],reference_object:Union[str,None],ignore_list:list):
        """Extract all properties which can be used for overlays

        :param geojson_anns: Individual or list of GeoJSON formatted annotations
        :type geojson_anns: Union[list,dict]
        :param reference_object: Path to external object containing information on each GeoJSON feature
        :type reference_object: Union[str,None]
        :param ignore_list: List of properties to not include in this component
        :type ignore_list: list
        :return: List of GeoJSON properties, List of feature names
        :rtype: tuple
        """
        geojson_properties = []
        feature_names = []
        for ann in geojson_anns:
            feature_names.append(ann['properties']['name'])
            for f in ann['features']:
                f_props = list(f['properties'].keys())
                for p in f_props:
                    # Checking for sub-properties: (only going 1 level)
                    if type(f['properties'][p])==dict:
                            sub_props = [f'{p} --> {sp}' for sp in list(f['properties'][p].keys()) if not p==sp]
                    else:
                        sub_props = [p]
                    
                    geojson_properties.extend([i for i in sub_props if not i in geojson_properties and not i in ignore_list])

        #TODO: After loading an experiment, reference the file here for additional properties
        
        geojson_properties = sorted(geojson_properties)

        return geojson_properties, feature_names

    def generate_property_dict(self):
        """Generate nested dictionary used for populating the property dropdown menus
        
        For more information, see: https://github.com/kapot65/dash-treeview-antd
        
        """
        self.property_dict = {}
        self.property_keys = {}

        self.property_dict = {
            'title': 'Features',
            'key': '0',
            'children': []
        }

        leaf_properties = list(set([i for i in self.available_properties if not '-->' in i]))
        branch_properties = list(set([i for i in self.available_properties if '-->' in i and i.split(' --> ')[0] not in leaf_properties]))
        trunk_properties = list(set([i.split(' --> ')[0] for i in branch_properties]))

        # Adding branch properties first
        property_dict_children = []
        for t_idx,t in enumerate(trunk_properties):
            trunk_dict = {
                'title': t,
                'key': f'0-{t_idx}',
                'children': []
            }

            sub_count = 0
            for b_idx, b in enumerate(branch_properties):
                if t in b:

                    b_dict = {
                        'title': b.split(' --> ')[1],
                        'key': f'0-{t_idx}-{sub_count}'
                    }
                    
                    trunk_dict['children'].append(b_dict)

                    self.property_keys[b_dict['key']] = b

                    sub_count+=1

            property_dict_children.append(trunk_dict)

        # Now adding leaf properties
        for l_idx, l in enumerate(leaf_properties):
            l_dict = {
                'title': l,
                'key': f'0-{t_idx+l_idx+1}',
                'children': []
            }

            property_dict_children.append(l_dict)

            self.property_keys[l_dict['key']] = l

        self.property_dict['children'].extend(property_dict_children)

    def get_callbacks(self):
        """Initializing callbacks for PropertyPlotter Tool
        """
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
                State({'type': 'feature-bounds','index':ALL},'data'),
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
                State({'type': 'property-plotter-store','index': ALL},'data')
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
                State({'type': 'property-plotter-store','index': ALL},'data')
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
                State({'type': 'feature-bounds','index': ALL},'data'),
                State({'type': 'label-list','index': ALL},'value')
            ]
        )(self.update_sub_div)

    def gen_layout(self):
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
                                            data = self.property_dict
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
                                options = self.available_properties
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
                            )
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

        return layout

    def update_property_graph(self, plot_butt_click, property_list, label_list, current_features, current_plot_data):
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

        # Don't do anything if not given properties
        if property_list is None:
            raise exceptions.PreventUpdate
        elif type(property_list)==list:
            if len(property_list)==0:
                raise exceptions.PreventUpdate

        property_names = [self.property_keys[i] for i in property_list if i in self.property_keys]
            
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
                label_cols = label_names,
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
                if split_p[0] in feature['properties']:
                    if split_p[1] in feature['properties'][split_p[0]]:
                        if not type(feature['properties'][split_p[0]][split_p[1]])==dict:
                            try:
                                f_dict[p] = float(feature['properties'][split_p[0]][split_p[1]])
                            except ValueError:
                                f_dict[p] = feature['properties'][split_p[0]][split_p[1]]
        
        if not labels is None:
            if type(labels)==list:
                for l in labels:
                    if l in feature['properties']:
                        f_dict[l] = feature['properties'][l]
            elif type(labels)==str:
                if labels in feature['properties']:
                    f_dict[labels] = feature['properties'][labels]

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
        print(filter_list)
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
                pointpos=0
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
                    width=30
                )
            ),
            yaxis_title = dict(
                text = '<br>'.join(
                    textwrap.wrap(
                        f'{property_column}',
                        width=15
                    )
                ),
                font = dict(size = 10)
            ),
            xaxis_title = dict(
                text = '<br>'.join(
                    textwrap.wrap(
                        label_col,
                        width=15
                    )
                ) if not label_col is None else 'Group',
                font = dict(size = 10)
            ),
            margin = {'r':0,'b':25}
        )

        return figure

    def gen_scatter_plot(self, data_df:pd.DataFrame, plot_cols:list, label_cols:Union[str,None], customdata_cols:list):
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
        if not label_cols is None:
            figure = go.Figure(
                data = px.scatter(
                    data_frame=data_df,
                    x = plot_cols[0],
                    y = plot_cols[1],
                    color = label_cols,
                    custom_data = customdata_cols,
                    title = '<br>'.join(
                        textwrap.wrap(
                            f'Scatter plot of {plot_cols[0]} and {plot_cols[1]} labeled by {label_cols}',
                            width = 30
                            )
                        )
                )
            )
            if not data_df[label_cols].dtype == np.number:
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
                            'color': data_df[label_cols].values,
                            'colorbar':{
                                'title': label_cols
                            },
                            'colorscale':'jet'
                        },
                        text = data_df[label_cols].values,
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
                            width = 30
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

    def gen_selected_div(self, n_markers: int):
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
                        dbc.Label('Select property for sub-plot: ',html_for = {'type': 'selected-sub-drop','index':0}),
                        md = 3
                    ),
                    dbc.Col(
                        dcc.Dropdown(
                            options = self.available_properties,
                            value = [],
                            id = {'type': 'selected-sub-drop','index': 0},
                            multi = False
                        ),
                        md = 9
                    )
                ],align='center'),
                dbc.Row(
                    dbc.Button(
                        'Update Sub-Plot',
                        className = 'd-grid col-12 mx-auto',
                        n_clicks = 0,
                        id = {'type': 'selected-sub-butt','index': 0},
                        color = 'primary'
                    )
                ),
                html.B(),
                dbc.Row(
                    dbc.Button(
                        'See Selected Marker Features',
                        className = 'd-grid col-12 mx-auto',
                        n_clicks=0,
                        id = {'type': 'selected-sub-markers','index':0},
                        color = 'secondary'
                    )
                ),
                dbc.Row(
                    html.Div(
                        id = {'type': 'selected-sub-div','index': 0},
                        children = 0
                    )
                )
            ])
        ]

        return new_selected_div

    def select_data_from_plot(self, selected_data, current_plot_data):
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

        if selected_data is None:
            raise exceptions.PreventUpdate
        if type(selected_data)==list:
            if len(selected_data)==0:
                raise exceptions.PreventUpdate

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
                                id = {'type': 'selected-marker-delete','index': p_idx}
                            ),
                            id = {'type': 'selected-marker-popup','index': p_idx}
                        )
                    ]
                )
            )
        
        map_marker_div = html.Div(
            map_marker
        )
        current_plot_data['selected'] = selected_data
        current_plot_data = [json.dumps(current_plot_data)]

        # Update property_graph_selected_div
        property_graph_selected_div = self.gen_selected_div(len(map_marker))


        return property_graph_selected_div, [map_marker_div], current_plot_data

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
                        id = {'type': 'property-summary-table','index': u_idx},
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
                    id = {'type': 'property-summary-table','index': 0},
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
            id = {'type': 'property-summary-tab','index': 0},
            children = property_summary_children,
            tab_id = 'property-summary',
            label = 'Property Summary'
        )

        # Property statistics
        label_stats_children = []
        if not label_col is None:
            unique_labels = data_df[label_col].unique().tolist()
            if len(unique_labels)>1:
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
                                    id = {'type': 'property-stats-table','index': 0},
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
                                )
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
                                    id = {'type': 'property-stats-table','index':0},
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
                                    id = {'type': 'property-stats-tukey','index': 0},
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
                                id='pearson-table',
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
                                id='silhouette-table',
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
                    dbc.Alert(f'Only one label present! ({unique_labels[0]})',color='warning')
                )
        else:
            label_stats_children.append(
                dbc.Alert('No labels assigned to the plot!',color='warning')
            )

        label_stats_tab = dbc.Tab(
            id = {'type': 'property-stats-tab','index': 0},
            children = label_stats_children,
            tab_id = 'property-stats',
            label = 'Property Statistics'
        )

        selected_data_tab = dbc.Tab(
            id = {'type': 'property-selected-data-tab','index': 0},
            children = html.Div(
                id = {'type': 'property-graph-selected-div','index': 0},
                children = ['Select data points in the plot to get started!']
            ),
            tab_id = 'property-selected-data',
            label = 'Selected Data'
        )

        property_plot_tabs = dbc.Tabs(
            id = {'type': 'property-plot-tabs','index': 0},
            children = [
                property_summary_tab,
                label_stats_tab,
                selected_data_tab
            ],
            active_tab = 'property-summary'
        )

        return property_plot_tabs

    def remove_marker_label(self, delete_click, current_plot_data):
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
        n_marked = len(current_plot_data['selected']['points'])

        patched_list = Patch()
        values_to_remove = []
        for i, val in enumerate(delete_click):
            if val:
                values_to_remove.insert(0,i)

        for v in values_to_remove:
            del patched_list[v]
            del current_plot_data['selected']['points'][v]
        
        
        current_plot_data = [json.dumps(current_plot_data)]

        new_selected_div = self.update_selected_div(n_marked-1)

        return patched_list, current_plot_data, new_selected_div

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

        if ctx.triggered_id['type']=='selected-sub-butt':
            if not sub_plot_value is None:
                # Pulling selected data points from current plot_data
                current_selected = current_plot_data['selected']['points']
                
                selected_data = self.extract_data_from_features(
                    geo_list=current_features,
                    properties=[sub_plot_value],
                    labels = current_labels,
                    filter_list = [i['customdata'][1] for i in current_selected]
                )

                if len(selected_data)>0:
                    data_df = pd.DataFrame.from_records(selected_data).dropna(subset= [sub_plot_value],how='all')
                    data_df.reset_index(inplace=True,drop=True)

                    sub_plot_figure = self.gen_violin_plot(
                        data_df = data_df,
                        label_col = current_labels,
                        property_column = sub_plot_value,
                        customdata_columns = ['bbox','point_info']
                    )

                    sub_div_content = dcc.Graph(
                        id = {'type': 'property-sub-graph','index': 0},
                        figure = sub_plot_figure
                    )
                else:
                    sub_div_content = dbc.Alert(
                        f'Property: {sub_plot_value} not found in selected points!',
                        color = 'warning'
                    )

        elif ctx.triggered_id['type'] == 'selected-sub-markers':
            current_selected = current_plot_data['selected']['points']

            selected_data = self.extract_data_from_features(
                geo_list = current_features,
                properties = self.available_properties,
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
                    id = {'type': 'property-sub-wilcox','index': 0},
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


class FeatureAnnotator(Tool):
    """FeatureAnnotator Tool used to annotate individual GeoJSON features.
    These annotations can include either drawings highlighting regions within a feature or labels for a feature.

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self):
        """Constructor method
        """

        self.title = 'Feature Annotator'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        pass

    def get_callbacks(self):
        pass

class HRAViewer(Tool):
    """HRAViewer Tool which enables hierarchy visualization for organs, cell types, biomarkers, and proteins in the Human Reference Atlas

    For more information on the Human Reference Atlas (HRA), see: https://humanatlas.io/

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self):
        """Constructor method
        """
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

        self.title = 'HRA Viewer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        """Generate layout for HRA Viewer component
        """

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Human Reference Atlas (HRA) Viewers')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Select one of the embedded components below or select an organ to view the ASCT+B table for that organ'
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('HRA View Select: ',html_for = {'type': 'hra-viewer-drop','index': 0})
                        ],md=2),
                        dbc.Col(
                            dcc.Dropdown(
                                options = [
                                    {'label': 'FTU Explorer','value': 'FTU Explorer','disabled': False},
                                ] + self.organ_table_options,
                                value = [],
                                multi = False,
                                id = {'type': 'hra-viewer-drop','index': 0}
                            ),
                            md = 10
                        )
                    ]),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'hra-viewer-parent','index': 0},
                            children = []
                        )
                    ])
                ])
            ])
        ])

        return layout

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
            )

            table_attribution = {}
            attribution_rows = pd.read_csv(
                BytesIO(
                    new_table_request.content
                )
            ).iloc[1:9,:2]

            table_attribution['authors'] = attribution_rows.iloc[0,:].values[1].split('; ')
            table_attribution['authors_orcs'] = attribution_rows.iloc[1,:].values[1].split('; ')
            table_attribution['reviewers'] = attribution_rows.iloc[2,:].values[1].split('; ')
            table_attribution['reviewers_orcs'] = attribution_rows.iloc[3,:].values[1].split('; ')
            table_attribution['publications'] = re.split('; |, ', attribution_rows.iloc[4,:].values[1])
            table_attribution['data_doi'] = attribution_rows.iloc[5,:].values[1]
            table_attribution['date'] = attribution_rows.iloc[6,:].values[1]
            table_attribution['version'] = attribution_rows.iloc[7,:].values[1]

        else:
            new_table = None
            table_attribution = None

        return new_table, table_attribution

    def update_hra_viewer(self, viewer_drop_value):
        """Updating the HRAViewer component based on selected view

        :param viewer_drop_value: Selected component from dropdown (one of FTU Explorer or {organ} ASCT+B Table)
        :type viewer_drop_value: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        viewer_drop_value = get_pattern_matching_value(viewer_drop_value)

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

        elif viewer_drop_value in self.asct_b_release['Organ'].tolist():
            
            organ_table, table_attribution = self.get_organ_table(viewer_drop_value)
            if not organ_table is None and not table_attribution is None:
                viewer_children = html.Div([
                    dbc.Row([
                        dbc.Label(html.H4('Authors:'),html_for={'type': 'hra-viewer-authors','index': 0})
                    ],style={'marginBottom': '5px'}),
                    dbc.Row([
                        dmc.AvatarGroup(
                            id = {'type': 'hra-viewer-authors','index': 0},
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
                    ],style={'marginBottom': '5px'},align='center'),
                    dbc.Row([
                        dbc.Label(html.H6('Reviewers: '),html_for={'type': 'hra-viewer-reviewers','index': 0})
                    ],style = {'marginBottom':'5px'}),
                    dbc.Row([
                        dmc.AvatarGroup(
                            id = {'type': 'hra-viewer-reviewers','index': 0},
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
                    ],style = {'marginBottom': '5px'},align='center'),
                    dbc.Row([
                        'Publications, Data DOI, Date, Version'
                    ],style = {'marginBottom':'5px'}),
                    html.Hr(),
                    dbc.Row([
                        dash_table.DataTable(
                            id = {'type':'hra-viewer-table','index': 0},
                            columns = [{'name':i,'id':i,'deletable':False,'selectable':True} for i in organ_table.columns],
                            data = organ_table.to_dict('records'),
                            editable = False,
                            filter_action='native',
                            sort_action='native',
                            sort_mode='multi',
                            style_cell = {
                                'overflowX': 'auto'
                            },
                            tooltip_data = [
                                {
                                    column: {'value': str(value),'type':'markdown'}
                                    for column,value in row.items()
                                } for row in organ_table.to_dict('records')
                            ],
                            tooltip_duration = None
                        )
                    ],style={'maxHeight': '1000px','overflow':'scroll','marginBottom':'5px'}),
                    html.Hr(),
                    dbc.Row([
                        dbc.Label(html.H6('Table Data Sources:'),html_for={'type':'hra-viewer-table-sources','index':0})
                    ]),
                    dbc.Row([
                        dbc.Col(
                            'General Publication(s):',
                            md = 4
                        ),
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    children = [
                                        dbc.Row(html.A(
                                            p if 'http' in p else f'https://doi.org/{p.split("DOI: ")[-1]}',
                                            href = p,
                                            target = '_blank'
                                        ),align='left')
                                        for p in table_attribution['publications']
                                    ],
                                    style = {'maxHeight':'100px','overflow':'scroll'}
                                )
                            ),
                            md = 8
                        )
                    ],align='center'),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label('Data DOI: ',html_for = {'type':'hra-viewer-data-doi','index': 0}),
                            md = 4
                        ),
                        dbc.Col(
                            html.A(
                                table_attribution['data_doi'],
                                href = table_attribution['data_doi'],
                                target = '_blank'
                            )
                        )
                    ],align = 'center'),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label('Date: ',html_for = {'type': 'hra-viewer-date','index': 0}),
                            md = 4
                        ),
                        dbc.Col(
                            table_attribution['date'],
                            md = 8
                        )
                    ],align='center'),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label('Version Number: ',html_for = {'type':'hra-viewer-version','index': 0}),
                            md = 4
                        ),
                        dbc.Col(
                            table_attribution['version'],
                            md = 8
                        )
                    ],align='center')
                ])

            else:
                viewer_children = dbc.Alert(f'Unable to get ASCT+B Table for {viewer_drop_value}',color='warning')

        return [viewer_children]







