"""

Interactive components which handle plot generation from data in a SlideMap component.

"""

import json
import numpy as np
import pandas as pd
import textwrap

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
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
from dash.dash_table.Format import Format, Scheme
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform, BlockingCallbackTransform
from dash_extensions.javascript import Namespace, arrow_function

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import (
    find_intersecting, 
)
from fusion_tools.utils.stats import get_label_statistics, run_wilcox_rank_sum
from fusion_tools.components.base import Tool, MultiTool

import time


class PropertyViewer(Tool):
    """PropertyViewer Tool which allows users to view distribution of properties across the current viewport of the SlideMap

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data
    :type Tool: None
    """

    title = 'Property Viewer'
    description = 'Pan around on the slide to view select properties across regions of interest'

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

    def gen_layout(self, session_data:dict):
        """Generating layout for PropertyViewer Tool

        :return: Layout added to DashBlueprint() object to be embedded in larger layout
        :rtype: dash.html.Div.Div
        """
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
            ],
            blocking = True
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

        start = time.time()

        if not active_tab is None:
            if not active_tab=='property-viewer':
                return [no_update], [no_update]
        else:
            return [no_update], [no_update]
        
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
            update_viewer = False

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
        #minx, miny, maxx, maxy
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

    title = 'Property Plotter'
    description = 'Select one or a combination of properties to generate a plot.'

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

    def get_callbacks(self):
        """Initializing callbacks for PropertyPlotter Tool
        """
        
        # Updating for a new slide:
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-info-store','index':ALL},'data')
            ],
            [
                Output({'type': 'property-plotter-property-drop','index': ALL},'options'),
                Output({'type': 'label-list','index': ALL},'options'),
                Output({'type': 'property-graph','index': ALL},'figure'),
                Output({'type': 'property-graph-tabs-div','index': ALL},'children'),
            ]
        )(self.update_slide)

        # Updating plot based on selected properties and labels
        self.blueprint.callback(
            [
                Input({'type': 'property-plotter-butt','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'property-graph','index': ALL},'figure'),
                Output({'type': 'property-graph-tabs-div','index': ALL},'children'),
                Output({'type': 'property-plotter-store','index': ALL},'data')
            ],
            [
                State({'type':'property-plotter-property-drop','index': ALL},'value'),
                State({'type': 'label-list','index': ALL},'value'),
                State({'type': 'map-slide-information','index': ALL},'data'),
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
                State({'type':'label-list','index': ALL},'options'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.select_data_from_plot)

        # Clearing individual markers
        self.blueprint.callback(
            [
                Input({'type': 'property-plotter-markers','index': ALL},'n_dblclicks')
            ],
            [
                Output({'type': 'property-plotter-selected-n','index': ALL},'children'),
                Output({'type': 'property-plotter-store','index': ALL},'data')
            ],
            [
                State({'type': 'property-plotter-markers','index': ALL},'data'),
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
                State({'type': 'label-list','index': ALL},'value'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.update_sub_div)

        # Selecting points in selected data:
        self.blueprint.callback(
            [
                Input({'type': 'property-sub-graph','index': ALL},'selectedData')
            ],
            [
                Output({'type': 'map-marker-div','index': ALL},'children')
            ],
            [
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.sub_select_data)

    def update_slide(self, new_annotations_info:list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        new_annotations_info = json.loads(get_pattern_matching_value(new_annotations_info))
        new_available_properties = new_annotations_info['available_properties']

        new_figure = go.Figure()
        new_graph_tabs_children = []

        return [new_available_properties.copy()], [new_available_properties.copy()], [new_figure], [new_graph_tabs_children]
        
    def gen_layout(self, session_data:dict):
        """Generating layout for PropertyPlotter Tool

        :return: Layout for PropertyPlotter DashBlueprint object to be embedded in larger layouts
        :rtype: dash.html.Div.Div
        """
        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        html.H3(self.title)
                    ]),
                    html.Hr(),
                    dbc.Row(
                        self.description
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
                                        dcc.Dropdown(
                                            id = {'type': 'property-plotter-property-drop','index': 0},
                                            placeholder = 'Select a property',
                                            multi = True,
                                            options = [],
                                        )
                                    ],
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

    def get_data_from_database(self, slide_info:dict, property_list:list,structure_id:Union[list,str,None] = None):
        """Grabbing data from the database for selected list of properties

        :param slide_info: Slide information, contains "id"
        :type slide_info: dict
        :param property_list: List of properties to extract (plotted properties + label)
        :type property_list: list
        :param structure_id: If specific structures are needed, provide a list here., defaults to None
        :type structure_id: Union[list,str,None], optional
        """
        property_data_list = self.database.get_structure_property_data(
            item_id = slide_info.get('id'),
            structure_id = structure_id,
            layer_id = None,
            property_list = [p for p in property_list if not p is None]
        )

        return property_data_list   

    def update_property_graph(self, plot_butt_click, property_names, label_list, slide_information,current_plot_data):
        """Updating the property plotter graph based on selected properties/labels

        :param plot_butt_click: Plot button clicked
        :type plot_butt_click: list
        :param property_names: List of selected properties from dropdown menu
        :type property_names: list
        :param label_list: Selected label from dropdown menu
        :type label_list: list
        :param slide_information: Information for the current slide
        :type slide_information: list
        :param current_plot_data: Data currently in use for the plot (rows = structure, columns = properties)
        :type current_plot_data: list
        """
        
        # Testing with get_data_from_database integration
        #start = time.time()
        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))

        slide_information = json.loads(get_pattern_matching_value(slide_information))

        property_names = get_pattern_matching_value(property_names)
        label_names = get_pattern_matching_value(label_list)

        if property_names is None:
            raise exceptions.PreventUpdate

        property_data = self.get_data_from_database(
            slide_info = slide_information,
            property_list = property_names + [label_names]
        )
              
        current_plot_data['data'] = property_data

        data_df = pd.DataFrame.from_records(property_data).dropna(subset=property_names,how = 'all')
        data_df.reset_index(inplace=True,drop=True)
        if len(property_names)==1:
            # Single feature visualization
            plot_figure = self.gen_violin_plot(
                data_df = data_df,
                label_col = label_names,
                property_column = property_names[0],
                customdata_columns=['bbox','structure.id']
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
                customdata_cols = ['bbox','structure.id']
            )

        current_plot_data = json.dumps(current_plot_data)

        property_graph_tabs_div = self.make_property_plot_tabs(data_df,label_names,property_names,['bbox','structure.id'])

        #print(f'Time for update_property_graph: {time.time() - start}')

        return [plot_figure], [property_graph_tabs_div], [current_plot_data]

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
        label_x = None
        if not label_col is None:
            label_x = data_df[label_col]
            if type(label_x)==pd.DataFrame:
                label_x = label_x.iloc[:,0]

        figure = go.Figure(
            data = go.Violin(
                x = label_x,
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

            label_data = data_df[label_col]
            if type(label_data)==pd.DataFrame:
                label_data = label_data.iloc[:,0]

            if not label_data.dtype == np.number:
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
                            'color': label_data.values,
                            'colorbar':{
                                'title': label_col
                            },
                            'colorscale':'jet'
                        },
                        text = label_data.values,
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
                html.H3(f'Selected Samples: {n_markers}',id = {'type': f'{self.component_prefix}-property-plotter-selected-n','index': 0}),
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

    def select_data_from_plot(self, selected_data, current_plot_data, available_properties, slide_information):
        """Updating selected data tab based on selection in primary graph


        :param selected_data: Selected data points in the current plot
        :type selected_data: list
        :param current_plot_data: Data used to generate the current plot
        :type current_plot_data: list
        :param slide_information: Data on the current slide
        :type slide_information: list
        :raises exceptions.PreventUpdate: Stop callback execution because there is no selected data
        :raises exceptions.PreventUpdate: Stop callback execution because there is no selected data
        :return: Selected data description div, markers to add to the map, updated current plot data
        :rtype: tuple
        """

        property_graph_selected_div = [no_update]*len(ctx.outputs_list[0])
        
        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))
        selected_data = get_pattern_matching_value(selected_data)
        available_properties = get_pattern_matching_value(available_properties)
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        if selected_data is None:
            raise exceptions.PreventUpdate
        if type(selected_data)==list:
            if len(selected_data)==0:
                raise exceptions.PreventUpdate
        
        x_scale = slide_information.get('x_scale',1)
        y_scale = slide_information.get('y_scale',1)

        map_marker_geojson = dl.GeoJSON(
            data = {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'geometry': {
                            'type': 'Point',
                            'coordinates': [
                                x_scale*((p['customdata'][0][0]+p['customdata'][0][2])/2),
                                y_scale*((p['customdata'][0][1]+p['customdata'][0][3])/2)
                            ]
                        },
                        'properties': {
                            'customdata': p['customdata']
                        }
                    }
                    for p_idx, p in enumerate(selected_data['points'])
                ]
            },
            pointToLayer=self.js_namespace("markerRender"),
            onEachFeature=self.js_namespace("tooltipMarker"),
            id = {'type': f'{self.component_prefix}-property-plotter-markers','index': 0},
            eventHandlers = {
                'dblclick': self.js_namespace('removeMarker')
            }
        )

        current_plot_data['selected'] = [i['customdata'] for i in selected_data['points']]
        current_plot_data = [json.dumps(current_plot_data)]

        # Update property_graph_selected_div
        property_graph_selected_div = self.gen_selected_div(len(selected_data['points']), available_properties)

        return property_graph_selected_div, [map_marker_geojson], current_plot_data

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
            label_data = data_df[label_col]
            if type(label_data)==pd.DataFrame:
                label_data = label_data.iloc[:,0]

            unique_labels = [i for i in label_data.unique().tolist() if type(i)==str]
            for u_idx, u in enumerate(unique_labels):
                try:
                    u_label_data = data_df[label_data.astype(str).str.match(u)].loc[:,[i for i in property_cols if i in data_df]]
                except:
                    u_label_data = data_df[label_data.str.match(u)].loc[:,[i for i in property_cols if i in data_df]]

                summary = u_label_data.describe().round(decimals=4)
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
        try:
            if data_df.shape[0]>1:
                if not label_col is None:
                    label_data = data_df[label_col]
                    if type(label_data)==pd.DataFrame:
                        label_data = label_data.iloc[:,0]

                    unique_labels = label_data.unique().tolist()
                    if len(unique_labels)>1:
                        if any([i>1 for i in list(label_data.value_counts().to_dict().values())]):

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

        except:
            label_stats_children.append(
                dbc.Alert('Error generating property statistics tabs',color = 'danger')
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

    def remove_marker_label(self, marker_dblclicked, marker_geo, current_plot_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))
        marker_geo = get_pattern_matching_value(marker_geo)
        marker_count = len(marker_geo['features'])

        current_marker_count = f'Selected Samples: {marker_count}'

        current_plot_data['selected'] = [
            p['properties']['customdata'] for p in marker_geo['features']
        ]


        return [current_marker_count], [json.dumps(current_plot_data)]

    def update_sub_div(self, plot_butt_clicked, marker_butt_clicked, sub_plot_value, current_plot_data, current_labels, slide_information):
        """Updating the property-graph-selected-div based on selection of either a property to plot a sub-plot of or whether the marker properties button was clicked

        :param plot_butt_clicked: Update sub-plot button was clicked
        :type plot_butt_clicked: list
        :param marker_butt_clicked: Get marker features for selected samples clicked
        :type marker_butt_clicked: list
        :param current_plot_data: Current data in the plot
        :type current_plot_data: list
        :param current_labels: Current labels applied to the main plot
        :type current_labels: list
        :param slide_information: Information relating to the current slide
        :type slide_information: list
        :return: Updated children of the selected-property-graph-div including either sub-plot or table of marker features
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_plot_data = json.loads(get_pattern_matching_value(current_plot_data))
        sub_plot_value = get_pattern_matching_value(sub_plot_value)
        current_labels = get_pattern_matching_value(current_labels)

        slide_information = json.loads(get_pattern_matching_value(slide_information))
        sub_div_content = []

        if 'selected-sub-butt' in ctx.triggered_id['type']:
            if not sub_plot_value is None:

                if type(sub_plot_value)==str:
                    sub_plot_value = [sub_plot_value]
                if type(sub_plot_value[0])==list:
                    sub_plot_value = sub_plot_value[0]

                # Pulling selected data points from current plot_data
                current_selected = current_plot_data['selected']
                
                selected_data = self.get_data_from_database(
                    slide_info = slide_information,
                    structure_id = [i[1] for i in current_selected],
                    property_list = sub_plot_value + [current_labels]
                )

                if len(selected_data)>0:
                    data_df = pd.DataFrame.from_records(selected_data).dropna(subset = sub_plot_value, how='all')
                    data_df.reset_index(inplace=True,drop=True)

                    if len(sub_plot_value)==1:
                        sub_plot_figure = self.gen_violin_plot(
                            data_df = data_df,
                            label_col = current_labels,
                            property_column = sub_plot_value[0],
                            customdata_columns = ['bbox','structure.id']
                        )
                    elif len(sub_plot_value)==2:
                        sub_plot_figure = self.gen_scatter_plot(
                            data_df = data_df,
                            plot_cols = sub_plot_value,
                            label_col = current_labels,
                            customdata_cols = ['bbox','structure.id']
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
                            customdata_cols = ['bbox','structure.id']
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
            current_selected = current_plot_data['selected']

            property_columns = list(current_plot_data['data'][0].keys())

            selected_data = self.get_data_from_database(
                slide_info = slide_information,
                structure_id = [i[1] for i in current_selected],
                propety_list = property_columns
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

    def sub_select_data(self, sub_selected_data, slide_information):
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
        slide_information = json.loads(get_pattern_matching_value(slide_information))
        
        if sub_selected_data is None:
            raise exceptions.PreventUpdate
        if type(sub_selected_data)==list:
            if len(sub_selected_data)==0:
                raise exceptions.PreventUpdate

        x_scale = slide_information.get('x_scale')
        y_scale = slide_information.get('y_scale')

        map_marker_geojson = dl.GeoJSON(
            data = {
                'type': 'FeatureCollection',
                'features': [
                    {
                        'type': 'Feature',
                        'geometry': {
                            'type': 'Point',
                            'coordinates': [
                                x_scale*((p['customdata'][0][0]+p['customdata'][0][2])/2),
                                y_scale*((p['customdata'][0][1]+p['customdata'][0][3])/2)
                            ]
                        },
                        'properties': {
                            'id': p['customdata'][1]
                        }
                    }
                    for p_idx, p in enumerate(sub_selected_data['points'])
                ]
            },
            pointToLayer=self.js_namespace("markerRender"),
            onEachFeature=self.js_namespace("tooltipMarker"),
            id = {'type': f'{self.component_prefix}-property-plotter-markers','index': 0},
            eventHandlers = {
                'dblclick': self.js_namespace('removeMarker')
            }
        )

        return [map_marker_geojson]


class GlobalPropertyPlotter(MultiTool):
    """
    This is a Property Plotter component which can be used for generating plots across multiple different slides
    """

    title = 'Global Property Plotter'
    description = 'Select one or a combination of properties to generate a plot.'

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

        else:
            self.preloaded_options = None

    def extract_property_keys(self, session_data:dict):

        start = time.time()
        all_property_keys = []
        for slide in session_data['current']:

            #TODO: Check if slide is in cache

            # Determine whether this is a DSA slide or local
            if slide.get('type')=='remote_item':
                item_id = slide['metadata'].split('/')[-1]
                # Setting request string
                external_token = session_data.get('user').get('external',{}).get('token')
                if not external_token is None:
                    request_str = f'{slide["url"]}/annotation/item/{item_id}/plot/list?token={external_token}'
                else:
                    request_str = f'{slide["url"]}/annotation/item/{item_id}/plot/list'

                sep_str = '&' if '?' in request_str else '?'
                request_str+=f'{sep_str}adjacentItems=false&sources=item,annotation,annotationelement&annotations=["__all__"]'
                
                req_time = time.time()
                req_obj = requests.post(request_str)
                if req_obj.ok:
                    all_property_keys.extend(req_obj.json())
                
            else:
                item_id = slide['id']
                # Setting LocalTileServer request string
                request_str = f'{slide["annotations_metadata"].replace("metadata","data/list")}'

                req_obj = requests.get(request_str)
                if req_obj.ok:
                    all_property_keys.extend(req_obj.json())

        property_names = []
        property_keys = []
        for k in all_property_keys:
            # Ignore dimension reduction keys
            if 'Dimension Reduction' in k['title']:
                continue

            if not k['title'] in property_names:
                property_names.append(k['title'])
                property_keys.append(k)
            else:
                p_info = property_keys[property_names.index(k['title'])]
                p_info['count']+=k['count']

                if k['type']==p_info['type']:
                    if k['type']=='string':
                        if not all([i in p_info['distinct'] for i in k.get('distinct',[])]):
                            p_info['distinct'].extend([i for i in k['distinct'] if not i in p_info['distinct']])
                            p_info['distinctcount'] = len(p_info['distinct'])
                    elif k['type']=='number':
                        if p_info['max']<k['max']:
                            p_info['max'] = k['max']
                        
                        if p_info['min']>k['min']:
                            p_info['min'] = k['min']
                else:
                    # BIG NO-NO ERROR >:o
                    continue

                property_keys[property_names.index(k['title'])] = p_info

        bbox_cols = ['bbox.x0','bbox.y0','bbox.x1','bbox.y1']
        slide_col = 'item.name'
        structure_col = 'annotation.name'


        return property_keys, property_names, structure_col, slide_col, bbox_cols
    
    def get_plottable_data(self, session_data, keys_list, label_keys, structure_list):

        #TODO: Enable database integration here 
        # Main changes:
        #   1) Checking cache for items in "current"
        #   2) Updating "annotation.name" to "layer.name" in cached/local items
        #   3) Updating "bbox" keys to "bbox.min_x", "bbox.min_y", "bbox.max_x", "bbox.max_y" instead of x0, y0, x1, y1

        # self.database.get_structure_property_data automatically returns 
        # [*propery_list: numeric or str for each property, structure.id: str, bbox: list, layer.id: str, layer.name: str, item.id: str, item.name: str]


        # Required keys for backwards identification
        req_keys = ['item.name','annotation.name','bbox.x0','bbox.y0','bbox.x1','bbox.y1']
        if not label_keys is None and not label_keys in req_keys and not label_keys in keys_list:
            keys_list += [label_keys]
        keys_list+= [i for i in req_keys if not i in keys_list]

        property_data = pd.DataFrame()

        user_external_token = self.get_user_external_token(session_data)
        user_internal_token = self.get_user_internal_token(session_data)

        for slide in session_data['current']:
            if slide.get('cached'):
                #TODO: Grab data from the local fusionDB instance
                pass

            # Determine whether this is a DSA slide or local
            if slide.get('type')=='remote_item':
                item_id = slide['metadata'].split('/')[-1]
                if not structure_list is None and not structure_list==[]:
                    if external_token is None:
                        ann_meta = requests.get(
                            slide['annotations_metadata']
                        ).json()
                    else:
                        ann_meta = requests.get(
                            slide['annotations_metadata']+f'?token={user_external_token}'
                        ).json()

                    structure_names = [a['annotation']['name'] for a in ann_meta]
                    structure_ids = []
                    for s in structure_list:
                        if s in structure_names:
                            structure_ids.append(ann_meta[structure_names.index(s)]['_id'])
                else:
                    structure_ids = ["__all__"]

                if len(structure_ids)==0:
                    structure_ids = ["__all__"]
                
                # Setting request string
                if not external_token is None:
                    request_str = f'{slide["url"]}/annotation/item/{item_id}/plot/data?token={user_external_token}'
                else:
                    request_str = f'{slide["url"]}/annotation/item/{item_id}/plot/data'

                sep_str = '&' if '?' in request_str else '?'
                request_str+=f'{sep_str}keys={",".join(keys_list)}&sources=annotationelement,item,annotation&annotations={json.dumps(structure_ids).strip()}'
                req_obj = requests.post(request_str)
                if req_obj.ok:
                    req_json = req_obj.json()
                    if property_data.empty:
                        property_data = pd.DataFrame(columns = [i['key'] for i in req_json['columns']], data = req_json['data'])
                    else:
                        new_df = pd.DataFrame(columns = [i['key'] for i in req_json['columns']], data = req_json['data'])
                        property_data = pd.concat([property_data,new_df],axis=0,ignore_index=True)
                else:
                    print(request_str)
                    print(f'DSA req no good')

            else:

                if structure_list is None:
                    structure_list = ['__all__']

                item_id = slide['id']
                # Setting LocalTileServer request string
                request_str = f'{slide["annotations_metadata_url"].replace("metadata","data")}?include_keys={",".join(keys_list).strip()}&include_anns={",".join(structure_list).strip()}&token={user_internal_token}'
                req_obj = requests.get(request_str)
                if req_obj.ok:
                    req_json = req_obj.json()
                    if property_data.empty:
                        property_data = pd.DataFrame(columns = req_json['columns'], data = req_json['data'])
                    else:
                        new_df = pd.DataFrame(columns = req_json['columns'], data = req_json['data'])
                        property_data = pd.concat([property_data,new_df],axis=0,ignore_index=True)
                else:
                    print(f'request_str: {request_str}')
                    print('local request no good')


        return property_data

    def extract_property_info(self, property_data):
            
        property_info = {}
        for p in property_data:
            if any([i in str(property_data[p].dtype).lower() for i in ['object','category','string']]):
                p_data = property_data[p]
                if type(p_data)==pd.DataFrame:
                    p_data = p_data.iloc[:,0]

                property_info[p] = {
                    'unique': property_data[p].unique().tolist(),
                    'distinct': int(property_data[p].nunique())
                }
            elif any([i in str(property_data[p].dtype).lower() for i in ['int','float','bool']]):
                property_info[p] = {
                    'min': float(property_data[p].min()),
                    'max': float(property_data[p].max()),
                    'distinct': int(property_data[p].nunique())
                }
            else:
                print(f'property: {p} has dtype {property_data[p].dtype} which is not implemented!')

        return property_info

    def update_layout(self, session_data:dict, use_prefix:bool):
        
        property_keys = []
        property_names = []
        structure_col = []
        slide_col = []
        bbox_cols = []
        structure_names = []

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        html.H3(self.title)
                    ]),
                    html.Hr(),
                    dbc.Row(
                        self.description
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Label('Select properties below: ',html_for = {'type': 'global-property-plotter-drop','index': 0}),
                    ]),
                    dcc.Store(
                        id = {'type': 'global-property-plotter-keys-store','index': 0},
                        data = json.dumps({
                            'dropdown': property_names,
                            'slide_col': slide_col,
                            'structure_col': structure_col,
                            'bbox_cols': bbox_cols,
                        }),
                        storage_type='memory'
                    ),
                    dcc.Store(
                        id = {'type': 'global-property-plotter-property-info','index': 0},
                        data = json.dumps(property_keys),
                        storage_type = 'memory'
                    ),
                    dcc.Store(
                        id = {'type': 'global-property-plotter-fetch-error-store','index': 0},
                        data = json.dumps({}),
                        storage_type='memory'
                    ),
                    dbc.Row([
                        dcc.Loading(html.Div(
                            dcc.Dropdown(
                                options = property_names,
                                value = [],
                                id = {'type': 'global-property-plotter-drop','index': 0},
                                multi = True,
                                placeholder = 'Properties'
                            ),
                            id = {'type': 'global-property-plotter-drop-div','index': 0}
                        ))
                    ]),
                    html.Hr(),
                    dbc.Row(
                        dbc.Label('Select structures to include: ', html_for = {'type': 'global-property-plotter-structures','index': 0})
                    ),
                    dbc.Row([
                        dcc.Loading(dcc.Dropdown(
                            options = structure_names,
                            value = [],
                            id = {'type': 'global-property-plotter-structures','index': 0},
                            multi = True,
                            placeholder = 'Structures'
                        )),
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
                                        id = {'type': 'global-property-plotter-add-filter-butt','index': 0},
                                        disable_n_clicks=True
                                    )
                                ),
                                dbc.Tooltip(
                                    target = {'type': 'global-property-plotter-add-filter-butt','index': 0},
                                    children = 'Click to add a filter.'
                                )
                            ],style = {'width': '100%'})
                        ],align='center',md='auto')
                    ],align='center',justify='center',style = {'width': '100%'}),
                    html.Hr(),
                    dbc.Row([
                        dbc.Label('Select a label to apply to points in the plot',html_for = {'type': 'global-property-plotter-label-drop','index': 0})
                    ]),
                    dbc.Row([
                        dcc.Loading(dcc.Dropdown(
                            options = property_names,
                            value = [],
                            multi = False,
                            id = {'type': 'global-property-plotter-label-drop','index': 0},
                            placeholder = 'Label'
                        ))
                    ],style = {'marginBottom':'10px'}),
                    dbc.Row([
                        dbc.Button(
                            'Generate Plot!',
                            id = {'type': 'global-property-plotter-plot-butt','index': 0},
                            n_clicks = 0,
                            className = 'd-grid col-12 mx-auto',
                            disabled = True
                        )
                    ],style = {'marginBottom': '10px'}),
                    dbc.Row([
                        dbc.Col([
                            dcc.Loading([
                                dcc.Store(
                                    id = {'type': 'global-property-plotter-selection-store','index': 0},
                                    data = json.dumps({'property_names': [], 'property_keys': [], 'structure_names': [], 'label_names': [], 'filters': [], 'data': []}),
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
                    ]),
                    html.Hr(),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'global-property-plotter-plot-report-div','index': 0},
                            children = [],
                            style = {'marginTop': '5px'}
                        )
                    ])
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow':'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(layout)

        return layout

    def get_callbacks(self):
        
        #TODO: Callbacks
        # Callback for updating type of feature selector (either dropdown or tree)
        # Callback for running statistics
        # Callback for exporting plot data

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
                Output({'type': 'global-property-plotter-selection-store','index': ALL},'data')
            ],
            [
                State({'type': 'global-property-plotter-add-filter-parent','index': ALL},'children'),
                State({'type': 'global-property-plotter-selection-store','index': ALL},'data'),
                State({'type': 'global-property-plotter-keys-store','index': ALL},'data'),
                State({'type': 'global-property-plotter-property-info','index': ALL},'data')
            ]
        )(self.update_properties_and_filters)

        # Generating plot of selected properties, structures, labels
        self.blueprint.callback(
            [
                Input({'type': 'global-property-plotter-plot-butt','index':ALL},'n_clicks')
            ],
            [
                Output({'type': 'global-property-plotter-selection-store','index': ALL},'data'),
                Output({'type': 'global-property-plotter-plot-div','index': ALL},'children'),
                Output({'type': 'global-property-plotter-plot-report-div','index': ALL},'children')
            ],
            [
                State({'type': 'global-property-plotter-selection-store','index': ALL},'data'),
                State({'type': 'global-property-plotter-data-store','index': ALL},'data'),
                State({'type': 'global-property-plotter-keys-store','index': ALL},'data'),
                State('anchor-vis-store','data')
            ],
            running = [
                (Output({'type': 'global-property-plotter-plot-butt','index': ALL},'disabled'),True,False)
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
                State('anchor-vis-store','data')
            ]
        )(self.select_data_from_plot)

    def get_clientside_callbacks(self):
        
        self.blueprint.clientside_callback(
            """
            async function processData(page_url,page_path,page_search,session_data,current_keys_store,current_property_info,current_structures,current_labels) {

            if (!session_data) {
                throw window.dash_clientside.PreventUpdate;
            }
            if (!current_property_info || !current_property_info[0]) {
                throw window.dash_clientside.PreventUpdate;
            }

            const mergePropertyKeys = (allPropertyKeys) => {
                const uniqueKeys = [...new Set(allPropertyKeys.filter((prop) => !(prop.key.includes('compute'))).map((prop) => prop.key))];

                return uniqueKeys.map((key) => {
                    const props = allPropertyKeys.filter((prop) => prop.key === key);
                    const base = {
                        key,
                        title: props[0].title,
                        count: props.reduce((sum, p) => sum + p.count, 0),
                        type: props[0].type,
                    };
                    if (props.length > 1) {
                        if (props[0].type === 'string') {
                            // Check this with your code since it's string and it can be messy sometimes for different inputs. 
                            const distinctValues = [...new Set(props.flatMap((p) => p.distinct))];
                            return {
                                ...base,
                                distinct: distinctValues,
                                distinctcount: distinctValues.length,
                            };
                        } else {
                            const mins = props.map((p) => p.min);
                            const maxs = props.map((p) => p.max);
                            return {
                                ...base,
                                min: Math.min(...mins),
                                max: Math.max(...maxs),
                            };
                        }
                    }
                return base;
                });
            };

            const parsedSessionData = JSON.parse(session_data);
            const parsedPropertyInfo = JSON.parse(current_property_info[0])[0];

            // Just using ternary operators for if conditions. Change it back to original if you want. 
            const currentItems =
                parsedPropertyInfo && parsedPropertyInfo.find((x) => x.key === 'item.id')
                ? parsedPropertyInfo.find((x) => x.key === 'item.id').distinct
                : [];

            
            const sessionItems = parsedSessionData.current.map((s_data) =>
                'url' in s_data
                ? s_data.metadata.split('/').reverse()[0]
                : s_data.metadata.split('/').reverse()[1]
            );
            console.log(sessionItems);

            // If session items haven't changed, return
            if (JSON.stringify(sessionItems) === JSON.stringify(currentItems)) {
                return [
                    [JSON.stringify(current_keys_store)],
                    [JSON.stringify(parsedPropertyInfo)],
                    [current_labels],
                    [current_structures],
                    [current_labels],
                    [JSON.stringify({})],
                    [false],
                    [false]
                ];
            }

            const cloudSlides = parsedSessionData.current.filter(
                (item) => item.type=='remote_item'
            );
            const localSlides = parsedSessionData.current.filter(
                (item) => item.type=='local_item'
            );

            const localPropUrls = localSlides.map((slide_info) =>
                slide_info.annotations_metadata_url.replace('metadata', 'data/list')
            );

            const cloudPropUrls = cloudSlides.map((slide_info) =>
                'user' in parsedSessionData
                ? `${slide_info.annotations}/plot/list?token=${parsedSessionData.user.external.token}&adjacentItems=false&sources=item,annotation,annotationelement&annotations=["__all__"]`
                : `${slide_info.annotations}/plot/list?token=${parsedSessionData.user.token}&adjacentItems=false&sources=item,annotation,annotationelement&annotations=["__all__"]`
            );

            // Fetch cloud data (POST) concurrently 
            const fetchCloudData = async () => {
                const responses = await Promise.all(
                    cloudPropUrls.map(async (url) => {
                        const res = await fetch(url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        });
                        return res.json();
                    })
                );
                return responses.flat();
            };

            // Fetch local data (GET) concurrently
            const fetchLocalData = async () => {
                const responses = await Promise.all(
                    localPropUrls.map(async (url) => {
                        const res = await fetch(url, {
                        method: 'GET',
                        headers: { 'Content-Type': 'application/json' },
                        });
                        return res.json();
                    })
                );
                return responses.flat();
            };

            // Waiting for both cloud and local requests to complete before proceeding
            // This is the main part of the code where we are fetching data from cloud and local and handling Promises
            const [cloudData, localData] = await Promise.all([
                fetchCloudData(),
                fetchLocalData(),
            ]);
            const allPropertyKeys = [...cloudData, ...localData];

            const mergedPropertyKeys = mergePropertyKeys(allPropertyKeys);

            const keysStoreData = {
                dropdown: [...new Set(mergedPropertyKeys.map((prop) => prop.title))],
                tree: { name_key: {}, full: {} },
                slide_col: 'item.name',
                structure_col: 'annotation.name',
                bbox_cols: ['bbox.x0', 'bbox.y0', 'bbox.x1', 'bbox.y1'],
            };

            let structureNames = [];
            let labelDrop = [];
            let propDrop = [];
            const annotationKeyObj = mergedPropertyKeys.find(
                (k) => k.key === 'annotation.name'
            );
            if (annotationKeyObj && annotationKeyObj.distinct) {
                structureNames = annotationKeyObj.distinct;
            }
            labelDrop = mergedPropertyKeys.map((k) => k.title);
            propDrop = mergedPropertyKeys.map((k) => k.title);

            // Return the final JSON data for Dash
            return [
                [JSON.stringify(keysStoreData)],
                [JSON.stringify(mergedPropertyKeys)],
                [propDrop],
                [structureNames],
                [labelDrop],
                [JSON.stringify({})],
                [false],
                [false]
            ];
            }
            """,
            [
                Output({'type': 'global-property-plotter-keys-store','index': ALL},'data'),
                Output({'type': 'global-property-plotter-property-info','index': ALL},'data'),
                Output({'type': 'global-property-plotter-drop','index': ALL},'options'),
                Output({'type': 'global-property-plotter-structures','index': ALL},'options'),
                Output({'type': 'global-property-plotter-label-drop','index': ALL},'options'),
                Output({'type': 'global-property-plotter-fetch-error-store','index': ALL},'data'),
                Output({'type': 'global-property-plotter-plot-butt','index': ALL},'disabled'),
                Output({'type': 'global-property-plotter-add-filter-butt','index': ALL},'disabled')
            ],
            [
                Input('anchor-page-url','href'),
                Input('anchor-page-url','pathname'),
                Input('anchor-page-url','search')
            ],
            [
                State('anchor-vis-store','data'),
                State({'type': 'global-property-plotter-keys-store','index': ALL},'data'),
                State({'type': 'global-property-plotter-property-info','index': ALL},'data'),
                State({'type': 'global-property-plotter-structures','index': ALL},'options'),
                State({'type': 'global-property-plotter-label-drop','index': ALL},'options'),
            ],
            prevent_initial_call = True,
        )

        #TODO: Have to update the inputs to this callback since those don't always change now when a new page is accessed

    def update_properties_and_filters(self, property_selection, property_checked, structure_selection, label_selection, filter_prop_mod, filter_prop_remove, filter_prop_selector, property_divs,current_data, keys_info, property_info):
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
        keys_info = json.loads(get_pattern_matching_value(keys_info))
        property_divs = get_pattern_matching_value(property_divs)
        property_info = json.loads(get_pattern_matching_value(property_info))

        processed_prop_filters = self.parse_filter_divs(property_divs)

        current_data['filters'] = processed_prop_filters
        if not get_pattern_matching_value(property_selection) is None:
            current_data['property_names'] = get_pattern_matching_value(property_selection)
        elif not get_pattern_matching_value(property_checked) is None:
            current_data['property_names'] = [keys_info['tree']['name_key'][i] for i in get_pattern_matching_value(property_checked) if i in keys_info['name_key']]
        
        current_data['property_keys'] = []
        prop_titles = [i['title'] for i in property_info]
        for p in current_data['property_names']:
            if p in prop_titles:
                current_data['property_keys'].append(property_info[prop_titles.index(p)]['key'])

        current_data['structure_names'] = get_pattern_matching_value(structure_selection)
        selected_labels = get_pattern_matching_value(label_selection)
        if selected_labels in prop_titles:
            current_data['label_names'] = selected_labels
            current_data['label_keys'] = property_info[prop_titles.index(selected_labels)]['key']
        else:
            current_data['label_names'] = None
            current_data['label_keys'] = None
        
        return [json.dumps(current_data)]

    def generate_plot(self, butt_click, data_selection, plottable_data, keys_info, session_data):
        """Generate a new plot based on selected properties

        :param butt_click: Generate Plot button clicked
        :type butt_click: list
        :param current_data: Dictionary containing current selected properties (in a list)
        :type current_data: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        data_selection = json.loads(get_pattern_matching_value(data_selection))
        property_names = data_selection['property_names']
        property_keys = data_selection['property_keys']
        structure_names = data_selection['structure_names']
        label_names = data_selection['label_names']
        label_keys = data_selection['label_keys']
        filters = data_selection['filters']

        if len(property_names)==0:
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)
        keys_info = json.loads(get_pattern_matching_value(keys_info))

        # Checking if slide_col, structure_col, or any bbox_col's are used by properties or labels
        slide_col = keys_info['slide_col']
        structure_col = keys_info['structure_col']
        bbox_cols = keys_info['bbox_cols']
       
        if slide_col in property_keys or slide_col==label_keys:
            if slide_col in property_keys:
                slide_col = property_names[property_keys.index(slide_col)]
            elif slide_col==label_keys:
                slide_col = label_names
        
        if structure_col in property_keys or structure_col==label_keys:
            if structure_col in property_keys:
                structure_col = property_names[property_keys.index(structure_col)]
            elif structure_col==label_keys:
                structure_col = label_names

        if any([b in property_keys for b in bbox_cols]):
            overlap_one = [b for b in bbox_cols if b in property_keys][0]
            bbox_cols[bbox_cols.index(overlap_one)] = property_keys[property_keys.index(overlap_one)]
        elif any([b==label_keys for b in bbox_cols]):
            overlap_one = [b for b in bbox_cols if b==label_keys][0]
            bbox_cols[bbox_cols.index(overlap_one)] = label_keys

        plottable_df = self.get_plottable_data(session_data,property_keys,label_keys,structure_names)

        # Updating with renamed columns from labels
        plottable_df = plottable_df.rename(columns = {k:v for k,v in zip([keys_info['structure_col']],[structure_col])} | {h:q for h,q in zip([keys_info['slide_col']],[slide_col])} | {i:r for i,r in zip(keys_info['bbox_cols'],bbox_cols)})

        # Applying filters to the current data
        filtered_properties = pd.DataFrame()
        if not plottable_df.empty:
            if not structure_names is None:
                filtered_properties = plottable_df[plottable_df[structure_col].isin(structure_names)]
            else:
                filtered_properties = plottable_df.copy()

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
            data_selection['data'] = filtered_properties.to_dict('records')

            renamed_props = filtered_properties.rename(columns = {k:v for k,v in zip([label_keys],[label_names])} | {h:q for h,q in zip(property_keys,property_names)})
            #print(f'renamed_props columns: {renamed_props.columns.tolist()}')
            #print(f'property_names: {property_names}')
            if len(property_names)==1:
                plot_fig = self.gen_violin_plot(renamed_props, label_names, property_names[0], [slide_col]+bbox_cols)
            elif len(property_names)==2:
                plot_fig = self.gen_scatter_plot(renamed_props,property_names,label_names,[slide_col]+bbox_cols)
            elif len(property_names)>2:
                
                umap_columns = self.gen_umap_cols(renamed_props,property_names)
                filtered_properties['UMAP1'] = umap_columns['UMAP1'].tolist()
                filtered_properties['UMAP2'] = umap_columns['UMAP2'].tolist()
                renamed_props['UMAP1'] = umap_columns['UMAP1'].tolist()
                renamed_props['UMAP2'] = umap_columns['UMAP2'].tolist()

                data_selection['data'] = filtered_properties.to_dict('records')
 
                plot_fig = self.gen_scatter_plot(renamed_props,['UMAP1','UMAP2'],label_names,[slide_col]+bbox_cols)

            return_fig = dcc.Graph(
                id = {'type': f'{self.component_prefix}-global-property-plotter-plot','index': 0},
                figure = plot_fig
            )

        plot_report_tabs = self.make_property_plot_tabs(renamed_props, label_names, property_names, [slide_col,structure_col]+bbox_cols)

        return [json.dumps(data_selection)],[return_fig],[plot_report_tabs]
    
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
            label_data = data_df[label_col]
            if type(label_data)==pd.DataFrame:
                label_data = label_data.iloc[:,0]

            unique_labels = [i for i in label_data.unique().tolist() if type(i)==str]

            for u_idx, u in enumerate(unique_labels):
                this_label_data = data_df[label_data.astype(str).str.match(u)].loc[:,[i for i in property_cols if i in data_df]]
                
                summary = this_label_data.describe().round(decimals=4)
                summary.reset_index(inplace=True,drop=False)

                property_summary_children.extend([
                    html.H3(f'Samples labeled: {u}'),
                    html.Hr(),
                    dash_table.DataTable(
                        id = {'type': f'{self.component_prefix}-global-property-summary-table','index': u_idx},
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
                    id = {'type': f'{self.component_prefix}-global-property-summary-table','index': 0},
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
            id = {'type': f'{self.component_prefix}-global-property-summary-tab','index': 0},
            children = property_summary_children,
            tab_id = 'property-summary',
            label = 'Property Summary'
        )

        # Property statistics
        label_stats_children = []
        if data_df.shape[0]>1:
            if not label_col is None:
                label_data = data_df[label_col]
                if type(label_data)==pd.DataFrame:
                    label_data = label_data.iloc[:,0]

                unique_labels = label_data.unique().tolist()

                if len(unique_labels)>1:
                    
                    multiple_members_check = any([i>1 for i in list(label_data.value_counts().to_dict().values())])

                    if multiple_members_check:
                        
                        data_df = data_df.T.drop_duplicates().T.dropna(axis=0,how='any')
                        p_value, results = get_label_statistics(
                            data_df = data_df.loc[:,[i for i in data_df if not i in customdata_cols or i==label_col]],
                            label_col=label_col
                        )

                        if not p_value is None:
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
                                                id = {'type': f'{self.component_prefix}-global-property-stats-table','index': 0},
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
                                                id = {'type': f'{self.component_prefix}-global-property-stats-table','index':0},
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
                                                id = {'type': f'{self.component_prefix}-global-property-stats-tukey','index': 0},
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
                                            id=f'{self.component_prefix}-global-pearson-table',
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
                                            id=f'{self.component_prefix}-global-silhouette-table',
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
                                dbc.Alert(f'Property is "nan" or otherwise missing in one or more labels',color = 'warning')
                            )

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
            id = {'type': f'{self.component_prefix}-global-property-stats-tab','index': 0},
            children = label_stats_children,
            tab_id = 'property-stats',
            label = 'Property Statistics'
        )

        selected_data_tab = dbc.Tab(
            id = {'type': f'{self.component_prefix}-global-property-selected-data-tab','index': 0},
            children = html.Div(
                id = {'type': f'{self.component_prefix}-global-property-graph-selected-div','index': 0},
                children = ['Select data points in the plot to get started!']
            ),
            tab_id = 'property-selected-data',
            label = 'Selected Data'
        )

        property_plot_tabs = dbc.Tabs(
            id = {'type': f'{self.component_prefix}-global-property-plot-tabs','index': 0},
            children = [
                property_summary_tab,
                label_stats_tab,
                #selected_data_tab
            ],
            active_tab = 'property-summary'
        )

        return property_plot_tabs

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

        label_x = None
        if label_col is not None:
            label_x = data_df[label_col]
            if type(label_x)==pd.DataFrame:
                label_x = label_x.iloc[:,0]


        figure = go.Figure(
            data = go.Violin(
                x = label_x,
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

        data_df = data_df.T.drop_duplicates().T

        title_width = 30

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
                            width = title_width
                            )
                        )
                )
            )

            label_data = data_df[label_col]
            if type(label_data)==pd.DataFrame:
                label_data = label_data.iloc[:,0]

            if not label_data.dtype == np.number:
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
                            'color': label_data.values,
                            'colorbar':{
                                'title': label_col
                            },
                            'colorscale':'jet'
                        },
                        text = label_data.values,
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
                            width = title_width
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

        session_data = json.loads(session_data)
        selected_data = get_pattern_matching_value(selected_data)

        user_external_token = self.get_user_external_token(session_data)
        user_internal_token = self.get_user_internal_token(session_data)

        session_names = [i['name'] for i in session_data['current']]
        local_names = [i['name'] for i in session_data['local']]
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
                if s_slide in local_names:
                    user_token = user_internal_token
                else:
                    user_token = user_external_token

                image_region = Image.open(
                    BytesIO(
                        requests.get(
                            session_data['current'][session_names.index(s_slide)]['regions']+f'?top={s_bbox[1]}&left={s_bbox[0]}&bottom={s_bbox[3]}&right={s_bbox[2]}&token={user_token}'
                        ).content
                    )
                )

                selected_image_list.append(image_region)

        if len(selected_image_list)==1:
            selected_image = px.imshow(
                selected_image_list[0]
            )

            selected_image.update_layout(margin = {'t':0,'b':0,'l':0,'r':0})

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

            selected_image = px.imshow(
                np.stack(
                    modded_images,
                    axis=0
                ),
                animation_frame=0,
                binary_string=True
            )
            selected_image.update_layout(margin = {'t':0,'b':0,'l':0,'r':0})


        else:
            selected_image = go.Figure()
            print(f'No images found')
            print(f'selected:{selected_data}')

        return [dcc.Graph(figure = selected_image)]

















































