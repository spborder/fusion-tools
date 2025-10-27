import os
import pandas as pd
import numpy as np
import json
import uuid

from datetime import datetime

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, ALL, MATCH, ctx, exceptions, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashProxy, html, MultiplexerTransform, PrefixIdTransform, Input, State, Output

from typing_extensions import Union
from fusion_tools.tileserver import Slide, TileServer, DSATileServer, LocalTileServer, CustomTileServer
from fusion_tools.database.database import fusionDB
from fusion_tools.database.api import fusionAPI

import threading

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.middleware.cors import CORSMiddleware
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
                 local_slides: Union[Slide,list,str,None] = None,
                 local_annotations: Union[list,dict,None] = None,
                 slide_metadata: Union[list,dict,None] = None,
                 tileservers: Union[list,TileServer,None] = None,
                 database: Union[fusionDB, None] = None,
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
        self.database = database
        self.local_annotations = local_annotations
        self.components = components
        self.header = header
        self.app_options = app_options
        self.linkage = linkage

        self.access_count = 0

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
            'assets_folder': os.path.join(os.getcwd(),'.fusion_assets')+os.sep,
            'requests_pathname_prefix':'/',
            'server': 'default',
            'server_options': {},
            'port': 8080,
            'jupyter': False,
            'host': 'localhost',
            'debug': False,
            'layout_style': {},
            'cors': {
                'allow_origins': ['*'],
                'allow_methods': ['GET','OPTIONS'],
                'allow_credentials': False,
                'allow_headers': ['*'],
                'expose_headers': ['*'],
                'max_age': '36000000'
            },
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
            ]
        }

        # Where default options are merged with user-added options
        self.app_options = self.default_options | self.app_options

        self.default_page = self.app_options.get('default_page')

        self.assets_folder = self.app_options['assets_folder']
        if not os.path.exists(self.assets_folder):
            os.makedirs(self.assets_folder)

        self.initialize_database()

        self.vis_store_content = self.initialize_stores()

        self.viewer_app = DashProxy(
            __name__,
            url_base_pathname = None if not self.app_options['jupyter'] else self.app_options.get('url_base_pathname',None),
            requests_pathname_prefix = self.app_options.get('requests_pathname_prefix','/'),
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

    def initialize_database(self):

        #TODO: Find some way to make it easier for components to connect to this database
        if self.database is None:
            print(f'Creating fusionDB instance at: {self.app_options.get("assets_folder","")}fusion_database.db')
            if os.path.exists(self.app_options.get("assets_folder","")+'fusion_database.db'):
                print(f'Removing previous instance of fusionDB')
                print(self.app_options.get('assets_folder','')+'fusion_database.db')
                os.unlink(self.app_options.get('assets_folder','')+'fusion_database.db')

            self.database = fusionDB(
                db_url = f'sqlite:///{self.app_options.get("assets_folder","")}fusion_database.db',
                echo = False
            )

        elif type(self.database)==str:
            print(f'Creating fusionDB instance at: {self.database}')
            self.database = fusionDB(
                db_url = self.database,
                echo = False
            )

    def get_callbacks(self):

        self.viewer_app.callback(
            [
                Input('anchor-page-url','pathname'),
                Input('anchor-page-url','search'),
                Input({'type':'page-button','index': ALL},'n_clicks')
            ],
            [
                State('anchor-vis-store','data'),
                State('anchor-vis-memory-store','data')
            ],
            [
                Output('vis-container','children'),
                Output('user-current','children'),
                Output('anchor-vis-store','data'),
                Output('anchor-vis-memory-store','data')
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

        self.viewer_app.callback(
            [
                Input('user-current','n_clicks')
            ],
            [
                Output('login-modal','is_open'),
                Output('login-modal','children')
            ],
            [
                State('anchor-vis-store','data'),
                State('anchor-vis-memory-store','data')
            ]
        )(self.open_current_modal)

        # Callback(s) for logging in
        self.viewer_app.callback(
            [
                Input('user-login','n_clicks')
            ],
            [
                Output('login-modal','children')
            ],
            [
                State('anchor-vis-store','data'),
                State('anchor-vis-memory-store','data')
            ]
        )(self.open_login_modal)

        # Callback for creating a new user
        self.viewer_app.callback(
            [
                Input({'type': 'user-login-new', 'index': ALL},'n_clicks')
            ],
            [
                Output('login-modal','children')
            ],
            [
                State('anchor-vis-store','data'),
                State('anchor-vis-memory-store','data')
            ]
        )(self.open_new_user_modal)

        # Callback for submitting login/ submitting create new user
        self.viewer_app.callback(
            [
                Input({'type': 'user-login-new-submit','index': ALL},'n_clicks'),
                Input({'type': 'user-login-submit','index': ALL},'n_clicks'),
                Input({'type': 'user-logout-submit','index': ALL},'n_clicks'),
                Input({'type': 'user-info-save','index': ALL},'n_clicks')
            ],
            [
                Output('anchor-vis-memory-store','data'),
                Output('anchor-vis-store','data'),
                Output('anchor-page-url','pathname'),
                Output('login-modal','is_open')
            ],
            [
                State('anchor-vis-store','data'),
                State('anchor-vis-memory-store','data'),
                State('anchor-page-url','pathname'),
                State({'type': 'user-prev-key','index': ALL},'children'),
                State({'type': 'user-prev-val','index': ALL},'value'),
                State({'type': 'user-new-key','index': ALL},'children'),
                State({'type': 'user-new-val','index': ALL},'value'),
                State({'type': 'user-current-key','index': ALL},'children'),
                State({'type': 'user-current-val','index': ALL},'value')
            ]
        )(self.update_current_user)

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

    def open_current_modal(self, clicked, session_data, in_memory_store):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)
        in_memory_store = json.loads(in_memory_store)
        user_info = in_memory_store.get('user')
        session_info = session_data.get('session')
        user_FirstLast = f'{user_info.get("firstName")} {user_info.get("lastName")}'

        if 'guest' in user_info.get('id'):
            user_type = 'guest'
            user_badge = dmc.Badge(
                "guest", variant='filled'
            )
        elif user_info.get('admin'):
            user_type = 'admin'
            user_badge = dmc.Badge(
                'admin',variant='filled',color='red'
            )
        else:
            user_type = 'user'
            user_badge = dmc.Badge(
                'user', variant='filled',color='green'
            )

        user_avatar = dbc.Row([
                dbc.Col(
                    [
                        dmc.Avatar(id='user-avatar',name=user_FirstLast,color='initial',size='lg',radius='xl'),
                        dbc.Tooltip(user_info.get('login'),target='user-avatar',placement='top')
                    ],
                    md = 'auto'
                ),
                dbc.Col(
                    html.H5(f'{user_FirstLast}'),
                    md = 'auto'
                ),
                dbc.Col(
                    user_badge,
                    md = 'auto'
                )
            ],align='center'
        )

        # Note- Clipboard components don't show up in Chrome
        # Guest users can't change info, User/Admin users can
        if user_type in ['user','admin']:
            user_info_rows = []
            for idx, (key,value) in enumerate(user_info.items()):
                if key in ['id','token']:
                    input_row = html.P(
                        value,
                        id= {'type': 'user-current-val','index': idx}
                    )
                elif key in ['login','firstName','lastName','email']:
                    input_row = dbc.Input(
                        value=value,
                        type='text',
                        id={'type': 'user-current-val','index': idx}
                    )

                elif key=='external':
                    input_row = dmc.Badge(
                        children = [user_info.get('external',{}).get('login')],
                        color = 'teal',
                        variant = 'dot',
                        size = 'xl',
                        id = {'type': 'user-current-val','index': idx}
                    )

                else:
                    # Skipping password, admin, updated
                    continue

                user_info_rows.append(
                    dbc.Row([
                        dbc.Label(
                            key,
                            id = {'type': 'user-current-key','index': idx},
                            html_for={'type': 'user-current-val','index': idx},
                            width=2
                        ),
                        dbc.Col([
                            input_row
                        ],md=9),
                        dbc.Col([
                            dcc.Clipboard(
                                target_id = {'type': 'user-current-val','index': idx},
                                title = 'copy',
                                style = {
                                    'fontSize':20,
                                    'color': 'rgb(200,200,200)'
                                }
                            )
                        ],md=1)
                    ],align = 'center')
                )

            button_rows = dbc.Row([
                dbc.Col(
                    dbc.Button(
                        "Save Changes",
                        id = {'type': 'user-info-save','index': 0},
                        n_clicks = 0,
                        color = 'secondary',
                        className = 'd-grid col-12 mx-auto'
                    ),
                    md = 'auto'
                ),
                dbc.Col(
                    dbc.Button(
                        "Log Out",
                        id = {'type': 'user-logout-submit','index': 0},
                        n_clicks = 0,
                        color = 'danger',
                        className = 'd-grid col-12 mx-auto',
                        disabled = False
                    ),
                    md = 'auto'
                ),
            ])

        else:
            user_info_rows = []
            for idx, (key,value) in enumerate(user_info.items()):
                if not value is None:
                    if not key=='external':
                        user_info_rows.append(
                            dbc.Row([
                                dbc.Label(
                                    key,
                                    id = {'type': 'user-current-key','index': idx},
                                    html_for={'type': 'user-current-val','index': idx},
                                    width=2
                                ),
                                dbc.Col([
                                    html.P(
                                        value,
                                        id={'type': 'user-current-val','index': idx}
                                    )
                                ],md=9),
                                dbc.Col([
                                    dcc.Clipboard(
                                        target_id = {'type': 'user-current-val','index': idx},
                                        title = 'copy',
                                        style = {
                                            'fontSize':20,
                                            'color': 'rgb(200,200,200)'
                                        }
                                    )
                                ],md=1)
                            ],align = 'center')
                       )
                    elif key=='external':
                        user_info_rows.append(
                            dbc.Row([
                                dbc.Label(
                                    key,
                                    width = 2
                                ),
                                dbc.Col([
                                    dmc.Badge(
                                        children = [user_info.get('external',{}).get('login')],
                                        color = 'teal',
                                        variant = 'dot',
                                        size = 'xl',
                                        id = 'user-external'
                                    ),
                                ],md = 10)
                            ])
                        )
            

            button_rows = dbc.Row([
                dbc.Col(
                    dbc.Button(
                        "Login",
                        id = 'user-login',
                        n_clicks = 0,
                        color = 'success',
                        className = 'd-grid col-12 mx-auto'
                    ),
                    md = 12
                )
            ])

        #TODO: For User/Admin users, show a dropdown menu of session ids with name (id)
        session_info_rows = dbc.Row([
            dbc.Label(
                'session',
                html_for = 'user-session-row',
                width=2
            ),
            dbc.Col([
                html.P(
                    session_info.get('id'),
                    id = 'user-session-row'
                )
            ])
        ])

        modal_children = [
            dbc.ModalHeader([
                dbc.ModalTitle("Current User Actions")
            ]),
            dbc.ModalBody([
                user_avatar,   
                html.Hr(),
            ] + user_info_rows + [html.Hr(),session_info_rows]+[
                html.Hr(),
                button_rows
            ]),
            dbc.ModalFooter([
                dbc.Row([
                    dbc.Col([
                        html.P(
                            'fusion-tools v.3.6.35',
                            style={'font-style':'italics'}
                        )
                    ],md='auto'),
                    dbc.Col([
                        html.A(
                            'API',
                            href='/docs',
                            target='_blank'
                        )
                    ],md='auto')
                ]), 
            ])
        ]

        if clicked:
            return True, modal_children
        else:
            raise exceptions.PreventUpdate

    def open_login_modal(self, clicked, session_data, in_memory_store):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        modal_children = [
            dbc.ModalHeader([
                dbc.ModalTitle("Log in")
            ]),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Label(
                        'login',
                        id = {'type': 'user-prev-key','index': 0},
                        html_for = {'type': 'user-prev-val','index': 0},
                        width = 2
                    ),
                    dbc.Col(
                        dbc.Input(
                            type = 'text', 
                            id = {'type': 'user-prev-val','index': 0}, 
                            placeholder = 'login'
                        ),
                        md = 10
                    )
                ],align='center'),
                dbc.Row([
                    dbc.Label(
                        'password',
                        id = {'type': 'user-prev-key','index': 1},
                        html_for = {'type': 'user-prev-val','index': 1},
                        width = 2
                    ),
                    dbc.Col(
                        dbc.Input(
                            type = 'password', 
                            id = {'type': 'user-prev-val','index': 1}, 
                            placeholder = 'password'
                        )
                    )
                ],align='center'),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                            dbc.Button(
                            'Submit',
                            color = 'success',
                            id = {'type':'user-login-submit','index': 0},
                            n_clicks = 0,
                            className = 'd-grid col-12 mx-auto'
                        )
                    ],md=6),
                    dbc.Col([
                        dbc.Button(
                            'Create New User',
                            color = 'primary',
                            id = {'type': 'user-login-new','index': 0},
                            n_clicks = 0,
                            className = 'd-grid col-12 mx-auto'
                        )
                    ],md=6)
                ])
            ]),
            dbc.ModalFooter([
                dbc.Row([
                    dbc.Col([
                        html.P(
                            'fusion-tools v.3.6.35',
                            style={'font-style':'italics'}
                        )
                    ],md='auto'),
                    dbc.Col([
                        html.A(
                            'API',
                            href='/docs',
                            target='_blank'
                        )
                    ],md='auto')
                ]), 
            ])
        ]
        
        if clicked:
            return modal_children
        else:
            raise exceptions.PreventUpdate

    def open_new_user_modal(self, clicked, session_data, in_memory_store):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        modal_children = [
            dbc.ModalHeader([
                dbc.ModalTitle("Create New User")
            ]),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Label(
                        'firstName',
                        id = {'type': 'user-new-key','index': 0},
                        html_for = {'type': 'user-new-val','index': 0},
                        width=2
                    ),
                    dbc.Col([
                        dbc.Input(
                            type = 'text',
                            id = {'type': 'user-new-val','index': 0},
                            placeholder = 'First Name'
                        )
                    ],md=10)
                ],align='center'),
                dbc.Row([
                    dbc.Label(
                        'lastName',
                        id = {'type': 'user-new-key','index': 1},
                        html_for = {'type': 'user-new-val','index': 1},
                        width=2
                    ),
                    dbc.Col([
                        dbc.Input(
                            type = 'text',
                            id = {'type': 'user-new-val','index': 1},
                            placeholder = 'Last Name'
                        )
                    ],md=10)
                ],align='center'),
                dbc.Row([
                    dbc.Label(
                        'email',
                        id = {'type': 'user-new-key','index': 2},
                        html_for = {'type': 'user-new-val','index': 2},
                        width = 2
                    ),
                    dbc.Col([
                        dbc.Input(
                            type = 'email',
                            id = {'type': 'user-new-val','index': 2},
                            placeholder = 'example@email.com (OPTIONAL)'
                        )
                    ])
                ]),
                dbc.Row([
                    dbc.Label(
                        'login',
                        id = {'type': 'user-new-key','index': 3},
                        html_for = {'type': 'user-new-val','index': 3},
                        width = 2
                    ),
                    dbc.Col(
                        dbc.Input(
                            type = 'text', 
                            id = {'type': 'user-new-val','index': 3}, 
                            placeholder = 'login'
                        ),
                        md = 10
                    )
                ],align='center'),
                dbc.Row([
                    dbc.Label(
                        'password',
                        id = {'type': 'user-new-key','index': 4},
                        html_for = {'type': 'user-new-val','index': 4},
                        width = 2
                    ),
                    dbc.Col(
                        dbc.Input(
                            type = 'password', 
                            id = {'type': 'user-new-val','index': 4}, 
                            placeholder = 'password'
                        )
                    )
                ],align='center'),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                        dbc.Button(
                            'Create New User',
                            color = 'primary',
                            id = {'type': 'user-login-new-submit','index': 0},
                            n_clicks = 0,
                            className = 'd-grid col-12 mx-auto'
                        )
                    ],md=12)
                ])
            ]),
            dbc.ModalFooter([
                dbc.Row([
                    dbc.Col([
                        html.P(
                            'fusion-tools v.3.6.35',
                            style={'font-style':'italics'}
                        )
                    ],md='auto'),
                    dbc.Col([
                        html.A(
                            'API',
                            href='/docs',
                            target='_blank'
                        )
                    ],md='auto')
                ]), 
            ])
        ]
        
        if clicked:
            return modal_children
        else:
            raise exceptions.PreventUpdate

    def update_current_user(self, new_clicked, login_clicked, logout_clicked, update_info_clicked, session_data, in_memory_store, pathname, prev_keys, prev_vals, new_keys, new_vals, current_keys, current_vals):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        session_data = json.loads(session_data)
        in_memory_store = json.loads(in_memory_store)

        if 'user-login-new-submit' in ctx.triggered_id['type']:
            # Check new user info is present
            new_user_info = {
                k:v
                for k,v in zip(new_keys,new_vals)
                if not k=='external'
            } | {
                'admin': False,
                'token': uuid.uuid4().hex[:24],
                'external': in_memory_store.get('external')
            }

            new_user = self.database.create_new_user(
                user_kwargs = new_user_info
            )

            if new_user is None:
                # Some failure creating new user
                raise exceptions.PreventUpdate
            
            else:
                new_in_memory = {
                    'user': new_user,
                    'session': in_memory_store.get('session')
                }

        elif 'user-login-submit' in ctx.triggered_id['type']:
            # Check returning user info
            returning_user_info = {
                k:v
                for k,v in zip(prev_keys,prev_vals)
                if not k=='external'
            } | {'external': in_memory_store.get('external')}

            previous_user = self.database.check_user_login_password(
                prev_vals[0],prev_vals[1]
            )

            if previous_user is None:
                # Password failed/login not present
                raise exceptions.PreventUpdate
            else:
                new_in_memory = {
                    'user': previous_user,
                    'session': in_memory_store.get('session')
                }

        elif 'user-logout-submit' in ctx.triggered_id['type']:
            
            new_in_memory = {
                'user': None,
                'session': None
            }

        elif 'user-info-save' in ctx.triggered_id['type']:
            
            current_keys.append('token')
            current_vals.append(uuid.uuid4().hex[:24])

            updated_user = self.database.get_create(
                table_name = 'user',
                inst_id = in_memory_store.get('user').get('id'),
                kwargs = {k:v for k,v in zip(current_keys,current_vals) if not k in ['id','external']} | {'external': in_memory_store.get('user').get('external')}
            )
            if not updated_user is None:
                new_in_memory = {
                    'user': updated_user.to_dict(),
                    'session': in_memory_store.get('session')
                }
            else:
                raise exceptions.PreventUpdate

        new_session_data = session_data
        new_session_data['user'] = new_in_memory.get('user')
        new_session_data['session'] = new_in_memory.get('session')

        return json.dumps(new_in_memory,default=str), json.dumps(new_session_data,default=str), pathname+'#', False

    def update_page(self, pathname, path_search, path_button, session_data, in_memory_store):
        """Updating page in multi-page application

        :param pathname: Pathname or suffix of current url which is a key to the page name
        :type pathname: str
        """
        session_data = json.loads(session_data)
        in_memory_store = json.loads(in_memory_store)

        pathname = pathname.replace('#','')

        self.access_count +=1
        # session_data is preserved in the tab (not cleared on refresh)
        # in_memory_store is preserved in that instance of that tab (cleared on refreshing)
        current_user_ids = self.database.get_ids('user')
        current_vis_session_ids = self.database.get_ids('vis_session')

        if self.access_count == 1:
            print('-----------------First Access-------------')
            # This is the first time the app has been accessed, set to the created guest User and VisSession
            in_memory_store['user'] = self.database.get_user(
                user_id = self.database.get_ids('user')[0]
            )
            del in_memory_store['user']['updated']

            in_memory_store['session'] = {
                'id': self.database.get_ids('vis_session')[0]
            }

            session_data['user'] = in_memory_store['user']
            session_data['session'] = in_memory_store['session']

            session_data['current'] = self.vis_store_content.get('current')
            session_data['local'] = self.vis_store_content.get('local')

        elif self.access_count > 1:
            
            current_user_ids = self.database.get_ids('user')
            current_vis_session_ids = self.database.get_ids('vis_session')

            if in_memory_store.get('user') is None:
                if session_data.get('user') is None:
                    print(f'---------New Window/New User/New Session-------------')
                    # This is a new user, hasn't entered the application from this tab
                    new_user = self.new_user(guest = True)
                    new_session = self.new_session(guest = True)

                    session_data['current'] = [i for i in self.vis_store_content.get('current') if i.get('public')]
                    session_data['local'] = self.vis_store_content.get('local')

                    in_memory_store['user'] = new_user
                    in_memory_store['session'] = new_session
                    session_data['user'] = new_user
                    session_data['session'] = new_session

                    # Adding vis_session
                    self.database.add_vis_session(
                        session_data
                    )

                elif session_data.get('user') is not None:
                    if session_data.get('user').get('id') in current_user_ids:
                        if session_data.get('session').get('id') in current_vis_session_ids:
                            print(f'---------New Window/Previous User/Previous Session-------------')
                            in_memory_store['user'] = session_data.get('user')
                            in_memory_store['session'] = session_data.get('session')

                            # Checking which items this user has specific access to
                            prev_user_access = self.database.check_user_access(user_id = in_memory_store.get('user').get('id'), admin = in_memory_store.get('user').get('admin',False))
                            # Adding public items and items this user has access to
                            session_data['current'] = [i for i in self.vis_store_content.get('current') if i.get('public') or i.get('id') in prev_user_access]
                            session_data['local'] = self.vis_store_content.get('local')

                        else:
                            print(f'---------New Window/Previous User/New Session-------------')
                            # Creating a new session id
                            new_session = self.new_session(guest = not 'guest' in session_data.get('user').get('id'))
                            # Checking which items this user has specific access to
                            prev_user_access = self.database.check_user_access(user_id = session_data.get('user').get('id'), admin = session_data.get('user').get('admin',False))
                            # Adding public items and items this user has access to
                            session_data['current'] = [i for i in self.vis_store_content.get('current') if i.get('public') or i.get('id') in prev_user_access]
                            session_data['local'] = self.vis_store_content.get('local')

                            in_memory_store['session'] = new_session
                            session_data['session'] = new_session
                            in_memory_store['user'] = session_data.get('user')
                            in_memory_store['session'] = session_data.get('session')

                            # Adding vis_session
                            self.database.add_vis_session(
                                session_data
                            )
                    else:
                        print(f'---------New Window/New User/New Session-------------')
                        # This is a new user, hasn't entered the application from this tab
                        new_user = self.new_user(guest = True)
                        new_session = self.new_session(guest = True)

                        session_data['current'] = [i for i in self.vis_store_content.get('current') if i.get('public')]
                        session_data['local'] = self.vis_store_content.get('local')

                        in_memory_store['user'] = new_user
                        in_memory_store['session'] = new_session
                        session_data['user'] = new_user
                        session_data['session'] = new_session

                        # Adding vis_session
                        self.database.add_vis_session(
                            session_data
                        )

            elif in_memory_store.get('user').get('id') not in current_user_ids:
                print('--------Previous Window/New User/New Session---------------')
                # Not None user, not in current_user_ids
                new_user = self.new_user(guest = False, id = in_memory_store.get('user').get('id'))
                new_session = self.new_session(guest = not 'guest' in in_memory_store.get('user').get('id'))

                # Since this user is not registered in User, they only have access to 'public' Items
                session_data['current'] = [i for i in self.vis_store_content.get('current') if i.get('public')]
                session_data['local'] = self.vis_store_content.get('local')

                in_memory_store['user'] = new_user
                in_memory_store['session'] = new_session
                session_data['user'] = new_user
                session_data['session'] = new_session
            
            elif in_memory_store.get('user').get('id') in current_user_ids:
                if in_memory_store.get('session').get('id') in current_vis_session_ids:
                    print('------------Previous Window/Previous User/Previous Session---------------')
                    # Checking which items this user has specific access to
                    prev_user_access = self.database.check_user_access(user_id = in_memory_store.get('user').get('id'), admin = in_memory_store.get('user').get('admin',False))
                    # Adding public items and items this user has access to
                    session_data['current'] = [i for i in session_data.get('current') if i.get('public') or i.get('id') in prev_user_access]
                    session_data['local'] = session_data.get('local')

                else:
                    print('------------Previous Window/Previous User/New Session---------------')
                    # Not None user, in current_user_ids
                    # Creating a new session id
                    new_session = self.new_session(guest = not 'guest' in in_memory_store.get('user'))
                    # Checking which items this user has specific access to
                    prev_user_access = self.database.check_user_access(user_id = in_memory_store.get('user').get('id'), admin = in_memory_store.get('user').get('admin',False))
                    # Adding public items and items this user has access to
                    session_data['current'] = [i for i in self.vis_store_content.get('current') if i.get('public') or i.get('id') in prev_user_access]
                    session_data['local'] = self.vis_store_content.get('local')

                    in_memory_store['session'] = new_session
                    session_data['user'] = in_memory_store.get('user')
                    session_data['session'] = new_session

                    # Adding vis_session
                    self.database.add_vis_session(
                        session_data
                    )

        user_name = f'{in_memory_store.get("user").get("firstName")} {in_memory_store.get("user").get("lastName","")}'
        signed_in_user = f'Signed in as: {user_name}'

        page_content = no_update
        page_pathname = no_update
        page_search = no_update

        if ctx.triggered_id=='anchor-page-url':
            if pathname in self.layout_dict:
                # If that path is in the layout dict, return that page content

                # If the page needs to be updated based on changes in anchor-vis-data
                page_content = self.update_page_layout(
                    page_components_list = self.components[pathname.replace(self.app_options.get('requests_pathname_prefix','/'),'').replace('-',' ')],
                    use_prefix = True,
                    session_data=session_data
                )
            
            elif 'session' in pathname:
                from fusion_tools.handler.dsa_handler import DSAHandler
                temp_handler = DSAHandler(
                    girderApiUrl=os.environ.get('DSA_URL')
                )
                session_content = temp_handler.get_session_data(path_search.replace('?id=',''))
                new_session_data = {
                    'current': session_content['current'],
                    'local': session_data['local'],
                    'data': session_content['data'],
                }

                if 'user' in session_data:
                    new_session_data['user'] = session_data['user']
                
                page_pathname = session_content['page'].replace(self.app_options.get('requests_pathname_prefix','/'),'').replace('-',' ')

                page_content = self.update_page_layout(
                    page_components_list = self.components[page_pathname],
                    use_prefix=True,
                    session_data=new_session_data
                )

                in_memory_store['session'] = {
                    'id': path_search.replace('?id=','')
                }
            
            elif 'item' in pathname:
                #TODO: Loading an individual item from id

                pass

            else:
                if self.default_page is None:
                    # Otherwise, return a list of clickable links for valid pages
                    page_content = html.Div([
                        html.H1('Uh oh!'),
                        html.H2(f'The page: {pathname}, is not in the current layout!'),
                        html.Hr()
                    ] + [
                        html.P(html.A(page,href=page))
                        for page in self.layout_dict
                    ])

                else:
                    page_content = self.update_page_layout(
                        page_components_list = self.components[self.default_page.replace(self.app_options.get('requests_pathname_prefix','/'),'').replace('-',' ')],
                        use_prefix = True,
                        session_data=session_data
                    )

        elif ctx.triggered_id['type']=='page-button':
            new_pathname = list(self.layout_dict.keys())[ctx.triggered_id['index']]
            # If the page needs to be updated based on changes in anchor-vis-data
            page_content = self.update_page_layout(
                page_components_list = self.components[new_pathname.replace(self.app_options.get('requests_pathname_prefix','/'),'').replace('-',' ')],
                use_prefix = True,
                session_data=session_data
            )
    
        return page_content, signed_in_user, json.dumps(session_data), json.dumps(in_memory_store)

    def new_user(self, guest: bool = True, id: Union[str,None] = None):

        user_dict = {
            'id': f'guestuser{uuid.uuid4().hex[:15]}' if guest and id is None else id,
            'login': f'{uuid.uuid4().hex[:24]}',
            'firstName': 'Guest',
            'lastName': 'User',
            'token': uuid.uuid4().hex[:24]
        }

        return user_dict

    def new_session(self, guest: bool = True):

        session_dict = {
            'id': f'guestsession{uuid.uuid4().hex[:12]}' if guest else uuid.uuid4().hex[:24],
            'data': {}
        }

        return session_dict

    def initialize_stores(self):

        # This should be all the information necessary to reproduce the tileservers and annotations for each image
        slide_store = {
            "current": [],
            "local": [],
            "data": {},
            'session': self.new_session(guest = True),
            'user': self.new_user(guest = True),
        }

        self.database.add_vis_session(slide_store)

        s_idx = 0
        t_idx = 0

        if not self.local_slides is None:
            if self.local_annotations is None:
                self.local_annotations = [None]*len(self.local_slides)
            
            if self.slide_metadata is None:
                self.slide_metadata = [None]*len(self.local_slides)

            # Initializing a LocalTileServer instance.
            self.local_tile_server = LocalTileServer(
                tile_server_port = self.app_options['port'],
                host = self.app_options['host'],
                database = self.database,
                jupyter_server_url = self.app_options.get('jupyter_server_url','').replace(str(self.app_options['port']),str(self.app_options['port']+10))
            )

            for s_idx,(s,anns,meta) in enumerate(zip(self.local_slides,self.local_annotations,self.slide_metadata)):
                slide_dict = {}
                if not s is None:
                    # Adding this slide to list of local slides
                    local_slide_id = uuid.uuid4().hex[:24]
                    if not isinstance(s,Slide):
                        self.local_tile_server.add_new_image(
                            new_image_id = local_slide_id,
                            new_image_path = s,
                            new_annotations = anns,
                            new_metadata = meta,
                            session_id = slide_store.get('session').get('id'),
                            user_id = slide_store.get('user').get('id')
                        )

                        slide_dict = {
                            'name': s.split(os.sep)[-1],
                            'id': local_slide_id,
                            'cached': True,
                            'public': False,
                            'type': 'local_item',
                        } | self.local_tile_server.get_slide_urls(local_slide_id)
                    else:
                        self.local_tile_server.add_new_slide(
                            slide_id = local_slide_id,
                            slide_obj = s,
                            session_id = slide_store.get('session').get('id'),
                            user_id = slide_store.get('user').get('id') if not s.public else None
                        )

                        slide_dict = {
                            'name': s.image_filepath.split(os.sep)[-1],
                            'id': local_slide_id,
                            'cached': True,
                            'public': s.public,
                            'type': 'local_item',
                        } | self.local_tile_server.get_slide_urls(local_slide_id)

                slide_store['current'].append(slide_dict)
                slide_store['local'].append(slide_dict)

        else:
            self.local_tile_server = None

        if not self.tileservers is None:
            if isinstance(self.tileservers,TileServer):
                self.tileservers = [self.tileservers]
            
            for t_idx,t in enumerate(self.tileservers):
                if type(t)==LocalTileServer:
                    local_tile_server_url = f'{t.protocol}://{t.host}:{t.port}/tileserver'

                    slide_store['current'].extend([
                        {
                            'name': j.name,
                            'id': j.id,
                            'url': local_tile_server_url,
                            'cached': True,
                            'type': 'local_item',
                        } | t.get_slide_urls(j.id, standalone = True)
                        for j_idx,j in enumerate(t.get_item_names_ids())
                    ])
                    slide_store['local'].extend([
                        {
                            'name': j.name,
                            'id': j.id,
                            'url': local_tile_server_url,
                            'cached': True,
                            'type': 'local_item',
                        } | j.get_slide_urls(j.id,standalone=True)
                        for j_idx,j in enumerate(t.get_item_names_ids())
                    ])

                elif type(t)==DSATileServer:

                    #TODO: Update "public" as needed, it's possible this will have some other access control.
                    slide_store['current'].append({
                        'name': t.name,
                        'id': t.item_id,
                        'remote_id': t.item_id,
                        'url': t.base_url,
                        'public': True,
                        'type': 'remote_item',
                    })
                elif type(t)==CustomTileServer:
                    slide_store['current'].append({
                        'name': t.name,
                        'id': t.id,
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
                                                    n_clicks = 0,
                                                    className = 'd-grid col-12 mx-auto',
                                                    style = {'textTransform': 'none'}
                                                )
                                            )
                                            for page_idx,page in enumerate(self.layout_dict)
                                        ] + [
                                            dbc.DropdownMenuItem(divider=True),
                                            dbc.DropdownMenuItem([
                                                dbc.Button(
                                                    'Signed in as: Guest User',
                                                    id = 'user-current',
                                                    color = 'secondary',
                                                    outline = True,
                                                    n_clicks = 0,
                                                    style = {
                                                        'font-style': 'italic',
                                                        'textTransform': 'none'
                                                    }
                                                ),
                                                dbc.Modal(
                                                    id = 'login-modal',
                                                    centered = True,
                                                    is_open = False,
                                                    size = 'xl',
                                                    className = None,
                                                    children = []
                                                )
                                            ])
                                        ],
                                        label = 'Menu',
                                        nav = True,
                                        style = {
                                            'border-radius':'5px'
                                        }
                                    )
                                ),
                                dbc.NavItem(
                                    dbc.Button(
                                        'Examples',
                                        id = 'examples-button',
                                        outline=True,
                                        color='primary',
                                        href='https://spborder.github.io/fusion-welcome-page/',
                                        target='_blank',
                                        style={'textTransform':'none'}
                                    )
                                ),
                                dbc.NavItem(
                                    dbc.Button(
                                        'Docs',
                                        id = 'docs-button',
                                        outline=True,
                                        color='primary',
                                        href='https://fusion-tools.readthedocs.io/en/latest/',
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

        vis_data = html.Div([
            dcc.Store(
                id = 'anchor-vis-store',
                data = json.dumps({}),
                storage_type = 'session',
                modified_timestamp = -1
            ),
            dcc.Store(
                id = 'anchor-vis-memory-store',
                data = json.dumps({}),
                storage_type='memory',
                modified_timestamp = -1
            )
        ])

        self.app_start_time = datetime.now()
        print(f'app start time: {self.app_start_time}')

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

            self.default_page = 'main'

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
                            col.add_assets_folder(self.assets_folder)
                            col.load(component_prefix = component_prefix)
                            col.gen_layout(session_data = self.vis_store_content)
                            col.add_database(database = self.database)
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
                                
                                tab.add_assets_folder(self.assets_folder)
                                tab.load(component_prefix = component_prefix)
                                tab.gen_layout(session_data = self.vis_store_content)
                                tab.add_database(database = self.database)
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
                    
                    row.add_assets_folder(self.assets_folder)
                    row.load(component_prefix = component_prefix)
                    row.gen_layout(session_data = self.vis_store_content)
                    row.add_database(database = self.database)
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
            self.layout_dict[self.app_options.get('requests_pathname_prefix','/')+page.replace(" ","-")] = page_children

        upload_check = self.check_for_uploader(page_components)
        if upload_check:
            from fusion_tools.handler.dataset_uploader import DSAUploadHandler
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
            h.gen_layout({})
            h.add_database(database = self.database)

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

    def create_app(self):

        app = FastAPI(
            title = 'FUSION',
            description = 'Modular visualization and analysis dashboard creation for high-resolution microscopy images.',
            version='3.6.42',
            docs_url='/docs',
            redoc_url = '/redoc',
            license_info = {
                'name': 'Apache 2.0'
            }
        )

        app.include_router(
            fusionAPI(
                database = self.database
            ).router
        )

        allowed_origins = [
            'http://localhost',
            f'http://localhost:{self.app_options.get("port")}',
            f'http://0.0.0.0:{self.app_options.get("port")}',
            'http://0.0.0.0',
            f'http://127.0.0.1:{self.app_options.get("port")}',
            'http://127.0.0.1',
            'http://'+self.app_options.get('host'),
            'http://'+self.app_options.get('host')+':'+str(self.app_options.get('port'))
        ]

        if not self.app_options.get('jupyter_server_url') is None:
            allowed_origins.append(
                self.app_options.get('jupyter_server_url')
            )

        allowed_origins += [
            i.replace('http://','')
            for i in allowed_origins
        ]
        allowed_origins += [
            i+'/'
            for i in allowed_origins
        ]

        allowed_origins = list(set(allowed_origins))
        cors_options = self.app_options.get('cors')

        if self.local_tile_server is not None:
            self.local_tile_server.app.include_router(self.local_tile_server.router)
            app.mount(
                path = self.app_options.get('requests_pathname_prefix','/')+'tileserver/',
                app = CORSMiddleware(
                    self.local_tile_server.app,
                    allow_origins = allowed_origins if not cors_options.get('allow_origins')==['*'] else ['*'],
                    allow_methods = cors_options.get('allow_methods',['GET','OPTIONS']),
                    allow_headers = cors_options.get('allow_headers',['*']),
                    allow_credentials = cors_options.get('allow_credentials',False),
                    expose_headers = cors_options.get('expose_headers',['*']),
                    max_age = cors_options.get('max_age','36000000')
                )
            )
        
        app.mount(
            path = self.app_options.get('requests_pathname_prefix','/'), 
            app = CORSMiddleware(
                WSGIMiddleware(self.viewer_app.server),
                    allow_origins = allowed_origins if not cors_options.get('allow_origins')==['*'] else ['*'],
                    allow_methods = cors_options.get('allow_methods',['GET','OPTIONS']),
                    allow_headers = cors_options.get('allow_headers',['*']),
                    allow_credentials = cors_options.get('allow_credentials',False),
                    expose_headers = cors_options.get('expose_headers',['*']),
                    max_age = cors_options.get('max_age','36000000')
            )
        )

        return CORSMiddleware(
            app,
            allow_origins = allowed_origins if not cors_options.get('allow_origins')==['*'] else ['*'],
            allow_methods = cors_options.get('allow_methods',['GET','OPTIONS']),
            allow_headers = cors_options.get('allow_headers',['*']),
            allow_credentials = cors_options.get('allow_credentials',False),
            expose_headers = cors_options.get('expose_headers',['*']),
            max_age = cors_options.get('max_age','36000000')
        )

    def start(self):
        """Starting visualization session based on provided app_options
        """

        if not self.app_options['jupyter']:

            uvicorn.run(
                self.create_app(),
                host=self.app_options['host'],
                port=self.app_options['port']
            )

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


