"""Components related to segmentation
"""


import os
import sys
import json
import numpy as np
import pandas as pd
import textwrap
import re

from typing_extensions import Union
from shapely.geometry import box, shape
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go
from umap import UMAP

from io import BytesIO
from PIL import Image
import requests

from skimage.measure import label
import geobuf
import base64

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
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import find_intersecting, extract_geojson_properties, path_to_mask
from fusion_tools.components import Tool
from fusion_tools.tileserver import TileServer


class FeatureAnnotation(Tool):
    """Enables annotation (drawing) on top of structures in the SlideMap using a separate interface.

    :param Tool: General Class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self,
                 storage_path: str,
                 tile_server: TileServer,
                 labels_format: str = 'json',
                 annotations_format: str = 'one-hot'):
        """Constructor method

        :param storage_path: File path to store annotated images and labels
        :type storage_path: str
        """

        self.storage_path = storage_path
        self.tile_server = tile_server
        self.labels_format = labels_format
        self.annotations_format = annotations_format

        assert self.labels_format in ['csv','json']
        assert self.annotations_format in ['one-hot','one-hot-labeled','rgb','index']

        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)

        self.x_scale, self.y_scale = self.get_scale_factors()

        self.title = 'Feature Annotation'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        # Add callbacks here
        self.get_callbacks()

    def get_scale_factors(self):
        """Getting x and y scale factors to convert from map coordinates back to pixel coordinates
        """

        if hasattr(self.tile_server,'image_metadata'):
            base_dims = [
                self.tile_server.image_metadata['sizeX']/(2**(self.tile_server.image_metadata['levels']-1)),
                self.tile_server.image_metadata['sizeY']/(2**(self.tile_server.image_metadata['levels']-1))
            ]
        
            x_scale = base_dims[0] / self.tile_server.image_metadata['sizeX']
            y_scale = -(base_dims[1] / self.tile_server.image_metadata['sizeY'])
        
        elif hasattr(self.tile_server,'tiles_metadata'):
            base_dims = [
                self.tile_server.tiles_metadata['sizeX']/(2**(self.tile_server.tiles_metadata['levels']-1)),
                self.tile_server.tiles_metadata['sizeY']/(2**(self.tile_server.tiles_metadata['levels']-1))
            ]
        
            x_scale = base_dims[0] / self.tile_server.tiles_metadata['sizeX']
            y_scale = -(base_dims[1] / self.tile_server.tiles_metadata['sizeY'])

        else:
            raise AttributeError("Missing image or tiles metadata")


        return x_scale, y_scale

    def gen_layout(self):
        """Generating layout for component
        """

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        dbc.Col(
                            html.H3('Feature Annotation')
                        )
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Col(
                            'Used for annotating (drawing) on top of structures in the SlideMap'
                        )
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Select structure in current viewport: ',html_for = {'type': 'feature-annotation-structure-drop','index': 0})
                        ], md = 3),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = False,
                                placeholder = "Structure",
                                id = {'type': 'feature-annotation-structure-drop','index': 0}
                            )
                        ],md = 9),
                        dcc.Store(
                            id = {'type': 'feature-annotation-current-structures','index': 0},
                            storage_type='memory',
                            data = json.dumps({})
                        )
                    ],style = {'marginBottom': '10px'}),
                    dbc.Row([
                        dbc.Col([
                            dbc.Row([
                                html.Div(
                                    dcc.Graph(
                                        id = {'type': 'feature-annotation-figure','index': 0},
                                        figure = go.Figure(
                                            layout = {
                                                'margin': {'l':0,'r':0,'t':0,'b':0},
                                                'xaxis': {'showticklabels': False,'showgrid': False},
                                                'yaxis': {'showticklabels': False, 'showgrid': False},
                                                'dragmode': 'drawclosedpath'
                                            }
                                        ),
                                        config = {
                                            'modeBarButtonsToAdd': [
                                                'drawopenpath',
                                                'drawclosedpath',
                                                'eraseshape'
                                            ]
                                        }
                                    )
                                )
                            ]),
                            html.Div(
                                id = {'type': 'feature-annotation-buttons-div','index': 0},
                                children = [
                                    dcc.Loading(
                                        dbc.Row([
                                            dbc.Col([
                                                dbc.Button(
                                                    'Previous',
                                                    className = 'd-grid col-12 mx-auto',
                                                    n_clicks = 0,
                                                    id = {'type': 'feature-annotation-previous','index': 0}
                                                )
                                            ],md = 4),
                                            dbc.Col([
                                                dbc.Button(
                                                    'Save',
                                                    className = 'd-grid col-12 mx-auto',
                                                    n_clicks = 0,
                                                    color = 'success',
                                                    id = {'type':'feature-annotation-save','index': 0}
                                                )
                                            ],md = 4),
                                            dbc.Col([
                                                dbc.Button(
                                                    'Next',
                                                    className = 'd-grid col-12 mx-auto',
                                                    n_clicks = 0,
                                                    id = {'type': 'feature-annotation-next','index': 0}
                                                )
                                            ],md = 4)
                                        ])
                                    )
                                ],
                                style = {'marginTop':'10px'}
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Annotation Options')
                        ])
                    ],style = {'marginTop': '5px'}),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Current Classes: ',html_for = {'type': 'feature-annotation-class-drop','index': 0})
                        ],md = 3),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = False,
                                placeholder = 'Class',
                                id = {'type': 'feature-annotation-class-drop','index': 0}
                            )
                        ], md = 7),
                        dbc.Col([
                            dbc.Button(
                                'New',
                                n_clicks = 0,
                                className = 'd-grid col-12 mx-auto',
                                id = {'type': 'feature-annotation-class-new','index': 0},
                                style = {'width': '100%','height': '100%'}
                            )
                        ], md = 2)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Current Labels: ',html_for = {'type': 'feature-annotation-label-drop','index': 0})
                        ],md = 2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [],
                                value = [],
                                multi = False,
                                placeholder = 'Label',
                                id = {'type': 'feature-annotation-label-drop','index': 0}
                            )
                        ], md = 4),
                        dbc.Col([
                            dcc.Textarea(
                                id = {'type': 'feature-annotation-label-text','index': 0},
                                maxLength = 1000,
                                placeholder = 'Label Value',
                                style = {'width': '100%','height': '100px'}
                            )
                        ], md = 5),
                        dbc.Col([
                            html.A(
                                html.I(
                                    id = {'type': 'feature-annotation-label-submit','index': 0},
                                    className = 'bi bi-check-circle-fill fa-lg',
                                    style = {'color': 'rgb(0,255,0)'}
                                )
                            )
                        ],md = 1)
                    ],style = {'marginTop':'10px'}),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Add Class/Label: ',html_for={'type': 'feature-annotation-add-class','index': 0})
                        ],md = 2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = ['Class','Label'],
                                value = [],
                                placeholder = 'New Type',
                                id = {'type': 'feature-annotation-add-class','index': 0}
                            )
                        ], md = 4),
                        dbc.Col([
                            html.Div(
                                id = {'type':'feature-annotation-add-options','index': 0},
                                children = [],
                            )
                        ], md = 4),
                        dbc.Col([
                            dbc.Button(
                                'Add',
                                id = {'type': 'feature-annotation-add-submit','index': 0},
                                className = 'd-grid col-12 mx-auto',
                                color = 'success',
                                disabled = True,
                                style = {'height': '100%','width': '100%'}
                            )
                        ], md = 2)
                    ])
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow': 'scroll'})

        return layout

    def get_callbacks(self):
        """Initializing callbacks and adding to DashBlueprint
        """

        # Updating which structures are available in the dropdown menu
        self.blueprint.callback(
            [
                Input({'type': 'slide-map','index':ALL},'bounds')
            ],
            [
                Output({'type': 'feature-annotation-structure-drop','index': ALL},'options'),
                Output({'type': 'feature-annotation-current-structures','index': ALL},'data')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'vis-layout-tabs','index': ALL},'active_tab')
            ]
        )(self.update_structure_options)

        # Updating which structure is in the annotation figure
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-structure-drop','index': ALL},'value'),
                Input({'type': 'feature-annotation-previous','index': ALL},'n_clicks'),
                Input({'type': 'feature-annotation-next','index': ALL},'n_clicks'),
            ],
            [
                Output({'type': 'feature-annotation-figure','index': ALL},'figure'),
                Output({'type': 'feature-annotation-save','index':ALL},'children'),
                Output({'type':'feature-annotation-current-structures','index': ALL},'data'),
                Output({'type': 'feature-annotation-label-text','index': ALL},'value')
            ],
            [
                State({'type': 'feature-annotation-current-structures','index': ALL},'data'),
                State({'type': 'feature-annotation-class-drop','index':ALL},'value')
            ]
        )(self.update_structure)

        # Adding a new class/label to the available set of classes/labels
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-add-class','index': ALL},'value'),
                Input({'type': 'feature-annotation-add-submit','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-add-class','index': ALL},'value'),
                Output({'type': 'feature-annotation-add-options','index': ALL},'children'),
                Output({'type': 'feature-annotation-add-submit','index': ALL},'disabled'),
                Output({'type': 'feature-annotation-class-drop','index':ALL},'options'),
                Output({'type': 'feature-annotation-label-drop','index': ALL},'options')
            ],
            [
                State({'type': 'feature-annotation-add-class-color', 'index': ALL},'value'),
                State({'type': 'feature-annotation-add-class-name','index':ALL},'value'),
                State({'type': 'feature-annotation-add-label-name', 'index': ALL},'value'),
                State({'type': 'feature-annotation-class-drop','index': ALL},'options'),
                State({'type': 'feature-annotation-label-drop','index': ALL},'options')
            ]
        )(self.create_class_label)

        # Adding a new class/label to the current figure and structure
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-class-new','index': ALL},'n_clicks'),
                Input({'type': 'feature-annotation-label-submit','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-figure','index': ALL},'figure')
            ],
            [
                State({'type': 'feature-annotation-class-drop','index': ALL},'value'),
                State({'type': 'feature-annotation-label-drop','index': ALL},'value'),
                State({'type': 'feature-annotation-label-text','index': ALL},'value'),
                State({'type': 'feature-annotation-current-structures','index': ALL},'data'),
                State({'type': 'feature-annotation-structure-drop','index': ALL},'value')
            ]
        )(self.add_new_class_label)

        # Saving the current annotation mask:
        self.blueprint.callback(
            [
                Input({'type': 'feature-annotation-save','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-save','index': ALL},'children')
            ],
            [
                State({'type': 'feature-annotation-figure','index': ALL},'relayoutData'),
                State({'type': 'feature-annotation-class-drop','index': ALL},'options'),
                State({'type': 'feature-annotation-current-structures','index': ALL},'data'),
                State({'type': 'feature-annotation-structure-drop','index': ALL},'value')
            ]
        )(self.save_annotation)

    def save_label(self, label_name, label_text, image_bbox):
        """Save new label to current save folder.

        :param label_name: Name of label type adding label_text to (e.g. "color")
        :type label_name: str
        :param label_text: Label to add (e.g. "blue")
        :type label_text: str
        """

        # Converting image bbox to slide pixel coordinates:
        image_bbox = [
            int(image_bbox[0]/self.x_scale),
            int(image_bbox[3]/self.y_scale),
            int(image_bbox[2]/self.x_scale),
            int(image_bbox[1]/self.y_scale)
        ]

        if self.labels_format == 'json': 
            if os.path.exists(f'{self.storage_path}/labels.{self.labels_format}'):
                with open(f'{self.storage_path}/labels.{self.labels_format}','r') as f:
                    current_labels = json.load(f)
                    f.close()

                current_labels["Labels"].append(
                    {
                        label_name: label_text,
                        "bbox": image_bbox
                    }
                )

            else:
                current_labels = {
                    "Labels": [
                        {
                            label_name: label_text,
                            "bbox": image_bbox
                        }
                    ]
                }

            print(current_labels)
            with open(f'{self.storage_path}/labels.{self.labels_format}','w') as f:
                json.dump(current_labels,f)
                f.close()
        
        else:

            if os.path.exists(f'{self.storage_path}/labels.{self.labels_format}'):
                current_labels = pd.read_csv(f'{self.storage_path}/labels.{self.labels_format}').to_dict('records')
                
            else:
                current_labels = []
            
            current_labels.append(
                {
                    label_name: label_text,
                    'bbox': image_bbox
                }
            )

            pd.DataFrame.from_records(current_labels).to_csv(f'{self.storage_path}/labels.{self.labels_format}')

    def save_mask(self, annotations, class_options, image_bbox):
        """Saving annotation mask with annotated classes using pre-specified format

        :param annotations: List of SVG paths from the current figure
        :type annotations: list
        :param class_options: List of colors and names for all classes
        :type class_options: list
        :param image_bbox: Bounding box for the current image
        :type image_bbox: list
        """

        image_bbox = [
            int(image_bbox[0] / self.x_scale),
            int(image_bbox[3] / self.y_scale),
            int(image_bbox[2] / self.x_scale),
            int(image_bbox[1] / self.y_scale)
        ]

        height = int(image_bbox[3]-image_bbox[1])
        width = int(image_bbox[2]-image_bbox[0])

        all_class_colors = [i['value'] for i in class_options]

        combined_mask = np.zeros((height, width, len(class_options)))
        for a in range(len(annotations)):
            if 'path' in annotations[a]:
                mask = path_to_mask(annotations[a]['path'], (height,width))
                class_color = annotations[a]['line']['color']
                
                combined_mask[:,:,all_class_colors.index(class_color)] += mask

        # Creating mask in whichever format was specified in initialization
        if 'one-hot' in self.annotations_format:
            if self.annotations_format=='one-hot-labeled':
                # Labeling instances for each class with a unique index
                formatted_mask = np.apply_over_axes(label, combined_mask, [2])
            else:
                formatted_mask = combined_mask.copy()
        elif self.annotations_format == 'rgb':
            # Creating RGB representation of class masks (not good for overlapping classes)
            formatted_mask = np.zeros((height,width,3))

            for c_idx,color in enumerate(all_class_colors):
                rgb_vals = [int(float(i.replace('rgb(','').replace(')',''))) for i in color.split(',')]

                for r_idx,r in enumerate(rgb_vals):
                    formatted_mask[:,:,r_idx] += (combined_mask[:,:,c_idx] * r)

        elif self.annotations_format == 'index':
            # Creating 2D representation of masks where class pixels are replaced with class index (starting with 1, 0=background) (also not good for overlaps)
            formatted_mask = np.zeros((height,width))

            for c_idx in range(combined_mask.shape[2]):
                formatted_mask+=combined_mask[:,:,c_idx]

        # Pulling image region from slide:
        slide_image_region = self.get_structure_region(image_bbox, False)
        # Saving annotation mask:
        save_path = f'{self.storage_path}/Annotations/'
        if not os.path.exists(save_path):
            os.makedirs(save_path)
            os.makedirs(save_path+'Images/')
            os.makedirs(save_path+'Masks/')

        mask_save_path = f'{save_path}/Masks/{"_".join([str(i) for i in image_bbox])}.png'
        image_save_path = f'{save_path}/Images/{"_".join([str(i) for i in image_bbox])}.png'

        if formatted_mask.shape[-1] in [1,3]:
            Image.fromarray(np.uint8(formatted_mask)).save(mask_save_path)
            slide_image_region.save(image_save_path)

        else:
            np.save(mask_save_path.replace('.png','.npy'),np.uint8(formatted_mask))
            slide_image_region.save(image_save_path)

    def update_structure_options(self, slide_bounds, current_features, active_tab):
        """Updating the structure options based on updated slide bounds

        :param slide_bounds: Current slide bounds
        :type slide_bounds: list
        :param current_features: Current set of GeoJSON FeatureCollections
        :type current_features: list
        :param active_tab: Active tab in vis-tools
        :type active_tab: list
        :return: Updated structure dropdown options and bounding box data
        :rtype: tuple
        """

        active_tab = get_pattern_matching_value(active_tab)
        if not active_tab is None:
            if not active_tab == 'feature-annotation':
                raise exceptions.PreventUpdate
            
        slide_map_bounds = get_pattern_matching_value(slide_bounds)
        slide_map_box = box(slide_map_bounds[0][1],slide_map_bounds[0][0],slide_map_bounds[1][1],slide_map_bounds[1][0])

        current_features = json.loads(get_pattern_matching_value(current_features))

        structure_options = []
        structure_bboxes = {}
        for g in current_features:
            intersecting_shapes, intersecting_properties = find_intersecting(g,slide_map_box)
            if len(intersecting_shapes)>0:
                structure_options.append(g['properties']['name'])

                structure_bboxes[g['properties']['name']] = [
                    list(shape(f['geometry']).bounds) for f in intersecting_shapes['features']
                ]
                structure_bboxes[f'{g["properties"]["name"]}_index'] = 0

        new_structure_bboxes = json.dumps(structure_bboxes)

        return [structure_options], [new_structure_bboxes]

    def update_structure(self, structure_drop_value, prev_click, next_click, current_structure_data, current_class_value):
        """Updating the current structure figure based on selections

        :param structure_drop_value: Structure name selected from the structure dropdown menu
        :type structure_drop_value: list
        :param prev_click: Previous button clicked
        :type prev_click: list
        :param next_click: Next button clicked
        :type next_click: list
        :param current_structure_data: Current structure bounding boxes and indices
        :type current_structure_data: list
        :param current_class_value: Current class value from the class dropdown menu
        :type current_class_value: list
        :return: Updated figure containing new structure, updated structure index if previous or next button is clicked, cleared label text
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        structure_drop_value = get_pattern_matching_value(structure_drop_value)
        current_structure_data = json.loads(get_pattern_matching_value(current_structure_data))
        current_class_value = get_pattern_matching_value(current_class_value)

        if structure_drop_value is None or not structure_drop_value in current_structure_data:
            raise exceptions.PreventUpdate

        if ctx.triggered_id['type'] in ['feature-annotation-structure-drop','feature-annotation-class-new']:
            # Getting a new structure:
            current_structure_index = current_structure_data[f'{structure_drop_value}_index']
            current_structure_region = current_structure_data[structure_drop_value][current_structure_index]

        elif ctx.triggered_id['type'] == 'feature-annotation-previous':
            # Going to previous structure
            current_structure_index = current_structure_data[f'{structure_drop_value}_index']
            if current_structure_index==0:
                current_structure_index = len(current_structure_data[structure_drop_value])-1
            else:
                current_structure_index -= 1
            
            current_structure_region = current_structure_data[structure_drop_value][current_structure_index]

        elif ctx.triggered_id['type'] == 'feature-annotation-next':
            # Going to next structure
            current_structure_index = current_structure_data[f'{structure_drop_value}_index']
            if current_structure_index==len(current_structure_data[structure_drop_value])-1:
                current_structure_index = 0
            else:
                current_structure_index += 1

            current_structure_region = current_structure_data[structure_drop_value][current_structure_index]

        current_structure_data[f'{structure_drop_value}_index'] = current_structure_index
        
        # Getting the current selected class
        if not current_class_value is None:
            line_color = current_class_value
            fill_color = current_class_value.replace('(','a(').replace(')',',0.2)')
        else:
            line_color = 'rgb(0,0,0)'
            fill_color = 'rgba(0,0,0,0.2)'

        # Removing old label text
        new_label_text = []

        # Pulling out the desired region:
        image_region = self.get_structure_region(current_structure_region)
        image_figure = go.Figure(px.imshow(np.array(image_region)))
        image_figure.update_layout(
            {
                'margin': {'l':0,'r':0,'t':0,'b':0},
                'xaxis':{'showticklabels':False,'showgrid':False},
                'yaxis':{'showticklabels':False,'showgrid':False},
                'dragmode':'drawclosedpath',
                #"shapes":annotations,
                #"newshape.line.width": line_slide,
                "newshape.line.color": line_color,
                "newshape.fillcolor": fill_color
            }
        )

        return [image_figure], ['Save'], [json.dumps(current_structure_data)], [new_label_text]

    def get_structure_region(self, structure_bbox:list, scale:bool = True):
        """Using the tile server "regions_url" property to pull out a specific region of tissue

        :param structure_bbox: List of minx, miny, maxx, maxy coordinates
        :type structure_bbox: list
        :param scale: Whether or not to scale the bbox values to slide coordinates
        :type scale: bool
        """

        # Converting structure bbox from map coordinates to slide-pixel coordinates
        if scale:
            slide_coordinates = [
                int(structure_bbox[0]/self.x_scale), 
                int(structure_bbox[3]/self.y_scale), 
                int(structure_bbox[2]/self.x_scale), 
                int(structure_bbox[1]/self.y_scale)
            ]
        else:
            slide_coordinates = structure_bbox

        #TODO: Update this function for multi-frame images
        image_region = Image.open(
            BytesIO(
                requests.get(
                    self.tile_server.regions_url+f'?left={slide_coordinates[0]}&top={slide_coordinates[1]}&right={slide_coordinates[2]}&bottom={slide_coordinates[3]}'
                ).content
            )
        )

        return image_region
    
    def add_new_class_label(self, add_class, add_label, new_class, new_label, label_text, current_structure_data, current_structure):
        """Adding a new class or label to the current structure

        :param add_class: Add class clicked
        :type add_class: list
        :param add_label: Add label clicked
        :type add_label: list
        :param new_class: New class to add to the current structure
        :type new_class: list
        :param new_label: New label name to add for the current structure
        :type new_label: list
        :param label_text: New label text to add for the current structure
        :type label_text: list
        :param current_structure_data: Current structure bounding boxes and indices
        :type current_structure_data: list
        :param current_structure: Current structure selection
        :type current_structure: list
        :return: Returning updated figure with new line color, fill color and saving the new label to the save directory
        :rtype: list
        """
        new_class = get_pattern_matching_value(new_class)
        new_label = get_pattern_matching_value(new_label)
        label_text = get_pattern_matching_value(label_text)
        current_structure_data = json.loads(get_pattern_matching_value(current_structure_data))
        current_structure = get_pattern_matching_value(current_structure)

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        # Updating the figure "newshape.line.color" and "newshape.fillcolor" properties
        if ctx.triggered_id['type']=='feature-annotation-class-new':
            if not new_class is None:
                figure_update = Patch()
                figure_update['layout']['newshape']['line']['color'] = new_class
                figure_update['layout']['newshape']['fillcolor'] = new_class.replace('(','a(').replace(')',',0.2)')
            else:
                raise exceptions.PreventUpdate
        
        # Adding a label to 
        elif ctx.triggered_id['type'] == 'feature-annotation-label-submit':
            figure_update = no_update

            image_bbox = current_structure_data[current_structure][current_structure_data[f'{current_structure}_index']]

            if not new_label is None:
                # Saving label to running file
                self.save_label(new_label, label_text, image_bbox)
            else:
                raise exceptions.PreventUpdate
        
        return [figure_update]
    
    def create_class_label(self, add_class_value, add_submit_click, add_class_color, add_class_name, add_label_name, current_class_options, current_label_options):
        """Creating a new class or label to add to the session

        :param add_class_value: Dropdown value for adding either a class or label
        :type add_class_value: list
        :param add_submit_click: Submit button clicked
        :type add_submit_click: list
        :param add_class_color: New color for the new class added
        :type add_class_color: list
        :param add_class_name: New name for the new class added
        :type add_class_name: list
        :param add_label_name: New name for new label added
        :type add_label_name: list
        :param current_class_options: Current options in the class dropdown menu
        :type current_class_options: list
        :param current_label_options: Current options in the label dropdown menu
        :type current_label_options: list
        :return: Updating the label and class dropdown options
        :rtype: tuple
        """
        add_class_value = get_pattern_matching_value(add_class_value)
        add_class_color = get_pattern_matching_value(add_class_color)
        add_class_name = get_pattern_matching_value(add_class_name)
        add_label_name = get_pattern_matching_value(add_label_name)

        current_class_options = get_pattern_matching_value(current_class_options)
        current_label_options = get_pattern_matching_value(current_label_options)

        if ctx.triggered_id['type'] == 'feature-annotation-add-class':

            if add_class_value == 'Class':
                # Getting the class name input and color picker:
                options_div = html.Div([
                    dcc.Input(
                        type = 'text',
                        maxLength = 1000,
                        id = {'type': 'feature-annotation-add-class-name','index': 0},
                        placeholder = 'New Class Name',
                        style = {'width': '100%'}
                    ),
                    html.Div(
                        dmc.ColorInput(
                            id = {'type':'feature-annotation-add-class-color','index':0},
                            label = 'Color',
                            format = 'rgb',
                            value = f'rgb({np.random.randint(0,255)},{np.random.randint(0,255)},{np.random.randint(0,255)})'
                        ),
                        style = {'width':'100%'}
                    )                       
                ])

            elif add_class_value == 'Label':
                # Getting the new label name input
                options_div = html.Div([
                    dcc.Input(
                        type = 'text',
                        maxLength = 1000,
                        placeholder = 'New Label Name',
                        id = {'type': 'feature-annotation-add-label-name','index': 0}
                    )
                ],style = {'width': '100%'})


            add_submit_disabled = False
            new_class_options = no_update
            new_label_options = no_update

            add_class_drop_value = add_class_value

        elif ctx.triggered_id['type'] == 'feature-annotation-add-submit':

            if add_class_value == 'Class':
                if not add_class_color is None and not add_class_name is None:
                    options_div = []
                    add_submit_disabled = True
                    if not current_class_options is None:
                        new_class_options = current_class_options + [{'label': html.Div(add_class_name,style = {'color': add_class_color}), 'value': add_class_color}]
                    else:
                        new_class_options = [{'label': html.Div(add_class_name,style={'color': add_class_color}),'value': add_class_color}]
                    new_label_options = no_update
                
                else:
                    raise exceptions.PreventUpdate
            elif add_class_value == 'Label':
                if not add_label_name is None:
                    options_div = []
                    add_submit_disabled = True
                    new_class_options = no_update
                    if not current_label_options is None:
                        new_label_options = current_label_options + [{'label': add_label_name, 'value': add_label_name}]
                    else:
                        new_label_options = [{'label': add_label_name,'value': add_label_name}]
                
                else:
                    raise exceptions.PreventUpdate
                
            add_class_drop_value = []


        return [add_class_drop_value], [options_div], [add_submit_disabled], [new_class_options], [new_label_options]

    def save_annotation(self, save_click, current_annotations, current_classes, current_structure_data, current_structure):
        """Saving the current annotation in image format

        :param save_click: Save button is clicked
        :type save_click: list
        :param current_annotations: Current annotations (in SVG path format)
        :type current_annotations: list
        """

        current_annotations = get_pattern_matching_value(current_annotations)
        current_classes = get_pattern_matching_value(current_classes)
        current_structure_data = json.loads(get_pattern_matching_value(current_structure_data))
        current_structure = get_pattern_matching_value(current_structure)

        if not any([i['value'] for i in ctx.triggered]) or current_classes is None:
            raise exceptions.PreventUpdate

        annotations = []
        if not current_annotations is None:
            if 'shapes' in current_annotations.keys():
                annotations += current_annotations['shapes']

                if 'line' in current_annotations.keys():
                    annotations += current_annotations['line']
            
        image_bbox = current_structure_data[current_structure][current_structure_data[f'{current_structure}_index']]

        # Saving annotation to storage_path
        self.save_mask(annotations, current_classes, image_bbox)

        return ['Saved!']

class BulkLabels(Tool):
    """Add labels to many structures at the same time

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data
    :type Tool: None
    """
    def __init__(self,
                 geojson_anns: Union[list,dict],
                 tile_server: TileServer,
                 reference_object: Union[str,None] = None,
                 ignore_list: list = [],
                 property_depth: int = 4,
                 storage_path: str = "./",
                 labels_format: str = "json"):
        """Constructor method

        :param storage_path: Path to save labels and outputs to
        :type storage_path: str
        :param labels_format: Format for labels, defaults to "json"
        :type labels_format: str, optional
        """

        self.tile_server = tile_server
        self.reference_object = reference_object
        self.property_options, self.feature_names, self.property_info = extract_geojson_properties(geojson_anns, self.reference_object, ignore_list, property_depth)

        self.x_scale, self.y_scale = self.get_scale_factors()

        self.storage_path = storage_path
        self.labels_format = labels_format

        assert self.labels_format in ['json','csv']

        self.title = 'Bulk Labels'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def get_scale_factors(self):
        """Getting x and y scale factors to convert from map coordinates back to pixel coordinates
        """

        if hasattr(self.tile_server,'image_metadata'):
            base_dims = [
                self.tile_server.image_metadata['sizeX']/(2**(self.tile_server.image_metadata['levels']-1)),
                self.tile_server.image_metadata['sizeY']/(2**(self.tile_server.image_metadata['levels']-1))
            ]
        
            x_scale = base_dims[0] / self.tile_server.image_metadata['sizeX']
            y_scale = -(base_dims[1] / self.tile_server.image_metadata['sizeY'])
        
        elif hasattr(self.tile_server,'tiles_metadata'):
            base_dims = [
                self.tile_server.tiles_metadata['sizeX']/(2**(self.tile_server.tiles_metadata['levels']-1)),
                self.tile_server.tiles_metadata['sizeY']/(2**(self.tile_server.tiles_metadata['levels']-1))
            ]
        
            x_scale = base_dims[0] / self.tile_server.tiles_metadata['sizeX']
            y_scale = -(base_dims[1] / self.tile_server.tiles_metadata['sizeY'])

        else:
            raise AttributeError("Missing image or tiles metadata")


        return x_scale, y_scale

    def gen_layout(self):
        """Generating layout for BulkLabels component

        :return: BulkLabels layout
        :rtype: html.Div
        """
        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Bulk Labels')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Apply labels to structures based on several different inclusion and exclusion criteria.'
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(
                            html.H5('Step 1: Where?'),
                            md = 9
                        ),
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-rotate fa-xl',
                                    n_clicks = 0,
                                    id = {'type': 'bulk-labels-refresh-icon','index': 0}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'bulk-labels-refresh-icon','index': 0},
                                children = 'Click to reset labeling components'
                            )
                        ],md = 3)
                    ],justify='left'),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Include',html_for = {'type': 'bulk-labels-include-structures','index': 0})
                        ],md = 3),
                        dbc.Col([
                            dcc.Dropdown(
                                options = self.feature_names,
                                value = [],
                                multi = True,
                                placeholder = 'Include Structures',
                                id = {'type': 'bulk-labels-include-structures','index': 0}
                            )
                        ],md = 9),
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'bulk-labels-spatial-query-div','index': 0},
                                children = []
                            )
                        ])
                    ],style={'marginTop':'10px'}),
                    dbc.Row([
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-map-location fa-xl',
                                    id = {'type': 'bulk-labels-spatial-query-icon','index': 0},
                                    n_clicks = 0,
                                    style = {'marginLeft': '50%'}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'bulk-labels-spatial-query-icon','index': 0},
                                children = 'Click to add a spatial query'
                            )
                        ])
                    ],style={'marginBottom': '10px','marginTop':'10px'}),
                    html.Hr(),
                    dbc.Row(
                        html.H5('Step 2: What?')
                    ),
                    html.Hr(),
                    dcc.Store(
                        id = {'type': 'bulk-labels-property-info','index': 0},
                        storage_type='memory',
                        data = json.dumps(self.property_info)
                    ),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'bulk-labels-add-property-div','index': 0},
                                children = []
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-square-plus fa-xl',
                                    id = {'type': 'bulk-labels-add-property-icon','index': 0},
                                    n_clicks = 0,
                                    style = {'marginLeft': '50%'}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'bulk-labels-add-property-icon','index': 0},
                                children = 'Click to add a property filter'
                            )
                        ],align='center')
                    ],style = {'marginBottom': '10px'}),
                    dbc.Row([
                        dbc.Col(
                            dcc.Loading(dbc.Button(
                                'Update Structures',
                                n_clicks = 0,
                                id = {'type': 'bulk-labels-update-structures','index': 0},
                                className = 'd-grid col-12 mx-auto'
                            ))
                        )
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'bulk-labels-current-structures','index': 0},
                                children = []
                            )
                        ])
                    ],style = {'marginBottom': '10px'}),
                    html.Hr(),
                    dbc.Row([
                        html.H5('Step 3: Label!')
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Label: ',html_for = {'type': 'bulk-labels-label-text','index': 0})
                        ],md = 2),
                        dbc.Col([
                            dcc.Input(
                                id = {'type': 'bulk-labels-label-type','index': 0},
                                value = [],
                                placeholder = 'Label Type',
                                disabled = True,
                                style = {'width': '100%'}
                            )
                        ],md = 5),
                        dbc.Col([
                            dcc.Textarea(
                                id = {'type': 'bulk-labels-label-text','index': 0},
                                value = [],
                                maxLength = 1000,
                                placeholder = 'Enter Label Here',
                                required=True,
                                style = {'width': '100%','height':'100px'},
                                disabled = True
                            )
                        ],md = 5)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Additional Rationale: ',html_for = {'type': 'bulk-labels-label-rationale','index': 0})
                        ],md = 3),
                        dbc.Col([
                            dcc.Textarea(
                                id = {'type': 'bulk-labels-label-rationale','index': 0},
                                value = [],
                                maxLength = 1000,
                                placeholder = 'Enter Additional Rationale Here',
                                style = {'width': '100%','height': '100px'},
                                disabled = True
                            )
                        ], md = 9)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Label Source: ',html_for = {'type': 'bulk-labels-label-source','index': 0})
                        ],md = 3),
                        dbc.Col([
                            dcc.Markdown(
                                '`Label Source Data`',
                                id = {'type': 'bulk-labels-label-source','index': 0},
                                style = {'width': '100%','maxHeight': '150px','overflow': 'scroll'}                            
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                'Apply Label!',
                                className = 'd-grid col-12 mx-auto',
                                n_clicks = 0,
                                id = {'type': 'bulk-labels-apply-labels','index': 0},
                                disabled = True
                            )
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                'Download Labels!',
                                className = 'd-grid col-12 mx-auto',
                                n_clicks = 0,
                                id = {'type': 'bulk-labels-download-labels','index': 0},
                                disabled = True
                            ),
                            dcc.Download(
                                id = {'type':'bulk-labels-download-data','index': 0}
                            )
                        ])
                    ],style = {'marginTop': '10px'})
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow': 'scroll'})

        return layout
    
    def get_callbacks(self):
        """Adding callbacks to DashBlueprint object
        """
        
        # Adding spatial relationships 
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-spatial-query-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-remove-spatial-query-icon','index':ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-spatial-query-div','index': ALL},'children')
            ],
            [
                State({'type':'feature-overlay','index': ALL},'name')
            ]
        )(self.update_spatial_queries)

        # Updating inclusion/inclusion criteria
        self.blueprint.callback(
            [
                Input({'type':'bulk-labels-update-structures','index':ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-current-structures','index': ALL},'children'),
                Output({'type': 'map-marker-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-label-source','index': ALL},'children'),
                Output({'type': 'bulk-labels-label-type','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-label-text','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-label-rationale','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-apply-labels','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-download-labels','index': ALL},'disabled')
            ],
            [
                State({'type': 'bulk-labels-include-structures','index': ALL},'value'),
                State({'type': 'bulk-labels-add-property-div','index': ALL},'children'),
                State({'type':'bulk-labels-spatial-query-div','index': ALL},'children'),
                State({'type': 'map-annotations-store','index': ALL},'data')
            ]
        )(self.update_label_structures)

        # Adding new property
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-add-property-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-remove-property-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-add-property-div','index': ALL},'children')
            ]
        )(self.update_label_properties)

        # Updating property selector
        self.blueprint.callback(
            [
                Input({'type':'bulk-labels-filter-property-drop','index': MATCH},'value')
            ],
            [
                Output({'type':'bulk-labels-property-selector-div','index':MATCH},'children')
            ],
            [
                State({'type': 'bulk-labels-property-info','index': ALL},'data')
            ]
        )(self.update_property_selector)

        # Updating spatial query definition:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-spatial-query-drop','index':MATCH},'value')
            ],
            [
                Output({'type': 'bulk-labels-spatial-query-definition','index': MATCH},'children')
            ]
        )(self.update_spatial_query_definition)

        # Applying labels to marked points:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-apply-labels','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-property-info','index': ALL},'data')
            ],
            [
                State({'type': 'map-marker-div','index': ALL},'children'),
                State({'type': 'bulk-labels-property-info','index': ALL},'data'),
                State({'type': 'bulk-labels-label-type','index': ALL},'value'),
                State({'type': 'bulk-labels-label-text','index': ALL},'value'),
                State({'type': 'bulk-labels-label-rationale','index': ALL},'value'),
                State({'type': 'bulk-labels-label-source','index': ALL},'children')
            ]
        )(self.apply_labels)

        # Resetting everything:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-refresh-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type':'bulk-labels-include-structures','index': ALL},'value'),
                Output({'type': 'bulk-labels-spatial-query-div','index':ALL},'children'),
                Output({'type': 'bulk-labels-add-property-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-current-structures','index': ALL},'children'),
                Output({'type': 'bulk-labels-label-type','index': ALL},'value'),
                Output({'type': 'bulk-labels-label-type','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-label-text','index': ALL},'value'),
                Output({'type': 'bulk-labels-label-text','index':ALL},'disabled'),
                Output({'type': 'bulk-labels-label-rationale','index': ALL},'value'),
                Output({'type': 'bulk-labels-label-rationale','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-label-source','index': ALL},'children'),
                Output({'type': 'bulk-labels-apply-labels','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-include-structures','index':ALL},'options'),
                Output({'type': 'bulk-labels-spatial-query-structures','index':ALL},'options')
            ],
            [
                State({'type': 'feature-overlay','index':ALL},'name')
            ]
        )(self.refresh_labels)

        # Downloading labels
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-download-labels','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-download-data','index': ALL},'data')
            ],
            [
                State({'type': 'bulk-labels-property-info','index': ALL},'data')
            ]
        )(self.download_data)

        # Clearing markers:
        self.blueprint.callback(
            [
                Input({'type': 'label-marker-delete','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'map-marker-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-current-structures','index': ALL},'children'),
            ],
            [
                State({'type': 'map-marker-div','index': ALL},'children')
            ]
        )(self.remove_marker)

    def update_spatial_query_definition(self, query_type):
        """Returning the definition for the selected spatial predicate type

        :param query_type: Name of spatial predicate
        :type query_type: str
        :return: Markdown string
        :rtype: dcc.Markdown
        """

        if query_type is None:
            raise exceptions.PreventUpdate
        
        query_types = {
            'within': '''
            Returns `True` if the *boundary* and *interior* of the object intsect only with the *interior* of the other (not its *boundary* or *exterior*)
            ''',
            'intersects': '''
            Returns `True` if the *boundary* or *interior* of the object intersect in any way with those of the other.
            ''',
            'crosses': '''
            Returns `True` if the *interior* of the object intersects the *interior* of the other but does not contain it, and the dimension of the intersection is less than the dimension of the one or the other.
            ''',
            'contains': '''
            Returns `True` if no points of *other* lie in the exterior of the *object* and at least one point of the interior of *other* lies in the interior of *object*
            ''',
            'touches': '''
            Returns `True` if the objects have at least one point in common and their interiors do not intersect with any part of the other.
            ''',
            'overlaps': '''
            Returns `True` if the geometries have more than one but not all points in common, have the same dimension, and the intersection of the interiors of the geometries has the same dimension as the geometries themselves.
            ''',
            'nearest': '''
            Returns `True` if *other* is within `max_distance` of *object* 
            '''
        }

        if query_type in query_types:
            if query_type=='nearest':
                return [
                    dmc.NumberInput(
                        label = 'Pixel distance',
                        stepHoldDelay = 500,
                        stepHoldInterval=100,
                        value = 0,
                        step = 1,
                        min = 0,
                        style = {'width': '100%'},
                        id = {'type': 'bulk-labels-spatial-query-nearest','index':ctx.triggered_id['index']}
                    ), 
                    dcc.Markdown(
                        query_types[query_type]
                    )
                ]
            else:
                return [dcc.Markdown(query_types[query_type])]
        else:
            raise exceptions.PreventUpdate

    def update_spatial_queries(self, add_click, remove_click, structure_names):
        
        
        queries_div = Patch()
        add_click = get_pattern_matching_value(add_click)

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        if ctx.triggered_id['type']=='bulk-labels-spatial-query-icon':

            def new_query_div():
                return html.Div([
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': 'intersects','value': 'intersects'},
                                    {'label': 'contains','value': 'contains'},
                                    {'label': 'within','value': 'within'},
                                    {'label': 'touches','value': 'touches'},
                                    {'label': 'crosses','value': 'crosses'},
                                    {'label': 'overlaps','value': 'overlaps'},
                                    {'label': 'nearest','value': 'nearest'}
                                ],
                                value = [],
                                multi= False,
                                id = {'type': 'bulk-labels-spatial-query-drop','index': add_click}
                            )
                        ],md = 5),
                        dbc.Col([
                            dcc.Dropdown(
                                options = structure_names,
                                value = [],
                                multi = False,
                                placeholder = 'Select structure',
                                id = {'type': 'bulk-labels-spatial-query-structures','index':add_click}
                            )
                        ],md=5),
                        dbc.Col([
                            html.A(
                                html.I(
                                    id = {'type': 'bulk-labels-remove-spatial-query-icon','index': add_click},
                                    n_clicks = 0,
                                    className = 'bi bi-x-circle-fill fa-2x',
                                    style = {'color': 'rgb(255,0,0)'}
                                )
                            )
                        ], md = 2)
                    ]),
                    html.Div(
                        id = {'type': 'bulk-labels-spatial-query-definition','index': add_click},
                        children = []
                    )
                ])

            queries_div.append(new_query_div())

        elif ctx.triggered_id['type']=='bulk-labels-remove-spatial-query-icon':

            values_to_remove = []
            for i, val in enumerate(remove_click):
                if val:
                    values_to_remove.insert(0,i)

            for v in values_to_remove:
                del queries_div[v]

        
        return [queries_div]

    def parse_filter_divs(self, add_property_parent: list)->list:

        processed_filters = []
        if not add_property_parent is None:
            for div in add_property_parent:
                div_children = div['props']['children']
                filter_name = div_children[0]['props']['children'][0]['props']['children'][0]['props']['value']

                if 'value' in div_children[1]['props']['children']['props']:
                    filter_value = div_children[1]['props']['children']['props']['value']
                else:
                    filter_value = div_children[1]['props']['children']['props']['children']['props']['value']

                if not any([i is None for i in [filter_name,filter_value]]):
                    processed_filters.append({
                        'name': filter_name,
                        'range': filter_value
                    })

        return processed_filters

    def parse_spatial_divs(self, spatial_query_parent: list)->list:

        processed_queries = []
        if not spatial_query_parent is None:
            for div in spatial_query_parent:
                div_children = div['props']['children'][0]['props']['children']

                query_type = div_children[0]['props']['children'][0]['props']['value']
                query_structure = div_children[1]['props']['children'][0]['props']['value']
                
                if not any([i is None for i in [query_type,query_structure]]):
                    if not query_type=='nearest':
                        processed_queries.append({
                            'type': query_type,
                            'structure': query_structure
                        })
                    else:
                        distance_div = div['props']['children'][1]['props']['children']
                        query_distance = distance_div[0]['props']['value']

                        if not query_distance is None:
                            processed_queries.append({
                                'type': query_type,
                                'structure': query_structure,
                                'distance': query_distance*self.x_scale
                            })

        return processed_queries

    def process_filters_queries(self, filter_list, spatial_list, structures, all_geo_list):

        # First getting the listed structures:
        for g_idx, g in enumerate(all_geo_list):
            if type(g)==str:
                print(len(g))
                print(g[0:100])
                all_geo_list[g_idx] = geobuf.decode(g.encode('utf-8'))

        structure_filtered = [gpd.GeoDataFrame.from_features(i['features']) for i in all_geo_list if i['properties']['name'] in structures]

        # Now going through spatial queries
        if len(spatial_list)>0:
            remainder_structures = []

            for s in structure_filtered:
                intermediate_gdf = s.copy()
                for s_q in spatial_list:
                    sq_geo = [i for i in all_geo_list if i['properties']['name']==s_q['structure']][0]
                    sq_structure = gpd.GeoDataFrame.from_features(sq_geo['features'])

                    if not s_q['type'] == 'nearest':
                        intermediate_gdf = gpd.sjoin(
                            left_df = intermediate_gdf, 
                            right_df = sq_structure, 
                            how = 'inner', 
                            predicate=s_q['type']
                        )
                    else:
                        intermediate_gdf = gpd.sjoin_nearest(
                            left_df = intermediate_gdf, 
                            right_df = sq_structure,
                            how = 'inner',
                            max_distance = s_q['distance']
                        )
                    
                    intermediate_gdf = intermediate_gdf.drop([i for i in ['index_left','index_right'] if i in intermediate_gdf], axis = 1)

                remainder_structures.append(intermediate_gdf)
        else:
            remainder_structures = structure_filtered

        # Combining into one GeoJSON
        combined_geojson = {
            'type': 'FeatureCollection',
            'features': []
        }
        for g in remainder_structures:
            g_json = json.loads(g.to_json(show_bbox=True))

            if len(g_json['features'])>0:
                combined_geojson['features'].extend(g_json['features'])

        # Going through property filters:
        if len(filter_list)>0:
            filtered_geojson = {
                'type': 'FeatureCollection',
                'features': []
            }

            for feat in combined_geojson['features']:
                include = True
                for f in filter_list:
                    if include:
                        filter_name_parts = f['name'].split(' --> ')

                        include = True
                        feat_props = feat['properties'].copy()
                        feat_props = {i.replace('_left',''):j for i,j in feat_props.items()}

                        for filt in filter_name_parts:
                            if filt in feat_props:
                                feat_props = feat_props[filt]
                            else:
                                include = include & False
                                break
                        
                        if include:
                            if all([type(i) in [int,float] for i in f['range']]):
                                if f['range'][0]<=feat_props and feat_props<=f['range'][1]:
                                    include = include & True
                                else:
                                    include = include & False
                            
                            elif all([type(i)==str for i in f['range']]):
                                if feat_props in f['range']:
                                    include = include & True
                                else:
                                    include = include & False
                    
                if include:
                    filtered_geojson['features'].append(feat)

        else:
            filtered_geojson = combined_geojson
        
        return filtered_geojson

    def update_label_structures(self, update_structures_click, include_structures, filter_properties, spatial_queries, current_features):


        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        include_structures = get_pattern_matching_value(include_structures)
        current_features = json.loads(get_pattern_matching_value(current_features))

        include_properties = get_pattern_matching_value(filter_properties)
        spatial_queries = get_pattern_matching_value(spatial_queries)

        processed_filters = self.parse_filter_divs(include_properties)
        processed_spatial_queries = self.parse_spatial_divs(spatial_queries)

        filtered_geojson = self.process_filters_queries(processed_filters, processed_spatial_queries, include_structures, current_features)

        new_structures_div = [
            dbc.Alert(
                f'{len(filtered_geojson["features"])} Structures Included!',
                color = 'success' if len(filtered_geojson['features'])>0 else 'danger'
            )
        ]

        new_markers_div = [
                dl.Marker(
                    position = [
                        (f['bbox'][0]+f['bbox'][2])/2,
                        (f['bbox'][1]+f['bbox'][3])/2
                    ][::-1],
                    children = [
                        dl.Popup(
                            dbc.Button(
                                'Clear Marker',
                                color = 'danger',
                                n_clicks = 0,
                                id = {'type': 'label-marker-delete','index': f_idx}
                            ),
                            id = {'type':'label-marker-popup','index': f_idx}
                        )
                    ],
                    id = {'type': 'label-marker','index': f_idx}
                )
                for f_idx, f in enumerate(filtered_geojson['features'])
            ]

        new_labels_source = f'`{json.dumps({"Spatial": processed_spatial_queries,"Filters": processed_filters})}`'

        if len(filtered_geojson['features'])>0:
            labels_type_disabled = False
            labels_text_disabled = False
            labels_rationale_disabled = False
            labels_apply_button_disabled = False
            labels_download_button_disabled = False
        else:
            labels_type_disabled = True
            labels_text_disabled = True
            labels_rationale_disabled = True
            labels_apply_button_disabled = True
            labels_download_button_disabled = True


        return [new_structures_div], [new_markers_div], [new_labels_source], [labels_type_disabled], [labels_text_disabled], [labels_rationale_disabled], [labels_apply_button_disabled], [labels_download_button_disabled]

    def update_label_properties(self, add_click, remove_click):


        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        properties_div = Patch()
        add_click = get_pattern_matching_value(add_click)

        if ctx.triggered_id['type']=='bulk-labels-add-property-icon':

            def new_property_div():
                return html.Div([
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options = self.property_options,
                                value = [],
                                multi = False,
                                placeholder = 'Select property',
                                id = {'type': 'bulk-labels-filter-property-drop','index':add_click}
                            )
                        ],md=10),
                        dbc.Col([
                            html.A(
                                html.I(
                                    id = {'type': 'bulk-labels-remove-property-icon','index': add_click},
                                    n_clicks = 0,
                                    className = 'bi bi-x-circle-fill fa-2x',
                                    style = {'color': 'rgb(255,0,0)'}
                                )
                            )
                        ], md = 2)
                    ]),
                    html.Div(
                        id = {'type': 'bulk-labels-property-selector-div','index': add_click},
                        children = []
                    )
                ])

            properties_div.append(new_property_div())

        elif ctx.triggered_id['type']=='bulk-labels-remove-property-icon':

            values_to_remove = []
            for i, val in enumerate(remove_click):
                if val:
                    values_to_remove.insert(0,i)

            for v in values_to_remove:
                del properties_div[v]

        
        return [properties_div]

    def update_property_selector(self, property_value, property_info):


        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        property_info = json.loads(get_pattern_matching_value(property_info))

        property_values = property_info[property_value]

        if 'min' in property_values:
            # Used for numeric type filters
            values_selector = html.Div(
                dcc.RangeSlider(
                    id = {'type':'bulk-labels-filter-selector','index': ctx.triggered_id['index']},
                    min = property_values['min'] - 0.01,
                    max = property_values['max'] + 0.01,
                    value = [property_values['min'], property_values['max']],
                    step = 0.01,
                    marks = None,
                    tooltip = {
                        'placement': 'bottom',
                        'always_visible': True
                    },
                    allowCross=True,
                    disabled = False
                ),
                style = {'display': 'inline-block','margin':'auto','width': '100%'}
            )

        elif 'unique' in property_values:
            values_selector = html.Div(
                dcc.Dropdown(
                    id = {'type': 'bulk-labels-filter-selector','index': ctx.triggered_id['index']},
                    options = property_values['unique'],
                    value = property_values['unique'],
                    multi = True
                )
            )

        return values_selector

    def parse_marker_div(self, parent_marker_div):


        marker_coords = []
        for p in parent_marker_div:
            coords = p['props']['position']
            marker_coords.append(
                [coords[1]/self.x_scale,coords[0]/self.y_scale]
            )

        return marker_coords        

    def apply_labels(self, button_click, current_markers, current_data, label_type, label_text, label_rationale, label_source):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        label_type = get_pattern_matching_value(label_type)
        label_text = get_pattern_matching_value(label_text)

        if label_text is None or label_type is None:
            raise exceptions.PreventUpdate

        label_rationale = get_pattern_matching_value(label_rationale)
        label_source = json.loads(get_pattern_matching_value(label_source).replace('`',''))
        current_data = json.loads(get_pattern_matching_value(current_data))
        current_markers = get_pattern_matching_value(current_markers)

        marker_positions = self.parse_marker_div(current_markers)

        if 'labels' in current_data:
            current_data['labels'].extend([
                {'centroid': m, 'label_type': label_type, 'label_text': label_text, 'label_rationale': label_rationale, 'label_source': label_source}
                for m in marker_positions
            ])
        
        else:
            current_data['labels'] = [
                {'centroid': m, 'label_type': label_type, 'label_text': label_text, 'label_rationale': label_rationale, 'label_source': label_source}
                for m in marker_positions
            ]

        new_data = json.dumps(current_data)

        return [new_data]

    def refresh_labels(self, refresh_click, structure_options):
        
        if refresh_click:

            include_structures = []
            spatial_queries = []
            add_property = []
            current_structures = []
            label_type = []
            type_disable = True
            label_text = []
            text_disable = True
            label_rationale = []
            rationale_disable = True
            label_source = '`Label Source`'
            apply_disable = True

            include_options = [{'label': i, 'value': i} for i in structure_options]
            if len(ctx.outputs_list[13])>0:
                spatial_queries = [include_options for i in range(len(ctx.outputs_list[13]))]        
            else:
                spatial_queries = []

            return [include_structures], [spatial_queries], [add_property], [current_structures],[label_type],[type_disable],[label_text], [text_disable], [label_rationale], [rationale_disable], [label_source], [apply_disable], [include_options], spatial_queries
        else:
            raise exceptions.PreventUpdate

    def download_data(self, button_click, label_data):

        if button_click:
            label_data = json.loads(get_pattern_matching_value(label_data))

            return [{'content': json.dumps(label_data['labels']),'filename': 'label_data.json'}]
        else:
            raise exceptions.PreventUpdate

    def remove_marker(self, clear_click, current_markers):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        n_marked = len(get_pattern_matching_value(current_markers))

        patched_list = Patch()
        values_to_remove = []
        for i,val in enumerate(clear_click):
            if val:
                values_to_remove.insert(0,i)

        for v in values_to_remove:
            del patched_list[v]
        
        new_structures_div = [
            dbc.Alert(
                f'{n_marked-1} Structures Included!',
                color = 'success' if (n_marked-1)>0 else 'danger'
            )
        ]

        return [patched_list], [new_structures_div]

