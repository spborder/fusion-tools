"""

Components used for high-resolution image viewing


"""

import os
import sys
import pandas as pd
import numpy as np
import uuid
from typing_extensions import Union
import geojson
import json
import base64
import requests
from PIL import Image
import lxml.etree as ET
from copy import deepcopy

#os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, dash_table, Patch, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, MultiplexerTransform, PrefixIdTransform
from dash_extensions.javascript import assign, arrow_function, Namespace

# fusion-tools imports
from fusion_tools import MapComponent
from fusion_tools.utils.shapes import (
    find_intersecting,
    spatially_aggregate,
    histomics_to_geojson,
    detect_image_overlay,
    aperio_to_geojson,
    extract_geojson_properties
)
from fusion_tools.visualization.vis_utils import get_pattern_matching_value




class SlideMap(MapComponent):
    """This is a general high-resolution tiled image component. 
    

    :param MapComponent: General class for components added to SlideMap
    :type MapComponent: None
    """
    def __init__(self):
        """Constructor method
        """
        super().__init__()

        # Add Namespace functions here:
        self.assets_folder = os.getcwd()+'/.fusion_assets/'
        self.get_namespace()
    
    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Slide Map'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix=f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )        

        # Add callback functions here
        self.get_callbacks()
        self.get_annotations_callbacks()

    def __str__(self):
        return 'Slide Map'

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
        y_scale = -((base_dims[1]) / image_metadata['sizeY'])

        return x_scale, y_scale

    def get_image_overlay_popup(self, st, st_idx):
        """Getting popup components for image overlay annotations

        :param st: New ImageOverlay annotation
        :type st: SlideImageOverlay
        :param st_idx: Index to use for interactive components
        :type st_idx: int
        """

        image_overlay_popup = dl.Popup(
                                dbc.Accordion(
                                    children = [
                                        dbc.AccordionItem(
                                            title = 'Info',
                                            children = [
                                                html.P(f'Path: {st["image_path"]}'),
                                            ]
                                        ),
                                        dbc.AccordionItem(
                                            title = 'Properties',
                                            children = [
                                                f'{k}: {v}'
                                                for k,v in st['image_properties'].items()
                                            ]
                                        ),
                                        dbc.AccordionItem(
                                            title = 'Transparency',
                                            children = [
                                                dbc.Label(
                                                    'Transparency Slider:',
                                                    html_for = {'type': f'{self.component_prefix}-image-overlay-transparency','index': st_idx},
                                                    style = {'marginBottom': '5px'}
                                                ),
                                                dcc.Slider(
                                                    id = {'type': f'{self.component_prefix}-image-overlay-transparency','index': st_idx},
                                                    min = 0,
                                                    max = 1.0,
                                                    step = 0.1,
                                                    value = 0.5,
                                                    marks = None,
                                                    tooltip = {
                                                        'always_visible': True,
                                                        'placement': 'bottom'
                                                    }
                                                )
                                            ]
                                        ),
                                        dbc.AccordionItem(
                                            title = 'Position',
                                            children = [
                                                dbc.Row([
                                                    dbc.Col(
                                                        dbc.Button(
                                                            'Move it!',
                                                            id = {'type': f'{self.component_prefix}-image-overlay-position-butt','index': st_idx},
                                                            n_clicks = 0,
                                                            className = 'd-grid col-12 mx-auto'
                                                        )
                                                    )
                                                ]),
                                                dbc.Row([
                                                    dbc.Col([
                                                        dbc.Button(
                                                            'Save Position',
                                                            id = {'type': f'{self.component_prefix}-image-overlay-save-position','index': st_idx},
                                                            n_clicks = 0,
                                                            className = 'd-grid col-12 mx-auto',
                                                            color = 'secondary'
                                                        ),
                                                        dcc.Download(
                                                            id = {'type': f'{self.component_prefix}-image-overlay-save-position-download','index': st_idx}
                                                        )
                                                    ])
                                                ])
                                            ]
                                        )
                                    ],
                                    style = {'width':'300px'}
                                ),
                                autoPan = False
                            )

        return image_overlay_popup

    def update_layout(self, session_data:dict, use_prefix: bool):
        """Generating SlideMap layout

        :return: Div object containing interactive components for the SlideMap object.
        :rtype: dash.html.Div.Div
        """

        layout = html.Div([
            dcc.Dropdown(
                id = {'type': 'slide-select-drop','index': 0},
                placeholder = 'Select a slide to view',
                options = [
                    {'label': i['name'],'value': idx}
                    for idx,i in enumerate(session_data['current'])
                ],
                value = [],
                multi = False,
                style = {'marginBottom': '10px'}
            ),
            html.Div(
                dcc.Store(
                    id = {'type': 'map-slide-information','index': 0},
                    storage_type='memory',
                    data = json.dumps({})
                )
            ),
            html.Hr(),
            dl.Map(
                id = {'type': 'slide-map','index': 0},
                crs = 'Simple',
                center = [-120,120],
                eventHandlers = {
                    'dblclick': self.js_namespace('sendPosition')
                },
                zoom = 0,
                zoomDelta = 0.25,
                style = {'height': '90vh','width': '100%','margin': 'auto','display': 'inline-block'},
                children = [
                    html.Div(
                        id = {'type': 'map-tile-layer-holder','index': 0},
                        children = [
                            dl.TileLayer(
                                id = {'type': 'map-tile-layer','index': 0},
                                url = '',
                                tileSize=240,
                                maxNativeZoom=5,
                                minZoom = -1
                            )
                        ]
                    ),
                    dl.FullScreenControl(
                        position = 'upper-left'
                    ),
                    dl.FeatureGroup(
                        id = {'type': 'edit-feature-group','index': 0},
                        children = [
                            dl.EditControl(
                                id = {'type': 'edit-control','index': 0},
                                draw = dict(
                                    polyline=False, 
                                    line=False, 
                                    circle = False, 
                                    circlemarker=False,
                                    marker=False
                                ),
                                edit = dict(edit=False),
                                position='topleft',
                            )
                        ]
                    ),
                    html.Div(
                        id = {'type': 'map-colorbar-div','index': 0},
                        children = []
                    ),
                    html.Div([
                        dcc.Store(
                            id = {'type': 'map-annotations-store','index': 0},
                            data = json.dumps({}),
                            storage_type = 'memory'
                        ),
                        dcc.Store(
                            id = {'type': 'map-annotations-info-store','index': 0},
                            data = json.dumps({}),
                            storage_type = 'memory'
                        )
                    ]),
                    dl.LayersControl(
                        id = {'type': 'map-layers-control','index': 0},
                        children = [
                            html.Div(
                                id = {'type': 'map-initial-annotations','index': 0},
                                children = []
                            ),
                            html.Div(
                                id = {'type': 'map-manual-rois','index': 0},
                                children = []
                            ),
                            html.Div(
                                id = {'type': 'map-generated-rois','index': 0},
                                children = []
                            )
                        ]
                    ),
                    dl.EasyButton(
                        icon = 'fa-solid fa-arrows-to-dot',
                        title = 'Re-Center Map',
                        id = {'type': 'center-map','index': 0},
                        position = 'top-left',
                        eventHandlers = {
                            'click': self.js_namespace('centerMap')
                        }
                    ),
                    dl.EasyButton(
                        icon = 'fa-solid fa-upload',
                        title = 'Upload Shapes',
                        id = {'type': 'upload-shape','index': 0},
                        position = 'top-left'
                    ),
                    html.Div(
                        id = {'type': 'map-marker-div','index': 0},
                        children = []
                    ),
                ]
            ),
            dbc.Modal(
                id = {'type': 'upload-shape-modal','index': 0},
                is_open = False,
                children = [
                    html.Div(
                        dcc.Upload(
                            children = [
                                'Drag and Drop or ',
                                html.A('Select a File')
                            ], 
                            id = {'type': 'upload-shape-data','index': 0},
                            style={'width': '100%','height': '60px','lineHeight': '60px','borderWidth': '1px','borderStyle': 'dashed','borderRadius': '5px','textAlign': 'center'}
                        )
                    )
                ]
            ),
            dbc.Modal(
                id = {'type': 'load-annotations-modal','index': 0},
                is_open = False,
                children = []
            ),
            html.Div(
                id = {'type': 'map-slide-metadata-div','index': 0},
                children = []
            ),
        ])

        if use_prefix:
            PrefixIdTransform(prefix = self.component_prefix).transform_layout(layout)

        return layout
    
    def gen_layout(self, session_data:dict):

        self.blueprint.layout = self.update_layout(session_data,use_prefix=False)

    def get_namespace(self):
        """Adding JavaScript functions to the SlideMap Namespace

        These functions are automatically written to .fusion_assets/fusionTools_default.js where they are accessible
        to select interactive components in SlideMap.

        For more information on adding JS functions to a Dash application, see:

        https://www.dash-extensions.com/sections/javascript
        and 
        https://www.dash-leaflet.com/docs/geojson_tutorial
        
        """
        self.js_namespace = Namespace(
            "fusionTools","slideMap"
        )

        self.js_namespace.add(
            src = 'function(e,ctx){ctx.map.flyTo([-120,120],1);}',
            name = "centerMap"
        )

        self.js_namespace.add(
            src = """
                function(feature,context){
                var {overlayBounds, overlayProp, fillOpacity, lineColor, filterVals, lineWidth, colorMap} = context.hideout;
                var style = {};
                if (Object.keys(chroma.brewer).includes(colorMap)){
                    colorMap = colorMap;
                } else {
                    colorMap = colorMap.split("->");
                }

                if ("min" in overlayBounds) {
                    var csc = chroma.scale(colorMap).domain([overlayBounds.min,overlayBounds.max]);
                } else if ("unique" in overlayBounds) {
                    var class_indices = overlayBounds.unique.map(str => overlayBounds.unique.indexOf(str));
                    var csc = chroma.scale(colorMap).colors(class_indices.length);
                } else {
                    style.fillColor = 'white';
                    style.fillOpacity = fillOpacity;
                    if ('name' in feature.properties) {
                        style.color = lineColor[feature.properties.name];
                    } else {
                        style.color = 'white';
                    }

                    return style;
                }

                var overlayVal = Number.Nan;
                if (overlayProp) {
                    if (overlayProp.name) {
                        //TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                        var overlaySubProps = overlayProp.name.split(" --> ");
                        var prop_dict = feature.properties;
                        for (let i = 0; i < overlaySubProps.length; i++) {
                            if (prop_dict==prop_dict && prop_dict!=null && typeof prop_dict === 'object') {
                                if (overlaySubProps[i] in prop_dict) {
                                    var prop_dict = prop_dict[overlaySubProps[i]];
                                    var overlayVal = prop_dict;
                                } else {
                                    prop_dict = Number.Nan;
                                    var overlayVal = Number.Nan;
                                }
                            }
                        }
                    } else {
                        var overlayVal = Number.Nan;
                    }
                } else {
                    var overlayVal = Number.Nan;
                }

                if (overlayVal==overlayVal && overlayVal!=null) {
                    if (typeof overlayVal==='number') {
                        style.fillColor = csc(overlayVal);
                    } else if ('unique' in overlayBounds) {
                        overlayVal = overlayBounds.unique.indexOf(overlayVal);
                        style.fillColor = csc[overlayVal];
                    } else {
                        style.fillColor = "f00";
                    }
                } else {
                    style.fillColor = "f00";
                }

                style.fillOpacity = fillOpacity;
                if (feature.properties.name in lineColor) {
                    style.color = lineColor[feature.properties.name];
                } else {
                    style.color = 'white';
                }

                return style;
                }
                """,
            name = 'featureStyle'
        )

        self.js_namespace.add(
            src = """
                function(feature,context){
                const {overlayBounds, overlayProp, fillOpacity, lineColor, filterVals, lineWidth, colorMap} = context.hideout;

                var returnFeature = true;
                if (filterVals) {
                    for (let i = 0; i < filterVals.length; i++) {
                        // Iterating through filterVals list
                        var filter = filterVals[i];
                        if (filter.name) {
                            //TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                            var filterSubProps = filter.name.split(" --> ");
                            var prop_dict = feature.properties;
                            for (let j = 0; j < filterSubProps.length; j++) {
                                if (prop_dict==prop_dict && prop_dict!=null && typeof prop_dict==='object') {
                                    if (filterSubProps[j] in prop_dict) {
                                        var prop_dict = prop_dict[filterSubProps[j]];
                                        var testVal = prop_dict;
                                    } else {
                                        prop_dict = Number.Nan;
                                        returnFeature = returnFeature & false;
                                    }
                                }
                            }
                        }
                            
                        if (filter.range && returnFeature) {
                            if (typeof filter.range[0]==='number') {
                                if (testVal < filter.range[0]) {
                                    returnFeature = returnFeature & false;
                                }
                                if (testVal > filter.range[1]) {
                                    returnFeature = returnFeature & false;
                                }
                            } else {
                                if (filter.range.includes(testVal)) {
                                    returnFeature = returnFeature & true;
                                } else {
                                    returnFeature = returnFeature & false;
                                }
                            }
                        }
                    }
                }  else {
                    return returnFeature;
                }              
                return returnFeature;
                }
                """,
            name = 'featureFilter'
        )

        self.js_namespace.add(
            src = """
            function(e,ctx){
                ctx.setProps({
                    data: e.latlng,
                });
            }
            """,
            name = 'sendPosition'
        )

        self.js_namespace.dump(
            assets_folder = self.assets_folder
        )

    def get_callbacks(self):
        """Initializing callback functions for interactive components in SlideMap. 
        Adding these callbacks to the DashBlueprint() object enable embedding into other layouts.
        """
        
        # Updating based on modifications to current visualization session
        self.blueprint.callback(
            [
                Input('anchor-vis-store','data')
            ],
            [
                Output({'type':'slide-select-drop','index': ALL},'options')
            ]
        )(self.update_vis_session)

        # Updating current slide and annotations
        self.blueprint.callback(
            [
                Input({'type': 'slide-select-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'map-initial-annotations','index': MATCH},'children'),
                Output({'type': 'edit-control','index': MATCH},'editToolbar'),
                Output({'type': 'map-manual-rois','index': MATCH},'children'),
                Output({'type': 'map-generated-rois','index': MATCH},'children'),
                Output({'type': 'map-tile-layer-holder','index': MATCH},'children'),
                Output({'type': 'map-slide-information','index': MATCH},'data'),
                Output({'type': 'map-slide-metadata-div','index': MATCH},'children'),
            ],
            [
                State('anchor-vis-store','data')
            ]
        )(self.update_slide)

        # Extracting properties from loaded GeoJSONs
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-store','index': ALL},'data')
            ],
            [
                Output({'type': 'map-annotations-info-store','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.update_ann_info)

        # Getting popup info for clicked feature
        self.blueprint.callback(
            [
                Input({'type':'feature-bounds','index': MATCH},'clickData')
            ],
            [
                Output({'type': 'feature-popup','index': MATCH},'children')
            ]
        )(self.get_click_popup)

        # Drawing manual ROIs and spatially aggregating underlying info
        self.blueprint.callback(
            [
                Input({'type':'edit-control','index': ALL},'geojson'),
                Input({'type':'upload-shape-data','index': ALL},'contents')
            ],
            [
                Output({'type': 'map-manual-rois','index': ALL},'children'),
                Output({'type': 'map-annotations-store','index': ALL},'data'),
                Output('anchor-vis-store','data')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'base-layer','index': ALL},'children'),
                State({'type': 'feature-lineColor','index': ALL},'value'),
                State({'type': 'adv-overlay-colormap','index': ALL},'value'),
                State({'type': 'manual-roi-separate-switch','index': ALL},'checked'),
                State({'type': 'manual-roi-summarize-switch','index': ALL},'checked'),
                State({'type': 'map-slide-information','index': ALL},'data'),
                State('anchor-vis-store','data')
            ]
        )(self.add_manual_roi)

        # Image overlay transparency adjustment
        self.blueprint.callback(
            [
                Input({'type': 'image-overlay-transparency','index': ALL},'value')
            ],
            [
                Output({'type': 'image-overlay','index': MATCH},'opacity')
            ]
        )(self.update_image_overlay_transparency)

        # Creating a draggable marker to move an image overlay
        self.blueprint.callback(
            [
                Input({'type':'image-overlay-position-butt','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'image-overlay-mover-layergroup','index': MATCH},'children'),
                Output({'type': 'image-overlay-position-butt','index': MATCH},'children')
            ],
            [
                State({'type': 'image-overlay','index': ALL},'bounds'),
                State({'type': 'image-overlay-position-butt','index': ALL},'children')
            ]
        )(self.gen_image_mover)

        # Moving image overlay to location of draggable marker
        self.blueprint.callback(
            [
                Input({'type': 'image-overlay-mover','index': ALL},'data')
            ],
            [
                Output({'type': 'image-overlay','index': MATCH},'bounds')
            ],
            [
                State({'type': 'image-overlay','index': ALL},'bounds')
            ]
        )(self.move_image_overlay)

        # Downloading position of image overlay
        self.blueprint.callback(
            [
                Input({'type': 'image-overlay-save-position','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'image-overlay-save-position-download','index': MATCH},'data')
            ],
            [
                State({'type': 'image-overlay','index': ALL},'bounds'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.export_image_overlay_bounds)

        # Downloading manual ROI
        self.blueprint.callback(
            [
                Input({'type': 'download-manual-roi','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'download-manual-roi-download','index': MATCH},'data')
            ],
            [
                State({'type': 'edit-control','index': ALL},'geojson'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ]
        )(self.download_manual_roi)

        # Open upload modal
        self.blueprint.callback(
            [
                Input({'type': 'upload-shape','index': ALL},'n_clicks'),
            ],
            [
                Output({'type': 'upload-shape-modal','index': MATCH},'is_open'),
            ],
            [
                State({'type': 'upload-shape-modal','index': ALL},'is_open')
            ]
        )(self.upload_shape)

    def get_annotations_callbacks(self):

        self.blueprint.clientside_callback(
            """
            async function(slide_information){
                // Prevent update at initialization
                if (slide_information[0]==undefined){
                    throw window.dash_clientside.PreventUpdate;
                };

                // Getting component prefix for the triggered id
                var component_prefix = window.dash_clientside.callback_context.triggered_id.type.split('-')[0];

                // Reading in map-slide-information
                var map_slide_information = JSON.parse(slide_information);

                function uuidv4() {
                    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'
                    .replace(/[xy]/g, function (c) {
                        const r = Math.random() * 16 | 0, 
                            v = c == 'x' ? r : (r & 0x3 | 0x8);
                        return v.toString(16);
                    });
                };

                // Annotations have to be in GeoJSON format already in order to use this
                function process_json(json_data, idx, ann_meta){
                    if (json_data.constructor.name == 'Object'){
                        return scale_geoJSON(json_data, ann_meta[idx].name, ann_meta[idx]["_id"],map_slide_information.x_scale, map_slide_information.y_scale);
                    } else {
                        let scaled_list = [];
                        for (let j=0; j<json_data.length; j++){
                            scaled_list.push(scale_geoJSON(json_data[j], ann_meta[idx+j].name, ann_meta[idx+j]["_id"], map_slide_information.x_scale, map_slide_information.y_scale));
                        }
                        return scaled_list;
                    }
                };

                const scale_geoJSON = (data, name, id, x_scale, y_scale) => {
                    return {
                        ...data,
                        properties: {
                            name: name,
                            _id: id
                        },
                        features: data.features.map((feature,f_idx) => ({
                            ...feature,
                            geometry: {
                                ...feature.geometry,
                                coordinates: feature.geometry.coordinates.map(axes =>
                                    axes.map(([x, y]) => [x*x_scale, y*y_scale])
                                )
                            },
                            properties: {
                                ...feature.properties.user,
                                name: name,
                                _id: uuidv4(),
                                _index: f_idx
                            }
                        }))
                    }
                };


                // Getting the names of each annotation
                let ann_meta_url = map_slide_information.annotations_metadata_url;
                var ann_meta_response = await fetch(
                    ann_meta_url, {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    }
                );

                if (!ann_meta_response.ok) {
                    throw new Error(`Oh no! Error encountered: ${ann_meta_response.status}`)
                }

                var ann_meta = await ann_meta_response.json();

                // Making sure these are only structural annotations, not image overlays
                ann_meta = ann_meta.filter(item => !('image_path' in item))

                if (ann_meta.length==0){
                    let empty_geojson = {
                        'type': 'FeatureCollection',
                        'features': [],
                        'properties': {}
                    };

                    return [[empty_geojson], [JSON.stringify([empty_geojson])]]
                }

                // Initializing empty annotations list
                var annotations_list = new Array(ann_meta.length);
                try {
                    if ('annotations_geojson_url' in map_slide_information){
                        // This slide has a specific url for getting individual GeoJSON formatted annotations
                        var new_annotations = [];
                        ann_meta.forEach((ann_,idx) => ann_meta.splice(idx,1,{'name': ann_.annotation.name, '_id': ann_._id}))
                        const promises = map_slide_information.annotations_geojson_url.map((url,idx) =>
                            fetch(url, {
                                method: 'GET',
                                headers: {
                                    'Content-Type': 'application/json',
                                }
                            })
                            .then((response) => response.json())
                            .then(function(json_data){return process_json(json_data,idx,ann_meta)})
                            .then((geojson_anns) => annotations_list.splice(idx,1,geojson_anns))
                        );

                        const promise_await = await Promise.all(promises);

                    } else {
                        const promises = [map_slide_information.annotations_url].map((url,idx) =>
                            fetch(url, {
                                method: 'GET',
                                headers: {
                                    'Content-Type': 'application/json',
                                }
                            })
                            .then((response) => response.json())
                            .then((json_data) => annotations_list.push(process_json(json_data,idx,ann_meta)))
                        );
                        const promise_await = await Promise.all(promises);
                        annotations_list = annotations_list.flat();

                    }

                } catch (error) {
                    console.error(error.message);
                } 

                // If manual ROIs are present
                if ('manual_rois' in map_slide_information){
                    // var geojson_features = L.geoJson(map_slide_information.manual_rois);
                    for (let m=0; m<map_slide_information.manual_rois.length; m++){
                        console.log(map_slide_information.manual_rois[m]);
                        let manual_roi = map_slide_information.manual_rois[m];
                        annotations_list.push(scale_geoJSON(manual_roi, manual_roi.properties.name, manual_roi.properties._id, map_slide_information.x_scale, map_slide_information.y_scale))
                    }
                };

                return [annotations_list, [JSON.stringify(annotations_list)]];
            }
            """,
            [
                Output({'type': 'feature-bounds','index': ALL},'data'),
                Output({'type': 'map-annotations-store','index': ALL},'data'),
            ],
            [
                Input({'type': 'map-slide-information','index': ALL},'data')
            ]
        )

    def update_vis_session(self, new_vis_data):
        """Updating slide dropdown options based on current visualization session

        :param new_vis_data: Visualization session data containing information on selectable slides
        :type new_vis_data: str
        :return: New options for slide dropdown
        :rtype: list
        """
        new_vis_data = json.loads(new_vis_data)

        new_slide_options = [
            {
                'label': i['name'],
                'value': idx
            }
            for idx, i in enumerate(new_vis_data['current'])
        ]

        return [new_slide_options]

    def update_slide(self, slide_selected, vis_data):
        
        if not any([i['value'] or i['value']==0 for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        vis_data = json.loads(vis_data)
        new_slide = vis_data['current'][get_pattern_matching_value(slide_selected)]

        #TODO: Add progress bar for loading annotations?
        #TODO: Load manual ROIs and marker layer from visualization session

        # Getting data from the tileservers:
        if not 'current_user' in vis_data:
            new_url = new_slide['tiles_url']
            image_metadata_url = new_slide['image_metadata_url']
            metadata_url = new_slide['metadata_url']
            annotations_metadata_url = new_slide['annotations_metadata_url']

        else:
            new_url = new_slide['tiles_url']+f'?token={vis_data["current_user"]["token"]}'
            image_metadata_url = new_slide['image_metadata_url']+f'?token={vis_data["current_user"]["token"]}'
            metadata_url = new_slide['metadata_url']+f'?token={vis_data["current_user"]["token"]}'
            annotations_metadata_url = new_slide['annotations_metadata_url']

        new_image_metadata = requests.get(image_metadata_url).json()
        new_metadata = requests.get(metadata_url).json()
        annotations_metadata = requests.get(annotations_metadata_url).json()
        print(annotations_metadata)

        # Detecting DSA-formatted annotations
        if any(['annotation' in i for i in annotations_metadata]):
            annotations_metadata = [
                {
                    'name': a['annotation']['name'],
                    '_id': a['_id']
                }
                for a in annotations_metadata
            ]

        annotation_names = [i['name'] for i in annotations_metadata]

        new_tile_size = new_image_metadata['tileHeight']

        image_overlay_annotations = [i for i in annotations_metadata if 'image_path' in i]
        non_image_overlay_metadata = [i for i in annotations_metadata if not 'image_path' in i]
        x_scale, y_scale = self.get_scale_factors(new_image_metadata)
        new_layer_children = []

        if 'manual_rois' in new_slide:
            non_image_overlay_metadata += [
                i['properties']
                for i in new_slide['manual_rois']
            ]
            annotation_names += [i['properties']['name'] for i in new_slide['manual_rois']]

        # Adding overlaid annotation layers:
        for st_idx, st_info in enumerate(non_image_overlay_metadata):
            new_layer_children.append(
                dl.Overlay(
                    dl.LayerGroup(
                        dl.GeoJSON(
                            data = {
                                'type': 'FeatureCollection',
                                'features': []
                            },
                            #format = 'geojson',
                            id = {'type': f'{self.component_prefix}-feature-bounds','index': st_idx},
                            options = {
                                'style': self.js_namespace('featureStyle')
                            },
                            filter = self.js_namespace("featureFilter"),
                            hideout = {
                                'overlayBounds': {},
                                'overlayProp': {},
                                'fillOpacity': 0.5,
                                'lineColor': {
                                    k: '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255))
                                    for k in annotation_names
                                },
                                'filterVals': [],
                                'colorMap': 'blue->red'
                            },
                            hoverStyle = arrow_function(
                                {
                                    'weight': 5,
                                    'color': '#9caf00',
                                    'dashArray': ''
                                }
                            ),
                            zoomToBounds = False,
                            children = [
                                dl.Popup(
                                    id = {'type': f'{self.component_prefix}-feature-popup','index': st_idx},
                                    autoPan = False
                                )
                            ]
                        )
                    ),
                    name = st_info['name'],
                    checked = True,
                    id = {'type': f'{self.component_prefix}-feature-overlay','index': np.random.randint(0,1000)}
                )
            )


        for img_idx, img in enumerate(image_overlay_annotations):

            # miny, minx, maxy, maxx (a.k.a. minlat, minlng, maxlat, maxlng)
            scaled_image_bounds = [
                [img['image_bounds'][1]*y_scale,
                 img['image_bounds'][0]*x_scale],
                [img['image_bounds'][3]*y_scale,
                 img['image_bounds'][2]*x_scale]
            ]
            # Creating data: path for image
            with open(img['image_path'],'rb') as f:
                new_image_path = f'data:image/{img["image_path"].split(".")[-1]};base64,{base64.b64encode(f.read()).decode("ascii")}'
                f.close()

            image_overlay_popup = self.get_image_overlay_popup(img, img_idx)

            new_layer_children.extend([
                dl.ImageOverlay(
                    url = new_image_path,
                    opacity = 0.5,
                    interactive = True,
                    bounds = scaled_image_bounds,
                    id = {'type': f'{self.component_prefix}-image-overlay','index': img_idx},
                    children = [
                        image_overlay_popup
                    ]
                ),
                dl.LayerGroup(
                    id = {'type': f'{self.component_prefix}-image-overlay-mover-layergroup','index': img_idx},
                    children = []
                )
            ])

        # For MultiFrameSlideMap, add frame BaseLayers and RGB layer (if present)
        if isinstance(self,MultiFrameSlideMap):
            new_layer_children.extend(self.process_frames(new_image_metadata, new_url))
            new_tile_layer = dl.TileLayer(
                id = {'type': f'{self.component_prefix}-map-tile-layer','index': np.random.randint(0,1000)},
                url = '',                
                tileSize=new_tile_size,
                maxNativeZoom=new_image_metadata['levels']-2 if new_image_metadata['levels']>=2 else 0,
                minZoom = 0
            )
        else:
            new_tile_layer = dl.TileLayer(
                id = {'type': f'{self.component_prefix}-map-tile-layer','index': np.random.randint(0,1000)},
                url = new_url,
                tileSize = new_tile_size,
                maxNativeZoom=new_image_metadata['levels']-2 if new_image_metadata['levels']>=2 else 0,
                minZoom = 0
            )

        new_slide_info = {}
        new_slide_info['x_scale'] = x_scale
        new_slide_info['y_scale'] = y_scale
        new_slide_info['image_overlays'] = image_overlay_annotations
        new_slide_info['annotations_metadata'] = annotations_metadata
        new_slide_info['metadata'] = new_metadata
        new_slide_info = new_slide_info | new_slide

        new_slide_info = json.dumps(new_slide_info)

        # Updating manual and generated ROIs divs
        manual_rois = []
        gen_rois = []

        remove_old_edits = {
            'mode':'remove',
            'n_clicks':0,
            'action':'clear all'
        }

        #TODO: Add something else to make sure that "Filtered" annotations are removed after loading a new slide
        if 'meta' in new_metadata:
            display_metadata = {
                k: v
                for k,v in new_metadata['meta'].items()
                if not type(v)==dict
            }
        else:
            display_metadata = {}

        for k,v in new_metadata.items():
            if not k=='meta':
                if not type(v)==dict:
                    display_metadata[k] = v

        slide_metadata_div = html.Div(
            dbc.Accordion(
                children = [
                    dbc.AccordionItem(
                        title = 'Image Metadata',
                        children = [
                            self.make_dash_table(
                                pd.DataFrame.from_records([
                                    {
                                        'Key': k,
                                        'Value': v
                                    }
                                    for k,v in new_image_metadata.items()
                                ])
                            )
                        ]
                    ),
                    dbc.AccordionItem(
                        title = 'Case Metadata',
                        children = [
                            self.make_dash_table(
                                pd.DataFrame.from_records([
                                    {
                                        'Key': k,
                                        'Value': v
                                    }
                                    for k,v in display_metadata.items()
                                ])
                            )
                        ]
                    )
                ]
            )
        )

        return new_layer_children, remove_old_edits, manual_rois, gen_rois, new_tile_layer, new_slide_info, slide_metadata_div

    def update_ann_info(self, annotations_geojson):
        """Extracting descriptive information on properties stored in GeoJSON data, referenced by other components

        :param annotations_geojson: GeoJSON data
        :type annotations_geojson: list
        """
        if not any([i['value'] for i in ctx.triggered]):
            empty_store = {
                'available_properties': [],
                'feature_names': [],
                'property_info': {}
            }
            return [json.dumps(empty_store)]
        
        annotations_geojson = json.loads(get_pattern_matching_value(annotations_geojson))

        new_available_properties, new_feature_names, new_property_info = extract_geojson_properties(annotations_geojson,None,['_id','_index'],4)

        annotations_info_store = json.dumps({
            'available_properties': new_available_properties,
            'feature_names': new_feature_names,
            'property_info': new_property_info
        })

        return [annotations_info_store]

    def upload_shape(self, upload_clicked, is_open):

        upload_clicked = get_pattern_matching_value(upload_clicked)
        is_open = get_pattern_matching_value(is_open)

        if upload_clicked:
            return [not is_open]

    def make_dash_table(self, df:pd.DataFrame):
        """
        Populate dash_table.DataTable
        """
        return_table = dash_table.DataTable(
            columns = [{'name':i,'id':i,'deletable':False,'selectable':True} for i in df],
            data = df.to_dict('records'),
            editable=False,                                        
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
                } for row in df.to_dict('records')
            ],
            tooltip_duration = None
        )

        return return_table
    
    def make_sub_accordion(self, input_data: Union[list,dict]):
        """Recursively generating sub-accordion objects for nested properties

        :param input_dict: Input dictionary containing nested and non-nested key/value pairs
        :type input_dict: dict
        """
        main_list = []
        sub_list = []
        for idx,in_data in enumerate(input_data):
            title = list(in_data.keys())[0]
            non_nested_data = [{'Sub-Property':key, 'Value': val} for key,val in in_data[title].items() if not type(val) in [list,dict]]
            nested_data = [{key:val} for key,val in in_data[title].items() if type(val)==dict]
            if len(non_nested_data)>0:
                main_list.append(
                    dbc.AccordionItem([
                        html.Div([
                            self.make_dash_table(pd.DataFrame.from_records(non_nested_data))
                        ])
                    ],title = title)
                )
            if len(nested_data)>0:
                nested_list = self.make_sub_accordion(nested_data)
                sub_list.extend(nested_list)
        
            if len(sub_list)>0:
                main_list.append(
                    dbc.Accordion(
                        dbc.AccordionItem(
                            dbc.Accordion(
                                sub_list
                            ),
                            title = title
                        )
                    )
                )
                sub_list = []
        
        return main_list

    def get_click_popup(self, clicked):
        """Populating popup Div with summary information on the clicked GeoJSON feature

        :param clicked: GeoJSON feature on SlideMap that was selected
        :type clicked: dl.GeoJSON.GeoJSON
        :raises exceptions.PreventUpdate: Stops callback execution
        :return: Popup with summary information on clicked GeoJSON. Nested properties (in dictionaries) appear as collapsible dbc.AccordionItem() with their own dash_table.DataTable
        :rtype: dash.html.Div.Div
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        clicked = get_pattern_matching_value(clicked)
        
        accordion_children = []
        all_properties = list(clicked['properties'].keys())

        non_dict_properties = [i for i in all_properties if not type(clicked['properties'][i]) in [list,dict]]
        non_dict_prop_list = {'Property': non_dict_properties, 'Value': [clicked['properties'][i] for i in non_dict_properties]}

        accordion_children.append(
            dbc.AccordionItem([
                html.Div([
                    self.make_dash_table(pd.DataFrame(non_dict_prop_list))
                ])
            ], title = 'Properties')
        )

        # Now loading the dict properties as sub-accordions
        sub_properties = [{i:clicked['properties'][i]} for i in clicked['properties'] if type(clicked['properties'][i])==dict]
        test_sub_accordions = self.make_sub_accordion(sub_properties)
        if len(test_sub_accordions)>0:
            accordion_children.extend(test_sub_accordions)

        # If this is a manual ROI then add a download option:
        if 'Manual' in clicked['properties']['name']:
            clicked_idx = int(float(clicked['properties']['name'].split(' ')[-1]))
            accordion_children.append(
                dbc.AccordionItem([
                    html.Div([
                        dbc.Button(
                            'Download Shape',
                            id = {'type': f'{self.component_prefix}-download-manual-roi','index': clicked_idx},
                            n_clicks = 0,
                            className = 'd-grid col-12 mx-auto'
                        ),
                        dcc.Download(
                            id = {'type': f'{self.component_prefix}-download-manual-roi-download','index': clicked_idx}
                        )
                    ])
                ],
                title = 'Download Shape')
            )

        popup_div = html.Div(
            dbc.Accordion(
                children = accordion_children,
                start_collapsed=True,
                style = {'maxHeight': '800px','overflow': 'scroll','width': '300px'}
            )
        )

        return popup_div
    
    def make_geojson_layers(self, geojson_list:list, names_list:list, index_list: list, line_color:list, colormap: str) -> list:
        """Creates new dl.Overlay() dl.GeoJSON components from list of GeoJSON FeatureCollection objects

        :param geojson_list: List of GeoJSON FeatureCollection objects
        :type geojson_list: list
        :param names_list: List of names for each layer
        :type names_list: list
        :param index_list: List of indices to apply to each component
        :type index_list: list
        :return: Overlay components on SlideMap.
        :rtype: list
        """

        if any(['Manual' in i for i in names_list]):
            manual_rois = [
                {
                    'type': 'FeatureCollection',
                    'features': [
                        i
                    ],
                    'properties': i['properties'] if '_id' in i['properties'] else i['properties'] | {'_id': uuid.uuid4().hex[:24], 'name': f'Manual ROI {idx+1}'}
                }
                for idx,i in enumerate(geojson_list[-1]['features'])
            ]

            non_manual_n = len(geojson_list)-1
            manual_n = len(manual_rois)
            geojson_list[non_manual_n:non_manual_n+manual_n] = manual_rois

        annotation_components = []
        for st,st_name,st_idx,st_color in zip(geojson_list,names_list,index_list,line_color):
            
            annotation_components.append(
                dl.Overlay(
                    dl.LayerGroup(
                        dl.GeoJSON(
                            data = st,
                            id = {'type': f'{self.component_prefix}-feature-bounds','index': st_idx},
                            options = {
                                'style': self.js_namespace("featureStyle")
                            },
                            filter = self.js_namespace("featureFilter"),
                            hideout = {
                                'overlayBounds': {},
                                'overlayProp': {},
                                'fillOpacity': 0.5,
                                'lineColor': {st_name: st_color},
                                'filterVals': [],
                                'colorMap': colormap
                            },
                            hoverStyle = arrow_function(
                                {
                                    'weight': 5,
                                    'color': '#9caf00',
                                    'dashArray':''
                                }
                            ),
                            zoomToBounds = False,
                            children = [
                                dl.Popup(
                                    id = {'type': f'{self.component_prefix}-feature-popup','index': st_idx},
                                    autoPan = False,
                                )
                            ]
                        )
                    ),
                    name = st_name, checked = True, id = {'type':f'{self.component_prefix}-feature-overlay','index':st_idx}
                )
            )

        return annotation_components

    def add_manual_roi(self,new_geojson:list, uploaded_shape: list, current_annotations:list, frame_layers:list, line_colors:list, colormap:list, separate_switch: list, summarize_switch: list, map_slide_information:list, session_data:dict) -> list:
        """Adding a manual region of interest (ROI) to the SlideMap using dl.EditControl() tools including polygon, rectangle, and markers.

        :param new_geojson: Incoming GeoJSON object that is emitted by dl.EditControl() following annotation on SlideMap
        :type new_geojson: list
        :param current_annotations: Initial annotations added to the map on initialization
        :type current_annotations: list
        :param annotation_names: Names for each annotation layer on the slide map
        :type annotation_names: list
        :param frame_layers: Frame layers for multi-frame visualization
        :type frame_layers: list
        :param map_slide_information: Current slide image metadata
        :type map_slide_information: list
        :param session_data: Current Visualization session data
        Ptype session_data: dict
        :raises exceptions.PreventUpdate: new_geojson input is None
        :raises exceptions.PreventUpdate: No new features are added, this can occur after deletion of previous manual ROIs.
        :return: List of new children to dl.LayerControl() consisting of overlaid GeoJSON components.
        :rtype: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        uploaded_shape = get_pattern_matching_value(uploaded_shape)
        new_geojson = get_pattern_matching_value(new_geojson)
        current_annotations = json.loads(get_pattern_matching_value(current_annotations))

        session_data = json.loads(session_data)
        map_slide_information = json.loads(get_pattern_matching_value(map_slide_information))

        colormap = get_pattern_matching_value(colormap)
        separate_switch = get_pattern_matching_value(separate_switch)
        summarize_switch = get_pattern_matching_value(summarize_switch)
        separate_switch = separate_switch if not separate_switch is None else False
        summarize_switch = summarize_switch if not summarize_switch is None else False

        if colormap is None or len(colormap)==0:
            colormap = 'blue->red'

        # All but the last one which holds the manual ROIs
        initial_annotations = [i for i in current_annotations if not any([j in i['properties']['name'] for j in ['Manual','Filtered','Upload']])]
        # Current manual rois (used for determining if a new ROI has been created/edited)
        annotation_names = [i['properties']['name'] for i in current_annotations]
        manual_roi_idxes = [0]+[int(i.split(' ')[-1]) for i in annotation_names if 'Manual' in i]

        manual_rois = [i for i in current_annotations if 'Manual' in i['properties']['name']]

        # The three different types of ROIs present on maps
        manual_roi_idx = [idx for idx,i in enumerate(current_annotations) if 'Manual' in i['properties']['name']]

        # Initializing layers with partial update object
        new_manual_rois = Patch()
        added_rois = []
        added_roi_names = []
        deleted_rois = []

        #TODO: Add functionality for if a manual ROI is edited (Have to add in "edit" back to EditControl to make this option appear)
        #TODO: Add functionality for adding a marker (render a point GeoJSON component to enable access by DataExtractor)

        if 'edit-control' in ctx.triggered_id['type']:
            # Checking for new manual ROIs
            for f_idx, f in enumerate(new_geojson['features']):
                # If this feature is not a match for one of the current_manual_rois (in annotation store)
                if not any([f['geometry']==i['features'][0]['geometry'] for i in manual_rois]):
                    # Create a new manual ROI (This would also be the case for edited ROIs which is acceptable as the spatial aggregation merits new item creation).
                    new_roi_name = f'Manual ROI {max(manual_roi_idxes)+1}'
                    new_roi = {
                        'type': 'FeatureCollection',
                        'features': [f],
                        'properties':{
                            'name': new_roi_name,
                            '_id': uuid.uuid4().hex[:24]
                        }
                    }
                    
                    for f_idx,f in enumerate(new_roi['features']):
                        f['properties'] = {
                            'name': new_roi_name,
                            '_id': uuid.uuid4().hex[:24],
                            '_index': f_idx
                        }

                    manual_roi_idxes.append(max(manual_roi_idxes)+1)
                    
                    # Aggregate if any initial annotations are present
                    if len(initial_annotations)>0:
                        # Spatial aggregation performed just between individual manual ROIs and initial annotations (no manual ROI to manual ROI aggregation)
                        new_roi = spatially_aggregate(new_roi, initial_annotations,separate=separate_switch,summarize=summarize_switch)
                    
                    added_rois.append(new_roi)
                    added_roi_names.append(new_roi_name)

        elif 'upload-shape-data' in ctx.triggered_id['type']:
            x_scale = map_slide_information['x_scale']
            y_scale = map_slide_information['y_scale']

            if not uploaded_shape is None:
                upload_shape_type = uploaded_shape.split(',')[0]
                if 'json' in upload_shape_type:
                    uploaded_roi = json.loads(base64.b64decode(uploaded_shape.split(',')[-1]).decode())
                elif 'xml' in upload_shape_type:
                    uploaded_roi = ET.fromstring(base64.b64decode(uploaded_shape.split(',')[-1]).decode())
                    uploaded_roi = aperio_to_geojson(uploaded_roi)
                else:
                    print(f'upload_shape_type: {upload_shape_type}')
                    raise exceptions.PreventUpdate

                if type(uploaded_roi)==dict:
                    uploaded_roi = [uploaded_roi]
                
                for up_idx, up in enumerate(uploaded_roi):
                    scaled_upload = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]*x_scale,c[1]*y_scale),g),up)

                    # Checking if there is a name or _id property:
                    if 'properties' in scaled_upload:
                        if 'name' in scaled_upload['properties']:
                            if 'Manual' in scaled_upload['properties']['name']:
                                scaled_upload['properties']['name'] = scaled_upload['properties']['name'].replace('Manual','Upload')
                        
                        scaled_upload['properties']['_id'] = uuid.uuid4().hex[:24]

                    else:
                        scaled_upload['properties'] = {
                            'name': f'Upload {len([i for i in annotation_names if "Upload" in i])+1+up_idx}',
                            '_id': uuid.uuid4().hex[:24]
                        }

                    # Aggregate if any initial annotations are present
                    new_roi_name = scaled_upload['properties']['name']
                    if len(initial_annotations)>0:
                        # Spatial aggregation performed just between individual manual ROIs and initial annotations (no manual ROI to manual ROI aggregation)
                        new_roi = spatially_aggregate(scaled_upload, initial_annotations,separate=separate_switch,summarize=summarize_switch)
                    else:
                        new_roi = scaled_upload

                    added_rois.append(new_roi)
                    added_roi_names.append(new_roi_name)
                    manual_roi_idxes.append(max(manual_roi_idxes)+1+up_idx)

        # Checking for deleted manual ROIs
        for m_idx,(m,man_idx) in enumerate(zip(manual_rois,manual_roi_idx)):
            if not m['features'][0]['geometry'] in [j['geometry'] for j  in new_geojson['features']]:
                # Adding both the index in the manual-rois layer and the index in the current annotations layer
                deleted_rois.append((m_idx,man_idx))

        operation = False
        if len(added_rois)>0:
            operation = True
            line_colors = ['#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255)) for i in added_roi_names]

            new_layers = self.make_geojson_layers(
                added_rois,added_roi_names,[len(initial_annotations)+i for i in manual_roi_idxes],line_colors,colormap
            )
            new_manual_rois.extend(new_layers)

            if type(current_annotations)==list:
                current_annotations.extend(added_rois)
            else:
                if len(list(current_annotations.keys()))==0:
                    current_annotations = added_rois
                else:
                    current_annotations = [current_annotations]+added_rois
        
        if len(deleted_rois)>0:
            operation = True
            for d_idx,(man_d,current_d) in enumerate(deleted_rois):
                del new_manual_rois[man_d-d_idx]
                del current_annotations[current_d-d_idx]

        annotations_data = json.dumps(current_annotations)
        new_session_data = deepcopy(session_data)

        # Finding the current slide index:
        if 'tiles_url' in map_slide_information:
            current_slide_tile_urls = [i['tiles_url'] for i in new_session_data['current']]
            slide_idx = current_slide_tile_urls.index(map_slide_information['tiles_url'])

            if not 'manual_rois' in new_session_data['current'][slide_idx]:
                scaled_rois = [geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/map_slide_information['x_scale'],c[1]/map_slide_information['y_scale']),g),a) for a in deepcopy(added_rois)]
                new_session_data['current'][slide_idx]['manual_rois'] = [
                    i | {'properties': a['properties']}
                    for a,i in zip(added_rois,scaled_rois)
                ]
            else:
                new_session_data['current'][slide_idx]['manual_rois'] += [geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/map_slide_information['x_scale'],c[1]/map_slide_information['y_scale']),g),a) for a in deepcopy(added_rois)]
                new_session_data['current'][slide_idx]['manual_rois'] = [
                    i | {'properties': a['properties']}
                    for a,i in zip(added_rois,scaled_rois)
                ]


        new_session_data = json.dumps(new_session_data)

        if not operation:
            new_manual_rois = no_update

        return [new_manual_rois], [annotations_data], new_session_data

    def update_image_overlay_transparency(self, new_opacity: float):
        """Update transparency of image overlay component

        :param new_opacity: New opacity level (0-1 (0.1 increments)) from slider
        :type new_opacity: float
        :return: New opacity level
        :rtype: float
        """
        if new_opacity is not None:
            return new_opacity
        else:
            raise exceptions.PreventUpdate

    def gen_image_mover(self,button_click,current_bounds,button_text):
        """Creates a draggable Marker to facilitate moving an image overlay around

        :param button_click: Position button is clicked
        :type button_click: dict
        :param current_bounds: Current bounds of the image overlay, used for setting initial position of mover Marker
        :type current_bounds: list
        :param button_text: Text displayed on position button.
        :type button_text: str
        :raises exceptions.PreventUpdate: Prevent update if button is not pressed.
        :return: New text for the position button and mover Marker
        :rtype: tuple
        """
        button_click = get_pattern_matching_value(button_click)
        current_bounds = get_pattern_matching_value(current_bounds)
        if button_click:
            button_text = get_pattern_matching_value(button_text)
            if button_text=='Move it!':
                new_button_text = 'Lock in!'
                mover = dl.DivMarker(
                    id = {'type': f'{self.component_prefix}-image-overlay-mover','index': ctx.triggered_id['index']},
                    position = current_bounds[0],
                    draggable = True,
                    iconOptions = {
                        'className': 'fa-solid fa-crosshairs fa-xl',
                    },
                    children = [
                        dl.Tooltip(
                            'Double click to move the image!'
                        )
                    ],
                    eventHandlers={
                        'dblclick': self.js_namespace('sendPosition')
                    }
                )

            elif button_text == 'Lock in!':

                new_button_text = 'Move it!'
                mover = []

            return mover, new_button_text
        else:
            raise exceptions.PreventUpdate

    def move_image_overlay(self, new_position, old_bounds):
        """Move image overlay to location of mover Marker

        :param new_position: New top-left position of image overlay (keys: lat, lng)
        :type new_position: dict
        :param old_bounds: Old bounds of the image, used for determining bottom-right coordinates
        :type old_bounds: list
        :raises exceptions.PreventUpdate: Prevents callback execution until a position is set
        :return: New bounds for image overlay component
        :rtype: list
        """
        new_position = get_pattern_matching_value(new_position)
        old_bounds = get_pattern_matching_value(old_bounds)
        if not new_position is None:
            old_size = [
                old_bounds[1][0] - old_bounds[0][0],
                old_bounds[1][1] - old_bounds[0][1]
            ]

            new_bounds = [
                [new_position['lat'],new_position['lng']],
                [new_position['lat']+old_size[0], new_position['lng']+old_size[1]]
            ]

            return new_bounds
        else:
            raise exceptions.PreventUpdate

    def export_image_overlay_bounds(self, button_click, current_position, slide_information):
        """Exporting position of image overlay

        :param button_click: Export button clicked
        :type button_click: int
        :param current_position: Current position of the image overlay
        :type current_position: list
        :raises exceptions.PreventUpdate: Preventing callback if button isn't clicked
        :return: JSON file containing original image path and current position on the slide 
        :rtype: dict
        """
        button_click = get_pattern_matching_value(button_click)
        if button_click:
            current_position = get_pattern_matching_value(current_position)
            image_overlay_index = ctx.triggered_id['index']

            slide_information = json.loads(get_pattern_matching_value(slide_information))

            scaled_position = [
                [current_position[0][1]/slide_information['x_scale'], current_position[0][0]/slide_information['y_scale']],
                [current_position[1][1]/slide_information['x_scale'], current_position[1][0]/slide_information['y_scale']]
            ]
            export_data = {
                'content': json.dumps({
                    'imagePath': slide_information['image_overlays'][image_overlay_index]['image_path'],
                    'imageBounds': scaled_position
                }),
                'filename': "fusion_image_overlay_position.json"
            }

            return export_data
        else:
            raise exceptions.PreventUpdate

    def download_manual_roi(self, button_click, current_manual_geojson,slide_information):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        manual_roi_feature_index = ctx.triggered_id['index']-1
        manual_roi_geojson = get_pattern_matching_value(current_manual_geojson)['features'][manual_roi_feature_index]

        slide_information = json.loads(get_pattern_matching_value(slide_information))

        manual_roi = {
            'type': 'FeatureCollection',
            'features': [
                manual_roi_geojson
            ]
        }

        scaled_manual_roi = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),manual_roi)

        return {'content': json.dumps(scaled_manual_roi),'filename': f'Manual ROI {manual_roi_feature_index+1}.json'}


class MultiFrameSlideMap(SlideMap):
    """MultiFrameSlideMap component, containing an image with multiple frames which are added as additional, selectable dl.TileLayer() components

    :param SlideMap: dl.Map() container where image tiles are displayed.
    :type SlideMap: None
    """
    def __init__(self):
        """Constructor method

        :param tile_server: TileServer object in use. For remote DSA tile sources this would be DSATileServer while for local images this would be LocalTileServer
        :type tile_server: TileServer
        :param annotations: Individual or list of GeoJSON formatted annotations to add on top of the MultiFrameSlideMap
        :type annotations: Union[dict,list,None]
        """

        super().__init__()

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Multi-Frame Slide Map'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        super().get_callbacks()
    
    def __str__(self):
        return 'Multi-Frame Slide Map'
    
    def update_layout(self, session_data: dict, use_prefix:bool):
        """Updating layout of MultiFramSlideMap component

        :param session_data: Data relating to current visualization session
        :type session_data: dict
        :param use_prefix: Whether or not this is the initial loading of the component
        :type use_prefix: bool
        :return: Component layout
        """
        layout = html.Div([
            dcc.Dropdown(
                id = {'type': 'slide-select-drop','index': 0},
                placeholder = 'Select a slide to view',
                options = [
                    {
                        'label': i['name'],
                        'value': idx
                    }
                    for idx, i in enumerate(session_data['current'])
                ]
            ),
            html.Div(
                dcc.Store(
                    id = {'type': 'map-slide-information','index': 0},
                    storage_type='memory',
                    data = json.dumps({})
                )
            ),
            html.Hr(),
            dl.Map(
                id = {'type': 'slide-map','index': 0},
                crs = 'Simple',
                center = [-120,120],
                zoom = 1,
                style = {'height': '90vh','width': '100%','margin': 'auto','display': 'inline-block'},
                children = [
                    html.Div(
                        id = {'type': 'map-tile-layer-holder','index': 0},
                        children = []
                    ),
                    dl.FullScreenControl(
                        position = 'upper-left'
                    ),
                    dl.FeatureGroup(
                        id = {'type': 'edit-feature-group','index': 0},
                        children = [
                            dl.EditControl(
                                id = {'type': 'edit-control','index': 0},
                                draw = dict(polyline=False, line=False, marker = False, circle = False, circlemarker=False),
                                position='topleft'
                            )
                        ]
                    ),
                    html.Div(
                        id = {'type': 'map-colorbar-div','index': 0},
                        children = []
                    ),
                    html.Div(
                        dcc.Store(
                            id = {'type':'map-annotations-store','index': 0},
                            data = json.dumps({})
                        )
                    ),
                    dl.LayersControl(
                        id = {'type': 'map-layers-control','index': 0},
                        children = [
                            html.Div(
                                id = {'type': 'map-initial-annotations','index': 0},
                                children = []
                            ),
                            html.Div(
                                id = {'type': 'map-manual-rois','index': 0},
                                children = []
                            ),
                            html.Div(
                                id = {'type': 'map-generated-rois','index': 0},
                                children = []
                            )
                        ]
                    ),
                    dl.EasyButton(
                        icon = 'fa-solid fa-arrows-to-dot',
                        title = 'Re-Center Map',
                        id = {'type': 'center-map','index': 0},
                        position = 'top-left',
                        eventHandlers = {
                            'click': self.js_namespace('centerMap')
                        }
                    ),
                    dl.EasyButton(
                        icon = 'fa-solid fa-upload',
                        title = 'Upload Shapes',
                        id = {'type': 'upload-shape','index': 0},
                        position = 'top-left'
                    ),
                    html.Div(
                        id = {'type': 'map-marker-div','index': 0},
                        children = []
                    ),
                ]
            ),
            dbc.Modal(
                id = {'type': 'upload-shape-modal','index': 0},
                is_open = False,
                children = [
                    html.Div(
                        dcc.Upload(
                            children = [
                                'Drag and Drop or ',
                                html.A('Select a File')
                            ],
                            id = {'type': 'upload-shape-data','index': 0},
                            style={'width': '100%','height': '60px','lineHeight': '60px','borderWidth': '1px','borderStyle': 'dashed','borderRadius': '5px','textAlign': 'center'}
                        )
                    )
                ]
            ),
            dbc.Modal(
                id = {'type': 'load-annotations-modal','index': 0},
                is_open = False,
                children = []
            )
        ])

        if use_prefix:
            PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(layout)

        return layout

    def gen_layout(self, session_data: dict):
        """Generating layout for MultiFrameSlideMap
        """

        self.blueprint.layout = self.update_layout(session_data,use_prefix = True)

    def process_frames(self,image_metadata,tiles_url):
        """Create BaseLayer and TileLayer components for each of the different frames present in a multi-frame image
        Also initializes base tile url and styled tile url
        """

        frame_layers = []

        if 'frames' in image_metadata:
            if len(image_metadata['frames'])>0:
                
                if any(['Channel' in i for i in image_metadata['frames']]):
                    frame_names = [i['Channel'] for i in image_metadata['frames']]
                else:
                    frame_names = [f'Frame {i}' for i in range(len(image_metadata['frames']))]

                # This is a multi-frame image
                if len(image_metadata['frames'])==3:
                    # Treat this as an RGB image by default
                    if '?token' in tiles_url:
                        rgb_url = tiles_url+'&style={"bands": [{"framedelta":0,"palette":"rgba(255,0,0,0)"},{"framedelta":1,"palette":"rgba(0,255,0,0)"},{"framedelta":2,"palette":"rgba(0,0,255,0)"}]}'
                    else:
                        rgb_url = tiles_url+'?style={"bands": [{"framedelta":0,"palette":"rgba(255,0,0,0)"},{"framedelta":1,"palette":"rgba(0,255,0,0)"},{"framedelta":2,"palette":"rgba(0,0,255,0)"}]}'
                else:
                    # Checking for "red", "green" and "blue" frame names
                    if all([i in frame_names for i in ['red','green','blue']]):
                        rgb_style_dict = {
                            "bands": [
                                {
                                    "palette": ["rgba(0,0,0,0)",'rgba('+','.join(['255' if i==c_idx else '0' for i in range(3)]+['0'])+')'],
                                    "framedelta": frame_names.index(c)
                                }
                                for c_idx,c in enumerate(['red','green','blue'])
                            ]
                        }

                        if '?token' in tiles_url:
                            rgb_url = tiles_url+'&style='+json.dumps(rgb_style_dict)
                        else:
                            rgb_url = tiles_url+'?style='+json.dumps(rgb_style_dict)
                    
                    else:
                        rgb_url = None

                # Pre-determining indices:
                if not rgb_url is None:
                    layer_indices = list(range(0,len(frame_names)+1))
                else:
                    layer_indices = list(range(0,len(frame_names)))
                
                for f_idx,f in enumerate(frame_names):
                    if '?token' in tiles_url:
                        frame_url = tiles_url+'&style={"bands": [{"palette":["rgba(0,0,0,0)","rgba(255,255,255,255)"],"framedelta":'+str(f_idx)+'}]}'
                    else:
                        frame_url = tiles_url+'?style={"bands": [{"palette":["rgba(0,0,0,0)","rgba(255,255,255,255)"],"framedelta":'+str(f_idx)+'}]}'

                    frame_layers.append(
                        dl.BaseLayer(
                            dl.TileLayer(
                                url = frame_url,
                                tileSize = image_metadata['tileHeight'],
                                maxNativeZoom=image_metadata['levels']-2 if image_metadata['levels']>=2 else 0,
                                minZoom = -1,
                                id = {'type': f'{self.component_prefix}-tile-layer','index': layer_indices[f_idx]}
                            ),
                            name = f,
                            checked = f==frame_names[0],
                            id = {'type': f'{self.component_prefix}-base-layer','index': layer_indices[f_idx]}
                        )
                    )
                if rgb_url:
                    frame_layers.append(
                        dl.BaseLayer(
                            dl.TileLayer(
                                url = rgb_url,
                                tileSize = image_metadata['tileHeight'],
                                maxNativeZoom=image_metadata['levels']-2 if image_metadata['levels']>=2 else 0,
                                minZoom = -1,
                                id = {'type': f'{self.component_prefix}-tile-layer','index': layer_indices[f_idx+1]},
                                #bounds = [[0,0],[-image_metadata['tileWidth'], image_metadata['tileWidth']]]
                            ),
                            name = 'RGB Image',
                            checked = False,
                            id = {'type': f'{self.component_prefix}-base-layer','index': layer_indices[f_idx+1]}
                        )
                    )
            else:
                frame_layers.append(
                    dl.BaseLayer(
                        dl.TileLayer(
                            url = tiles_url,
                            tileSize = image_metadata['tileHeight'],
                            maxNativeZoom=image_metadata['levels']-2 if image_metadata['levels']>=2 else 0,
                            minZoom = -1,
                            id = {'type': f'{self.component_prefix}-tile-layer','index': 0},
                            #bounds = [[0,0],[-image_metadata['tileWidth'],image_metadata['tileWidth']]]
                        ),
                        name = 'RGB Image',
                        id = {'type': f'{self.component_prefix}-base-layer','index': 0}
                    )
                )
        else:
            raise TypeError("Missing 'frames' key in image metadata")
                
        return frame_layers


class LargeSlideMap(SlideMap):
    """This is a subclass of SlideMap used for LARGE amounts of annotations (>50k)

    :param SlideMap: _description_
    :type SlideMap: _type_
    """
    def __init__(self,
                 min_zoom:int,
                 ):
        super().__init__()

        self.min_zoom = min_zoom

    def load(self,component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Large Slide Map'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

        self.large_map_callbacks()

    def __str__(self):
        return "Large Slide Map"
    
    def get_namespace(self):

        self.js_namespace = Namespace(
            "fusionTools","largeSlideMap"
        )

        self.js_namespace.add(
            src = 'function(e,ctx){ctx.map.flyTo([-120,120],1);}',
            name = "centerMap"
        )

        self.js_namespace.add(
            src = """
                function(feature,context){
                var {overlayBounds, overlayProp, fillOpacity, lineColor, filterVals, lineWidth, colorMap} = context.hideout;
                var style = {};
                if (Object.keys(chroma.brewer).includes(colorMap)){
                    colorMap = colorMap;
                } else {
                    colorMap = colorMap.split("->");
                }

                if ("min" in overlayBounds) {
                    var csc = chroma.scale(colorMap).domain([overlayBounds.min,overlayBounds.max]);
                } else if ("unique" in overlayBounds) {
                    var class_indices = overlayBounds.unique.map(str => overlayBounds.unique.indexOf(str));
                    var csc = chroma.scale(colorMap).colors(class_indices.length);
                } else {
                    style.fillColor = 'white';
                    style.fillOpacity = fillOpacity;
                    if ('name' in feature.properties) {
                        style.color = lineColor[feature.properties.name];
                    } else {
                        style.color = 'white';
                    }

                    return style;
                }

                var overlayVal = Number.Nan;
                if (overlayProp) {
                    if (overlayProp.name) {
                        //TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                        var overlaySubProps = overlayProp.name.split(" --> ");
                        var prop_dict = feature.properties;
                        for (let i = 0; i < overlaySubProps.length; i++) {
                            if (prop_dict==prop_dict && prop_dict!=null && typeof prop_dict === 'object') {
                                if (overlaySubProps[i] in prop_dict) {
                                    var prop_dict = prop_dict[overlaySubProps[i]];
                                    var overlayVal = prop_dict;
                                } else {
                                    prop_dict = Number.Nan;
                                    var overlayVal = Number.Nan;
                                }
                            }
                        }
                    } else {
                        var overlayVal = Number.Nan;
                    }
                } else {
                    var overlayVal = Number.Nan;
                }

                if (overlayVal==overlayVal && overlayVal!=null) {
                    if (typeof overlayVal==='number') {
                        style.fillColor = csc(overlayVal);
                    } else if ('unique' in overlayBounds) {
                        overlayVal = overlayBounds.unique.indexOf(overlayVal);
                        style.fillColor = csc[overlayVal];
                    } else {
                        style.fillColor = "f00";
                    }
                } else {
                    style.fillColor = "f00";
                }

                style.fillOpacity = fillOpacity;
                if (feature.properties.name in lineColor) {
                    style.color = lineColor[feature.properties.name];
                } else {
                    style.color = 'white';
                }

                return style;
                }
                """,
            name = 'featureStyle'
        )

        self.js_namespace.add(
            src = """
                function(feature,context){
                const {overlayBounds, overlayProp, fillOpacity, lineColor, filterVals, lineWidth, colorMap} = context.hideout;

                var returnFeature = true;
                if (filterVals) {
                    for (let i = 0; i < filterVals.length; i++) {
                        // Iterating through filterVals list
                        var filter = filterVals[i];
                        if (filter.name) {
                            //TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                            var filterSubProps = filter.name.split(" --> ");
                            var prop_dict = feature.properties;
                            for (let j = 0; j < filterSubProps.length; j++) {
                                if (prop_dict==prop_dict && prop_dict!=null && typeof prop_dict==='object') {
                                    if (filterSubProps[j] in prop_dict) {
                                        var prop_dict = prop_dict[filterSubProps[j]];
                                        var testVal = prop_dict;
                                    } else {
                                        prop_dict = Number.Nan;
                                        returnFeature = returnFeature & false;
                                    }
                                }
                            }
                        }
                            
                        if (filter.range && returnFeature) {
                            if (typeof filter.range[0]==='number') {
                                if (testVal < filter.range[0]) {
                                    returnFeature = returnFeature & false;
                                }
                                if (testVal > filter.range[1]) {
                                    returnFeature = returnFeature & false;
                                }
                            } else {
                                if (filter.range.includes(testVal)) {
                                    returnFeature = returnFeature & true;
                                } else {
                                    returnFeature = returnFeature & false;
                                }
                            }
                        }
                    }
                }  else {
                    return returnFeature;
                }              
                return returnFeature;
                }
                """,
            name = 'featureFilter'
        )

        self.js_namespace.add(
            src = """
            function(e,ctx){
                ctx.setProps({
                    data: e.latlng
                });
            }
            """,
            name = 'sendPosition'
        )

        self.js_namespace.dump(
            assets_folder = self.assets_folder
        )

    def large_map_callbacks(self):

        self.blueprint.clientside_callback(
            """
            async function(map_bounds,slide_information,current_zoom){
                // Prevent Update at initialization
                if (slide_information[0]==undefined){
                    throw window.dash_clientside.PreventUpdate;
                } else if (current_zoom[0]==undefined){
                    throw window.dash_clientside.PreventUpdate;
                }

                // Run annotation region request, return annotations within that region
                // Reading in map-slide-information
                var map_slide_information = JSON.parse(slide_information);
                var scaled_map_bounds = [
                    Math.floor(map_bounds[0][1][0] / map_slide_information.y_scale),
                    Math.floor(map_bounds[0][0][1] / map_slide_information.x_scale),
                    Math.floor(map_bounds[0][0][0] / map_slide_information.y_scale),
                    Math.floor(map_bounds[0][1][1] / map_slide_information.x_scale)
                ];

                // Checking if the maps current zoom level is above the minimum zoom setting
                if (current_zoom[0] < map_slide_information.minZoom){
                    throw window.dash_clientside.PreventUpdate;
                }
                
                // This is for DSA slides, annotations are only accessible for regions on an individual basis
                // and then must be converted to GeoJSON.
                var annotations_list = [];
                var annotations_str = [];
                if ("api_url" in map_slide_information.slide_info){
                    for (let ann = 0; ann<map_slide_information.annotations_metadata.length; ann++) {
                        var annotation = map_slide_information.annotations_metadata[ann];

                        try {
                            let ann_url = map_slide_information.annotations_region_url + annotation._id+"?top="+scaled_map_bounds[0]+"&left="+scaled_map_bounds[1]+"&bottom="+scaled_map_bounds[2]+"&right="+scaled_map_bounds[3]
                            var ann_response = await fetch(
                                ann_url, {
                                method: 'GET',
                                headers: {
                                    'Content-Type': 'application/json'    
                                }
                            });

                            if (!ann_response.ok) {
                                throw new Error(`Oh no! Error encountered: ${ann_response.status}`)
                            }

                            // Scaling coordinates of returned annotations
                            var new_annotations = await ann_response.json();
                            let new_geojson = {
                                "type": "FeatureCollection",
                                "features": [],
                                "properties": {
                                    "name": annotation.annotation.name,
                                    "_id": annotation._id
                                }
                            };
                            for (let i = 0; i<new_annotations.annotation.elements.length; i++){

                                if ("user" in new_annotations.annotation.elements[i]) {
                                    var user_properties = new_annotations.annotation.elements[i].user;
                                } else {
                                    var user_properties = new Object;
                                }
                                user_properties["id"] = i;
                                user_properties["cluster"] = false;
                                user_properties["name"] = annotation.annotation.name;

                                let new_feature = {
                                    "type": "Feature",
                                    "properties": user_properties,
                                    "geometry": {
                                        "type": "Polygon",
                                        "coordinates": [[]]
                                    }
                                };

                                for (let j = 0; j<new_annotations.annotation.elements[i].points.length;j++){
                                    let these_coords = new_annotations.annotation.elements[i].points[j];
                                    new_feature.geometry.coordinates[0].push([these_coords[0] * map_slide_information.x_scale, these_coords[1] * map_slide_information.y_scale]);
                                }
                                new_geojson.features.push(new_feature);
                            }

                            annotations_str.push(new_geojson);
                            annotations_list.push(new_geojson);
                        } catch (error) {
                            console.error(error.message);
                        }
                    }
                } else {
                    // General case.
                    try {
                        let ann_url = map_slide_information.annotations_region_url+"?top="+scaled_map_bounds[0]+"&left="+scaled_map_bounds[1]+"&bottom="+scaled_map_bounds[2]+"&right="+scaled_map_bounds[3];
                        var ann_response = await fetch(
                            ann_url, {
                            method: 'GET',
                            headers: {
                                'Content-Type': 'application/json'    
                            }
                        });

                        if (!ann_response.ok) {
                            throw new Error(`Oh no! Error encountered: ${ann_response.status}`)
                        }

                        // Scaling coordinates of returned annotations
                        var new_annotations = await ann_response.json();
                        // Thanks Suhas
                        const scale_geoJSON = (data, name, id, x_scale, y_scale) => {
                            return {
                                ...data,
                                properties: {
                                    name: name,
                                    _id: id
                                },
                                features: data.features.map(feature => ({
                                    ...feature,
                                    geometry: {
                                        ...feature.geometry,
                                        coordinates: feature.geometry.coordinates.map(axes => 
                                            axes.map(([x, y]) => [x * x_scale, y * y_scale])
                                        )
                                    }
                                }))
                            }
                        }

                        for (let ann=0; ann<new_annotations.length; ann++){
                            let annotation = map_slide_information.annotations_metadata[ann];
                            let new_geojson = scale_geoJSON(new_annotations[ann], annotation.name, annotation._id, map_slide_information.x_scale, map_slide_information.y_scale);
                            
                            annotations_str.push(new_geojson);
                            annotations_list.push(new_geojson);
                        }

                    } catch (error) {
                        console.error(error.message);
                    }                
                }

                return [annotations_list, [JSON.stringify(annotations_str)]];
            }
            """,
            [
                Output({'type': 'feature-bounds','index': ALL},'data'),
                Output({'type': 'map-annotations-store','index':ALL},'data')
            ],
            Input({'type': 'slide-map','index': ALL},'bounds'),
            [
                State({'type':'map-slide-information','index': ALL},'data'),
                State({'type': 'slide-map','index': ALL},'zoom')
            ],
            prevent_initial_call = True
        )

    def update_slide(self, slide_selected, vis_data):
        
        if not any([i['value'] or i['value']==0 for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        vis_data = json.loads(vis_data)
        new_slide = vis_data['current'][get_pattern_matching_value(slide_selected)]

        # Getting data from the tileservers:
        if not 'current_user' in vis_data or not 'api_url' in new_slide:
            new_tile_url = new_slide['tiles_url']
            new_annotations_url = new_slide['annotations_url']
            new_annotations_region_url = new_slide['annotations_region_url']
            new_annotations_metadata_url = new_slide['annotations_metadata_url']
            new_metadata_url = new_slide['metadata_url']
        else:
            new_tile_url = new_slide['tiles_url']+f'?token={vis_data["current_user"]["token"]}'
            new_annotations_url = new_slide['annotations_url']+f'?token={vis_data["current_user"]["token"]}'
            new_annotations_metadata_url = new_slide['annotations_metadata_url']+f'?token={vis_data["current_user"]["token"]}'
            new_metadata_url = new_slide['metadata_url']+f'?token={vis_data["current_user"]["token"]}'

        new_metadata = requests.get(new_metadata_url).json()
        new_annotations_metadata = requests.get(new_annotations_metadata_url).json()
        new_tile_size = new_metadata['tileHeight']
        x_scale, y_scale = self.get_scale_factors(new_metadata)

        annotation_names = []
        image_overlays = []
        print(new_annotations_metadata)
        initial_anns = []
        for a in new_annotations_metadata:
            if 'annotation' in a:
                annotation_names.append(a['annotation']['name'])
                initial_anns.append({
                    'type': 'FeatureCollection', 
                    'properties': {'name': a['annotation']['name'], '_id': a['_id']},
                    'features': []
                    })
            elif 'name' in a:
                annotation_names.append(a['name'])
                initial_anns.append({
                    'type': 'FeatureCollection',
                    'properties': {'name': a['name'],'_id': a['_id']},
                    'features': []
                })
            elif 'image_path' in a:
                image_overlays.append(a)

        print(annotation_names)

        # Creating annotation layers
        new_layer_children = []
        for ann_idx, ann in enumerate(annotation_names):
            new_layer_children.append(
                dl.Overlay(
                    dl.LayerGroup(
                        dl.GeoJSON(
                            data = {
                                "type": "FeatureCollection",
                                "features": []
                            },
                            format = 'geojson',
                            id = {'type': f'{self.component_prefix}-feature-bounds','index': ann_idx},
                            options = {
                                'style': self.js_namespace("featureStyle")
                            },
                            filter = self.js_namespace("featureFilter"),
                            hideout = {
                                'overlayBounds': {},
                                'overlayProp': {},
                                'fillOpacity': 0.5,
                                'lineColor': {
                                    k: '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255))
                                    for k in annotation_names
                                },
                                'filterVals': [],
                                'colorMap': 'blue->red'
                            },
                            hoverStyle = arrow_function(
                                {
                                    'weight': 5,
                                    'color': '#9caf00',
                                    'dashArray':''
                                }
                            ),
                            zoomToBounds = False,
                            children = [
                                dl.Popup(
                                    id = {'type': f'{self.component_prefix}-feature-popup','index': ann_idx},
                                    autoPan = False,
                                )
                            ]
                        )
                    ),
                    name = ann, checked = True, id = {'type':f'{self.component_prefix}-feature-overlay','index':np.random.randint(0,1000)}
                )
            )

        # Adding image annotations
        #TODO: Make these region specific
        for img_idx, img in enumerate(image_overlays):

            # miny, minx, maxy, maxx (a.k.a. minlat, minlng, maxlat, maxlng)
            scaled_image_bounds = [
                [img['image_bounds'][1]*y_scale,
                 img['image_bounds'][0]*x_scale],
                [img['image_bounds'][3]*y_scale,
                 img['image_bounds'][2]*x_scale]
            ]
            # Creating data: path for image
            with open(img['image_path'],'rb') as f:
                new_image_path = f'data:image/{img["image_path"].split(".")[-1]};base64,{base64.b64encode(f.read()).decode("ascii")}'
                f.close()

            image_overlay_popup = self.get_image_overlay_popup(img, img_idx)

            new_layer_children.extend([
                dl.ImageOverlay(
                    url = new_image_path,
                    opacity = 0.5,
                    interactive = True,
                    bounds = scaled_image_bounds,
                    id = {'type': f'{self.component_prefix}-image-overlay','index': img_idx},
                    children = [
                        image_overlay_popup
                    ]
                ),
                dl.LayerGroup(
                    id = {'type': f'{self.component_prefix}-image-overlay-mover-layergroup','index': img_idx},
                    children = []
                )
            ])

        # For MultiFrameSlideMap, add frame BaseLayers and RGB layer (if present)
        if isinstance(self,MultiFrameSlideMap):
            new_layer_children.extend(self.process_frames(new_metadata, new_tile_url))
            new_tile_layer = dl.TileLayer(
                id = {'type': f'{self.component_prefix}-map-tile-layer','index': np.random.randint(0,1000)},
                url = '',                
                tileSize=new_tile_size,
                maxNativeZoom=new_metadata['levels']-2 if new_metadata['levels']>=2 else 0,
                minZoom = 0
            )
        else:
            new_tile_layer = dl.TileLayer(
                id = {'type': f'{self.component_prefix}-map-tile-layer','index': np.random.randint(0,1000)},
                url = new_tile_url,
                tileSize = new_tile_size,
                maxNativeZoom=new_metadata['levels']-2 if new_metadata['levels']>=2 else 0,
                minZoom = 0
            )

        new_slide_info = {}
        new_slide_info['x_scale'] = x_scale
        new_slide_info['y_scale'] = y_scale
        new_slide_info['image_overlays'] = image_overlays
        new_slide_info['slide_info'] = new_slide
        new_slide_info['tiles_url'] = new_tile_url
        new_slide_info['annotations_url'] = new_annotations_url
        new_slide_info['annotations_region_url'] = new_annotations_region_url
        new_slide_info['annotations_metadata'] = new_annotations_metadata
        new_slide_info['minZoom'] = self.min_zoom

        geo_annotations = json.dumps(initial_anns)
        new_slide_info = json.dumps(new_slide_info)

        # Updating manual and generated ROIs divs
        manual_rois = []
        gen_rois = []

        return new_layer_children, manual_rois, gen_rois, geo_annotations, new_tile_layer, new_slide_info

class LargeMultiFrameSlideMap(MultiFrameSlideMap):
    """This is a sub-class of MultiFrameSlideMap used for LARGE amounts of annotations (>50k)

    :param MultiFrameSlideMap: _description_
    :type MultiFrameSlideMap: _type_
    """
    def __init__(self,
                 min_zoom:int):
        
        super().__init__()
        
        self.min_zoom = min_zoom

    def __str__(self):
        return "Large Multi Frame Slide Map"

    def get_namespace(self):
        
        self.js_namespace = Namespace(
            "fusionTools","largeSlideMap"
        )

        self.js_namespace.add(
            src = 'function(e,ctx){ctx.map.flyTo([-120,120],1);}',
            name = "centerMap"
        )

        self.js_namespace.add(
            src = """
                function(feature,context){
                var {overlayBounds, overlayProp, fillOpacity, lineColor, filterVals, lineWidth, colorMap} = context.hideout;
                var style = {};
                if (Object.keys(chroma.brewer).includes(colorMap)){
                    colorMap = colorMap;
                } else {
                    colorMap = colorMap.split("->");
                }

                if ("min" in overlayBounds) {
                    var csc = chroma.scale(colorMap).domain([overlayBounds.min,overlayBounds.max]);
                } else if ("unique" in overlayBounds) {
                    var class_indices = overlayBounds.unique.map(str => overlayBounds.unique.indexOf(str));
                    var csc = chroma.scale(colorMap).colors(class_indices.length);
                } else {
                    style.fillColor = 'white';
                    style.fillOpacity = fillOpacity;
                    if ('name' in feature.properties) {
                        style.color = lineColor[feature.properties.name];
                    } else {
                        style.color = 'white';
                    }

                    return style;
                }

                var overlayVal = Number.Nan;
                if (overlayProp) {
                    if (overlayProp.name) {
                        //TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                        var overlaySubProps = overlayProp.name.split(" --> ");
                        var prop_dict = feature.properties;
                        for (let i = 0; i < overlaySubProps.length; i++) {
                            if (prop_dict==prop_dict && prop_dict!=null && typeof prop_dict === 'object') {
                                if (overlaySubProps[i] in prop_dict) {
                                    var prop_dict = prop_dict[overlaySubProps[i]];
                                    var overlayVal = prop_dict;
                                } else {
                                    prop_dict = Number.Nan;
                                    var overlayVal = Number.Nan;
                                }
                            }
                        }
                    } else {
                        var overlayVal = Number.Nan;
                    }
                } else {
                    var overlayVal = Number.Nan;
                }

                if (overlayVal==overlayVal && overlayVal!=null) {
                    if (typeof overlayVal==='number') {
                        style.fillColor = csc(overlayVal);
                    } else if ('unique' in overlayBounds) {
                        overlayVal = overlayBounds.unique.indexOf(overlayVal);
                        style.fillColor = csc[overlayVal];
                    } else {
                        style.fillColor = "f00";
                    }
                } else {
                    style.fillColor = "f00";
                }

                style.fillOpacity = fillOpacity;
                if (feature.properties.name in lineColor) {
                    style.color = lineColor[feature.properties.name];
                } else {
                    style.color = 'white';
                }

                return style;
                }
                """,
            name = 'featureStyle'
        )

        self.js_namespace.add(
            src = """
                function(feature,context){
                const {overlayBounds, overlayProp, fillOpacity, lineColor, filterVals, lineWidth, colorMap} = context.hideout;

                var returnFeature = true;
                if (filterVals) {
                    for (let i = 0; i < filterVals.length; i++) {
                        // Iterating through filterVals list
                        var filter = filterVals[i];
                        if (filter.name) {
                            //TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                            var filterSubProps = filter.name.split(" --> ");
                            var prop_dict = feature.properties;
                            for (let j = 0; j < filterSubProps.length; j++) {
                                if (prop_dict==prop_dict && prop_dict!=null && typeof prop_dict==='object') {
                                    if (filterSubProps[j] in prop_dict) {
                                        var prop_dict = prop_dict[filterSubProps[j]];
                                        var testVal = prop_dict;
                                    } else {
                                        prop_dict = Number.Nan;
                                        returnFeature = returnFeature & false;
                                    }
                                }
                            }
                        }
                            
                        if (filter.range && returnFeature) {
                            if (typeof filter.range[0]==='number') {
                                if (testVal < filter.range[0]) {
                                    returnFeature = returnFeature & false;
                                }
                                if (testVal > filter.range[1]) {
                                    returnFeature = returnFeature & false;
                                }
                            } else {
                                if (filter.range.includes(testVal)) {
                                    returnFeature = returnFeature & true;
                                } else {
                                    returnFeature = returnFeature & false;
                                }
                            }
                        }
                    }
                }  else {
                    return returnFeature;
                }              
                return returnFeature;
                }
                """,
            name = 'featureFilter'
        )

        self.js_namespace.add(
            src = """
            function(e,ctx){
                ctx.setProps({
                    data: e.latlng
                });
            }
            """,
            name = 'sendPosition'
        )

        self.js_namespace.dump(
            assets_folder = self.assets_folder
        )

    def load(self,component_prefix:int):

        self.component_prefix = component_prefix

        self.title = 'Large Multi-Frame Slide Map'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

        self.large_map_callbacks()
    
    def large_map_callbacks(self):

        self.blueprint.clientside_callback(
            """
            async function(map_bounds,slide_information,current_zoom){
                // Prevent Update at initialization
                if (slide_information[0]==undefined){
                    throw window.dash_clientside.PreventUpdate;
                } else if (current_zoom[0]==undefined){
                    throw window.dash_clientside.PreventUpdate;
                }

                // Run annotation region request, return annotations within that region
                // Reading in map-slide-information
                var map_slide_information = JSON.parse(slide_information);
                var scaled_map_bounds = [
                    Math.floor(map_bounds[0][1][0] / map_slide_information.y_scale),
                    Math.floor(map_bounds[0][0][1] / map_slide_information.x_scale),
                    Math.floor(map_bounds[0][0][0] / map_slide_information.y_scale),
                    Math.floor(map_bounds[0][1][1] / map_slide_information.x_scale)
                ];

                // Checking if the maps current zoom level is above the minimum zoom setting
                if (current_zoom[0] < map_slide_information.minZoom){
                    throw window.dash_clientside.PreventUpdate;
                }
                
                // This is for DSA slides, annotations are only accessible for regions on an individual basis
                // and then must be converted to GeoJSON.
                var annotations_list = [];
                var annotations_str = [];
                if ("api_url" in map_slide_information.slide_info){
                    for (let ann = 0; ann<map_slide_information.annotations_metadata.length; ann++) {
                        var annotation = map_slide_information.annotations_metadata[ann];

                        try {
                            let ann_url = map_slide_information.annotations_region_url + annotation._id+"?top="+scaled_map_bounds[0]+"&left="+scaled_map_bounds[1]+"&bottom="+scaled_map_bounds[2]+"&right="+scaled_map_bounds[3]
                            var ann_response = await fetch(
                                ann_url, {
                                method: 'GET',
                                headers: {
                                    'Content-Type': 'application/json'    
                                }
                            });

                            if (!ann_response.ok) {
                                throw new Error(`Oh no! Error encountered: ${ann_response.status}`)
                            }

                            // Scaling coordinates of returned annotations
                            var new_annotations = await ann_response.json();
                            let new_geojson = {
                                "type": "FeatureCollection",
                                "features": [],
                                "properties": {
                                    "name": annotation.annotation.name,
                                    "_id": annotation._id
                                }
                            };
                            for (let i = 0; i<new_annotations.annotation.elements.length; i++){
                                let new_feature = {
                                    "type": "Feature",
                                    "properties": new_annotations.annotation.elements[i].user,
                                    "geometry": {
                                        "type": "Polygon",
                                        "coordinates": [[]]
                                    }
                                };

                                new_feature["properties"]["id"] = i;
                                new_feature["properties"]["cluster"] = false;

                                for (let j = 0; j<new_annotations.annotation.elements[i].points.length;j++){
                                    let these_coords = new_annotations.annotation.elements[i].points[j];
                                    new_feature.geometry.coordinates[0].push([these_coords[0] * map_slide_information.x_scale, these_coords[1] * map_slide_information.y_scale]);
                                }
                                new_geojson.features.push(new_feature);
                            }

                            annotations_str.push(new_geojson);
                            annotations_list.push(new_geojson);
                        } catch (error) {
                            console.error(error.message);
                        }
                    }
                } else {
                    // General case.
                    try {
                        let ann_url = map_slide_information.annotations_region_url+"?top="+scaled_map_bounds[0]+"&left="+scaled_map_bounds[1]+"&bottom="+scaled_map_bounds[2]+"&right="+scaled_map_bounds[3]
                        var ann_response = await fetch(
                            ann_url, {
                            method: 'GET',
                            headers: {
                                'Content-Type': 'application/json'    
                            }
                        });

                        if (!ann_response.ok) {
                            throw new Error(`Oh no! Error encountered: ${ann_response.status}`)
                        }

                        // Scaling coordinates of returned annotations
                        var new_annotations = await ann_response.json();
                        // Thanks Suhas
                        const scale_geoJSON = (data, name, id, x_scale, y_scale) => {
                            return {
                                ...data,
                                properties: {
                                    name: name,
                                    _id: id
                                },
                                features: data.features.map(feature => ({
                                    ...feature,
                                    geometry: {
                                        ...feature.geometry,
                                        coordinates: feature.geometry.coordinates.map(axes => 
                                            axes.map(([x, y]) => [x * x_scale, y * y_scale])
                                        )
                                    }
                                }))
                            }
                        }

                        for (let ann=0; ann<new_annotations.length; ann++){
                            let annotation = map_slide_information.annotations_metadata[ann];
                            let new_geojson = scale_geoJSON(new_annotations[ann], annotation.name, annotation._id, map_slide_information.x_scale, map_slide_information.y_scale);
                            
                            annotations_str.push(new_geojson);
                            annotations_list.push(new_geojson);
                        }

                    } catch (error) {
                        console.error(error.message);
                    }                
                }

                return [annotations_list, [JSON.stringify(annotations_str)]];
            }
            """,
            [
                Output({'type': 'feature-bounds','index': ALL},'data'),
                Output({'type': 'map-annotations-store','index':ALL},'data')
            ],
            Input({'type': 'slide-map','index': ALL},'bounds'),
            [
                State({'type':'map-slide-information','index': ALL},'data'),
                State({'type': 'slide-map','index': ALL},'zoom')
            ],
            prevent_initial_call = True
        )

    def update_slide(self, slide_selected, vis_data):
        
        if not any([i['value'] or i['value']==0 for i in ctx.triggered]):
            raise exceptions.PreventUpdate

        vis_data = json.loads(vis_data)
        new_slide = vis_data['current'][get_pattern_matching_value(slide_selected)]

        # Getting data from the tileservers:
        if not 'current_user' in vis_data or not 'api_url' in new_slide:
            new_tile_url = new_slide['tiles_url']
            new_annotations_url = new_slide['annotations_url']
            new_annotations_region_url = new_slide['annotations_region_url']
            new_annotations_metadata_url = new_slide['annotations_metadata_url']
            new_metadata_url = new_slide['metadata_url']
        else:
            new_tile_url = new_slide['tiles_url']+f'?token={vis_data["current_user"]["token"]}'
            new_annotations_url = new_slide['annotations_url']+f'?token={vis_data["current_user"]["token"]}'
            new_annotations_metadata_url = new_slide['annotations_metadata_url']+f'?token={vis_data["current_user"]["token"]}'
            new_metadata_url = new_slide['metadata_url']+f'?token={vis_data["current_user"]["token"]}'

        new_metadata = requests.get(new_metadata_url).json()
        new_annotations_metadata = requests.get(new_annotations_metadata_url).json()
        new_tile_size = new_metadata['tileHeight']
        x_scale, y_scale = self.get_scale_factors(new_metadata)

        annotation_names = []
        image_overlays = []
        initial_anns = []
        for a in new_annotations_metadata:
            if 'annotation' in a:
                annotation_names.append(a['annotation']['name'])
                initial_anns.append({
                    'type': 'FeatureCollection', 
                    'properties': {'name': a['annotation']['name'], '_id': a['_id']},
                    'features': []
                    })
            elif 'name' in a:
                annotation_names.append(a['name'])
                initial_anns.append({
                    'type': 'FeatureCollection',
                    'properties': {'name': a['name'],'_id': a['_id']},
                    'features': []
                })
            elif 'image_path' in a:
                image_overlays.append(a)

        # Creating annotation layers
        new_layer_children = []
        for ann_idx, ann in enumerate(annotation_names):
            new_layer_children.append(
                dl.Overlay(
                    dl.LayerGroup(
                        dl.GeoJSON(
                            data = {
                                "type": "FeatureCollection",
                                "features": []
                            },
                            format = 'geojson',
                            id = {'type': f'{self.component_prefix}-feature-bounds','index': ann_idx},
                            options = {
                                'style': self.js_namespace("featureStyle")
                            },
                            filter = self.js_namespace("featureFilter"),
                            hideout = {
                                'overlayBounds': {},
                                'overlayProp': {},
                                'fillOpacity': 0.5,
                                'lineColor': {
                                    k: '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255))
                                    for k in annotation_names
                                },
                                'filterVals': [],
                                'colorMap': 'blue->red'
                            },
                            hoverStyle = arrow_function(
                                {
                                    'weight': 5,
                                    'color': '#9caf00',
                                    'dashArray':''
                                }
                            ),
                            zoomToBounds = False,
                            children = [
                                dl.Popup(
                                    id = {'type': f'{self.component_prefix}-feature-popup','index': ann_idx},
                                    autoPan = False,
                                )
                            ]
                        )
                    ),
                    name = ann, checked = True, id = {'type':f'{self.component_prefix}-feature-overlay','index':np.random.randint(0,1000)}
                )
            )

        # Adding image annotations
        #TODO: Make these region specific
        for img_idx, img in enumerate(image_overlays):

            # miny, minx, maxy, maxx (a.k.a. minlat, minlng, maxlat, maxlng)
            scaled_image_bounds = [
                [img['image_bounds'][1]*y_scale,
                 img['image_bounds'][0]*x_scale],
                [img['image_bounds'][3]*y_scale,
                 img['image_bounds'][2]*x_scale]
            ]
            # Creating data: path for image
            with open(img['image_path'],'rb') as f:
                new_image_path = f'data:image/{img["image_path"].split(".")[-1]};base64,{base64.b64encode(f.read()).decode("ascii")}'
                f.close()

            image_overlay_popup = self.get_image_overlay_popup(img, img_idx)

            new_layer_children.extend([
                dl.ImageOverlay(
                    url = new_image_path,
                    opacity = 0.5,
                    interactive = True,
                    bounds = scaled_image_bounds,
                    id = {'type': f'{self.component_prefix}-image-overlay','index': img_idx},
                    children = [
                        image_overlay_popup
                    ]
                ),
                dl.LayerGroup(
                    id = {'type': f'{self.component_prefix}-image-overlay-mover-layergroup','index': img_idx},
                    children = []
                )
            ])

        # For MultiFrameSlideMap, add frame BaseLayers and RGB layer (if present)
        if isinstance(self,MultiFrameSlideMap):
            new_layer_children.extend(self.process_frames(new_metadata, new_tile_url))
            new_tile_layer = dl.TileLayer(
                id = {'type': f'{self.component_prefix}-map-tile-layer','index': np.random.randint(0,1000)},
                url = '',                
                tileSize=new_tile_size,
                maxNativeZoom=new_metadata['levels']-2 if new_metadata['levels']>=2 else 0,
                minZoom = 0
            )
        else:
            new_tile_layer = dl.TileLayer(
                id = {'type': f'{self.component_prefix}-map-tile-layer','index': np.random.randint(0,1000)},
                url = new_tile_url,
                tileSize = new_tile_size,
                maxNativeZoom=new_metadata['levels']-2 if new_metadata['levels']>=2 else 0,
                minZoom = 0
            )

        new_slide_info = {}
        new_slide_info['x_scale'] = x_scale
        new_slide_info['y_scale'] = y_scale
        new_slide_info['image_overlays'] = image_overlays
        new_slide_info['slide_info'] = new_slide
        new_slide_info['tiles_url'] = new_tile_url
        new_slide_info['annotations_url'] = new_annotations_url
        new_slide_info['annotations_region_url'] = new_annotations_region_url
        new_slide_info['annotations_metadata'] = new_annotations_metadata
        new_slide_info['minZoom'] = self.min_zoom

        geo_annotations = json.dumps(initial_anns)
        new_slide_info = json.dumps(new_slide_info)

        # Updating manual and generated ROIs divs
        manual_rois = []
        gen_rois = []

        return new_layer_children, manual_rois, gen_rois, geo_annotations, new_tile_layer, new_slide_info

    

#TODO: This can be rewritten as its own embeddable blueprint
class SlideImageOverlay(MapComponent):
    """Image overlay on specific coordinates within a SlideMap

    :param MapComponent: General component class for children of SlideMap
    :type MapComponent: None
    """
    def __init__(self,
                 image_path: str,
                 image_crs: list = [0,0],
                 name: Union[str,None] = None,
                 image_properties: Union[dict,None] = {"None": ""}
                ):
        """Constructor method

        :param image_path: Filepath for image to be overlaid on top of SlideMap
        :type image_path: str
        :param image_crs: Top-left coordinates (x,y) for the image, defaults to [0,0]
        :type image_crs: list, optional
        """

        super().__init__()
        self.image_path = image_path
        self.image_crs = image_crs
        self.image_properties = image_properties
        if name is None:
            self.name = self.image_path.split(os.sep)[-1]
        else:
            self.name = name

        self.image_bounds = self.get_image_bounds()
        self._id = uuid.uuid4().hex[:24]

    def get_image_bounds(self):
        """Get total bounds of image overlay in original CRS (number of pixels)

        :return: List of image bounds in overlay CRS ([minx, miny, maxx, maxy])
        :rtype: list
        """

        read_image = np.uint8(np.array(Image.open(self.image_path)))
        image_shape = np.shape(read_image)

        return self.image_crs + [self.image_crs[0]+image_shape[1], self.image_crs[1]+image_shape[0]]

    def to_dict(self):
        overlay_info_dict = {
            'image_path': self.image_path,
            'image_crs': self.image_crs,
            'image_properties': self.image_properties,
            'image_bounds': self.image_bounds,
            'name': self.name,
            '_id': self._id
        }

        return overlay_info_dict

class ChannelMixer(MapComponent):
    """ChannelMixer component that allows users to select various frames from their image to overlay at the same time with different color (styles) applied.

    :param MapComponent: General component class for children of SlideMap
    :type MapComponent: None
    """
    def __init__(self):
        """Constructor method

        :param image_metadata: Dictionary containing "frames" data for a given image. "frames" here is a list containing channel names and indices.
        :type image_metadata: dict
        :param tiles_url: URL to refer to for accessing tiles (contains /{z}/{x}/{y}). Allows for "style" parameter to be passed. See large-image documentation: https://girder.github.io/large_image/getting_started.html#styles-changing-colors-scales-and-other-properties
        :type tiles_url: str
        """
        super().__init__()

    def __str__(self):
        return 'Channel Mixer'

    def load(self, component_prefix: int):

        self.component_prefix = component_prefix
        self.title = 'Channel Mixer'
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def process_frames(self, image_metadata:dict):
        """Extracting names for each frame for easy reference
        """
        if 'frames' in image_metadata:
            if len(image_metadata['frames'])>0:
                frame_names = [i['Channel'] if 'Channel' in i else f'Frame {idx}' for idx,i in enumerate(image_metadata['frames'])]
            else:
                raise IndexError("No frames found in this image!")
        else:
            raise TypeError("Image is not multi-frame")
        
        return frame_names

    def update_layout(self, session_data: dict, use_prefix: bool):
        """Updating layout of ChannelMixer component

        :param session_data: Current data relating to visualization session
        :type session_data: dict
        :param use_prefix: Whether or not this is the initial load of the component
        :type use_prefix: bool
        :return: ChannelMixer component
        """
        
        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        html.H3('Channel Mixer')
                    ]),
                    html.Hr(),
                    dbc.Row(
                        'Select one or more channels and colors to view at the same time.'
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Label('Select Channels below: ',html_for = {'type':'channel-mixer-drop','index': 0}),
                        style = {'marginBottom': '5px'}
                    ),
                    dbc.Row([
                        dcc.Dropdown(
                            id = {'type': 'channel-mixer-drop','index': 0},
                            options = [],
                            value = [],
                            multi = True,
                            disabled = False
                        )
                    ]),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'channel-mixer-color-parent','index': 0},
                            children = [],
                            style = {'marginTop': '5px','marginBottom': '5px'}
                        )
                    ]),
                    dbc.Row([
                        dbc.Button(
                            'Overlay Channels!',
                            id = {'type': 'channel-mixer-butt','index': 0},
                            className = 'd-grid col-12 mx-auto',
                            disabled = False,
                            n_clicks = 0
                        )
                    ])
                ])
            ])
        ])

        if use_prefix:
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(layout)

        return layout

    def gen_layout(self, session_data:dict):
        """Generating layout for ChannelMixer component
        """
        self.blueprint.layout = self.update_layout(session_data, use_prefix=False)

    def get_callbacks(self):
        """Initializing callbacks and adding to DashBlueprint
        """

        # Updating based on new slide selection
        self.blueprint.callback(
            [
                Input({'type': 'slide-select-drop','index':ALL},'value')
            ],
            [
                Output({'type': 'channel-mixer-drop','index': ALL},'options'),
                Output({'type': 'channel-mixer-color-parent','index': ALL},'children')
            ],
            [
                State('anchor-vis-store','data')
            ]
        )(self.update_slide)

        # Creating new color selector for a selected channel
        self.blueprint.callback(
            [
                Input({'type': 'channel-mixer-drop','index':ALL},'value')
            ],
            [
                State({'type': 'channel-mixer-tab','index': ALL},'label'),
                State({'type': 'channel-mixer-tab','index': ALL},'label_style')
            ],
            [
                Output({'type': 'channel-mixer-color-parent','index': ALL},'children')
            ]
        )(self.add_color_selector_tab)

        self.blueprint.callback(
            [
                Input({'type': 'channel-mixer-color','index': MATCH},'value')
            ],
            [
                Output({'type': 'channel-mixer-tab','index': MATCH},'label_style')
            ]
        )(self.update_tab_style)

        self.blueprint.callback(
            [
                Input({'type': 'channel-mixer-butt','index':ALL},'n_clicks')
            ],
            [
                State({'type': 'channel-mixer-tab','index': ALL},'label'),
                State({'type': 'channel-mixer-tab','index': ALL},'label_style'),
                State({'type': 'channel-mixer-drop','index': ALL},'options'),
                State({'type': 'map-slide-information','index': ALL},'data')
            ],
            [
                Output({'type': 'tile-layer','index': ALL},'url')
            ]
        )(self.update_channel_mix)

    def update_slide(self, selected_slide, vis_data):
        """Updating component data when a new slide is selected

        :param selected_slide: New slide
        :type selected_slide: list
        :param vis_data: Data relating to current visualization session
        :type vis_data: str
        """

        if not any([i['value'] or i['value']==0 for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        vis_data = json.loads(vis_data)
        new_slide = vis_data['current'][get_pattern_matching_value(selected_slide)]

        if not 'current_user' in vis_data:
            new_metadata = requests.get(new_slide['metadata_url']).json()
        else:
            new_metadata = requests.get(new_slide['metadata_url']+f'?token={vis_data["current_user"]["token"]}').json()

        new_frame_list = self.process_frames(new_metadata)
        new_color_selector_children = []

        return [new_frame_list], [new_color_selector_children]

    def add_color_selector_tab(self, channel_mix_values: Union[list,None], current_channels:Union[list,None], current_colors: Union[list,None]):
        """Add a new color selector tab to channel-mixer-parent for selecting overlaid channel color

        :param channel_mix_values: Selected list of channels to overlay
        :type channel_mix_values: list
        :param current_channels: Current set of overlaid channels (names)
        :type current_channels: list
        :param current_colors: Current set of overlaid channels (colors)
        :type current_colors: list
        """

        channel_mix_values = get_pattern_matching_value(channel_mix_values)
        if current_channels is None:
            current_channels = []
        
        channel_mix_tabs = []
        c = None
        if not channel_mix_values is None:
            for c_idx, c in enumerate(channel_mix_values):
                if not c in current_channels:
                    channel_tab = dbc.Tab(
                        id = {'type': f'{self.component_prefix}-channel-mixer-tab','index': c_idx},
                        tab_id = c.lower().replace(' ','-'),
                        label = c,
                        activeTabClassName='fw-bold fst-italic',
                        label_style = {'color': 'rgb(0,0,0,255)'},
                        children = [
                            dmc.ColorPicker(
                                id = {'type': f'{self.component_prefix}-channel-mixer-color','index': c_idx},
                                format = 'rgba',
                                value = 'rgba(255,255,255,255)',
                                fullWidth=True
                            )
                        ]
                    )
                else:
                    channel_tab = dbc.Tab(
                        id = {'type': f'{self.component_prefix}-channel-mixer-tab','index': c_idx},
                        tab_id = c.lower().replace(' ','-'),
                        label = c,
                        activeTabClassName='fw-bold fst-italic',
                        label_style = current_colors[c_idx],
                        children = [
                            dmc.ColorPicker(
                                id = {'type': f'{self.component_prefix}-channel-mixer-color','index': c_idx},
                                format='rgba',
                                value = current_colors[c_idx]['color'],
                                fullWidth = True
                            )
                        ]
                    )

                channel_mix_tabs.append(channel_tab)

        channel_tabs = dbc.Tabs(
            id = {'type': f'{self.component_prefix}-channel-mixer-tabs','index': 0},
            children = channel_mix_tabs,
            active_tab = c.lower().replace(' ','-') if not c is None else []
        )

        return [channel_tabs]

    def update_tab_style(self, color_select):
        """Updating color of tab label based on selection

        :param color_select: "rgba" formatted color selection
        :type color_select: str
        """
        if not ctx.triggered:
            raise exceptions.PreventUpdate
        
        color_select = get_pattern_matching_value(color_select)
        return {'color': color_select}
    
    def update_channel_mix(self, butt_click:list, current_channels:list,current_colors:list, frame_names: list, slide_info:list):
        """Updating urls of all tile layers to include selected overlay channels

        :param butt_click: Button clicked to update channel mix
        :type butt_click: list
        :param current_channels: Names of channels to overlay
        :type current_channels: list
        :param current_colors: Colors of channels to overlay
        :type current_colors: list
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        slide_info = json.loads(get_pattern_matching_value(slide_info))
        frame_names = get_pattern_matching_value(frame_names)
        
        style_dict = {"bands": []}
        for c in range(len(current_channels)):
            
            # Checking that the alpha channel is uint8
            rgba_val = current_colors[c]['color']
            alpha_val = rgba_val.split(', ')[-1].replace(')','')

            if not alpha_val=='255':
                current_colors[c]['color'] = rgba_val.replace(alpha_val,str(int(255*float(alpha_val))))
            
            style_dict['bands'].append(
                {
                    "palette": ["rgba(0,0,0,0)",current_colors[c]["color"]],
                    "framedelta": frame_names.index(current_channels[c])
                }
            )

        styled_urls = []
        if all([i in frame_names for i in ['red','green','blue']]):
            # There can be an RGB image by default
            rgb_style_dict = {
                "bands": [
                    {
                        "palette": ["rgba(0,0,0,0)",'rgba('+','.join(['255' if i==c_idx else '0' for i in range(3)]+['0'])+')'],
                        "framedelta": frame_names.index(c)
                    }
                    for c_idx,c in enumerate(['red','green','blue'])
                ]
            }

        else:
            rgb_style_dict = None

        styled_urls = []
        for f in frame_names:
            f_dict = {"bands": [
                    {
                        "palette": ["rgba(0,0,0,0)","rgba(255,255,255,255)"],
                        "framedelta": frame_names.index(f)
                    }
                ]
            }

            if '?token' in slide_info['tiles_url']:
                start_str = '&'
            else:
                start_str = '?'
            styled_urls.append(
                slide_info['tiles_url']+f'{start_str}style='+json.dumps({"bands":f_dict["bands"]+style_dict["bands"]})
            )

        if not rgb_style_dict is None:
            if '?token' in slide_info['tiles_url']:
                start_str = '&'
            else:
                start_str = '?'

            styled_urls.append(
                slide_info['tiles_url']+f'{start_str}style='+json.dumps({"bands":rgb_style_dict["bands"]+style_dict["bands"]})
            )

        return styled_urls



