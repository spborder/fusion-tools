"""
Functions related to visualization for data derived from FUSION.

- Interactive feature charts
    - View images at points
- Local slide viewers

"""

from fastapi import FastAPI, APIRouter, Response

import large_image
import pandas as pd
import dash_leaflet as dl
from dash import dcc, callback, ctx, ALL, exceptions
import dash_bootstrap_components as dbc
from dash_extensions.enrich import DashProxy, html, Input, Output, State

import plotly.express as px
import plotly.graph_objects as go

from typing_extensions import Union
from PIL import Image
from io import BytesIO
import json
import uvicorn


class TileServer:
    def __init__(self,
                 local_image_path: str
                 ):

        self.local_image_path = local_image_path

        self.tile_source = large_image.open(self.local_image_path,encoding='PNG')
        self.tile_metadata = self.tile_source.getMetadata()

        self.router = APIRouter()
        self.router.add_api_route('/',self.root,methods=["GET"])
        self.router.add_api_route('/tiles/{z}/{y}/{x}',self.get_tile,methods=["GET"])

    def root(self):
        return {'message': "Oh yeah, now we're cooking"}

    def get_tile(self,z:int, y:int, x:int):
        raw_tile = self.tile_source.getTile(
                    x = x,
                    y = y,
                    z = z
                )

        return Response(content = raw_tile, media_type='image/png')
    
    def get_metadata(self):
        large_image_metadata = self.tile_source.getMetadata()

        return Response(content = json.dumps(large_image_metadata),media_type = 'application/json')
    
    def start(self):
        app = FastAPI()
        app.include_router(self.router)

        uvicorn.run(app,host='0.0.0.0',port=8050)


class LocalSlideViewer:
    def __init__(self,
                 local_image_path: str,
                 port: list):
        
        self.local_image_path = local_image_path
        self.port = port
        
        self.viewer_app = DashProxy(__name__)
        self.viewer_app.layout = self.gen_layout(
            tile_size = 240,
            zoom_levels = 7
        )

        # Add callback functions here


        self.viewer_app.run(
            host = '0.0.0.0',
            port = self.port,
            debug = False
        )

    def gen_layout(self, tile_size:int, zoom_levels: int):
        """
        Generate simple slide viewer layout
        """
        layout = html.Div(
            dbc.Container(
                id = 'container',
                fluid = True,
                children = [
                    dbc.Row(
                        html.Div(
                            dl.Map(
                                id = 'slide-map',
                                crs = 'Simple',
                                style = {'height': '100%','width': '100%'},
                                children = [
                                    dl.TileLayer(
                                        id = 'slide-tile-layer',
                                        url = 'http://localhost:8050/tiles/{z}/{x}/{y}',
                                        tileSize=tile_size,
                                        maxNativeZoom=zoom_levels-1,
                                        minZoom = 0
                                    ),
                                    dl.FullScreenControl(
                                        position = 'upper-left'
                                    ),
                                    dl.LayersControl(
                                        id = 'slid-layers-control',
                                        children = []
                                    )
                                ]
                            )
                        )
                    )
                ]
            )
        )

        return layout


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





































    








































