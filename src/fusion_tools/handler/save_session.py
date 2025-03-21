"""

Saving session information on a linked DSA instance

"""

import json

from typing_extensions import Union

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import callback, ctx, ALL, MATCH, exceptions, no_update, dcc
import dash_bootstrap_components as dbc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform

from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools import DSATool


class DSASession(DSATool):
    """Handler for saving a session up on a linked DSA instance

    :param DSATool: Sub-class of Tool specific to DSA components. Updates with session data by default.
    :type DSATool: _type_
    """
    def __init__(self,
                 handler):
        
        self.handler = handler

    def __str__(self):
        return 'DSA Session'

    def load(self, component_prefix:int):
        self.component_prefix = component_prefix

        self.title = 'DSA Session'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def update_layout(self, session_data:dict, use_prefix:bool):
        
        layout = html.Div([
            html.H4(
                children = [
                    f'Click the button to save your current session on DSA'
                ]
            ),
            html.Hr(),
            html.Div(
                dbc.Stack([
                    dbc.Button(
                        'Save Session',
                        className = 'd-grid col-12 mx-auto',
                        color = 'primary',
                        id = {'type': 'dsa-save-session-button','index': 0},
                        n_clicks = 0
                    ),
                    dcc.Loading(
                        html.Div(
                            id = {'type': 'dsa-session-status-div','index': 0},
                            children = []
                        )
                    )
                ],direction = 'vertical')
            )
        ],style = {'padding': '10px 10px 10px 10px'})

        if use_prefix:
            PrefixIdTransform(prefix = self.component_prefix).transform_layout(layout)

        return layout

    def gen_layout(self, session_data:dict):
        """Creating the layout for this component.

        :param session_data: Dictionary containing current session info
        :type session_data: dict
        """

        self.blueprint.layout = self.update_layout(session_data,use_prefix = False)

    def get_callbacks(self):
        
        self.blueprint.callback(
            [
                Input({'type': 'dsa-save-session-button','index': ALL},'n_clicks')
            ],
            [
                State('anchor-vis-store','data'),
                State('anchor-page-url','href'),
                State('anchor-page-url','pathname')
            ],
            [
                Output({'type': 'dsa-session-status-div','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.save_session)

    def save_session(self, clicked, session_data, page_url, pathname):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)

        if not 'current_user' in session_data:
            session_status_div = html.Div(
                dbc.Alert(
                    'Sign in first to save a session',
                    color = 'danger',
                    dismissable=True
                )
            )
            return [session_status_div]

        saved_session_data = {
            'page_url': page_url,
            'page': pathname,
            'current': session_data['current'],
            'data': session_data['data'],
            'user_session': session_data['current_user']['login']
        }

        uploaded_file_details = self.handler.upload_session(saved_session_data,user_token = session_data['current_user']['token'])
        
        # Find a way to extract the window url or something
        session_link = f'{page_url}/session?id={uploaded_file_details["_id"]}'

        session_status_div = html.Div([
            dbc.Alert('Session Saved Successfully!',color = 'success',dismissable=True),
            dbc.Row([
                dbc.Col(
                    dbc.Label(
                        'Session URL:',
                        style = {'fontSize': 15}
                    ),
                    md = 2
                ),
                dbc.Col([
                    dcc.Input(
                        value = session_link,
                        disabled = True,
                        id = {'type': f'{self.component_prefix}-dsa-session-link','index': 0},
                        style = {
                            'width': '100%',
                            'fontSize': 20
                        }
                    )
                ], md = 9),
                dbc.Col(
                    dcc.Clipboard(
                        target_id = {'type': f'{self.component_prefix}-dsa-session-link','index':0},
                        title = 'copy',
                        style = {
                            'fontSize': 20,
                            'display': 'inline-block'
                        }
                    ),
                    md = 1
                )
            ])
        ])

        return [session_status_div]


