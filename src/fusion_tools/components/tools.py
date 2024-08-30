"""

Visualization tools which can be linked to SlideMap components (but don't have to be)


"""

import os
import sys
import json
import numpy as np
import pandas as pd
import textwrap

from typing_extensions import Union
from shapely.geometry import box, shape
import plotly.express as px
import plotly.graph_objects as go
from umap import UMAP

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import dash_treeview_antd as dta
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import find_intersecting




class Tool:
    """
    Components which can be added to tabs
    """
    pass

class OverlayOptions(Tool):
    """
    Creates dropdown menu for changing overlay colors based on structure properties

    Parameters
    --------
    geojson_anns: Union[list,dict]
        List or single GeoJSON object containing "property" key 

    reference_object: Union[str,None]
        File path to data file with properties not added to geojson objects but with some reference field which links the two
    
    ignore_list: list = []
        List of properties to ignore and not make usable for generating overlaid heatmaps


    """
    def __init__(self,
                 geojson_anns: Union[list,dict],
                 reference_object: Union[str,None] = None,
                 ignore_list: list = []
                 ):

        self.reference_object = reference_object
        self.overlay_options, self.feature_names, self.overlay_info = self.extract_overlay_options(geojson_anns, reference_object,ignore_list)
        
        self.title = 'Overlay Options'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        # Add callbacks here
        self.get_callbacks()

    def extract_overlay_options(self,geojson_anns,reference_object,ignore_list):
        """
        Extract all properties which can be used for overlays
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
        

        return geojson_properties, feature_names, property_info

    def gen_layout(self):
        
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
                    ])
                ])
            )
        ],style = {'maxHeight': '100vh','overflow':'scroll'})

        return layout

    def get_callbacks(self):

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
        """
        Add new filter based on selected overlay value
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
        """
        Updating the filter selector (either a RangeSlider or Dropdown component depending on property type)
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

    def parse_added_filters(self, add_filter_parent):
        """
        Getting all filter values from parent div

        add_filter_parent is a list of divs, each one containing two children (Row, Div).
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
        """
        Update overlay transparency and color based on property selection

        Adding new values to the "hideout" property of the GeoJSON layers triggers the featureStyle Namespace function
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

class PropertyViewer(Tool):
    def __init__(self,
                 geojson_list: Union[dict,list],
                 reference_object: Union[str,None] = None,
                 ignore_list: list = []
                 ):
        
        self.ignore_list = []
        self.reference_object = reference_object
        self.available_properties, self.feature_names = self.extract_overlay_options(geojson_list,reference_object,ignore_list)
    
        self.title = 'Property Viewer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()   
        
    def extract_overlay_options(self,geojson_anns,reference_object,ignore_list):
        """
        Extract all properties which can be used for overlays
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
        

        return geojson_properties, feature_names

    def gen_layout(self):
        
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
        """
        Updating visualization of properties within the current viewport

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
        """
        Checking for intersecting features and extracting necessary data
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
    def __init__(self,
                 geojson_list: Union[dict,list],
                 reference_object: Union[str,None] = None,
                 ignore_list: list = []
                 ):

        self.reference_object = reference_object
        self.ignore_list = ignore_list
        self.available_properties, self.feature_names = self.extract_overlay_options(geojson_list,reference_object,ignore_list)

        self.generate_property_dict()

        self.title = 'Property Plotter'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def extract_overlay_options(self,geojson_anns,reference_object,ignore_list):
        """
        Extract all properties which can be used for overlays
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
        

        return geojson_properties, feature_names

    def generate_property_dict(self):
        """
        Generate nested dictionary used for populating the property dropdown menus
        """

        self.label_dict = {}
        self.property_dict = {}
        self.label_keys = {}
        self.property_keys = {}

        # Populating label dict with structure name and properties (which will be a copy of property_dict_children)
        self.label_dict = {
            'title': 'Labels',
            'key': '0',
            'children': [
                {
                    'title': 'Structure Name',
                    'key': '0',
                    'children': []
                },
                {
                    'title': 'Property',
                    'key': '1',
                    'children': []
                }
            ]
        }

        self.label_keys['0'] = 'name'

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
        label_property_dict_children = []
        for t_idx,t in enumerate(trunk_properties):
            trunk_dict = {
                'title': t,
                'key': f'0-{t_idx}',
                'children': []
            }
            label_trunk_dict = {
                'title': t,
                'key': f'1-{t_idx}',
                'children': []
            }

            sub_count = 0
            for b_idx, b in enumerate(branch_properties):
                if t in b:

                    b_dict = {
                        'title': b.split(' --> ')[1],
                        'key': f'0-{t_idx}-{sub_count}'
                    }

                    label_b_dict = b_dict.copy()
                    label_b_dict['key'] = f'1-{t_idx}-{sub_count}'
                    
                    trunk_dict['children'].append(b_dict)
                    label_trunk_dict['children'].append(label_b_dict)

                    self.property_keys[b_dict['key']] = b
                    self.label_keys[label_b_dict['key']] = b

                    sub_count+=1

            property_dict_children.append(trunk_dict)
            label_property_dict_children.append(label_trunk_dict)

        # Now adding leaf properties
        for l_idx, l in enumerate(leaf_properties):
            l_dict = {
                'title': l,
                'key': f'0-{t_idx+l_idx+1}',
                'children': []
            }

            label_l_dict = l_dict.copy()
            label_l_dict['key'] = f'1-{t_idx+l_idx}'

            property_dict_children.append(l_dict)
            label_property_dict_children.append(l_dict)

            self.property_keys[l_dict['key']] = l
            self.label_keys[label_l_dict['key']] = l

        self.property_dict['children'].extend(property_dict_children)
        self.label_dict['children'][1]['children'].extend(label_property_dict_children)

    def get_callbacks(self):
        
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
                State({'type': 'label-list','index': ALL},'checked'),
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

        # Running clustering and finding cluster marker features

        # Applying label to points

        # Training a model to predict graph labels

        # Exporting plotter data

    def gen_layout(self):
        
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
                        dbc.Card(
                            id = {'type': 'label-list-card','index': 0},
                            children = [
                                html.Div(
                                    id = {'type': 'label-list-div','index': 0},
                                    children = [
                                        dta.TreeView(
                                            id = {'type': 'label-list','index': 0},
                                            multiple = True,
                                            checkable = True,
                                            checked = [],
                                            selected = [],
                                            expanded = [],
                                            data = self.label_dict
                                        )
                                    ],
                                    style = {'maxHeight': '250px','overflow': 'scroll'}
                                )
                            ]
                        )
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
        """
        Updating plot based on selected properties, label(s)

        Returns
        --------
        {'type': 'property-graph', 'index': ALL}, figure -> go.Figure()
        {'type': 'property-graph-tabs-div','index': ALL}, children -> list
        {'type': 'property-plotter-store','index': ALL}, data -> str
        """
        property_graph_tabs_div = [no_update]

        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))

        property_list = get_pattern_matching_value(property_list)
        label_list = get_pattern_matching_value(label_list)

        # Don't do anything if not given properties
        if property_list is None:
            raise exceptions.PreventUpdate
        elif type(property_list)==list:
            if len(property_list)==0:
                raise exceptions.PreventUpdate

        property_names = [self.property_keys[i] for i in property_list if i in self.property_keys]
        if not label_list is None:
            if label_list[0] in self.label_keys:
                label_names = self.label_keys[label_list[0]]
            else:
                label_names = None
        else:
            label_names = None
        

        extracted_data = self.extract_data_from_features(current_features, property_names, label_names)
        current_plot_data['data'] = extracted_data

        data_df = pd.DataFrame.from_records(extracted_data).dropna(subset=property_names)
        if len(property_names)==1:
            # Single feature visualization
            plot_figure = self.gen_violin_plot(
                data_df = data_df,
                label_col = label_names,
                property_column = property_names[0],
                customdata_columns=['bbox']
            )

        elif len(property_names)>1:
            # Multi-feature visualization

            if len(property_names)>2:
                umap_cols = self.gen_umap_cols(
                    data_df = data_df,
                    property_columns = property_names
                )

                data_df = pd.concat([data_df,umap_cols],axis=1,ignore_index=True)

                plot_cols = umap_cols.columns.tolist()

            elif len(property_names)==2:
                plot_cols = property_names

            plot_figure = self.gen_scatter_plot(
                data_df = data_df,
                plot_cols = plot_cols,
                label_cols = label_names,
                customdata_cols = ['bbox']
            )



        current_plot_data = json.dumps(current_plot_data)

        return [plot_figure], property_graph_tabs_div, [current_plot_data]

    def extract_data_from_features(self, geo_list, properties, labels):
        """
        Iterate through properties and extract data based on selection
        """

        extract_data = []
        for g_idx, g in enumerate(geo_list):
            for f_idx, f in enumerate(g['features']):
                f_dict = {}
                for p in properties:
                    if '-->' not in p:
                        if p in f['properties']:
                            f_dict[p] = f['properties'][p]
                    else:
                        split_p = p.split(' --> ')
                        if split_p[0] in f['properties']:
                            if split_p[1] in f['properties'][split_p[0]]:
                                f_dict[p] = f['properties'][split_p[0]][split_p[1]]
                
                if not labels is None:
                    if type(labels)==list:
                        for l in labels:
                            if l in f['properties']:
                                f_dict[l] = f['properties'][l]
                    elif type(labels)==str:
                        if labels in f['properties']:
                            f_dict[labels] = f['properties'][labels]

                # Getting bounding box info
                f_bbox = list(shape(f['geometry']).bounds)
                f_dict['bbox'] = f_bbox

                extract_data.append(f_dict)

        return extract_data

    def gen_violin_plot(self, data_df:pd.DataFrame, label_col: Union[str,None], property_column: str, customdata_columns:list):
        """
        Generating a violin plot using provided data, property columns, and customdata
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
        """
        Generating a 2D scatter plot using provided data
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

    def gen_umap_cols(self, data_df:pd.DataFrame, property_columns: list):
        """
        Scale and run UMAP for dimensionality reduction
        """
        quant_data = data_df.loc[:,[i for i in property_columns if i in data_df.columns]].values
        print(quant_data)
        feature_data_means = np.nanmean(quant_data,axis=0)
        feature_data_stds = np.nanstd(quant_data,axis=0)

        scaled_data = (quant_data-feature_data_means)/feature_data_stds
        scaled_data[np.isnan(scaled_data)] = 0.0
        scaled_data[~np.isfinite(scaled_data)] = 0.0

        umap_reducer = UMAP()
        embeddings = umap_reducer.fit_transform(scaled_data)
        umap_df = pd.DataFrame(data = embeddings, columns = ['UMAP1','UMAP2'])

        umap_df.columns = ['UMAP1','UMAP2']

        return umap_df

    def select_data_from_plot(self, selected_data, current_plot_data):
        """
        Updating selected data tab based on selection in primary graph
        Returns
        --------
        {'type': 'property-graph-selected-div','index': ALL}, children -> list
        {'type': 'map-marker-div','index': ALL}, children -> list
        {'type': 'property-plotter-store','index':ALL}, data -> str 
        """

        property_graph_selected_div = [no_update]
        map_marker_div = [no_update]
        
        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))
        selected_data = get_pattern_matching_value(selected_data)

        print(selected_data)
        if selected_data is None:
            raise exceptions.PreventUpdate
        if type(selected_data)==list:
            if len(selected_data)==0:
                raise exceptions.PreventUpdate





        return property_graph_selected_div, map_marker_div, current_plot_data


class FeatureAnnotator(Tool):
    def __init__(self):

        self.title = 'Feature Annotator'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        pass

    def get_callbacks(self):
        pass

class HRAViewer(Tool):
    def __init__(self):

        self.title = 'HRA Viewer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        pass

    def get_callbacks(self):
        pass



