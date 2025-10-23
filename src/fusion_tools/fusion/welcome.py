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
from fusion_tools.components.base import Tool

class WelcomePage(Tool):

    title = 'Welcome Page'
    desription = ''

    def __init__(self):
        super().__init__()

        #TODO: Just a note, these image addresses get rate-limited pretty quickly from GitHub, ideally these 
        # images would be locally accessible but I think that would make the package much heavier.
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
                            alt = 'FUSION background diagram',
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
                ),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/page-menu.png?raw=true',
                            alt = 'FUSION PageMenu',
                            style = {
                                'width': '100%'
                            }
                        )
                    ],md=6),
                    dbc.Col([
                        'Navigate to different pages in FUSION using the PAGES MENU in the navigation bar at the top of your screen. ',
                        'There you will see a few different buttons with page addresses on them like this: "/APP/VISUALIZATION", "/APP/DATASET BUILDER", etc. ',
                        'The Visualization and Dataset Builder pages are openly accessible to everyone. ',
                        'The Dataset Uploader page requires creating an account in order to associate any uploaded data to each user\'s quota. ',
                        'You can make a new account (100% free!), using the "DSA LOGIN" button underneath the navigation bar. ',
                        'Follow the instructions to create a new account or login using your username and password and navigate to the Dataset Uploader page to start uploading your own data. '
                    ],md=6)
                ])
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
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/slidemap/slidemap-tile-coordinates.png?raw=true',
                            alt = 'High-resolution tiled images',
                            style = {
                                'width': '100%'
                            }
                        ),
                    ], md = 6),
                    dbc.Col([
                        'Since high-resolution images are very large files, they are typically not loaded into memory at the highest resolution all at once, especially for web-applications. ',
                        'Therefore, smaller tiles are accessed from varying resolution levels using an application programming interface (API) request. ',
                        'For cloud-stored images in FUSION, this is facilitated by the large-image Girder plugin. ',
                    ],md = 6)
                ],style={'marginBottom':'5px','marginTop':'5px'}),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/slidemap/slidemap-dropdown.png?raw=true',
                            alt = 'SlideMap dropdown',
                            style = {
                                'width': '100%'
                            }
                        )
                    ], md = 6),
                    dbc.Col([
                        'To load a slide in FUSION, first navigate to the visualization page containing the SlideMap component. ',
                        'Next, select the slide you would like to view from the dropdown menu at the top of the SlideMap component. ',
                        'This will trigger FUSION collecting the necessary rendering information for that slide, including the tiles URL, annotations, and any other slide metadata. '
                    ])
                ]),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/slidemap/slidemap-layers.png?raw=true',
                            alt = 'SlideMap layers',
                            style = {
                                'width': '100%'
                            }
                        )
                    ],md=6),
                    dbc.Col([
                        'Use the layers selector in the top right of the map to turn different overlaid annotations off and on. '
                    ],md=6)
                ],align='center',style = {'marginBottom':'5px'}),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/slidemap/slidemap-multiframe.png?raw=true',
                            alt = 'MxIF image channels',
                            style = {
                                'width': '100%'
                            }
                        )
                    ],md=6),
                    dbc.Col([
                        'Multi-plexed immunofluorescence images which contain multiple channels for each fluorescent marker, can either be viewed individually in grayscale, or combined with manually selected colors using the ChannelMixer component. '
                    ],md=6)
                ],align='center',style = {'marginBottom':'5px'})
            ]),
            'Structure-level Properties': html.Div([
                dbc.Row(html.H5('Structure-level Properties')),
                html.Hr(),
                dbc.Row(
                    'One of the key concepts behind FUSION is the incorporation of structure-level properties. These comprise any kind of derived data or identifying information for structures in a slide which can be used in downstream analysis or visualization',
                    style={'marginBottom':'5px','marginTop':'5px'}
                ),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/geojson-example.png?raw=true',
                            alt = 'GeoJSON example',
                            style = {
                                'width':'100%'
                            }
                        )
                    ],md=6),
                    dbc.Col([
                        'Following GeoJSON conventions, each annotation is defined as a FeatureCollection consisting of one or more Features containing a type, geometry, and properties field. ',
                        'FUSION accesses structure-level features from the properties field and incorporates them into visualizations and analyses dynamically. '
                    ],md=6)
                ],align='center')
            ]),
            'Accessing Data with Tools': html.Div([
                dbc.Row(html.H5('Accessing Data with Tools')),
                html.Hr(),
                dbc.Row(
                    'Data for each slide can be accessed through a variety of interactive components in the "Tools" tabs to the right of the SlideMap.',
                    style={'marginBottom':'5px','marginTop':'5px'}
                ),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/properties/property-accessors.png?raw=true',
                            alt = 'Property accessors in FUSION',
                            style = {
                                'width':'100%'
                            }
                        )
                    ],md=6),
                    dbc.Col([
                        'The GlobalPropertyPlotter, PropertyPlotter, and PropertyViewer components access structural properties at 3 different levels. ',
                        'The PropertyViewer component loads properties from only the structures within the current viewport and can be used for assessing whether a given property is localized to particular regions. ',
                        'The PropertyPlotter accesses all of the properties for all of the structures in the current slide regardless of where they are. ',
                        'The GlobalPropertyPlotter accesses all of the properties from all of the structures from all of the slides in your current Visualization Session. To modify the slides in your Visualization Session, use the Dataset Builder page. '
                    ],md=6)
                ])
            ]),
            'Getting Started with fusion-tools': html.Div([
                dbc.Row(html.H5('Getting Started with fusion-tools')),
                html.Hr(),
                dbc.Row(
                    'This FUSION visualization is constructed using the fusion-tools Python library, which includes a variety of additional functionality for generating customizable dashboards locally.',
                    style={'marginBottom':'5px','marginTop':'5px'}
                ),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/fusion-tools/fusion-layout.png?raw=true',
                            alt = 'FUSION layout in fusion-tools',
                            style = {
                                'width':'100%'
                            }
                        )
                    ],md=6),
                    dbc.Col([
                        'The Visualization object in fusion-tools lets users define which data they would like to initially load as well as which components should be added to the layout. ',
                        'Multi-page layouts can be created by passing a dictionary with the name of each page to the "components" argument. ',
                        'The "start()" method initializes the application server where it is then accessible at the localhost:\{port\} address. '
                    ],md=6)
                ]),
                html.Hr(),
                dbc.Row([
                    dbc.Col([
                        html.Img(
                            src = 'https://github.com/spborder/fusion-tools/blob/main/docs/images/fusion-tools/simple-layout.png?raw=true',
                            alt= 'simple fusion-tools layout',
                            style = {
                                'width': '100%'
                            }
                        )
                    ],md=8),
                    dbc.Col([
                        'Simpler layouts which include locally stored data can be defined using a subset of available components. ',
                        'You can also create FUSION visualizations inline with Jupyter Notebooks by adding "jupyter": True to the "app_options" argument. '
                    ],md=4)
                ])
            ])
        }

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
                html.P("Select a topic to view more information", className="lead"),
                html.Hr(),
                dbc.Nav(
                    [
                        dbc.NavItem(dbc.NavLink(
                            n,
                            id = {'type': 'welcome-nav','index': n_idx},
                            active='exact'
                        ))
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
        














