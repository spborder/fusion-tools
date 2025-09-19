"""

Components which extract data from the current SlideMap for formatted download

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
#import dash_treeview_antd as dta
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform, BlockingCallbackTransform
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
from fusion_tools.components.base import Tool, MultiTool

import time


class DataExtractor(Tool):
    """
    """

    title = 'Data Extractor'
    description = 'Download select properties from indicated structures in the current slide.'

    def __init__(self):

        super().__init__()

        self.exportable_session_data = {
            'Slide Metadata':{
                'description': 'This is any information about the current slide including labels, preparation details, and image tile information.'
            },
            'Visualization Session':{
                'description': 'This is a record of your current Visualization Session which can be uploaded in the Dataset Builder page to reload.'
            }
        }


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
                        html.H3(self.title)
                    ),
                    html.Hr(),
                    dbc.Row(
                        self.description
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
        download_folder = self.assets_folder+'/downloads/'
        if not os.path.exists(download_folder+base_download_folder):
            os.makedirs(download_folder+base_download_folder)

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
                    if not os.path.exists(self.assets_folder+'/downloads/'+base_download_folder+'/'+data):
                        os.makedirs(self.assets_folder+'/downloads/'+base_download_folder+'/'+data)

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
                            'folder': self.assets_folder+'/downloads/'+base_download_folder,
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
                            'folder': self.assets_folder+'/downloads/'+base_download_folder,
                            'features': struct_features,
                            '_id': uuid.uuid4().hex[:24]
                        }
                    )

        download_data_store = json.dumps({
            'selected_data': [],
            'base_folder':self.assets_folder+'/downloads/'+base_download_folder,
            'zip_file_path': self.assets_folder+'/downloads/'+base_download_folder+'/fusion_download.zip',
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
        
