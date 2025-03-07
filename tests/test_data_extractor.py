"""Selective data grabber test
"""

import os
import sys
sys.path.append('./src/')
import json
import requests

from fusion_tools.visualization import Visualization
from fusion_tools.components import SlideMap, OverlayOptions, PropertyPlotter
from fusion_tools import Tool
from fusion_tools.visualization.vis_utils import get_pattern_matching_value

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


class DataExtractor(Tool):
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

        # Set of components for importing markers
        # Set of components for adding markers
        # Set of components for selecting properties
        # Set of components for selecting additional data (image, geometry, bbox, slide name)
        # Set of components for downloading data

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
                            is_open = [],
                            size = 'xl'
                        ),
                        dcc.Interval(
                            id = {'type': 'data-extractor-download-interval','index': 0},
                            disabled = True,
                            interval = 1000,
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
                        id = {'type':'data-extractor-selected-data-parent-div','index': 0},
                        children = [
                            'Selected data descriptions will appear here'
                        ],
                        style = {'maxHeight': '100vh','overflow': 'scroll'}
                    ),
                    dbc.Row([
                        dcc.Loading([
                            dbc.Button(
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
                Input({'type': 'map-annotations-store','index': ALL},'data')
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
                State({'type': 'data-extractor-store','index': ALL},'data')
            ],
            [
                Output({'type': 'data-extractor-selected-data-parent','index': ALL},'children'),
                Output({'type': 'data-extractor-download-button','index': ALL},'disabled'),
                Output({'type': 'data-extractor-store','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.update_data_info)

        # Callback for downloading selected data and clearing selections
        self.blueprint.callback(
            [
                Input({'type': 'data-extractor-download-button','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'data-extractor-download-interval','index': ALL},'disabled'),
                Output({'type': 'data-extractor-download','index': ALL},'data'),
                Output({'type':'data-extractor-current-structures-drop','index': ALL},'value'),
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
                State({'type': 'base-layer','index': ALL},'checked'),
                State({'type': 'tile-layer','index': ALL},'url')
            ],
            prevent_initial_call = True
        )(self.start_download_data)

        self.blueprint.callback(
            [
                Input({'type': 'data-extractor-download-interval','index': ALL},'n_intervals')
            ],
            [
                Output({'type':'data-extractor-download-interval','index': ALL},'disabled'),
                Output({'type': 'data-extractor-download-modal','index': ALL},'is_open'),
                Output({'type': 'data-extractor-download-modal','index':ALL},'children'),
                Output({'type': 'data-extractor-download','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.update_download_data)
    
    def update_slide(self, new_annotations:list):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        new_annotations = json.loads(get_pattern_matching_value(new_annotations))
        new_structure_names = [i['properties']['name'] for i in new_annotations if 'properties' in i]

        available_structures_drop = [
            {'label': i, 'value': i, 'disabled': False}
            for i in new_structure_names
        ]
        available_structures_drop += [{'label': 'Marked Structures','value': 'Marked Structures','disabled': True}]

        available_data_drop = [
            {'label': i, 'value': i, 'disabled': False}
            for i in self.exportable_data
        ]

        button_disabled = True
        new_data_extractor_store = json.dumps({'selected_data': []})

        return [available_structures_drop], [available_data_drop], ['Selected data descriptions will appear here'], [button_disabled], [new_data_extractor_store]

    def refresh_data(self, clicked, overlay_names, marker_div_children):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        print(overlay_names)
        print(marker_div_children)
        available_structures_drop = [
            {'label': i, 'value': i, 'disabled': False}
            for i in get_pattern_matching_value(overlay_names)
        ]
        available_structures_drop += [{'label': 'Marked Structures','value': 'Marked Structures','disabled': True if len(marker_div_children)==0 else False}]
        
        available_data_drop = [
            {'label': i, 'value': i, 'disabled': False}
            for i in self.exportable_data
        ]

        button_disabled = True

        new_data_extractor_store = json.dumps({'selected_data': []})


        return [available_structures_drop], [available_data_drop], ['Selected data descriptions will appear here'], [button_disabled],[new_data_extractor_store]

    def update_session_data_description(self, session_data_selection):
        
        if not any([i['value'] for i in ctx.triggered]):
            return ['Select a type of session data to see a description']
        
        session_data_selection = get_pattern_matching_value(session_data_selection)

        return [self.exportable_session_data[session_data_selection]['description']]

    def download_session_data(self, clicked, session_data_selection, current_slide_info, session_data):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data_selection = get_pattern_matching_value(session_data_selection)
        current_slide_info = json.loads(get_pattern_matching_value(current_slide_info))
        session_data = json.loads(session_data)

        if session_data_selection == 'Slide Metadata':
            slide_tile_url = current_slide_info['tiles_url']
            current_slide_tile_urls = [i['tiles_url'] for i in session_data['current']]
            slide_idx = current_slide_tile_urls.index(slide_tile_url)

            slide_metadata = requests.get(session_data['current'][slide_idx]['metadata_url'])

            download_content = {'content': json.dumps(slide_metadata,indent=4),'filename': 'slide_metadata.json'}
        elif session_data_selection == 'Visualization Session':
            download_content = {'content': json.dumps(session_data,indent=4),'filename': 'fusion_visualization_session.json'}

        return [download_content]

    def update_data_info(self, selected_data, data_extract_store):

        if not any([i['value'] for i in ctx.triggered]):
            return ['Selected data descriptions will appear here']
        
        print(selected_data)
        selected_data = get_pattern_matching_value(selected_data)
        current_selected_data = json.loads(get_pattern_matching_value(data_extract_store))['selected_data']
        print(current_selected_data)

        def make_new_info(data_type):
            data_type_index = list(self.exportable_data.keys()).index(data_type)
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
                    ])
                ])
            ])

            return return_card

        # Which ones are in selected_data that aren't in current_selected_data
        new_selected = list(set(selected_data) - set(current_selected_data))
        info_return = Patch()
        if len(new_selected)>0:
            # Appending to the partial property update
            info_return.append(make_new_info(new_selected))

        else:
            # Removing some de-selected values
            removed_type = list(set(current_selected_data)-set(selected_data))

            del info_return[current_selected_data.index(removed_type)]
        
        return [info_return]

    def start_download_data(self, clicked, selected_structures, selected_data, selected_data_formats, slide_annotations, slide_markers, slide_info, base_layer_checked, tile_layer_urls):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        interval_disabled = False
        new_values = []
        button_disabled = True
        selected_structures = get_pattern_matching_value(selected_structures)
        selected_data = get_pattern_matching_value(selected_data)
        slide_annotations = json.loads(get_pattern_matching_value(slide_annotations))


        print(selected_structures)
        print(selected_data)
        print(selected_data_formats)

        # Starting separate threads for downloads
        for s_idx, struct in enumerate(selected_structures):
            for d_idx, data in enumerate(selected_data):
                print(f'Starting thread for {struct} {data}')


        return [interval_disabled], [new_values], [new_values], ['Selected data descriptions will appear here'], [button_disabled]

    def update_download_data(self, new_interval):
        
        new_interval = get_pattern_matching_value(new_interval)

        if new_interval<5: 
            interval_disabled = False
            modal_open = True
            modal_children = [f'Interval count: {new_interval}/5']
            download_data = no_update
        else:
            interval_disabled = True
            modal_open = False
            modal_children = []
            download_data = no_update
        
        return [interval_disabled], [modal_open], [modal_children], [download_data]
        


def main():
    pass


if __name__=='__main__':
    main()


