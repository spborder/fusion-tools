import os
import pandas as pd
import numpy as np
import json

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, ALL, MATCH, ctx, exceptions, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashProxy, html, MultiplexerTransform, PrefixIdTransform, Input, State, Output

from typing_extensions import Union
from fusion_tools.tileserver import TileServer, DSATileServer, LocalTileServer, CustomTileServer
from fusion_tools.handler.dataset_uploader import DSAUploadHandler
from fusion_tools.handler.dsa_handler import DSAHandler
import threading

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
import asyncio
import nest_asyncio

from pathlib import Path
import dash_uploader as du

class Visualization:
    """General holder class used for initialization. Components added after initialization.
    To initialize a new visualization session, you can use the following syntax:

    .. code-block:: python

        # This is for a slide stored on the same computer you're running the fusion-tools instance from.
        local_slide = ['/path/to/slide.tif']
        annotations = ['/path/to/annotations.json']
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
        vis_session = Visualization(
            local_slides = local_slide,
            local_annotations = local_annotations,
            components = components
        )
        vis_session.start()
        
    """
    
    def __init__(self,
                 local_slides: Union[list,str,None] = None,
                 local_annotations: Union[list,dict,None] = None,
                 slide_metadata: Union[list,dict,None] = None,
                 tileservers: Union[list,TileServer,None] = None,
                 components: Union[list,dict] = [],
                 header: list = [],
                 app_options: dict = {},
                 linkage: Union[list,str] = 'row'
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
        :param components: List of components in layout format (rows-->columns-->tabs for nested lists) or dictionary containing names of pages and their component lists, defaults to []
        :type components: Union[list,dict], optional
        :param header: List of components to add to collapsed upper portion of the visualization, defaults to None
        :type header: Union[list,None], optional
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
        self.header = header
        self.app_options = app_options
        self.linkage = linkage

        # New parameter defining how unique components can be linked
        # page = components in the same page can communicate
        # row = components in the same row can communicate
        # col = components in the same column can communicate
        # tab = components in the same tab can communicate
        if type(self.linkage)==str:
            assert self.linkage in ['page','row','col','tab']
        elif type(self.linkage)==list:
            # Only applies for multi-page layouts
            assert type(self.components)==dict
            assert all([i in ['page','row','col','tab'] for i in self.linkage])

        self.default_options = {
            'title': 'FUSION',
            'assets_folder': '/.fusion_assets/',
            'server': 'default',
            'server_options': {},
            'port': 8080,
            'jupyter': False,
            'host': 'localhost',
            'debug': False,
            'layout_style': {},
            'external_stylesheets': [
                dbc.themes.LUX,
                dbc.themes.BOOTSTRAP,
                dbc.icons.BOOTSTRAP,
                dbc.icons.FONT_AWESOME,
                dmc.styles.ALL,
            ],
            'transforms': [
                MultiplexerTransform()
            ],
            'external_scripts': [
                'https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.1.0/chroma.min.js',
            ]
        }

        # Where default options are merged with user-added options
        self.app_options = self.default_options | self.app_options

        self.assets_folder = os.getcwd()+self.app_options['assets_folder']

        self.vis_store_content = self.initialize_stores()

        self.viewer_app = DashProxy(
            __name__,
            url_base_pathname = None if not self.app_options['jupyter'] else self.app_options.get('url_base_pathname'),
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
        self.get_callbacks()

    def get_callbacks(self):

        self.viewer_app.callback(
            [
                Input('anchor-page-url','pathname'),
                Input('anchor-page-url','search'),
                Input({'type':'page-button','index': ALL},'n_clicks')
            ],
            [
                State('anchor-vis-store','data')
            ],
            [
                Output('vis-container','children'),
                Output('anchor-page-url','pathname'),
                Output('anchor-vis-store','data')
            ],
            prevent_initial_call = True
        )(self.update_page)

        self.viewer_app.callback(
            [
                Input('navbar-toggler','n_clicks')
            ],
            [
                Output('navbar-collapse','is_open')
            ],
            [
                State('navbar-collapse','is_open')
            ]
        )(self.open_navbar)

        self.viewer_app.callback(
            [
                Input('header-toggler','n_clicks')
            ],
            [
                Output('header-collapse','is_open')
            ],
            [
                State('header-collapse','is_open')
            ]
        )(self.open_header)

        self.viewer_app.callback(
            [
                Input({'type': 'header-button','index': ALL},'n_clicks')
            ],
            [
                Output('header-modal','is_open'),
                Output('header-modal','size'),
                Output('header-modal','fullscreen'),
                Output('header-modal','className'),
                Output('header-modal','children')
            ],
            [
                State('anchor-vis-store','data')
            ]
        )(self.open_header_component)

    def open_navbar(self, clicked, is_open):

        if clicked:
            return not is_open
        return is_open
    
    def open_header(self, clicked, is_open):

        if clicked:
            return not is_open
        return is_open

    def open_header_component(self, clicked,session_data):

        if clicked:
            session_data = json.loads(session_data)
            header_open = True
            header_children = self.header[ctx.triggered_id['index']].update_layout(session_data = session_data, use_prefix = True)
            if hasattr(self.header[ctx.triggered_id['index']],'modal_size'):
                header_size = self.header[ctx.triggered_id['index']].modal_size
            else:
                header_size = 'lg'
            
            if hasattr(self.header[ctx.triggered_id['index']],'fullscreen'):
                header_fullscreen = self.header[ctx.triggered_id['index']].fullscreen
            else:
                header_fullscreen = False

            if hasattr(self.header[ctx.triggered_id['index']],'modal_className'):
                header_className = self.header[ctx.triggered_id['index']].modal_className
            else:
                header_className = None


            return header_open, header_size, header_fullscreen, header_className, header_children
        else:
            raise exceptions.PreventUpdate

    def update_page(self, pathname, path_search, path_button, session_data):
        """Updating page in multi-page application

        :param pathname: Pathname or suffix of current url which is a key to the page name
        :type pathname: str
        """

        session_data = json.loads(session_data)
        if ctx.triggered_id=='anchor-page-url':
            if pathname in self.layout_dict:
                # If that path is in the layout dict, return that page content

                # If the page needs to be updated based on changes in anchor-vis-data
                page_content = self.update_page_layout(
                    page_components_list = self.components[pathname.replace('/app/','').replace('-',' ')],
                    use_prefix = True,
                    session_data=session_data
                )

                return page_content, no_update, no_update
            
            elif 'session' in pathname:
                temp_handler = DSAHandler(
                    girderApiUrl=os.environ.get('DSA_URL')
                )
                session_content = temp_handler.get_session_data(path_search.replace('?id=',''))
                new_session_data = {
                    'current': session_content['current'],
                    'local': session_data['local'],
                    'data': session_content['data'],
                }

                if 'current_user' in session_data:
                    new_session_data['current_user'] = session_data['current_user']
                
                page_pathname = session_content['page'].replace('/app/','').replace('-',' ')

                page_content = self.update_page_layout(
                    page_components_list = self.components[page_pathname],
                    use_prefix=True,
                    session_data=new_session_data
                )

                return page_content, no_update, json.dumps(new_session_data)

            else:
                # Otherwise, return a list of clickable links for valid pages
                not_found_page = html.Div([
                    html.H1('Uh oh!'),
                    html.H2(f'The page: {pathname}, is not in the current layout!'),
                    html.Hr()
                ] + [
                    html.P(html.A(page,href=page))
                    for page in self.layout_dict
                ])
                return not_found_page, pathname, no_update
        elif ctx.triggered_id['type']=='page-button':
            new_pathname = list(self.layout_dict.keys())[ctx.triggered_id['index']]
            # If the page needs to be updated based on changes in anchor-vis-data
            page_content = self.update_page_layout(
                page_components_list = self.components[new_pathname.replace('/app/','').replace('-',' ')],
                use_prefix = True,
                session_data=session_data
            )

            return page_content, new_pathname, no_update
    
    def initialize_stores(self):

        # This should be all the information necessary to reproduce the tileservers and annotations for each image
        slide_store = {
            "current": [],
            "local": [],
            "data": {}
        }
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
                        'name': s.split(os.sep)[-1],
                        'tiles_url': self.local_tile_server.get_name_tiles_url(s.split(os.sep)[-1]),
                        'regions_url': self.local_tile_server.get_name_regions_url(s.split(os.sep)[-1]),
                        'image_metadata_url': self.local_tile_server.get_name_image_metadata_url(s.split(os.sep)[-1]),
                        'metadata_url': self.local_tile_server.get_name_metadata_url(s.split(os.sep)[-1]),
                        'annotations_url': self.local_tile_server.get_name_annotations_url(s.split(os.sep)[-1]),
                        'annotations_metadata_url': self.local_tile_server.get_name_annotations_metadata_url(s.split(os.sep)[-1]),
                        'annotations_region_url': self.local_tile_server.get_name_annotations_url(s.split(os.sep)[-1])
                    }

                slide_store['current'].append(slide_dict)
                slide_store['local'].append(slide_dict)

        else:
            self.local_tile_server = None


        if not self.tileservers is None:
            if isinstance(self.tileservers,TileServer):
                self.tileservers = [self.tileservers]
            
            for t_idx,t in enumerate(self.tileservers):
                if type(t)==LocalTileServer:
                    slide_store['current'].extend([
                        {
                            'name': j,
                            'tiles_url': t.get_name_tiles_url(j),
                            'regions_url': t.get_name_regions_url(j),
                            'image_metadata_url': t.get_name_image_metadata_url(j),
                            'metadata_url': t.get_name_metadata_url(j),
                            'annotations_url': t.get_name_annotations_url(j),
                            'annotations_metadata_url': t.get_name_annotations_metadata_url(j),
                            'annotations_region_url': t.get_name_annotations_url(j)
                        }
                        for j in t['names']
                    ])
                    slide_store['local'].extend([
                        {
                            'name': j,
                            'tiles_url': t.get_name_tiles_url(j),
                            'regions_url': t.get_name_regions_url(j),
                            'image_metadata_url': t.get_name_image_metadata_url(j),
                            'metadata_url': t.get_name_metadata_url(j),
                            'annotations_url': t.get_name_annotations_url(j),
                            'annotations_metadata_url': t.get_name_annotations_metadata_url(j),
                            'annotations_region_url': t.get_name_annotations_url(j)
                        }
                        for j in t['names']
                    ])

                elif type(t)==DSATileServer:
                    slide_store['current'].append({
                        'name': t.name,
                        'api_url': t.base_url,
                        'tiles_url': t.tiles_url,
                        'regions_url': t.regions_url,
                        'image_metadata_url': t.image_metadata_url,
                        'metadata_url': t.metadata_url,
                        'annotations_url': t.annotations_url,
                        'annotations_metadata_url':t.annotations_metadata_url,
                        'annotations_region_url': t.annotations_region_url,
                        'annotations_geojson_url': t.annotations_geojson_url
                    })
                elif type(t)==CustomTileServer:
                    slide_store['current'].append({
                        'name': t.name,
                        'tiles_url': t.tiles_url,
                        'regions_url': t.regions_url if hasattr(t,'regions_url') else None,
                        'image_metadata_url': t.image_metadata_url if hasattr(t,'image_metadata_url') else None,
                        'metadata_url': t.metadata_url if hasattr(t,'metadata_url') else None,
                        'annotations_url': t.annotations_url if hasattr(t,'annotations_url') else None,
                        'annotations_metadata_url': t.annotations_metadata_url if hasattr(t,'annotations_metadata_url') else None,
                        'annotations_region_url': t.annotations_regions_url if hasattr(t,'annotations_regions_url') else None,
                        'annotations_geojson_url': t.annotations_geojson_url if hasattr(t,'annotations_geojson_url') else None
                    })


        return slide_store

    def gen_layout(self):
        """Generating Visualization layout

        :return: Total layout containing embedded components
        :rtype: dmc.MantineProvider
        """
        self.get_layout_children()

        title_nav_bar = dbc.Navbar(
            dbc.Container([
                dcc.Location(id='anchor-page-url',refresh=False),
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
                                    dbc.DropdownMenu(
                                        children = [
                                            dbc.DropdownMenuItem(
                                                dbc.Button(
                                                    page,
                                                    id = {'type': 'page-button','index':page_idx},
                                                    n_clicks = 0
                                                )
                                            )
                                            for page_idx,page in enumerate(self.layout_dict)
                                        ],
                                        label = 'Pages Menu',
                                        nav = True,
                                        style = {
                                            'border-radius':'5px'
                                        }
                                    )
                                ),
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
                data = json.dumps(self.vis_store_content),
                storage_type = 'session'
            )   
        )

        if len(self.header)>0:
            header_components = self.gen_header_components()
        else:
            header_components = html.Div()

        layout = dmc.MantineProvider(
            children = [
                vis_data,
                html.Div(
                    dbc.Container(
                        id = 'full-vis-container',
                        fluid = True,
                        children = [title_nav_bar] + [header_components]+ [html.Div(id = 'vis-container',children = [])]
                    ),
                    style = self.app_options['app_style'] if 'app_style' in self.app_options else {}
                )
            ]
        )


        return layout

    def update_page_layout(self, page_components_list:list, use_prefix:bool, session_data:Union[list,dict]):
        
        page_children = []
        for row_idx,row in enumerate(page_components_list):
            row_children = []
            if type(row)==list:
                for col_idx, col in enumerate(row):
                    if not type(col)==list:
                        # If this component needs to be updated with new session data, call that method here
                        if col.session_update:
                            col_layout = col.update_layout(
                                session_data = session_data, 
                                use_prefix = use_prefix
                            )
                        else:
                            # If it doesn't need to be updated, get the layout as is
                            col_layout = col.blueprint.layout

                        row_children.append(
                            dbc.Col(
                                dbc.Card([
                                    dbc.CardHeader(
                                        col.title
                                    ),
                                    dbc.CardBody(
                                        col_layout
                                    )
                                ]),
                                width = True
                            )
                        )

                    else:
                        tabs_children = []
                        for tab_idx, tab in enumerate(col):
                            if tab.session_update:
                                tab_layout = tab.update_layout(
                                    session_data = session_data,
                                    use_prefix = use_prefix
                                )
                            else:
                                tab_layout = tab.blueprint.layout

                            tabs_children.append(
                                dbc.Tab(
                                    dbc.Card(
                                        dbc.CardBody(
                                            tab_layout
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
                                            id = {'type': f'{col[0].component_prefix}-vis-layout-tabs','index': np.random.randint(0,1000)},
                                            active_tab = col[0].title.lower().replace(' ','-')
                                        )
                                    )
                                ]),
                                width = True
                            )
                        )

            else:
                
                if row.session_update:
                    row_layout = row.update_layout(
                        session_data = session_data,
                        use_prefix = use_prefix
                    )
                else:
                    row_layout = row.blueprint.layout

                row_children.append(
                    dbc.Col(
                        dbc.Card([
                            dbc.CardHeader(row.title),
                            dbc.CardBody(
                                row_layout
                            )
                        ]),
                        width = True
                    )
                )
            
            page_children.append(
                dbc.Row(
                    row_children
                )
            )

        return page_children

    def get_layout_children(self):
        """Generating layout of embedded components from structure of components list

        :return: List of dbc.Row(dbc.Col(dbc.Tabs())) components
        :rtype: list
        """

        n_rows = 1
        n_cols = 1
        n_tabs = 0

        component_prefix = 0
        self.layout_dict = {}
        page_components = []
        row_components = []
        col_components = []
        tab_components = []

        if type(self.components)==list:
            n_rows = len(self.components)
            if any([type(i)==list for i in self.components]):
                n_cols = max([len(i) for i in self.components if type(i)==list])

                if any([any([type(j)==list for j in i]) for i in self.components if type(i)==list]):
                    n_tabs = max([max([len(i) for i in j if type(i)==list]) for j in self.components if type(j)==list])

            print(f'------Creating Visualization with {n_rows} rows, {n_cols} columns, and {n_tabs} tabs--------')
            print(f'----------------- Components in the same {self.linkage} may communicate through callbacks---------')
        
            self.components = {
                'main': self.components 
            }

        elif type(self.components)==dict:
            for page in self.components:
                n_cols = 1
                n_tabs = 0
                n_rows = len(self.components[page])
                if any([type(i)==list for i in self.components[page]]):
                    n_cols = max([len(i) for i in self.components[page] if type(i)==list])

                    if any([any([type(j)==list for j in i]) for i in self.components[page] if type(i)==list]):
                        n_tabs = max([max([len(i) for i in j if type(i)==list]) for j in self.components[page] if type(j)==list])

                print(f'------Creating Visualization Page {page} with {n_rows} rows, {n_cols} columns, and {n_tabs} tabs--------')
                print(f'----------------- Components in the same {self.linkage} may communicate through callbacks---------')
            

        # Iterating through each named page
        for page_idx,page in enumerate(list(self.components.keys())):
            page_children = []
            
            if type(self.linkage)==str:
                if self.linkage=='page':
                    component_prefix = page_idx
            elif type(self.linkage)==list:
                if self.linkage[page_idx]=='page':
                    component_prefix = page_idx

            row_components = []
            for row_idx,row in enumerate(self.components[page]):
                
                if type(self.linkage)==str:
                    if self.linkage=='row':
                        component_prefix = row_idx
                elif type(self.linkage)==list:
                    if self.linkage[page_idx]=='row':
                        component_prefix = row_idx

                row_children = []
                if type(row)==list:
                    col_components = []
                    for col_idx,col in enumerate(row):

                        if type(self.linkage)==str:
                            if self.linkage=='col':
                                component_prefix = col_idx
                        elif type(self.linkage)==list:
                            if self.linkage[page_idx]=='col':
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

                                if type(self.linkage)==str:
                                    if self.linkage=='tab':
                                        component_prefix = tab_idx
                                elif type(self.linkage)==list:
                                    if self.linkage[page_idx]=='tab':
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
                                                id = {'type': f'vis-layout-tabs','index': np.random.randint(0,1000)},
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

                page_children.append(
                    dbc.Row(
                        row_children
                    )
                )

            page_components.append(row_components)
            self.layout_dict['/app/'+page.replace(" ","-")] = page_children

        upload_check = self.check_for_uploader(page_components)
        if upload_check:
            du.configure_upload(
                self.viewer_app, 
                Path(self.assets_folder+'/tmp/uploads'),
                upload_api = '/upload',
                http_request_handler = DSAUploadHandler
            )

    def check_for_uploader(self, components):
        check = False
        for c in components:
            if type(c)==list:
                check = check | self.check_for_uploader(c)
            elif type(c)==str:
                if c=='DSA Uploader':
                    check = True
        
        return check

    def gen_header_components(self):
        
        for h_idx, h in enumerate(self.header):
            h.load(h_idx)

        header_components = html.Div([
            html.Hr(),
            dbc.Modal(
                id = 'header-modal',
                centered = True,
                is_open = False,
                size = 'xl',
                className = None,
                children = [
                    h.blueprint.embed(self.viewer_app)
                    for h_idx,h in enumerate(self.header)
                ]
            ),
            dbc.Row([
                dbc.Col([
                    dbc.NavbarToggler(id = 'header-toggler'),
                    dbc.Collapse(
                        dbc.Nav([
                            dbc.NavItem(
                                dbc.Button(
                                    h.title,
                                    id = {'type': 'header-button','index': h_idx},
                                    outline = True,
                                    color = 'primary',
                                    style = {'textTransform':'none'}
                                )
                            )
                            for h_idx,h in enumerate(self.header)
                        ],navbar=False),
                        id = 'header-collapse',
                        navbar=False,
                        is_open = True
                    )
                ])
            ]),
            html.Hr()
        ])

        return header_components

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


