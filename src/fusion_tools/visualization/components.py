"""
Functions related to visualization for data derived from FUSION.

- Interactive feature charts
    - View images at points
- Local slide viewers

"""
import os
import pandas as pd
import numpy as np

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashProxy, html, MultiplexerTransform


# fusion-tools imports
from fusion_tools.components import SlideMap
 


class Visualization:
    """
    General holder class used for initialization. Components added after initialization.
    
    Parameters
    --------
    components: list
        list of components to add to the visualization session (one of Tool or Map)
        Hierarchy goes from Row-->Column-->Tab for elements in lists. 
        (e.g. [0] would be one row with one component, 
        [0,1] would be one row with two columns, 
        [[0],[[1,2]]] would be two rows, first row with one column, second row with one column with two tabs)
    

    Examples
    --------
    >>> components = [
        [
            SlideMap(
                tile_server = LocalTileServer('/path/to/slide.svs'),
                annotations = geojson_list
            )
        ],
        [
            [
                OverlayOptions(geojson_list),
                PropertyViewer()
            ]
        ]
    ]

    >>> vis_session = Visualization(components)
    >>> vis_session.start()
        
    """
    def __init__(self,
                 components: list,
                 app_options: dict = {}):
        

        self.components = components
        #self.layout = layout
        self.app_options = app_options

        self.assets_folder = os.getcwd()+'/.fusion_assets/'

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
            external_scripts = ['https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.1.0/chroma.min.js'],
            assets_folder = self.assets_folder,
            prevent_initial_callbacks=True,
            transforms = [
                MultiplexerTransform()
            ]
        )
        self.viewer_app.title = self.app_options['title'] if 'title' in self.app_options else self.default_options['title']
        self.viewer_app.layout = self.gen_layout()
    
    def gen_layout(self):

        layout_children = self.get_layout_children()

        layout = dmc.MantineProvider(
                children = [
                    html.Div(
                        dbc.Container(
                            id = 'vis-container',
                            fluid = True,
                            children = [
                                html.H1('fusion-tools Visualization')
                            ]+layout_children
                        ),
                        style = self.app_options['app_style'] if 'app_style' in self.app_options else {}
                    )
                ]
        )

        return layout

    def get_layout_children(self):
        """
        Generate children of layout container from input list of components and layout options
        
        """

        layout_children = []
        for row in self.components:
            row_children = []
            if type(row)==list:
                for col in row:
                    if not type(col)==list:
                        row_children.append(
                            dbc.Col(
                                dbc.Card([
                                    dbc.CardHeader(
                                        col.title
                                    ),
                                    dbc.CardBody(
                                        col.blueprint.embed(self.viewer_app)
                                    )
                                ])
                            )
                        )
                    else:
                        tabs_children = []
                        for tab in col:
                            tabs_children.append(
                                dbc.Tab(
                                    dbc.Card(
                                        dbc.CardBody(
                                            tab.blueprint.embed(self.viewer_app)
                                        )
                                    ),
                                    label = tab.title,
                                    tab_id = tab.title.lower().replace(' ','-')
                                )
                            )

                        row_children.append(
                            dbc.Col(
                                dbc.Card([
                                    dbc.CardHeader('Tools'),
                                    dbc.CardBody(
                                        dbc.Tabs(
                                            tabs_children,
                                            id = {'type': 'vis-layout-tabs','index': np.random.randint(0,1000)}
                                        )
                                    )
                                ])
                            )
                        )
            else:
                row_children.append(
                    dbc.Col(
                        dbc.Card([
                            dbc.CardHeader(row.title),
                            dbc.CardBody(
                                row.blueprint.embed(self.viewer_app)
                            )
                        ])
                    )
                )

            layout_children.append(
                dbc.Row(
                    row_children
                )
            )

        return layout_children

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




