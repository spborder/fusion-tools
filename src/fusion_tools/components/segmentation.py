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
import plotly.express as px
import plotly.graph_objects as go
from umap import UMAP

from io import BytesIO
from PIL import Image
import requests

from skimage.measure import label

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
                State({'type': 'feature-bounds','index': ALL},'data'),
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
                 storage_path: str):
        pass






























