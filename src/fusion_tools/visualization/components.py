import os
import pandas as pd
import numpy as np
import json

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashProxy, html, MultiplexerTransform

from typing_extensions import Union
from fusion_tools.tileserver import TileServer, DSATileServer, LocalTileServer, CustomTileServer
from fusion_tools.components import SlideImageOverlay
import threading

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
import asyncio
import nest_asyncio

class Visualization:
    """General holder class used for initialization. Components added after initialization.

    .. code-block:: python

        components = [
            [
                SlideMap()
            ],
            [
                [
                    OverlayOptions(),
                    PropertyViewer()
                ]
            ]
        ]
        vis_session = Visualization(components)
        vis_session.start()

    """
    
    def __init__(self,
                 local_slides: Union[list,str,None] = None,
                 local_annotations: Union[list,dict,None] = None,
                 slide_metadata: Union[list,dict,None] = None,
                 tileservers: Union[list,TileServer,None] = None,
                 components: list = [],
                 app_options: dict = {},
                 linkage: str = 'row'
                 ):
        """Constructor method

        :param local_slides: Filepath for individual slide or list of filepaths stored locally, defaults to None
        :type local_slides: Union[list,str,None], optional
        :param local_annotations: List of processed annotations or filepaths for annotations stored locally (aligns with local_slides), defaults to None
        :type local_annotations: Union[list,dict,None], optional
        :param slide_metadata: List or single dictionary containing slide-level metadata keys and values, defaults to None
        :type slide_metadata: Union[list,dict,None], optional
        :param tileservers: Single tileserver or multiple tileservers, defaults to None
        :type tileservers: Union[list,TileServer,None], optional
        :param components: List of components in layout format (rows-->columns-->tabs for nested lists), defaults to []
        :type components: list, optional
        :param app_options: Additional options for the running visualization session, defaults to {}
        :type app_options: dict, optional
        :param linkage: Which levels of components are linked through callbacks (can be 'row','col',or 'tab'), defaults to 'row'
        :type linkage: str, optional
        """

        self.local_slides = local_slides
        self.slide_metadata = slide_metadata
        self.tileservers = tileservers
        self.local_annotations = local_annotations
        self.components = components
        self.app_options = app_options
        self.linkage = linkage

        # New parameter defining how unique components can be linked
        # row = components in the same row can communicate
        # col = components in the same column can communicate
        # tab = components in the same tab can communicate
        assert self.linkage in ['row','col','tab']

        self.default_options = {
            'title': 'FUSION',
            'assets_folder': '/.fusion_assets/',
            'server': 'default',
            'server_options': {},
            'port': 8080,
            'jupyter': False,
            'host': 'localhost',
            'layout_style': {},
            'external_stylesheets': [
                dbc.themes.LUX,
                dbc.themes.BOOTSTRAP,
                dbc.icons.BOOTSTRAP,
                dbc.icons.FONT_AWESOME,
                dmc.styles.ALL
            ],
            'transforms': [
                MultiplexerTransform()
            ],
            'external_scripts': [
                'https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.1.0/chroma.min.js',
                'https://cdn.jsdelivr.net/npm/spatialmerge',
                'https://cdn.jsdelivr.net/npm/@turf/turf@7/turf.min.js'
            ]
        }

        # Where default options are merged with user-added options
        self.app_options = self.default_options | self.app_options

        self.assets_folder = os.getcwd()+self.app_options['assets_folder']

        self.vis_store_content = self.initialize_stores()

        self.viewer_app = DashProxy(
            __name__,
            requests_pathname_prefix = '/app/' if not self.app_options['jupyter'] else None,
            suppress_callback_exceptions = True,
            external_stylesheets = self.app_options['external_stylesheets'],
            external_scripts = self.app_options['external_scripts'],
            assets_folder = self.assets_folder,
            prevent_initial_callbacks=True,
            transforms = self.app_options['transforms']
        )

        self.viewer_app.title = self.app_options['title']
        self.viewer_app.layout = self.gen_layout()
    
    def initialize_stores(self):

        # This should be all the information necessary to reproduce the tileservers and annotations for each image
        slide_store = []
        s_idx = 0
        t_idx = 0
        if not self.local_slides is None:
            if self.local_annotations is None:
                self.local_annotations = [None]*len(self.local_slides)
            
            if self.slide_metadata is None:
                self.slide_metadata = [None]*len(self.local_slides)

            self.local_tile_server = LocalTileServer(
                tile_server_port=self.app_options['port'] if not self.app_options['jupyter'] else self.app_options['port']+10,
                host = self.app_options['host']
            )

            for s_idx,(s,anns,meta) in enumerate(zip(self.local_slides,self.local_annotations,self.slide_metadata)):
                slide_dict = {}
                if not s is None:
                    # Adding this slide to list of local slides
                    self.local_tile_server.add_new_image(
                        new_image_path = s,
                        new_annotations = anns,
                        new_metadata = meta
                    )

                    slide_dict = {
                        'start_idx': s_idx,
                        'name': s.split(os.sep)[-1],
                        'tiles_url': self.local_tile_server.get_name_tiles_url(s.split(os.sep)[-1]),
                        'regions_url': self.local_tile_server.get_name_regions_url(s.split(os.sep)[-1]),
                        'metadata_url': self.local_tile_server.get_name_metadata_url(s.split(os.sep)[-1]),
                        'annotations_url': self.local_tile_server.get_name_annotations_url(s.split(os.sep)[-1])
                    }

                slide_store.append(slide_dict)

        else:
            self.local_tile_server = None

        if not self.tileservers is None:
            if isinstance(self.tileservers,TileServer):
                self.tileservers = [self.tileservers]
            
            for t_idx,t in enumerate(self.tileservers):
                if type(t)==LocalTileServer:
                    slide_store.extend([
                        {
                            'start_idx': (s_idx+t_idx+1),
                            'name': j,
                            'tiles_url': t.get_name_tiles_url(j),
                            'regions_url': t.get_name_regions_url(j),
                            'metadata_url': t.get_name_metadata_url(j),
                            'annotations_url': t.get_name_annotations_url(j)
                        }
                        for j in t['names']
                    ])
                elif type(t)==DSATileServer:
                    slide_store.append({
                        'start_idx': (s_idx+t_idx+1),
                        'name': t.name,
                        'tiles_url': t.tiles_url,
                        'regions_url': t.regions_url,
                        'metadata_url': t.metadata_url,
                        'annotations_url': t.annotations_url
                    })
                elif type(t)==CustomTileServer:
                    slide_store.append({
                        'start_idx': (s_idx+t_idx+t),
                        'name': t.name,
                        'tiles_url': t.tiles_url,
                        'regions_url': t.regions_url if hasattr(t,'regions_url') else None,
                        'metadata_url': t.metadata_url if hasattr(t,'metadata_url') else None,
                        'annotations_url': t.annotations_url if hasattr(t,'annotations_url') else None
                    })

        return slide_store

    def gen_layout(self):
        """Generating Visualization layout

        :return: Total layout containing embedded components
        :rtype: dmc.MantineProvider
        """
        layout_children = self.get_layout_children()

        header = dbc.Navbar(
            dbc.Container([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.H3(self.app_options['title'],style={'color': 'rgb(255,255,255)'})
                        ])
                    ],md=True,align='center')
                ],align='center'),
                dbc.Row([
                    dbc.Col([
                        dbc.NavbarToggler(id='navbar-toggler'),
                        dbc.Collapse(
                            dbc.Nav([
                                dbc.NavItem(
                                    dbc.Button(
                                        'CMIL Website',
                                        id = 'lab-web-button',
                                        outline=True,
                                        color='primary',
                                        href='https://cmilab.nephrology.medicine.ufl.edu',
                                        target='_blank',
                                        style={'textTransform':'none'}
                                    )
                                ),
                                dbc.NavItem(
                                    dbc.Button(
                                        'Issues',
                                        id = 'issues-button',
                                        outline=True,
                                        color='primary',
                                        href='https://github.com/spborder/fusion-tools/issues',
                                        target='_blank',
                                        style={'textTransform':'none'}
                                    )
                                )
                            ],navbar=True),
                            id = 'navbar-collapse',
                            navbar=True
                        )
                    ],md=2)
                ],align='center')
            ],fluid=True),
            dark=True,
            color='dark',
            sticky='fixed',
            style={'marginBottom':'20px'}
        )

        vis_data = html.Div(
            dcc.Store(
                id = 'anchor-vis-store',
                data = json.dumps(self.vis_store_content)
            )   
        )

        layout = dmc.MantineProvider(
            children = [
                vis_data,
                html.Div(
                    dbc.Container(
                        id = 'vis-container',
                        fluid = True,
                        children = [header] + layout_children
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

        n_rows = 1
        n_cols = 1
        n_tabs = 0

        n_rows = len(self.components)
        if any([type(i)==list for i in self.components]):
            n_cols = max([len(i) for i in self.components if type(i)==list])

            if any([any([type(j)==list for j in i]) for i in self.components if type(i)==list]):
                n_tabs = max([max([len(i) for i in j if type(i)==list]) for j in self.components if type(j)==list])

        print(f'------Creating Visualization with {n_rows} rows, {n_cols} columns, and {n_tabs} tabs--------')
        print(f'----------------- Components in the same {self.linkage} may communicate through callbacks---------')
        
        component_prefix = 0
        layout_children = []
        row_components = []
        col_components = []
        tab_components = []
        for row_idx,row in enumerate(self.components):
            
            if self.linkage=='row':
                component_prefix = row_idx

            row_children = []
            if type(row)==list:
                col_components = []
                for col_idx,col in enumerate(row):
                    if self.linkage=='col':
                        component_prefix = col_idx

                    if not type(col)==list:
                        col.load(component_prefix = component_prefix)
                        col.gen_layout(session_data = self.vis_store_content)
                        col_components.append(str(col))
                        
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
                        tab_components = []
                        tabs_children = []
                        for tab_idx,tab in enumerate(col):
                            if self.linkage=='tab': 
                                component_prefix = tab_idx
                            
                            tab.load(component_prefix = component_prefix)
                            tab.gen_layout(session_data = self.vis_store_content)
                            tab_components.append(str(tab))

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
                        col_components.append(tab_components)

                        row_children.append(
                            dbc.Col(
                                dbc.Card([
                                    dbc.CardHeader('Tools'),
                                    dbc.CardBody(
                                        dbc.Tabs(
                                            tabs_children,
                                            id = {'type': f'{component_prefix}-vis-layout-tabs','index': np.random.randint(0,1000)},
                                            active_tab=col[0].title.lower().replace(' ','-')
                                        )
                                    )
                                ]),
                                width = True
                            )
                        )
            
                row_components.append(col_components)
            else:
                
                row.load(component_prefix = component_prefix)
                row.gen_layout(session_data = self.vis_store_content)
                row_components.append(str(row))

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
        
        if not self.app_options['jupyter']:
            app = FastAPI()

            if not self.local_tile_server is None:
                app.include_router(self.local_tile_server.router)
            
            app.mount(path='/app',app=WSGIMiddleware(self.viewer_app.server))
            uvicorn.run(app,host=self.app_options['host'],port=self.app_options['port'])

        else:

            if not self.local_tile_server is None:      
                nest_asyncio.apply()      
                new_thread = threading.Thread(
                    target = self.local_tile_server.start,
                    daemon=True
                )
                new_thread.start()

                self.viewer_app.run(
                    host = self.app_options['host'],
                    port = self.app_options['port']
                )

            else:
                self.viewer_app.run(
                    host = self.app_options['host'],
                    port = self.app_options['port']
                )


