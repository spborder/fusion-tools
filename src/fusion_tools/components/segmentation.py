"""Components related to segmentation
"""


import os
import json
import numpy as np
import pandas as pd

from typing_extensions import Union
from shapely.geometry import box, shape
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go

from io import BytesIO
from PIL import Image, ImageOps
import requests
import time
import geojson

from skimage.measure import label

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table, ClientsideFunction
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
from dash_extensions.javascript import Namespace, assign

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import find_intersecting, extract_geojson_properties, path_to_mask, process_filters_queries
from fusion_tools import Tool


class FeatureAnnotation(Tool):
    """Enables annotation (drawing) on top of structures in the SlideMap using a separate interface.

    :param Tool: General Class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """
    def __init__(self,
                 storage_path: str,
                 labels_format: str = 'json',
                 annotations_format: str = 'one-hot'):
        """Constructor method

        :param storage_path: File path to store annotated images and labels
        :type storage_path: str
        """

        super().__init__()
        # Overruling inherited property 
        self.session_update = True

        self.storage_path = storage_path
        self.labels_format = labels_format
        self.annotations_format = annotations_format

        assert self.labels_format in ['csv','json']
        assert self.annotations_format in ['one-hot','one-hot-labeled','rgb','index']

        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
    
    def __str__(self):
        return 'Feature Annotation'

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Feature Annotation'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        # Add callbacks here
        self.get_callbacks()

    def get_scale_factors(self, image_metadata: dict):
        """Function used to initialize scaling factors applied to GeoJSON annotations to project annotations into the SlideMap CRS (coordinate reference system)

        :return: x and y (horizontal and vertical) scale factors applied to each coordinate in incoming annotations
        :rtype: float
        """

        base_dims = [
            image_metadata['sizeX']/(2**(image_metadata['levels']-1)),
            image_metadata['sizeY']/(2**(image_metadata['levels']-1))
        ]

        #x_scale = (base_dims[0]*(240/image_metadata['tileHeight'])) / image_metadata['sizeX']
        #y_scale = -((base_dims[1]*(240/image_metadata['tileHeight'])) / image_metadata['sizeY'])

        x_scale = base_dims[0] / image_metadata['sizeX']
        y_scale = -(base_dims[1]) / image_metadata['sizeY']


        return x_scale, y_scale

    def gen_layout(self, session_data:dict):
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
                        ],md =7),
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-rotate fa-xl',
                                    n_clicks = 0,
                                    id = {'type': 'feature-annotation-refresh-icon','index': 0}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': 'feature-annotation-refresh-icon','index': 0},
                                children = 'Click to refresh available structures'
                            )
                        ],md = 2),
                        dcc.Store(
                            id = {'type': 'feature-annotation-current-structures','index': 0},
                            storage_type='memory',
                            data = json.dumps({})
                        ),
                        dcc.Store(
                            id = {'type': 'feature-annotation-slide-information','index': 0},
                            storage_type = 'memory',
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

        self.blueprint.layout = layout

    def get_callbacks(self):
        """Initializing callbacks and adding to DashBlueprint
        """

        # Updating with new slide
        self.blueprint.callback(
            [
                Input({'type': 'slide-select-drop','index':ALL},'value')
            ],
            [
                Output({'type': 'feature-annotation-slide-information','index':ALL},'data')
            ],
            [
                State('anchor-vis-store','data')
            ]
        )(self.update_slide)

        # Updating which structures are available in the dropdown menu
        self.blueprint.callback(
            [
                Input({'type': 'feature-overlay','index':ALL},'name'),
                Input({'type': 'feature-annotation-refresh-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-annotation-structure-drop','index': ALL},'options'),
                Output({'type': 'feature-annotation-current-structures','index': ALL},'data')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'slide-map','index':ALL},'bounds'),
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
                State({'type': 'feature-annotation-class-drop','index':ALL},'value'),
                State({'type':'feature-annotation-slide-information','index':ALL},'data')
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
                State({'type': 'feature-annotation-structure-drop','index': ALL},'value'),
                State({'type': 'feature-annotation-slide-information','index': ALL},'data')
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
                State({'type': 'feature-annotation-structure-drop','index': ALL},'value'),
                State({'type':'feature-annotation-slide-information','index':ALL},'data')
            ]
        )(self.save_annotation)

    def update_slide(self, slide_selection,vis_data):

        if not any([i['value'] or i['value']==0 for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        vis_data = json.loads(vis_data)
        slide_data = vis_data['current'][get_pattern_matching_value(slide_selection)]
        new_slide_data = {}
        new_slide_data['regions_url'] = slide_data['regions_url']
        new_metadata = requests.get(slide_data['image_metadata_url']).json()
        new_slide_data['x_scale'], new_slide_data['y_scale'] = self.get_scale_factors(new_metadata)

        new_slide_data = json.dumps(new_slide_data)

        return [new_slide_data]

    def save_label(self, label_name, label_text, image_bbox, slide_information):
        """Save new label to current save folder.

        :param label_name: Name of label type adding label_text to (e.g. "color")
        :type label_name: str
        :param label_text: Label to add (e.g. "blue")
        :type label_text: str
        """

        # Converting image bbox to slide pixel coordinates:
        image_bbox = [
            int(image_bbox[0]/slide_information['x_scale']),
            int(image_bbox[3]/slide_information['y_scale']),
            int(image_bbox[2]/slide_information['x_scale']),
            int(image_bbox[1]/slide_information['y_scale'])
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

    def save_mask(self, annotations, class_options, image_bbox, slide_information):
        """Saving annotation mask with annotated classes using pre-specified format

        :param annotations: List of SVG paths from the current figure
        :type annotations: list
        :param class_options: List of colors and names for all classes
        :type class_options: list
        :param image_bbox: Bounding box for the current image
        :type image_bbox: list
        """

        image_bbox = [
            int(image_bbox[0] / slide_information['x_scale']),
            int(image_bbox[3] / slide_information['y_scale']),
            int(image_bbox[2] / slide_information['x_scale']),
            int(image_bbox[1] / slide_information['y_scale'])
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
        slide_image_region = self.get_structure_region(image_bbox, slide_information, False)
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

    def update_structure_options(self, overlay_names, refresh_clicked, current_features, slide_bounds, active_tab):
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
        else:
            raise exceptions.PreventUpdate
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        slide_map_bounds = get_pattern_matching_value(slide_bounds)
        slide_map_box = box(slide_map_bounds[0][1],slide_map_bounds[0][0],slide_map_bounds[1][1],slide_map_bounds[1][0])

        current_features = json.loads(get_pattern_matching_value(current_features))

        structure_options = []
        structure_bboxes = {}
        for g in current_features:
            intersecting_shapes, intersecting_properties = find_intersecting(g,slide_map_box)
            if len(intersecting_shapes['features'])>0:
                structure_options.append(g['properties']['name'])

                structure_bboxes[g['properties']['name']] = [
                    list(shape(f['geometry']).bounds) for f in intersecting_shapes['features']
                ]
                structure_bboxes[f'{g["properties"]["name"]}_index'] = 0

        new_structure_bboxes = json.dumps(structure_bboxes)

        return [structure_options], [new_structure_bboxes]

    def update_structure(self, structure_drop_value, prev_click, next_click, current_structure_data, current_class_value, slide_information):
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
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        if structure_drop_value is None or not structure_drop_value in current_structure_data:
            raise exceptions.PreventUpdate

        if any([i in ctx.triggered_id['type'] for i in ['feature-annotation-structure-drop','feature-annotation-class-new']]):
            # Getting a new structure:
            current_structure_index = current_structure_data[f'{structure_drop_value}_index']
            current_structure_region = current_structure_data[structure_drop_value][current_structure_index]

        elif 'feature-annotation-previous' in ctx.triggered_id['type']:
            # Going to previous structure
            current_structure_index = current_structure_data[f'{structure_drop_value}_index']
            if current_structure_index==0:
                current_structure_index = len(current_structure_data[structure_drop_value])-1
            else:
                current_structure_index -= 1
            
            current_structure_region = current_structure_data[structure_drop_value][current_structure_index]

        elif 'feature-annotation-next' in ctx.triggered_id['type']:
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
        image_region = self.get_structure_region(current_structure_region, slide_information)
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

    def get_structure_region(self, structure_bbox:list, slide_information: dict, scale:bool = True):
        """Using the tile server "regions_url" property to pull out a specific region of tissue

        :param structure_bbox: List of minx, miny, maxx, maxy coordinates
        :type structure_bbox: list
        :param scale: Whether or not to scale the bbox values to slide coordinates
        :type scale: bool
        """

        # Converting structure bbox from map coordinates to slide-pixel coordinates
        if scale:
            slide_coordinates = [
                int(structure_bbox[0]/slide_information['x_scale']), 
                int(structure_bbox[3]/slide_information['y_scale']), 
                int(structure_bbox[2]/slide_information['x_scale']), 
                int(structure_bbox[1]/slide_information['y_scale'])
            ]
        else:
            slide_coordinates = structure_bbox

        #TODO: Update this function for multi-frame images
        image_region = Image.open(
            BytesIO(
                requests.get(
                    slide_information['regions_url']+f'?left={slide_coordinates[0]}&top={slide_coordinates[1]}&right={slide_coordinates[2]}&bottom={slide_coordinates[3]}'
                ).content
            )
        )

        

        return image_region
    
    def add_new_class_label(self, add_class, add_label, new_class, new_label, label_text, current_structure_data, current_structure, slide_information):
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

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        new_class = get_pattern_matching_value(new_class)
        new_label = get_pattern_matching_value(new_label)
        label_text = get_pattern_matching_value(label_text)
        current_structure_data = json.loads(get_pattern_matching_value(current_structure_data))
        current_structure = get_pattern_matching_value(current_structure)
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        # Updating the figure "newshape.line.color" and "newshape.fillcolor" properties
        if 'feature-annotation-class-new' in ctx.triggered_id['type']:
            if not new_class is None:
                figure_update = Patch()
                figure_update['layout']['newshape']['line']['color'] = new_class
                figure_update['layout']['newshape']['fillcolor'] = new_class.replace('(','a(').replace(')',',0.2)')
            else:
                raise exceptions.PreventUpdate
        
        # Adding a label to 
        elif 'feature-annotation-label-submit' in ctx.triggered_id['type']:
            figure_update = no_update

            image_bbox = current_structure_data[current_structure][current_structure_data[f'{current_structure}_index']]

            if not new_label is None:
                # Saving label to running file
                self.save_label(new_label, label_text, image_bbox, slide_information)
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

        if 'feature-annotation-add-class' in ctx.triggered_id['type']:

            if add_class_value == 'Class':
                # Getting the class name input and color picker:
                options_div = html.Div([
                    dcc.Input(
                        type = 'text',
                        maxLength = 1000,
                        id = {'type': f'{self.component_prefix}-feature-annotation-add-class-name','index': 0},
                        placeholder = 'New Class Name',
                        style = {'width': '100%'}
                    ),
                    html.Div(
                        dmc.ColorInput(
                            id = {'type':f'{self.component_prefix}-feature-annotation-add-class-color','index':0},
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
                        id = {'type': f'{self.component_prefix}-feature-annotation-add-label-name','index': 0}
                    )
                ],style = {'width': '100%'})


            add_submit_disabled = False
            new_class_options = no_update
            new_label_options = no_update

            add_class_drop_value = add_class_value

        elif 'feature-annotation-add-submit' in ctx.triggered_id['type']:

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

    def save_annotation(self, save_click, current_annotations, current_classes, current_structure_data, current_structure, slide_information):
        """Saving the current annotation in image format

        :param save_click: Save button is clicked
        :type save_click: list
        :param current_annotations: Current annotations (in SVG path format)
        :type current_annotations: list
        """


        if not any([i['value'] for i in ctx.triggered]) or current_classes is None:
            raise exceptions.PreventUpdate

        current_annotations = get_pattern_matching_value(current_annotations)
        current_classes = get_pattern_matching_value(current_classes)
        current_structure_data = json.loads(get_pattern_matching_value(current_structure_data))
        current_structure = get_pattern_matching_value(current_structure)
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        annotations = []
        if not current_annotations is None:
            if 'shapes' in current_annotations.keys():
                annotations += current_annotations['shapes']

                if 'line' in current_annotations.keys():
                    annotations += current_annotations['line']
            
        image_bbox = current_structure_data[current_structure][current_structure_data[f'{current_structure}_index']]

        # Saving annotation to storage_path
        self.save_mask(annotations, current_classes, image_bbox, slide_information)

        return ['Saved!']

class BulkLabels(Tool):
    """Add labels to many structures at the same time

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data
    :type Tool: None
    """
    def __init__(self,
                 ignore_list: list = [],
                 property_depth: int = 4):
        """Constructor method
        """

        super().__init__()
        self.ignore_list = ignore_list
        self.property_depth = property_depth

        self.assets_folder = os.getcwd()+'/.fusion_assets/'
        self.get_namespace()

    def __str__(self):
        return 'Bulk Labels'

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix
        self.title = 'Bulk Labels'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def get_scale_factors(self, image_metadata: dict):
        """Function used to initialize scaling factors applied to GeoJSON annotations to project annotations into the SlideMap CRS (coordinate reference system)

        :return: x and y (horizontal and vertical) scale factors applied to each coordinate in incoming annotations
        :rtype: float
        """

        base_dims = [
            image_metadata['sizeX']/(2**(image_metadata['levels']-1)),
            image_metadata['sizeY']/(2**(image_metadata['levels']-1))
        ]

        #x_scale = (base_dims[0]*(240/image_metadata['tileHeight'])) / image_metadata['sizeX']
        #y_scale = -((base_dims[1]*(240/image_metadata['tileHeight'])) / image_metadata['sizeY'])

        x_scale = base_dims[0] / image_metadata['sizeX']
        y_scale = -(base_dims[1]) / image_metadata['sizeY']


        return x_scale, y_scale

    def get_namespace(self):
        """Adding JavaScript functions to the BulkLabels Namespace
        """
        self.js_namespace = Namespace(
            "fusionTools","bulkLabels"
        )

        self.js_namespace.add(
            name = 'removeMarker',
            src = """
                function(e,ctx){
                    e.target.removeLayer(e.layer._leaflet_id);
                    ctx.data.features.splice(ctx.data.features.indexOf(e.layer.feature),1);
                }
            """
        )

        self.js_namespace.add(
            name = 'tooltipMarker',
            src = 'function(feature,layer,ctx){layer.bindTooltip("Double-click to remove")}'
        )

        self.js_namespace.add(
            name = "markerRender",
            src = """
                function(feature,latlng,context) {
                    marker = L.marker(latlng, {
                        title: "BulkLabels Marker",
                        alt: "BulkLabels Marker",
                        riseOnHover: true,
                        draggable: false,
                    });

                    return marker;
                }
            """
        )

        self.js_namespace.dump(
            assets_folder = self.assets_folder
        )

    def gen_layout(self, session_data:dict):
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
                    html.Div(
                        dcc.Store(
                            id = {'type': 'bulk-annotation-property-info','index': 0},
                            storage_type='memory',
                            data = json.dumps({})
                        )
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
                                options = [],
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
                        id = {'type': 'bulk-labels-labels-store','index': 0},
                        storage_type = 'memory',
                        data = json.dumps({'labels': [], 'labels_metadata': []})
                    ),
                    dcc.Store(
                        id = {'type': 'bulk-labels-filter-data','index': 0},
                        storage_type = 'memory',
                        data = json.dumps({'Spatial': [], 'Filters': []})
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
                        dbc.Col([
                            html.H5('Step 3: Kind?')
                        ],md = 4),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': 'Inclusive','value': 'in'},
                                    {'label': 'Exclusive', 'value': 'over'},
                                    {'label': 'Unlabeled', 'value': 'un'}
                                ],
                                value = 'in',
                                placeholder = 'Label Method',
                                multi = False,
                                id = {'type': 'bulk-labels-label-method','index': 0}
                            )
                        ],md = 8)
                    ],style={'marginBottom': '10px'}),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'bulk-labels-method-explanation','index': 0},
                            children = [
                                dcc.Markdown('*Inclusive*: Allow multiple labels of the same "type". Use if multiple values are possible for a single structure.')
                            ]
                        )
                    ],style = {'marginBottom':'10px'}),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            html.H5('Step 4: Label!')
                        ])
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
                            ),
                            dbc.Tooltip(
                                'Saves current label to labeling session but does not add label to structure-level data',
                                target = {'type': 'bulk-labels-apply-labels','index': 0}
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
                            dbc.Tooltip(
                                'Downloads both individual labels as well as associated labeling metadata containing rationales for labels.',
                                target = {'type': 'bulk-labels-download-labels','index': 0}
                            ),
                            dcc.Download(
                                id = {'type':'bulk-labels-download-data','index': 0}
                            ),
                            dcc.Download(
                                id = {'type': 'bulk-labels-download-metadata','index': 0}
                            )
                        ])
                    ],style = {'marginTop': '10px'}),
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                'Add Labels to Structures',
                                id = {'type': 'bulk-labels-add-labels-to-structures','index': 0},
                                className = 'd-grid col-12 mx-auto',
                                n_clicks = 0,
                                disabled = True
                            ),
                            dbc.Tooltip(
                                'Adds current labels to structures for use in plotting, filtering, etc.',
                                target = {'type': 'bulk-labels-add-labels-to-structures','index': 0}
                            )
                        ])
                    ],style = {'marginTop': '10px'}),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'bulk-labels-label-stats-div','index': 0},
                                children = []
                            )
                        ])
                    ],style = {'marginTop': '10px'})
                ])
            ])
        ],style = {'maxHeight': '100vh','overflow': 'scroll'})

        self.blueprint.layout = layout

    def get_callbacks(self):
        """Adding callbacks to DashBlueprint object
        """
        
        # Updating for new slide
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-info-store','index': ALL},'data')
            ],
            [
                Output({'type': 'bulk-labels-labels-store','index': ALL},'data'),
                Output({'type': 'bulk-labels-label-stats-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-spatial-query-div','index': ALL},'children'),
                Output({'type': 'bulk-labels-add-property-div','index': ALL},'children')
            ]
        )(self.update_slide)

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
                Output({'type': 'bulk-labels-download-labels','index': ALL},'disabled'),
                Output({'type': 'bulk-labels-add-labels-to-structures','index': ALL},'disabled')
            ],
            [
                State({'type': 'bulk-labels-include-structures','index': ALL},'value'),
                State({'type': 'bulk-labels-filter-data','index': ALL},'data'),
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.update_label_structures)

        # Adding filtering data to a separate store:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-filter-selector','index': ALL},'value'),
                Input({'type': 'bulk-labels-spatial-query-drop','index': ALL},'value'),
                Input({'type': 'bulk-labels-spatial-query-structures','index': ALL},'value'),
                Input({'type': 'bulk-labels-spatial-query-nearest','index': ALL},'value'),
                Input({'type': 'bulk-labels-remove-spatial-query-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-remove-property-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-spatial-query-mod','index': ALL},'value'),
                Input({'type': 'bulk-labels-filter-property-mod','index': ALL},'value')
            ],
            [
                Output({'type': 'bulk-labels-filter-data', 'index': ALL},'data')
            ],
            [
                State({'type': 'bulk-labels-add-property-div','index': ALL},'children'),
                State({'type': 'bulk-labels-spatial-query-div','index':ALL},'children'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.update_filter_data)

        # Adding new property
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-add-property-icon','index': ALL},'n_clicks'),
                Input({'type': 'bulk-labels-remove-property-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'bulk-labels-add-property-div','index': ALL},'children')
            ],
            [
                State({'type': 'map-annotations-info-store','index': ALL},'data')
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
                State({'type': 'map-annotations-info-store','index': ALL},'data')
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
                Output({'type': 'bulk-labels-labels-store','index': ALL},'data'),
                Output({'type': 'bulk-labels-apply-labels','index': ALL},'color'),
                Output({'type': 'bulk-labels-label-stats-div','index': ALL},'children')
            ],
            [
                State({'type': 'bulk-labels-markers','index': ALL},'data'),
                State({'type': 'bulk-labels-labels-store','index': ALL},'data'),
                State({'type': 'bulk-labels-label-type','index': ALL},'value'),
                State({'type': 'bulk-labels-label-text','index': ALL},'value'),
                State({'type': 'bulk-labels-label-rationale','index': ALL},'value'),
                State({'type': 'bulk-labels-label-source','index': ALL},'children'),
                State({'type': 'bulk-labels-label-method','index': ALL},'value'),
                State({'type':'map-slide-information','index':ALL},'data')
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
                Output({'type': 'bulk-labels-spatial-query-structures','index':ALL},'options'),
                Output({'type': 'bulk-labels-apply-labels','index': ALL},'color'),
                Output({'type': 'map-marker-div','index': ALL},'children')
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
                Output({'type': 'bulk-labels-download-data','index': ALL},'data'),
                Output({'type': 'bulk-labels-download-metadata','index': ALL},'data')
            ],
            [
                State({'type': 'bulk-labels-labels-store','index': ALL},'data')
            ]
        )(self.download_data)

        # Updating label method description
        self.blueprint.callback(
            [
                Input({'type':'bulk-labels-label-method','index': ALL},'value')
            ],
            [
                Output({'type': 'bulk-labels-method-explanation','index': ALL},'children')
            ]
        )(self.update_method_explanation)

        # Updating number of markers when one is removed:
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-markers','index': ALL},'n_dblclicks')
            ],
            [
                Output({'type': 'bulk-labels-current-structures','index':ALL},'children')
            ],
            [
                State({'type': 'bulk-labels-markers','index': ALL},'data')
            ]
        )(self.update_structure_count)

        # Adding current labels to structure data
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-add-labels-to-structures','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'map-annotations-store','index': ALL},'data')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'bulk-labels-labels-store','index': ALL},'data')
            ]
        )(self.add_labels_to_structures)

        # Editing current labels by editing the label table
        self.blueprint.callback(
            [
                Input({'type': 'bulk-labels-label-table','index': ALL},'data'),
            ],
            [
                Output({'type': 'bulk-labels-labels-store','index': ALL},'data')
            ],
            [
                State({'type': 'bulk-labels-labels-store','index': ALL},'data'),
            ]
        )(self.update_label_table)

    def update_slide(self, new_annotations_info: list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        new_labels_data = json.dumps({'labels': [], 'labels_metadata': []})
        new_label_stats_div = []
        new_spatial_query_div = []
        new_property_filter_div = []

        return [new_labels_data], [new_label_stats_div], [new_spatial_query_div],[new_property_filter_div]

    def update_method_explanation(self, method):
        """Updating explanation given for the selected label method

        :param method: Name of method selected
        :type method: list
        :return: Description of the labeling method selected
        :rtype: list
        """
        
        method = get_pattern_matching_value(method)
        method_types = {
            'in': '*Inclusive*: Allow multiple labels of the same "type". Use if multiple values are possible for a single structure.',
            'over': '*Exclusive*: Only one "label" for each label "type" is allowed. New labels will overwrite previous labels for the same "type".',
            'un': '*Unlabeled*: Only applies this label to structures without any label assigned to this label "type".'
        }

        if method:
            if method in method_types:
                return [dcc.Markdown(method_types[method])]
            else:
                return [dcc.Markdown('Select a method to get started.')]
        else:
            raise exceptions.PreventUpdate

    def update_spatial_query_definition(self, query_type):
        """Returning the definition for the selected spatial predicate type

        :param query_type: Name of spatial predicate
        :type query_type: str
        :return: Markdown string
        :rtype: dcc.Markdown
        """

        if query_type is None:
            raise exceptions.PreventUpdate
        if not type(query_type)==str:
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
                        id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-nearest','index':ctx.triggered_id['index']}
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
        """Generating a new spatial query selector once the add/remove icons are clicked

        :param add_click: Add spatial query icon selected
        :type add_click: list
        :param remove_click: Delete spatial query icon selected
        :type remove_click: list
        :param structure_names: Names of current overlay structures
        :type structure_names: list
        :return: Spatial query selectors (two dropdown menus and delete icon)
        :rtype: tuple
        """
        
        queries_div = Patch()
        add_click = get_pattern_matching_value(add_click)

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        if 'bulk-labels-spatial-query-icon' in ctx.triggered_id['type']:

            def new_query_div():
                return html.Div([
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': html.Span('AND',style={'color': 'rgb(0,0,255)'}),'value': 'and'},
                                    {'label': html.Span('OR',style={'color': 'rgb(0,255,0)'}),'value': 'or'},
                                    {'label': html.Span('NOT',style={'color': 'rgb(255,0,0)'}),'value': 'not'}
                                ],
                                value = 'and',
                                placeholder='Modifier',
                                id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-mod','index': add_click}
                            )
                        ],md = 2),
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
                                id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-drop','index': add_click}
                            )
                        ],md = 3),
                        dbc.Col([
                            dcc.Dropdown(
                                options = structure_names,
                                value = [],
                                multi = False,
                                placeholder = 'Select structure',
                                id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-structures','index':add_click}
                            )
                        ],md=5),
                        dbc.Col([
                            html.A(
                                html.I(
                                    id = {'type': f'{self.component_prefix}-bulk-labels-remove-spatial-query-icon','index': add_click},
                                    n_clicks = 0,
                                    className = 'bi bi-x-circle-fill fa-2x',
                                    style = {'color': 'rgb(255,0,0)'}
                                )
                            )
                        ], md = 2)
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-bulk-labels-spatial-query-definition','index': add_click},
                        children = []
                    )
                ])

            queries_div.append(new_query_div())

        elif 'bulk-labels-remove-spatial-query-icon' in ctx.triggered_id['type']:

            values_to_remove = []
            for i, val in enumerate(remove_click):
                if val:
                    values_to_remove.insert(0,i)

            for v in values_to_remove:
                del queries_div[v]

        
        return [queries_div]

    def parse_filter_divs(self, add_property_parent: list)->list:
        """Processing parent div object and extracting name and range for each property filter.

        :param add_property_parent: Parent div containing property filters
        :type add_property_parent: list
        :return: List of property filters (dicts with keys: name and range)
        :rtype: list
        """
        processed_filters = []
        if not add_property_parent is None:
            for div in add_property_parent:
                div_children = div['props']['children']
                filter_mod = div_children[0]['props']['children'][0]['props']['children'][0]['props']['value']
                #print(f'filter_mod: {filter_mod}')
                filter_name = div_children[0]['props']['children'][1]['props']['children'][0]['props']['value']
                #print(f'filter_name: {filter_name}')
                if 'props' in div_children[1]['props']['children']:
                    if 'value' in div_children[1]['props']['children']['props']:
                        filter_value = div_children[1]['props']['children']['props']['value']
                    else:
                        filter_value = div_children[1]['props']['children']['props']['children']['props']['value']
                    
                    #print(f'filter_value: {filter_value}')

                    if not any([i is None for i in [filter_mod,filter_name,filter_value]]):
                        processed_filters.append({
                            'mod': filter_mod,
                            'name': filter_name,
                            'range': filter_value
                        })

        return processed_filters

    def parse_spatial_divs(self, spatial_query_parent: list, slide_information:dict)->list:
        """Parsing through parent div containing all spatial queries and returning them in list form

        :param spatial_query_parent: Div containing spatial query child divs
        :type spatial_query_parent: list
        :return: Processed queries with keys "type", "structure", and "distance" (if "nearest" selected)
        :rtype: list
        """
        processed_queries = []
        x_scale = slide_information['x_scale']
        if not spatial_query_parent is None:
            for div in spatial_query_parent:
                div_children = div['props']['children'][0]['props']['children']

                query_mod = div_children[0]['props']['children'][0]['props']['value']
                #print(f'query_mod: {query_mod}')
                query_type = div_children[1]['props']['children'][0]['props']['value']
                #print(f'query_type: {query_type}')
                query_structure = div_children[2]['props']['children'][0]['props']['value']
                
                if not any([i is None for i in [query_mod,query_type,query_structure]]):
                    if not query_type=='nearest':
                        processed_queries.append({
                            'mod': query_mod,
                            'type': query_type,
                            'structure': query_structure
                        })
                    else:
                        distance_div = div['props']['children'][1]['props']['children']
                        if 'value' in distance_div[0]['props']:
                            query_distance = distance_div[0]['props']['value']
                            #print(f'query_distance: {query_distance}')
                            if not any([i is None for i in [query_mod,query_type,query_structure,query_distance]]):
                                try:
                                    processed_queries.append({
                                        'mod': query_mod,
                                        'type': query_type,
                                        'structure': query_structure,
                                        'distance': query_distance*x_scale
                                    })
                                except TypeError:
                                    continue

        return processed_queries

    def update_filter_data(self, property_filter, sp_query_type, sp_query_structure, sp_query_distance, remove_sq, remove_prop, spatial_mod,prop_mod,property_divs: list, spatial_divs: list, slide_information:list):

        property_divs = get_pattern_matching_value(property_divs)
        spatial_divs = get_pattern_matching_value(spatial_divs)

        slide_information = json.loads(get_pattern_matching_value(slide_information))
        processed_prop_filters = self.parse_filter_divs(property_divs)
        processed_spatial_filters = self.parse_spatial_divs(spatial_divs,slide_information)

        new_filter_data = json.dumps({
            "Spatial": processed_spatial_filters,
            "Filters": processed_prop_filters
        })

        return [new_filter_data]

    def update_label_structures(self, update_structures_click:list, include_structures:list, filter_data:list, current_features:list, slide_information:list):
        """Go through current structures and return all those that pass spatial and property filters.

        :param update_structures_click: Button clicked
        :type update_structures_click: list
        :param include_structures: List of structures to include in the final filtered GeoJSON
        :type include_structures: list
        :param filter_properties: List of property filters to apply to current GeoJSON
        :type filter_properties: list
        :param spatial_queries: List of spatial filters to apply to current GeoJSON
        :type spatial_queries: list
        :param current_features: Current structures in slide map
        :type current_features: list
        :return: Markers over structures that pass the spatial and property filters, count of structures, enabled label components
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        include_structures = get_pattern_matching_value(include_structures)
        current_features = json.loads(get_pattern_matching_value(current_features))

        slide_information = json.loads(get_pattern_matching_value(slide_information))

        filter_data = json.loads(get_pattern_matching_value(filter_data))

        filtered_geojson, filtered_ref_list = process_filters_queries(filter_data["Filters"], filter_data["Spatial"], include_structures, current_features)

        new_structures_div = [
            dbc.Alert(
                f'{len(filtered_geojson["features"])} Structures Included!',
                color = 'success' if len(filtered_geojson['features'])>0 else 'danger'
            )
        ]
        
        new_markers_div = [
            dl.GeoJSON(
                data = {
                    'type': 'FeatureCollection',
                    'features': [
                        {
                            'type': 'Feature',
                            'geometry': {
                                'type': 'Point',
                                'coordinates': [
                                    (f['bbox'][0]+f['bbox'][2])/2,
                                    (f['bbox'][1]+f['bbox'][3])/2
                                ]
                            },
                            'properties': f_data | {'_id': f['properties']['_id']}
                        }
                        for f,f_data in zip(filtered_geojson['features'],filtered_ref_list)
                    ]
                },
                pointToLayer=self.js_namespace("markerRender"),
                onEachFeature = self.js_namespace("tooltipMarker"),
                id = {'type': f'{self.component_prefix}-bulk-labels-markers','index': 0},
                eventHandlers = {
                    'dblclick': self.js_namespace('removeMarker')
                }
            )
        ]

        new_labels_source = f'`{json.dumps({"Spatial": filter_data["Spatial"],"Filters": filter_data["Filters"]})}`'

        if len(filtered_geojson['features'])>0:
            labels_type_disabled = False
            labels_text_disabled = False
            labels_rationale_disabled = False
            labels_apply_button_disabled = False
            labels_download_button_disabled = False
            labels_add_to_structures_button_disabled = False
        else:
            labels_type_disabled = True
            labels_text_disabled = True
            labels_rationale_disabled = True
            labels_apply_button_disabled = True
            labels_download_button_disabled = True
            labels_add_to_structures_button_disabled = True


        return [new_structures_div], [new_markers_div], [new_labels_source], [labels_type_disabled], [labels_text_disabled], [labels_rationale_disabled], [labels_apply_button_disabled], [labels_download_button_disabled], [labels_add_to_structures_button_disabled]

    def update_label_properties(self, add_click:list, remove_click:list, annotations_info:list):
        """Adding/removing property filter dropdown

        :param add_click: Add property filter clicked
        :type add_click: list
        :param remove_click: Remove property filter clicked
        :type remove_click: list
        :return: Property filter dropdown and parent div of range selector
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        properties_div = Patch()
        add_click = get_pattern_matching_value(add_click)
        property_info = json.loads(get_pattern_matching_value(annotations_info))['property_info']

        if 'bulk-labels-add-property-icon' in ctx.triggered_id['type']:

            def new_property_div():
                return html.Div([
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': html.Span('AND',style={'color':'rgb(0,0,255)'}),'value': 'and'},
                                    {'label': html.Span('OR',style={'color': 'rgb(0,255,0)'}),'value': 'or'},
                                    {'label': html.Span('NOT',style={'color':'rgb(255,0,0)'}),'value': 'not'}
                                ],
                                value = 'and',
                                placeholder='Modifier',
                                id = {'type': f'{self.component_prefix}-bulk-labels-filter-property-mod','index': add_click}
                            )
                        ],md=2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = list(property_info.keys()),
                                value = [],
                                multi = False,
                                placeholder = 'Select property',
                                id = {'type': f'{self.component_prefix}-bulk-labels-filter-property-drop','index':add_click}
                            )
                        ],md=8),
                        dbc.Col([
                            html.A(
                                html.I(
                                    id = {'type': f'{self.component_prefix}-bulk-labels-remove-property-icon','index': add_click},
                                    n_clicks = 0,
                                    className = 'bi bi-x-circle-fill fa-2x',
                                    style = {'color': 'rgb(255,0,0)'}
                                )
                            )
                        ], md = 2)
                    ]),
                    html.Div(
                        id = {'type': f'{self.component_prefix}-bulk-labels-property-selector-div','index': add_click},
                        children = []
                    )
                ])

            properties_div.append(new_property_div())

        elif 'bulk-labels-remove-property-icon' in ctx.triggered_id['type']:

            values_to_remove = []
            for i, val in enumerate(remove_click):
                if val:
                    values_to_remove.insert(0,i)

            for v in values_to_remove:
                del properties_div[v]

        
        return [properties_div]

    def update_property_selector(self, property_value:str, annotations_info:list):
        """Updating property filter range selector

        :param property_value: Name of property to generate selector for
        :type property_value: str
        :param property_info: Dictionary containing range/unique values for each property
        :type property_info: list
        :return: Either a multi-dropdown for categorical properties or a RangeSlider for quantitative values
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        property_info = json.loads(get_pattern_matching_value(annotations_info))['property_info']
        property_values = property_info[property_value]

        if 'min' in property_values:
            # Used for numeric type filters
            values_selector = html.Div(
                dcc.RangeSlider(
                    id = {'type':f'{self.component_prefix}-bulk-labels-filter-selector','index': ctx.triggered_id['index']},
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
                    id = {'type': f'{self.component_prefix}-bulk-labels-filter-selector','index': ctx.triggered_id['index']},
                    options = property_values['unique'],
                    value = property_values['unique'] if len(property_values['unique'])<10 else [],
                    multi = True
                )
            )

        return values_selector 

    def search_labels(self, marker_features, current_labels, label_type, label_text, label_method):
        """Checking current labels and adding the new label based on label_method (inclusive, exclusive, or unlabeled).

        :param marker_features: GeoJSON Features for new markers
        :type marker_features: list
        :param current_labels: List of all current labels (dicts with keys: centroid, labels)
        :type current_labels: list
        :param label_type: String corresponding to the type for the new label
        :type label_type: str
        :param label_text: String corresponding to the new label to apply to each centroid
        :type label_text: str
        :param label_method: One of: in (inclusive, append new label to current regardless of type), over (exclusive, replace existing labels of same type), or un (unlabeled, only apply label to structures that do not have a label for this type)
        :type label_method: str
        :return: Updated set of labels, including original set
        :rtype: dict
        """
        if 'labels' in current_labels:
            current_centroids = [i['centroid'] for i in current_labels['labels']]
        else:
            current_labels['labels'] = []
            current_centroids = []

        for m_idx, m in enumerate(marker_features):
            m_centroid = list(m['geometry']['coordinates'])
            m_id = m['properties']['_id']
            if m_centroid in current_centroids:
                cent_idx = current_centroids.index(m_centroid)
                if label_method=='in':
                    # Adding inclusive label to current set of labels 
                    current_labels['labels'][cent_idx]['labels'].append(
                        {
                            'type': label_type,
                            'value': label_text
                        }
                    )
                elif label_method=='over':
                    if any([label_type==i['type'] for i in current_labels['labels'][cent_idx]['labels']]):
                        # Overruling label previously assigned for this "type"
                        current_labels['labels'][cent_idx]['labels'] = [i if not i['type']==label_type else {'type': label_type,'value': label_text} for i in current_labels['labels'][cent_idx]['labels']]
                    
                    else:
                        # Not previously labeled, nothing to overrule
                        current_labels['labels'][cent_idx]['labels'].append(
                            {
                                'type': label_type,
                                'value': label_text
                            }
                        )
                elif label_method=='un':
                    if not any([label_type==i['type'] for i in current_labels['labels'][cent_idx]['labels']]):
                        # Only adding this label if no other label of this "type" is added
                        current_labels['labels'][cent_idx]['labels'].append(
                            {
                                'type': label_type,
                                'value': label_text
                            }
                        )

            else:
                current_labels['labels'].append(
                    {
                        'centroid': m_centroid,
                        '_id': m_id,
                        'labels': [{
                            'type': label_type,
                            'value': label_text
                        }]
                    }
                )

        return current_labels

    def apply_labels(self, button_click, current_markers, current_data, label_type, label_text, label_rationale, label_source, label_method, slide_information):
        """Applying current label to marked structures

        :param button_click: Button clicked
        :type button_click: list
        :param current_markers: Current markers on the slide-map
        :type current_markers: list
        :param current_data: Current labels data
        :type current_data: list
        :param label_type: Type of label being added
        :type label_type: list
        :param label_text: Label being added to structures
        :type label_text: list
        :param label_rationale: Optional additional rationale to save with label decision
        :type label_rationale: list
        :param label_source: Property and spatial filters incorporated to generate markers
        :type label_source: list
        :param label_method: Method used to apply labels to structures
        :type label_method: list
        :param current_annotations: Current GeoJSON annotations on the slide map
        :type current_annotations: list
        :return: Updated labels data and annotations with label added as a property
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        label_type = get_pattern_matching_value(label_type)
        label_text = get_pattern_matching_value(label_text)
        label_method = get_pattern_matching_value(label_method)

        if label_text is None or label_type is None:
            raise exceptions.PreventUpdate

        label_rationale = get_pattern_matching_value(label_rationale)
        label_source = json.loads(get_pattern_matching_value(label_source).replace('`',''))
        current_data = json.loads(get_pattern_matching_value(current_data))
        current_markers = get_pattern_matching_value(current_markers)
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        scaled_markers = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),current_markers)
        
        labeled_items = self.search_labels(scaled_markers['features'], current_data, label_type, label_text, label_method)

        if 'labels' in current_data and 'labels_metadata' in current_data:
            current_data['labels'] = labeled_items['labels']
            current_data['labels_metadata'].append(
                {
                    'type': label_type,
                    'label': label_text,
                    'rationale': label_rationale,
                    'source': label_source
                }
            )
        else:
            current_data['labels'] = labeled_items['labels']
            current_data['labels_metadata'] = [
                {
                    'type': label_type,
                    'label': label_text,
                    'rationale': label_rationale,
                    'source': label_source
                }
            ]

        new_data = json.dumps(current_data)

        # Creating a table for count of unique labels:
        labels = []
        for l in labeled_items['labels']:
            for m in l['labels']:
                # Accounting for multiple values for the same "type"
                l_dict = {
                    'Label Type': m['type'],
                    'Value': m['value']
                }

                labels.append(l_dict)

        label_count_df = pd.DataFrame.from_records(labels).groupby(by='Label Type')
        label_counts = label_count_df.value_counts(['Value']).to_frame()
        label_counts.reset_index(inplace=True)
        label_counts.columns = ['Label Type','Label Value','Count']

        label_count_table = dash_table.DataTable(
            columns = [{'name':i,'id':i,'selectable':True} for i in label_counts],
            data = label_counts.to_dict('records'),
            editable=True,   
            row_deletable=True,                                     
            sort_mode='multi',
            sort_action = 'native',
            page_current=0,
            page_size=5,
            style_cell = {
                'overflow':'hidden',
                'textOverflow':'ellipsis',
                'maxWidth':0
            },
            tooltip_data = [
                {
                    column: {'value':str(value),'type':'markdown'}
                    for column, value in row.items()
                } for row in label_counts.to_dict('records')
            ],
            tooltip_duration = None,
            id = {'type': f'{self.component_prefix}-bulk-labels-label-table','index':0}
        )

        return [new_data], ['success'], [label_count_table]

    def refresh_labels(self, refresh_click, structure_options):
        """Clear current label components and start over

        :param refresh_click: Refresh icon clicked
        :type refresh_click: list
        :param structure_options: Names of current overlay layers
        :type structure_options: list
        :return: Cleared labeling components
        :rtype: tuple
        """
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
            apply_style = 'primary'
            markers = []

            include_options = [{'label': i, 'value': i} for i in structure_options]
            if len(ctx.outputs_list[13])>0:
                spatial_queries_structures = [include_options for i in range(len(ctx.outputs_list[13]))]        
            else:
                spatial_queries_structures = []

            return [include_structures], [spatial_queries], [add_property], [current_structures],[label_type],[type_disable],[label_text], [text_disable], [label_rationale], [rationale_disable], [label_source], [apply_disable], [include_options], spatial_queries_structures, [apply_style], [markers]
        else:
            raise exceptions.PreventUpdate

    def download_data(self, button_click, label_data):
        """Download both the labels applied to the current session as well as the labeling metadata

        :param button_click: Download button clicked
        :type button_click: list
        :param label_data: Current label data and metadata
        :type label_data: list
        :return: Data sent to the two download components in the layout containing JSON formatted label data and metadata
        :rtype: tuple
        """
        if button_click:
            label_data = json.loads(get_pattern_matching_value(label_data))

            return [{'content': json.dumps(label_data['labels']),'filename': 'label_data.json'}], [{'content': json.dumps(label_data['labels_metadata']), 'filename': 'label_metadata.json'}]
        else:
            raise exceptions.PreventUpdate

    def update_structure_count(self, marker_dblclicked,marker_geo):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        marker_geo = get_pattern_matching_value(marker_geo)
        new_structure_count_children = [
            dbc.Alert(
                f'{len(marker_geo["features"])} Structures Included!',
                color = 'success' if len(marker_geo["features"])>0 else 'danger'
            )
        ]

        return new_structure_count_children
    
    def add_labels_to_structures(self, button_click, current_annotations, current_labels):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_annotations = json.loads(get_pattern_matching_value(current_annotations))
        current_labels = json.loads(get_pattern_matching_value(current_labels))

        label_ids = [i['_id'] for i in current_labels['labels']]
        for c in current_annotations:
            feature_ids = [i['properties']['_id'] for i in c['features']]
            id_intersect = list(set(label_ids) & set(feature_ids))
            if len(id_intersect)>0:
                for id in id_intersect:
                    feature_label = current_labels['labels'][label_ids.index(id)]
                    c['features'][feature_ids.index(id)]['properties'] = c['features'][feature_ids.index(id)]['properties'] | feature_label

        updated_annotations = json.dumps(current_annotations)

        return [updated_annotations]

    def update_label_table(self, table_data, current_labels):
        
        table_data = get_pattern_matching_value(table_data)
        current_labels = json.loads(get_pattern_matching_value(current_labels))
        if not table_data is None:
            included_label_types = sorted(list(set([i['Label Type'] for i in table_data])))
            current_label_types = sorted(list(set([i['type'] for i in current_labels['labels_metadata']])))
            
            included_label_values = []
            current_label_values = []
            for t in included_label_types:
                included_label_values.extend(sorted([i['Label Value'] for i in table_data if i['Label Type']==t]))
                current_label_values.extend(sorted([i['label'] for i in current_labels['labels_metadata'] if i['type']==t]))

            # Removing not-included label from labels and label metadata
            if not included_label_types==current_label_types or not included_label_values==current_label_values:
                # If the len of included_label_types does not equal the len of current_label_types then there has been a type deletion
                deletion = False
                replation = False
                if not len(included_label_types)==len(current_label_types):
                    # This would be a deletion of one label type/value
                    #print(f'type deletion: {included_label_types}, {current_label_types}')
                    deletion = True
                    replation = False
                else:
                    # If the len of the types are the same length then check if they contain the same values:
                    if not included_label_types==current_label_types:
                        # This is a type replation
                        #print(f'type replation: {included_label_types}, {current_label_types}')
                        deletion = False
                        replation = {'type': [i for i in included_label_types if not i in current_label_types][0]}

                    else:
                        # In this case there is most likely a value replation
                        if not included_label_values==current_label_values and len(included_label_values)==len(current_label_values):
                            #print(f'value replation: {included_label_values}, {current_label_values}')
                            deletion = False
                            replation = {'value': [i for i in included_label_values if not i in current_label_values][0]}
                        elif not len(included_label_values)==len(current_label_values):
                            # This is a deletion
                            deletion = True
                            replation = False

                for l_idx,l in enumerate(current_labels['labels']):
                    for l_m_idx,l_m in enumerate(l['labels']):
                        if not l_m['type'] in included_label_types:
                            if deletion:
                                del current_labels['labels'][l_idx]['labels'][l_m_idx]
                            elif replation:
                                current_labels['labels'][l_idx]['labels'][l_m_idx]['type'] = replation['type']
                        else:
                            if not l_m['value'] in included_label_values:
                                if deletion:
                                    del current_labels['labels'][l_idx]['labels'][l_m_idx]
                                elif replation:
                                    current_labels['labels'][l_idx]['labels'][l_m_idx]['value'] = replation['value']

                    if len(l['labels'])==0:
                        del current_labels['labels'][l_idx]
                
                if deletion:
                    current_labels['labels_metadata'] = [i for i in current_labels['labels_metadata'] if i['label'] in included_label_values and i['type'] in included_label_types]
                elif replation:
                    if 'type' in replation:
                        current_labels['labels_metadata'] = [i if i['type'] in included_label_types else i | replation for i in current_labels['labels_metadata']]
                    elif 'value' in replation:
                        current_labels['labels_metadata'] = [i if i['label'] in included_label_values else i | {'label': replation['value']} for i in current_labels['labels_metadata']]
                
                updated_labels = json.dumps(current_labels)
            else:
                raise exceptions.PreventUpdate
        else:
            updated_labels = json.dumps({})

        return [updated_labels]







