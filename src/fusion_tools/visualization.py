"""
Functions related to visualization for data derived from FUSION.

- Interactive feature charts
    - View images at points
- Local slide viewers

"""
import os
import large_image.exceptions
from fastapi import FastAPI, APIRouter, Response

import large_image
import pandas as pd
import dash_leaflet as dl
from dash import dcc, callback, ctx, ALL, exceptions
import dash_bootstrap_components as dbc
from dash_extensions.enrich import DashProxy, DashBlueprint, html, Input, Output, State
from dash_extensions.javascript import assign, arrow_function, Namespace

import plotly.express as px
import plotly.graph_objects as go

import numpy as np

from typing_extensions import Union
from PIL import Image
from io import BytesIO
import json
import uvicorn
import requests


class Visualization:
    """
    General holder class used for initialization. Components added after initialization.
    """
    def __init__(self,
                 components: list,
                 layout: list,
                 app_options: dict = {}):
        

        self.components = components
        self.layout = layout
        self.app_options = app_options

        self.default_options = {
            'title': 'FUSION',
            'server': 'default',
            'server_options': {},
            'port': '8080'
        }

        self.viewer_app = DashProxy(
            __name__,
            external_stylesheets = [
                dbc.themes.LUX,
                dbc.themes.BOOTSTRAP,
                dbc.icons.BOOTSTRAP,
                dbc.icons.FONT_AWESOME
            ],
            assets_folder = self.assets_folder,
            prevent_initial_callbacks=True
        )
        self.viewer_app.title = self.app_options['title'] if 'title' in self.app_options else self.default_options['title']
        self.viewer_app.layout = []
    
    def start(self):
        """
        Starting the visualization app based on app_options        
        """
        
        if 'server' in self.app_options:
            if self.app_options['server']=='default':
                self.viewer_app.run_server(
                    host = '0.0.0.0',
                    port = self.app_options['port'] if 'port' in self.app_options else self.default_options['port'],
                    debug = False
                )
        else:
            self.viewer_app.run_server(
                host = '0.0.0.0',
                port = self.app_options['port'] if 'port' in self.app_options else self.default_options['port'],
                debug = False
            )



class TileServer:
    def __init__(self,
                 local_image_path: str
                 ):

        self.local_image_path = local_image_path

        self.tile_server_port = '8050'

        self.tile_source = large_image.open(self.local_image_path,encoding='PNG')
        self.tile_metadata = self.tile_source.getMetadata()

        self.router = APIRouter()
        self.router.add_api_route('/',self.root,methods=["GET"])
        self.router.add_api_route('/tiles/{z}/{x}/{y}',self.get_tile,methods=["GET"])
        self.router.add_api_route('/metadata',self.get_metadata,methods=["GET"])
    
    def __str__(self):
        return f'TileServer class for {self.local_image_path} to http://localhost:{self.tile_server_port}'

    def root(self):
        return {'message': "Oh yeah, now we're cooking"}

    def get_tile(self,z:int, x:int, y:int, style = {}):
        try:
            raw_tile = self.tile_source.getTile(
                        x = x,
                        y = y,
                        z = z
                    )
            
        except large_image.exceptions.TileSourceXYZRangeError:
            # This error appears for any negative tile coordinates
            raw_tile = np.zeros((self.tile_metadata['tileHeight'],self.tile_metadata['tileWidth']),dtype=np.uint8).tobytes()

        return Response(content = raw_tile, media_type='image/png')
    
    def get_metadata(self):
        large_image_metadata = self.tile_source.getMetadata()
        return Response(content = json.dumps(large_image_metadata),media_type = 'application/json')
    
    def start(self, port = 8050):
        app = FastAPI()
        app.include_router(self.router)

        uvicorn.run(app,host='0.0.0.0',port=port)


class LocalSlideViewer:
    def __init__(self,
                 tile_server_port: str
                ):
        
        self.tile_server_port = tile_server_port

        image_metadata = requests.get(
            f'http://localhost:{self.tile_server_port}/metadata'
        ).json()
        
        self.assets_folder = os.getcwd()+'/.fusion_assets/'

        self.layout = self.gen_layout(
            tile_size = image_metadata['tileWidth'],
            zoom_levels = image_metadata['levels'],
            tile_server_port = self.tile_server_port
        )

        # Add Namespace functions here:
        self.get_namespace()

        # Add callback functions here
        self.get_callbacks()

    def gen_layout(self, tile_size:int, zoom_levels: int, tile_server_port:str):
        """
        Generate simple slide viewer layout
        """
        layout = html.Div(
            dl.Map(
                id = 'slide-map',
                crs = 'Simple',
                center = [-tile_size,tile_size],
                zoom = 1,
                style = {'height': '90vh','width': '95vw','margin': 'auto','display': 'inline-block'},
                children = [
                    dl.TileLayer(
                        id = 'slide-tile-layer',
                        url = f'http://localhost:{tile_server_port}/tiles'+'/{z}/{x}/{y}',
                        tileSize=tile_size,
                        maxNativeZoom=zoom_levels-1,
                        minZoom = 0
                    ),
                    dl.FullScreenControl(
                        position = 'upper-left'
                    ),
                    dl.FeatureGroup(
                        id='edit-feature-group',
                        children = [
                            dl.EditControl(
                                id = 'edit-control',
                                draw = dict(polyline=False, line=False, circle = False, circlemarker=False),
                                position='topleft'
                            )
                        ]
                    ),
                    dl.LayersControl(
                        id = 'slid-layers-control',
                        children = []
                    ),
                    dl.EasyButton(
                        icon = 'fa-solid fa-arrows-to-dot',
                        title = 'Re-Center Map',
                        id = 'center-map',
                        position = 'top-left',
                        eventHandlers = {
                            'click': self.js_namespace('centerMap')
                        }
                    ),
                ]
            )
        )

        return layout

    def get_namespace(self):
        """
        Adding javascript functions to layout
        """
        self.js_namespace = Namespace(
            "fusionTools","default"
        )

        self.js_namespace.add(
            src = 'function(e,ctx){ctx.map.flyTo([-120,120],1);}',
            name = "centerMap"
        )

        self.js_namespace.add(
            src = """
                function(feature,context){
                const {colorKey, overlayProp, fillOpacity, lineColor, featureFilter} = context.hideout;
                var style = {};


                return style;
                }

                """,
            name = 'featureStyle'
        )

        self.js_namespace.add(
            src = """
                function(feature,context){
                const {colorKey, overlayProp, fillOpacity, lineColor, featureFilter} = context.hideout;
                
                var returnFeature = true;


                return returnFeature;
                }
                """,
            name = 'featureFilter'
        )


        self.js_namespace.dump(
            assets_folder = self.assets_folder
        )

    def get_callbacks(self):
        # Add callbacks to self.viewer_app
        # Maybe add something so users can point the app to some zarr storage or add polygons either through uploads or on initialization


        pass


class FeatureViewer:
    def __init__(self,
                 feature_df: pd.DataFrame,
                 item_id: str,
                 ann_name: str,
                 mode: str,
                 mode_col: Union[str,list],
                 fusion_handler,
                 viewer_title = 'Feature Viewer'
                 ):
        
        self.feature_df = feature_df
        self.viewer_title = viewer_title
        self.item_id = item_id
        self.mode = mode
        self.mode_col = mode_col
        self.ann_name = ann_name
        
        assert mode in ['bbox','index','column_index','element_id']

        if self.mode=='bbox' and not type(self.mode_col)==list:
            print('If using "bbox" mode, provide a list of column names containing bounding box coordinates in minx, miny, maxx, maxy format.')
            raise TypeError
        elif not self.mode=='bbox' and type(self.mode_col)==list:
            print('Provide a single column name (type: str) to identify samples in the target slide.')
            raise TypeError

        self.fusion_handler = fusion_handler

        self.feature_viewer = DashProxy(
            __name__
        )

        self.feature_viewer.title = self.viewer_title
        self.feature_viewer.layout = self.get_layout()
        self.get_callbacks()

    def get_callbacks(self):
        """
        Put all callbacks in here
        """
        # First callback is selecting features to view and plotting them when "Plot" button is pressed
        self.feature_viewer.callback(
            [
                Output('feature-graph','figure'),
                Output('image-graph','figure')
            ],
            [
                Input('feature-drop','value'),
                Input('label-drop','value')
            ],
            prevent_initial_call = True
        )(self.update_plot)

        # Second callback is grabbing images associated with selected points
        self.feature_viewer.callback(
            [
                Output('image-graph','figure')
            ],
            [
                Input('feature-graph','selectedData')
            ],
            prevent_initial_call = True
        )(self.graph_image)

    def get_layout(self):
        """
        Assembling a layout based on the provided feature dataframe
        """

        main_layout = html.Div([
            dbc.Container(
                id = 'feature-viewer-container',
                fluid = True,
                children = [
                    html.H1(self.viewer_title),
                    dbc.Row([
                        dbc.Col([
                            dbc.Row([
                                dbc.Col(
                                    dbc.Label('Select feature(s) for plotting:',html_for='feature-drop'),
                                    md = 3
                                ),
                                dbc.Col(
                                    dcc.Dropdown(
                                        options = [
                                            {'label': i, 'value': i, 'disabled': False}
                                            if not i in self.mode_col else
                                            {'label': i, 'value': i, 'disabled': True}
                                            for i in self.feature_df.columns.tolist() 
                                        ],
                                        value = [],
                                        multi = True,
                                        id = 'feature-drop'
                                    ),
                                    md = 9
                                )
                            ]),
                            dbc.Row([
                                dbc.Col(
                                    dbc.Label('(Optional) Select a label for the plot:',html_for='label-drop'),
                                    md = 3
                                ),
                                dbc.Col(
                                    dcc.Dropdown(
                                        options = [
                                            {'label': i,'value': i,'disabled': False}
                                            if not i in self.mode_col else
                                            {'label': i, 'value': i, 'disabled': True}
                                            for i in self.feature_df.columns.tolist()
                                        ],
                                        value = [],
                                        multi = False,
                                        id = 'label-drop'
                                    )
                                )
                            ]),
                            dbc.Row([
                                dcc.Graph(
                                    id = 'feature-graph',
                                    figure = go.Figure()
                                )
                            ])
                        ], md = 6),
                        dbc.Col([
                            dbc.Row(
                                html.H3('Select points to see the image at that point')
                            ),
                            dbc.Row(
                                dcc.Graph(
                                    id = 'image-graph',
                                    figure = go.Figure()
                                )
                            )
                        ])
                    ])
                ]
            )
        ])


        return main_layout

    def update_plot(self, features_selected, labels_selected, plot_button):
        """
        Plotting selected data with label
        """

        print(ctx.triggered)

        if not ctx.triggered:
            raise exceptions.PreventUpdate

        return_plot = go.Figure()



        return return_plot

    def grab_image(self, selected_points):
        """
        Grabbing image region based on selected points
        """

        return_image = go.Figure()



        return return_image


class MultiFrameSlideViewer(LocalSlideViewer):
    """
    Used for viewing slides with multiple "frames" (e.g. CODEX images)
    """
    def __init__(self,
                 tile_server_port: str
                 ):
        self.tile_server_port = tile_server_port

        pass
    














