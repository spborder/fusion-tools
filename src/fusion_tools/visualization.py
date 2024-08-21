"""
Functions related to visualization for data derived from FUSION.

- Interactive feature charts
    - View images at points
- Local slide viewers

"""


from fastapi import FastAPI

import large_image

import dash_leaflet as dl
from dash import dcc, callback, ctx, ALL
import dash_bootstrap_components as dbc
from dash_extensions.enrich import DashProxy, html, Input, Output, State


class LocalSlideViewer:
    def __init__(self,
                 local_image_path: str,
                 port: list):
        
        self.local_image_path = local_image_path
        self.port = port

        self.tile_source = large_image.open(self.local_image_path)
        self.tile_metadata = self.tile_source.getMetadata()

        self.tile_server = FastAPI()
        @self.tile_server.get('/')
        async def root():
            return {'message': "Oh yeah, now we're cooking"}

        @self.tile_server.get('/tiles/{z}/{x}/{y}')
        async def get_tile(z:int, y:int, x:int):
            raw_tile = self.tile_source.getTile(
                x = x,
                y = y,
                z = z
            )
            return raw_tile
        
        self.viewer_app = DashProxy(__name__)
        self.viewer_app.layout = self.gen_layout(
            tile_size = self.tile_metadata['tileSize'],
            zoom_levels = self.tile_metadata['levels']
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
                                        url = 'http://localhost:8080/tiles/{z}/{x}/{y}',
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









































