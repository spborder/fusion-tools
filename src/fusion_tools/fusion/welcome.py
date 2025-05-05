"""
Defining layout for a "Welcome" page in FUSION containing embedded YouTube videos with documentation/how-tos
as well as a brief description of the tool and 

"""

import os

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, ALL, MATCH, ctx, exceptions, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import (
    DashBlueprint,
    html, 
    MultiplexerTransform, 
    PrefixIdTransform, 
    Input, State, Output)

from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools import Tool

class WelcomePage(Tool):
    def __init__(self):
        super().__init__()

        self.content_dict = {
            'Background': html.Div([
                dbc.Row(html.H5('Background Information')),
                html.Hr(),
                dbc.Row(
                    'FUSION is an interactive analysis tool which enables integrated analysis of histology images with or without spatial --omics data.',
                    style={'marginBottom':'5px','marginTop':'5px'}
                ),
                dbc.Row([
                    dbc.Col(
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/background-flowchart.png?raw=true',
                            style = {
                                'width': '100%'
                            }
                        ),
                        md = 6
                    ),
                    dbc.Col([
                            'This cloud implementation of FUSION demonstrates the ability of FUSION to leverage cloud resources for storage and running jobs with high computational complexity. ',
                            'Digital Slide Archive (DSA) is here used as a "backend" for organization of files and running Dockerized plugins formatted using Slicer CLI specifications. '
                        ],md = 6)
                    ], align='center'
                )
            ]),
            'The SlideMap Component': html.Div([
                dbc.Row(html.H5('The SlideMap Component')),
                html.Hr(),
                dbc.Row(
                    'The SlideMap component is a base class which contains interactive components for high-resolution images. It leverages Dash-Leaflet for generation of Map-style interactive components integrating with Dash callbacks with other components.'
                ),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/slidemap/slidemap-dropdown.png?raw=true',
                            style = {
                                'width': '100%'
                            }
                        )
                    ], md = 6),
                    dbc.Col([
                        'Since high-resolution images are very large files, they are typically not loaded into memory at the highest resolution all at once, especially for web-applications. ',
                        'Therefore, smaller tiles are accessed from varying resolution levels using an application programming interface (API) request. ',
                        'For cloud-stored images in FUSION, this is facilitated by the large-image Girder plugin. ',
                    ],md = 6)
                ],style={'marginBottom':'5px','marginTop':'5px'}),
                dbc.Row([
                    'Multi-plexed immunofluorescence images which contain multiple channels for each fluorescent marker, can either be viewed individually in grayscale, or combined with manually selected colors using the ChannelMixer component.'
                ],style = {'marginBottom':'5px'})
            ]),
            'Structure-level Properties': html.Div([
                dbc.Row(html.H5('Structure-level Properties')),
                html.Hr(),
                dbc.Row(
                    'One of the key concepts behind FUSION is the incorporation of structure-level properties. These comprise any kind of derived data or identifying information for structures in a slide which can be used in downstream analysis or visualization',
                    style={'marginBottom':'5px','marginTop':'5px'}
                ),
                dbc.Row([
                    dbc.Col([],md=6),
                    dbc.Col([],md=6)
                ],align='center')
            ]),
            'Accessing Data with Tools': html.Div([
                dbc.Row(html.H5('Accessing Data with Tools')),
                html.Hr(),
                dbc.Row(
                    'Data for each slide can be accessed through a variety of interactive components in the "Tools" tabs to the right of the SlideMap.',
                    style={'marginBottom':'5px','marginTop':'5px'}
                ),
                dbc.Row([])
            ]),
            'Getting Started with fusion-tools': html.Div([
                dbc.Row(html.H5('Getting Started with fusion-tools')),
                html.Hr(),
                dbc.Row(
                    'This FUSION visualization is constructed using the fusion-tools Python library, which includes a variety of additional functionality for generating customizable dashboards locally.',
                    style={'marginBottom':'5px','marginTop':'5px'}
                ),
                dbc.Row([])
            ])
        }

    def __str__(self):
        return "Welcome Page"

    def load(self,component_prefix:int):

        self.component_prefix = component_prefix
        
        self.title = 'Welcome Page'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def get_callbacks(self):
        
        self.blueprint.callback(
            [
                Input({'type': 'welcome-nav','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'welcome-page-content','index': ALL},'children')
            ]
        )(self.update_page_content)

    def gen_layout(self, session_data:dict):

        # the style arguments for the sidebar. We use position:fixed and a fixed width
        SIDEBAR_STYLE = {
            "position": "relative",
            "top": 0,
            "left": 0,
            "bottom": 0,
            'height': '100%',
            "width": "25rem",
            "padding": "2rem 1rem",
            "background-color": "#f8f9fa"
        }

        # the styles for the main content position it to the right of the sidebar and
        # add some padding.
        CONTENT_STYLE = {
            "margin-left": "16rem",
            "margin-right": "2rem",
            "padding": "2rem 1rem",
        }

        sidebar = html.Div(
            [
                #html.H4("Categories", className="display-4"),
                #html.Hr(),
                html.P("Select a topic to view more information", className="lead"),
                html.Hr(),
                dbc.Nav(
                    [
                        dbc.NavLink(
                            n,
                            id = {'type': 'welcome-nav','index': n_idx},
                            active='exact'
                        )
                        for n_idx,n in enumerate(self.content_dict)
                    ],
                    vertical=True,
                    pills=True,
                ),
            ],
            style=SIDEBAR_STYLE,
        )

        content = html.Div(id={'type': "welcome-page-content",'index': 0}, style=CONTENT_STYLE)

        layout =  html.Div([
            dbc.Card([
                dbc.Row([
                    dbc.Col(
                        sidebar,
                        md = 2
                    ),
                    dbc.Col(
                        content,
                        md = 10
                    )
                ])
            ])
        ])

        self.blueprint.layout = layout

    def update_page_content(self, clicked):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        nav_clicked = list(self.content_dict.keys())[ctx.triggered_id['index']]

        return [self.content_dict[nav_clicked]]
        














