"""Selective data grabber test
"""

import os
import sys
sys.path.append('./src/')

from fusion_tools.visualization import Visualization
from fusion_tools.components import SlideMap, OverlayOptions, PropertyPlotter
from fusion_tools import Tool

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
from dash.dash_table.Format import Format, Scheme
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
import dash_treeview_antd as dta
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
from dash_extensions.javascript import Namespace, arrow_function


class DataExtractor(Tool):
    def __init__(self,
                 ignore_list: list = ["_id","_index"],
                 property_depth: int = 4
                 ):

        super().__init__()

    def __str__(self):
        return 'Data Extractor'

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Data Extractor'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}',escape = lambda input_id: self.prefix_escape(input_id)),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def gen_layout(self,session_data:dict):

        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Data Extractor')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Download select properties from indicated structures in the current slide.'
                    ),
                    html.Hr(),
                    dbc.Row([
                        # Set of components for importing markers
                        # Set of components for adding markers
                        # Set of components for selecting properties
                        # Set of components for selecting additional data (image, geometry, bbox, slide name)
                        # Set of components for downloading data
                    ])
                ])
            )
        ])

        self.blueprint.layout = layout

    def get_callbacks(self):

        # Callback for updating current slide
        # Callback to add markers to structures
        # Callback to import current markers (grab structures that are marked from other processes)
        # Callback to download provided property names from indicated structures (property names as a state val)
        #   (include option for extracting images as well)

        pass
    
    def update_slide(self, new_annotations:list):
        pass
    


def main():
    pass


if __name__=='__main__':
    main()


