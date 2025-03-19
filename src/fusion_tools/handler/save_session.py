"""

Saving session information on a linked DSA instance

"""

import json

from typing_extensions import Union

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import callback, ctx, ALL, MATCH, exceptions, no_update
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
                    html.Div(
                        id = {'type': 'dsa-session-status-div','index': 0},
                        children = []
                    )
                ],direction = 'vertical')
            )
        ])

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
                Input({'type': 'dsa-session-save-button','index': ALL},'n_clicks')
            ],
            [
                State('anchor-vis-store','data'),
                State('page-url','pathname')
            ],
            [
                Output({'type': 'dsa-session-status-div','index': ALL},'children')
            ],
            prevent_initial_call = True
        )(self.save_session)

    def save_session(self, clicked, session_data, page):
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        session_data = json.loads(session_data)
        
        print(json.dumps(session_data))
        print(f'Page: {page}')
        
        raise exceptions.PreventUpdate


