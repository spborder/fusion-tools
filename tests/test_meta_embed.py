"""Testing embedding blueprint with embedded blueprints
"""

import os
import sys

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform, DashProxy

class Embeddable1:
    def __init__(self):

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix='0'),
                MultiplexerTransform()
            ]
        )
        self.blueprint.layout = html.Div([
            dbc.Button(
                'Click me!',
                id = {'type': 'embeddable1-button','index': 0},
                n_clicks = 0
            ),
            html.Div(
                f'Button has been clicked: 0 times',
                id = {'type': 'embeddable1-div','index': 0}
            )
        ])

        self.blueprint.callback(
            [
                Input({'type': 'embeddable1-button','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'embeddable1-div','index': ALL},'children')
            ]
        )(self.update_n_clicks)
    
    def update_n_clicks(self, n_clicks):

        if n_clicks[0]:
            return [f'Button has been clicked: {n_clicks[0]} times']
        else:
            raise exceptions.PreventUpdate


class ParentApp:
    def __init__(self, embeddable):

        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix='0'),
                MultiplexerTransform()
            ]
        )
        self.blueprint.layout = html.Div([
            html.Div('This is embedded content'),
            embeddable.blueprint.embed(self.blueprint)
        ])

def main():

    internal_app = Embeddable1()
    parent_app = ParentApp(internal_app)
    parent_2_app = ParentApp(parent_app)

    main_app = DashProxy(__name__)
    main_app.layout = html.Div([
        parent_2_app.blueprint.embed(main_app)
    ])

    main_app.run(
        port = '8050'
    )

if __name__=='__main__':
    main()