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
    """General holder class used for initialization. Components added after initialization.

    .. code-block:: python

        components = [
            [
                SlideMap(
                    tile_server = LocalTileServer("/path/to/slide.svs"),
                    annotations = geojson_list
                )
            ],
            [
                [
                    OverlayOptions(geojson_list),
                    PropertyViewer(geojson_list)
                ]
            ]
        ]
        vis_session = Visualization(components)
        vis_session.start()

    """
    
    def __init__(self,
                 components: list,
                 app_options: dict = {}):
        """Constructor method

        :param components: List of rows, columns, and tabs to include current visualization session
        :type components: list
        :param app_options: Additional application options, defaults to {}
        :type app_options: dict, optional
        """

        self.components = components
        self.app_options = app_options

        self.assets_folder = os.getcwd()+'/.fusion_assets/'

        self.default_options = {
            'title': 'FUSION',
            'server': 'default',
            'server_options': {},
            'port': '8080',
            'external_scripts': [
                'https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.1.0/chroma.min.js'
            ]
        }

        self.app_options = self.default_options | self.app_options

        self.viewer_app = DashProxy(
            __name__,
            external_stylesheets = [
                dbc.themes.LUX,
                dbc.themes.BOOTSTRAP,
                dbc.icons.BOOTSTRAP,
                dbc.icons.FONT_AWESOME,
                dmc.styles.ALL
            ],
            external_scripts = self.app_options['external_scripts'],
            assets_folder = self.assets_folder,
            prevent_initial_callbacks=True,
            transforms = [
                MultiplexerTransform()
            ]
        )

        self.viewer_app.title = self.app_options['title']
        self.viewer_app.layout = self.gen_layout()
    
    def gen_layout(self):
        """Generating Visualization layout

        :return: Total layout containing embedded components
        :rtype: dmc.MantineProvider
        """
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
        """Generating layout of embedded components from structure of components list

        :return: List of dbc.Row(dbc.Col(dbc.Tabs())) components
        :rtype: list
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
                                ]),
                                width = True
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
                                ]),
                                width = True
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
                        ]),
                        width = True
                    )
                )

            layout_children.append(
                dbc.Row(
                    row_children
                )
            )

        return layout_children

    def start(self):
        """Starting visualization session based on provided app_options
        """
        
        if not 'jupyter_mode' in self.app_options:
            if 'server' in self.app_options:
                if self.app_options['server']=='default':
                    self.viewer_app.run_server(
                        host = '0.0.0.0',
                        port = self.app_options['port'],
                        debug = False
                    )
            else:
                self.viewer_app.run_server(
                    host = '0.0.0.0',
                    port = self.app_options['port'],
                    debug = False
                )
        else:
            self.viewer_app.run(
                jupyter_mode=self.app_options['jupyter_mode']
            )



