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

from PIL import Image

#os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, dash_table, Patch, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashProxy, DashBlueprint, html, Input, Output, State
from dash_extensions.javascript import assign, arrow_function, Namespace

# fusion-tools imports
from fusion_tools.tileserver import TileServer
from fusion_tools.utils.shapes import find_intersecting, spatially_aggregate
from fusion_tools.visualization.vis_utils import get_pattern_matching_value



class MapComponent:
    """General class for components added to SlideMap
        For more information see dash-leaflet: https://www.dash-leaflet.com/

    """
    pass

class SlideMap(MapComponent):
    """This is a general high-resolution tiled image component. 
    

    :param MapComponent: General class for components added to SlideMap
    :type MapComponent: None
    """
    def __init__(self,
                 tile_server: TileServer,
                 annotations: Union[dict,list,None]
                ):
        """Constructor method

        :param tile_server: Whichever TileServer is currently being hosted. For remote DSA sources, this is a DSATileServer while for local images this would be LocalTileServer
        :type tile_server: TileServer
        :param annotations: Initial GeoJSON formatted annotations added to the map
        :type annotations: Union[dict,list,None]
        """
        
        self.tiles_url = tile_server.tiles_url
        self.image_metadata = tile_server.tiles_metadata
        
        self.x_scale, self.y_scale = self.get_scale_factors()
        self.annotations = annotations
        
        self.assets_folder = os.getcwd()+'/.fusion_assets/'
        # Add Namespace functions here:
        self.get_namespace()

        self.initialize_map()

    def initialize_map(self):

        annotations, annotation_components, image_overlays = self.process_annotations()

        self.title = 'Slide Map'
        self.blueprint = DashBlueprint()        

        frame_layers = []

        self.blueprint.layout = self.gen_layout(annotations, annotation_components, image_overlays, frame_layers)

        # Add callback functions here
        self.get_callbacks()

    def get_scale_factors(self):
        """Function used to initialize scaling factors applied to GeoJSON annotations to project annotations into the SlideMap CRS (coordinate reference system)

        :return: x and y (horizontal and vertical) scale factors applied to each coordinate in incoming annotations
        :rtype: float
        """

        base_dims = [
            self.image_metadata['sizeX']/(2**(self.image_metadata['levels']-1)),
            self.image_metadata['sizeY']/(2**(self.image_metadata['levels']-1))
        ]

        x_scale = base_dims[0] / self.image_metadata['sizeX']
        y_scale = -(base_dims[1] / self.image_metadata['sizeY'])

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
                                                html.P(f'Path: {st.image_path}'),
                                            ]
                                        ),
                                        dbc.AccordionItem(
                                            title = 'Properties',
                                            children = [
                                                f'{k}: {v}'
                                                for k,v in st.image_properties.items()
                                            ]
                                        ),
                                        dbc.AccordionItem(
                                            title = 'Transparency',
                                            children = [
                                                dbc.Label(
                                                    'Transparency Slider:',
                                                    html_for = {'type': 'image-overlay-transparency','index': st_idx},
                                                    style = {'marginBottom': '5px'}
                                                ),
                                                dcc.Slider(
                                                    id = {'type': 'image-overlay-transparency','index': st_idx},
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
                                                            id = {'type': 'image-overlay-position-butt','index': st_idx},
                                                            n_clicks = 0,
                                                            className = 'd-grid col-12 mx-auto'
                                                        )
                                                    )
                                                ]),
                                                dbc.Row([
                                                    dbc.Col([
                                                        dbc.Button(
                                                            'Save Position',
                                                            id = {'type': 'image-overlay-save-position','index': st_idx},
                                                            n_clicks = 0,
                                                            className = 'd-grid col-12 mx-auto',
                                                            color = 'secondary'
                                                        ),
                                                        dcc.Download(
                                                            id = {'type': 'image-overlay-save-position-download','index': st_idx}
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

    def process_annotations(self):
        """Process incoming annotations and generate dl.Overlay components applied to the SlideMap

        :return: List of dl.Overlay components containing dl.GeoJSON objects where "data" contains the corresponding scaled GeoJSON information 
        :rtype: list
        """

        annotation_components = []
        image_overlays = []
        annotations_list = []
        if not self.annotations is None:
            if type(self.annotations)==dict:
                self.annotations = [self.annotations]
            
            for st_idx,st in enumerate(self.annotations):
                if type(st)==dict:
                    # Scale annotations to fit within base tile dimensions
                    st = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]*self.x_scale,c[1]*self.y_scale, c[2]), g), st)

                    if 'properties' not in st:
                        st['properties'] = {}
                        if 'name' in st['features'][0]['properties']:
                            st['properties']['name'] = st['features'][0]['properties']['name']
                        else:
                            st['properties']['name'] = f'Structure {st_idx}'

                        st['properties']['_id'] = uuid.uuid4().hex[:24]
                    else:
                        if not 'name' in st['properties']:
                            if 'name' in st['features'][0]['properties']:
                                st['properties']['name'] = st['features'][0]['properties']['name']
                            else:
                                st['properties']['name'] = f'Structure {st_idx}'

                        if not '_id' in st['properties']:
                            st['properties']['_id'] = uuid.uuid4().hex[:24]
                        
                    
                    annotations_list.append(st)

                    annotation_components.append(
                        dl.Overlay(
                            dl.LayerGroup(
                                dl.GeoJSON(
                                    data = dlx.geojson_to_geobuf(st),
                                    format = 'geobuf',
                                    id = {'type': 'feature-bounds','index': st_idx},
                                    options = {
                                        'style': self.js_namespace("featureStyle")
                                    },
                                    filter = self.js_namespace("featureFilter"),
                                    hideout = {
                                        'overlayBounds': {},
                                        'overlayProp': {},
                                        'fillOpacity': 0.5,
                                        'lineColor': {st['properties']['name']: '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255))},
                                        'filterVals': [],
                                        'lineWidth': 5,
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
                                            id = {'type': 'feature-popup','index': st_idx},
                                            autoPan = False,
                                        )
                                    ]
                                )
                            ),
                            name = st['properties']['name'], checked = True, id = {'type':'feature-overlay','index':st_idx}
                        )
                    )

                elif type(st)==SlideImageOverlay:
                    
                    scaled_image_bounds = [
                        [st.image_bounds[1]*self.y_scale, st.image_bounds[0]*self.x_scale],
                        [st.image_bounds[3]*self.y_scale, st.image_bounds[2]*self.x_scale]
                    ]

                    # Creating data: path for image
                    with open(st.image_path,'rb') as f:
                        new_image_path = f'data:image/{st.image_path.split(".")[-1]};base64,{base64.b64encode(f.read()).decode("ascii")}'
                        f.close()

                    image_overlay_popup = self.get_image_overlay_popup(st, st_idx)

                    image_overlays.extend([
                        dl.ImageOverlay(
                            url = new_image_path,
                            opacity = 0.5,
                            interactive = True,
                            bounds = scaled_image_bounds,
                            id = {'type': 'image-overlay','index': st_idx},
                            children = [
                                image_overlay_popup
                            ],
                        ),
                        dl.LayerGroup(
                            id = {'type': 'image-overlay-mover-layergroup','index': st_idx},
                            children = []
                        )
                    ])

        return annotations_list, annotation_components, image_overlays

    def gen_layout(self, annotations, annotation_components, image_overlays, frame_layers):
        """Generating SlideMap layout

        :return: Div object containing interactive components for the SlideMap object.
        :rtype: dash.html.Div.Div
        """

        layout = html.Div([
            dl.Map(
                id = {'type': 'slide-map','index': 0},
                crs = 'Simple',
                center = [-self.image_metadata['tileWidth']/2,self.image_metadata['tileWidth']/2],
                zoom = 1,
                style = {'height': '90vh','width': '100%','margin': 'auto','display': 'inline-block'},
                children = [
                    dl.TileLayer(
                        id = {'type': 'map-tile-layer','index': 0},
                        url = self.tiles_url,
                        tileSize=self.image_metadata['tileWidth'],
                        maxNativeZoom=self.image_metadata['levels']-1,
                        minZoom = 0
                    ),
                    dl.FullScreenControl(
                        position = 'upper-left'
                    ),
                    dl.FeatureGroup(
                        id = {'type': 'edit-feature-group','index': 0},
                        children = [
                            dl.EditControl(
                                id = {'type': 'edit-control','index': 0},
                                draw = dict(polyline=False, line=False, circle = False, circlemarker=False, marker = False),
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
                            id = {'type': 'map-annotations-store','index': 0},
                            data = json.dumps(annotations),
                            storage_type = 'memory'
                        )
                    ),
                    dl.LayersControl(
                        id = {'type': 'map-layers-control','index': 0},
                        children = frame_layers + annotation_components
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
                        id = {'type': 'upload-shape','index':0},
                        position = 'top-left'
                    ),
                    html.Div(
                        id = {'type': 'map-marker-div','index': 0},
                        children = []
                    ),
                    *image_overlays
                ]
            ),
            dbc.Modal(
                id = {'type': 'upload-shape-modal','index':0},
                is_open = False,
                children = [
                    html.Div(
                        dcc.Upload(
                            children = [
                                'Drag and Drop or ',
                                html.A('Select a File')
                            ], 
                            id = {'type': 'upload-shape-data','index':0},
                            style={'width': '100%','height': '60px','lineHeight': '60px','borderWidth': '1px','borderStyle': 'dashed','borderRadius': '5px','textAlign': 'center'}
                        )
                    )
                ]
            )
        ])

        return layout

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
            "fusionTools","default"
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
                        var overlaySubProps = overlayProp.name.split(" --> ");
                        var prop_dict = feature.properties;
                        for (let i = 0; i < overlaySubProps.length; i++) {
                            if (overlaySubProps[i] in prop_dict) {
                                var prop_dict = prop_dict[overlaySubProps[i]];
                                var overlayVal = prop_dict;
                            } else {
                                var overlayVal = Number.Nan;
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
                            var filterSubProps = filter.name.split(" --> ");
                            var prop_dict = feature.properties;
                            for (let j = 0; j < filterSubProps.length; j++) {
                                if (filterSubProps[j] in prop_dict) {
                                    var prop_dict = prop_dict[filterSubProps[j]];
                                    var testVal = prop_dict;
                                } else {
                                    returnFeature = returnFeature & false;
                                }
                            }
                        }
                            
                        if (filter.range) {
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

    def get_callbacks(self):
        """Initializing callback functions for interactive components in SlideMap. 
        Adding these callbacks to the DashBlueprint() object enable embedding into other layouts.
        """
        
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
                Output({'type': 'map-layers-control','index': ALL},'children'),
                Output({'type': 'map-annotations-store','index': ALL},'data')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'feature-overlay','index': ALL},'name'),
                State({'type': 'base-layer','index': ALL},'children'),
                State({'type': 'base-layer','index': ALL},'name')
            ]
        )(self.add_manual_roi)

        # Image overlay transparency adjustment
        self.blueprint.callback(
            [
                Input({'type': 'image-overlay-transparency','index': MATCH},'value')
            ],
            [
                Output({'type': 'image-overlay','index': MATCH},'opacity')
            ]
        )(self.update_image_overlay_transparency)

        # Creating a draggable marker to move an image overlay
        self.blueprint.callback(
            [
                Input({'type':'image-overlay-position-butt','index': MATCH},'n_clicks')
            ],
            [
                Output({'type': 'image-overlay-mover-layergroup','index': MATCH},'children'),
                Output({'type': 'image-overlay-position-butt','index': MATCH},'children')
            ],
            [
                State({'type': 'image-overlay','index': MATCH},'bounds'),
                State({'type': 'image-overlay-position-butt','index': MATCH},'children')
            ]
        )(self.gen_image_mover)

        # Moving image overlay to location of draggable marker
        self.blueprint.callback(
            [
                Input({'type': 'image-overlay-mover','index': MATCH},'data')
            ],
            [
                Output({'type': 'image-overlay','index': MATCH},'bounds')
            ],
            [
                State({'type': 'image-overlay','index': MATCH},'bounds')
            ]
        )(self.move_image_overlay)

        # Downloading position of image overlay
        self.blueprint.callback(
            [
                Input({'type': 'image-overlay-save-position','index': MATCH},'n_clicks')
            ],
            [
                Output({'type': 'image-overlay-save-position-download','index': MATCH},'data')
            ],
            [
                State({'type': 'image-overlay','index': MATCH},'bounds')
            ]
        )(self.export_image_overlay_bounds)

        # Downloading manual ROI
        self.blueprint.callback(
            [
                Input({'type': 'download-manual-roi','index': MATCH},'n_clicks')
            ],
            [
                Output({'type': 'download-manual-roi-download','index': MATCH},'data')
            ],
            [
                State({'type': 'edit-control','index': ALL},'geojson')
            ]
        )(self.download_manual_roi)

        # Open upload modal
        self.blueprint.callback(
            [
                Input({'type': 'upload-shape','index': ALL},'n_clicks'),
            ],
            [
                Output({'type': 'upload-shape-modal','index': ALL},'is_open'),
            ],
            [
                State({'type': 'upload-shape-modal','index': ALL},'is_open')
            ]
        )(self.upload_shape)

    def upload_shape(self, upload_clicked, is_open):
        upload_clicked = get_pattern_matching_value(upload_clicked)
        is_open = get_pattern_matching_value(is_open)
        if upload_clicked:
            return [not is_open]

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
        
        def make_dash_table(df:pd.DataFrame):
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

        accordion_children = []
        all_properties = list(clicked['properties'].keys())

        non_dict_properties = [i for i in all_properties if not type(clicked['properties'][i]) in [list,dict]]
        non_dict_prop_list = {'Property': non_dict_properties, 'Value': [clicked['properties'][i] for i in non_dict_properties]}

        accordion_children.append(
            dbc.AccordionItem([
                html.Div([
                    make_dash_table(pd.DataFrame(non_dict_prop_list))
                ])
            ], title = 'Properties')
        )


        # Now loading the dict properties as sub-accordions
        dict_properties = [i for i in all_properties if type(clicked['properties'][i])==dict]
        for d in dict_properties:
            sub_properties = clicked['properties'][d]
            sub_prop_record = [{'SubProperty': i, 'Value': j} for i,j in sub_properties.items() if not type(j) in [list,dict]]

            if len(sub_prop_record)>0:
                accordion_children.append(
                    dbc.AccordionItem([
                        html.Div([
                            make_dash_table(pd.DataFrame.from_records(sub_prop_record))
                        ])
                    ],title = d)
                )

        # If this is a manual ROI then add a download option:
        if 'Manual' in clicked['properties']['name']:
            clicked_idx = int(float(clicked['properties']['name'].split(' ')[-1]))
            accordion_children.append(
                dbc.AccordionItem([
                    html.Div([
                        dbc.Button(
                            'Download Shape',
                            id = {'type': 'download-manual-roi','index': clicked_idx},
                            n_clicks = 0,
                            className = 'd-grid col-12 mx-auto'
                        ),
                        dcc.Download(
                            id = {'type': 'download-manual-roi-download','index': clicked_idx}
                        )
                    ])
                ],
                title = 'Download Shape')
            )


        popup_div = html.Div(
            dbc.Accordion(
                children = accordion_children
            )
        )

        return popup_div
    
    def make_geojson_layers(self, geojson_list:list, names_list:list, index_list: list) -> list:
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

        #TODO: pass the color list here as well
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
        for st,st_name,st_idx in zip(geojson_list,names_list,index_list):

            annotation_components.append(
                dl.Overlay(
                    dl.LayerGroup(
                        dl.GeoJSON(
                            data = st,
                            #format = 'geobuf',
                            id = {'type': 'feature-bounds','index': st_idx},
                            options = {
                                'style': self.js_namespace("featureStyle")
                            },
                            filter = self.js_namespace("featureFilter"),
                            hideout = {
                                'overlayBounds': {},
                                'overlayProp': {},
                                'fillOpacity': 0.5,
                                'lineColor': {st_name: '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255))},
                                'filterVals': []
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
                                    id = {'type': 'feature-popup','index': st_idx},
                                    autoPan = False,
                                )
                            ]
                        )
                    ),
                    name = st_name, checked = True, id = {'type':'feature-overlay','index':st_idx}
                )
            )

        return annotation_components

    def add_manual_roi(self,new_geojson:list, uploaded_shape: list, current_annotations:list,annotation_names: list, frame_layers:list, frame_layer_names:list) -> list:
        """Adding a manual region of interest (ROI) to the SlideMap using dl.EditControl() tools including polygon, rectangle, and markers.

        :param new_geojson: Incoming GeoJSON object that is emitted by dl.EditControl() following annotation on SlideMap
        :type new_geojson: list
        :param current_annotations: Initial annotations added to the map on initialization
        :type current_annotations: list
        :param annotation_names: Names for each annotation layer on the slide map
        :type annotation_names: list
        :param frame_layers: Frame layers for multi-frame visualization
        :type frame_layers: list
        :param frame_layer_names: Names for each frame layer
        :type frame_layer_names: list
        :raises exceptions.PreventUpdate: new_geojson input is None
        :raises exceptions.PreventUpdate: No new features are added, this can occur after deletion of previous manual ROIs.
        :return: List of new children to dl.LayerControl() consisting of overlaid GeoJSON components.
        :rtype: list
        """
        

        uploaded_shape = get_pattern_matching_value(uploaded_shape)
        new_geojson = get_pattern_matching_value(new_geojson)
        current_annotations = json.loads(get_pattern_matching_value(current_annotations))

        # All but the last one which holds the manual ROIs
        initial_annotations = [i for i in current_annotations if not 'Manual' in i['properties']['name']]
        # Current manual rois (used for determining if a new ROI has been created/edited)
        manual_roi_idxes = [0]+[int(i.split(' ')[-1]) for i in annotation_names if 'Manual' in i]
        manual_rois = [i for i in current_annotations if 'Manual' in i['properties']['name']]

        # Initializing layers with partial update object
        new_children = Patch()
        added_rois = []
        added_roi_names = []
        deleted_rois = []

        if ctx.triggered_id['type']=='edit-control':
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
                    
                    manual_roi_idxes.append(max(manual_roi_idxes)+1)
                    
                    # Aggregate if any initial annotations are present
                    if len(initial_annotations)>0:
                        # Spatial aggregation performed just between individual manual ROIs and initial annotations (no manual ROI to manual ROI aggregation)
                        new_roi = spatially_aggregate(new_roi, initial_annotations)

                    added_rois.append(new_roi)
                    added_roi_names.append(new_roi_name)

        elif ctx.triggered_id['type']=='upload-shape-data':
            if not uploaded_shape is None:
                uploaded_roi = json.loads(base64.b64decode(uploaded_shape.split(',')[-1]).decode())
                uploaded_roi = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]*self.x_scale,c[1]*self.y_scale),g),uploaded_roi)

                # Checking if there is a name or _id property:
                if 'properties' in uploaded_roi:
                    if 'name' in uploaded_roi['properties']:
                        if 'Manual' in uploaded_roi['properties']['name']:
                            uploaded_roi['properties']['name'] = uploaded_roi['properties']['name'].replace('Manual','Upload')
                    
                    uploaded_roi['properties']['_id'] = uuid.uuid4().hex[:24]

                else:
                    uploaded_roi['properties'] = {
                        'name': f'Upload {len([i for i in annotation_names if "Upload" in i])+1}',
                        '_id': uuid.uuid4().hex[:24]
                    }

                # Aggregate if any initial annotations are present
                new_roi_name = uploaded_roi['properties']['name']
                if len(initial_annotations)>0:
                    # Spatial aggregation performed just between individual manual ROIs and initial annotations (no manual ROI to manual ROI aggregation)
                    new_roi = spatially_aggregate(uploaded_roi, initial_annotations)

                added_rois.append(new_roi)
                added_roi_names.append(new_roi_name)
                manual_roi_idxes.append(max(manual_roi_idxes)+1)


        # Checking for deleted manual ROIs
        for m_idx,m in enumerate(manual_rois):
            if not m['features'][0]['geometry'] in [j['geometry'] for j  in new_geojson['features']]:
                deleted_rois.append(m_idx)

        if len(added_rois)>0:
            new_children.extend(self.make_geojson_layers(added_rois,added_roi_names,[len(initial_annotations)+max(manual_roi_idxes)]))
            current_annotations.extend(added_rois)
        
        if len(deleted_rois)>0:
            for d in deleted_rois:
                del new_children[d+len(frame_layers)+len(initial_annotations)]
                del current_annotations[d+len(initial_annotations)]

        annotations_data = json.dumps(current_annotations)

        return [new_children], [annotations_data]

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
        if button_click:
            if button_text=='Move it!':
                
                new_button_text = 'Lock in!'
                mover = dl.DivMarker(
                    id = {'type': 'image-overlay-mover','index': ctx.triggered_id['index']},
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

    def export_image_overlay_bounds(self, button_click, current_position):
        """Exporting position of image overlay

        :param button_click: Export button clicked
        :type button_click: int
        :param current_position: Current position of the image overlay
        :type current_position: list
        :raises exceptions.PreventUpdate: Preventing callback if button isn't clicked
        :return: JSON file containing original image path and current position on the slide 
        :rtype: dict
        """

        if button_click:
            image_overlay_index = ctx.triggered_id['index']

            scaled_position = [
                [current_position[0][1]/self.x_scale, current_position[0][0]/self.y_scale],
                [current_position[1][1]/self.x_scale, current_position[1][0]/self.y_scale]
            ]
            export_data = {
                'content': json.dumps({
                    'imagePath': self.annotations[image_overlay_index].image_path,
                    'imageBounds': scaled_position
                }),
                'filename': "fusion_image_overlay_position.json"
            }

            return export_data
        else:
            raise exceptions.PreventUpdate

    def download_manual_roi(self, button_click, current_manual_geojson):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        manual_roi_feature_index = ctx.triggered_id['index']-1
        manual_roi_geojson = get_pattern_matching_value(current_manual_geojson)['features'][manual_roi_feature_index]

        manual_roi = {
            'type': 'FeatureCollection',
            'features': [
                manual_roi_geojson
            ]
        }

        scaled_manual_roi = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/self.x_scale,c[1]/self.y_scale),g),manual_roi)

        return {'content': json.dumps(scaled_manual_roi),'filename': f'Manual ROI {manual_roi_feature_index+1}.json'}



class MultiFrameSlideMap(SlideMap):
    """MultiFrameSlideMap component, containing an image with multiple frames which are added as additional, selectable dl.TileLayer() components

    :param SlideMap: dl.Map() container where image tiles are displayed.
    :type SlideMap: None
    """
    def __init__(self,
                 tile_server: TileServer,
                 annotations: Union[dict,list,None]
                 ):
        """Constructor method

        :param tile_server: TileServer object in use. For remote DSA tile sources this would be DSATileServer while for local images this would be LocalTileServer
        :type tile_server: TileServer
        :param annotations: Individual or list of GeoJSON formatted annotations to add on top of the MultiFrameSlideMap
        :type annotations: Union[dict,list,None]
        """
        self.frame_layers = []

        super().__init__(tile_server,annotations)
    
    def initialize_map(self):
        
        annotations, annotation_components, image_overlays = super().process_annotations()
        self.title = 'Multi-Frame Slide Map'
        frame_layers = self.process_frames()

        self.blueprint = DashBlueprint()
        self.blueprint.layout = super().gen_layout(annotations, annotation_components,image_overlays, frame_layers)

        super().get_callbacks()

    def gen_layout(self, annotations, annotation_components, image_overlays, frame_layers):
        """Generating layout for MultiFrameSlideMap

        :return: Layout added to DashBlueprint object to be embedded in larger layout.
        :rtype: dash.html.Div.Div
        """
        layout = html.Div(
            dl.Map(
                id = {'type': 'slide-map','index': 0},
                crs = 'Simple',
                center = [-self.image_metadata['tileWidth']/2,self.image_metadata['tileWidth']/2],
                zoom = 1,
                style = {'height': '90vh','width': '100%','margin': 'auto','display': 'inline-block'},
                children = [
                    dl.FullScreenControl(
                        position = 'upper-left'
                    ),
                    dl.FeatureGroup(
                        id = {'type': 'edit-feature-group','index': 0},
                        children = [
                            dl.EditControl(
                                id = {'type': 'edit-control','index': 0},
                                draw = dict(polyline=False, line=False, circle = False, circlemarker=False),
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
                            data = json.dumps(annotations)
                        )
                    ),
                    dl.LayersControl(
                        id = {'type': 'map-layers-control','index': 0},
                        children = frame_layers + annotation_components
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
                    html.Div(
                        id = {'type': 'map-marker-div','index': 0},
                        children = []
                    ),
                    *image_overlays
                ]
            )
        )

        return layout

    def process_frames(self):
        """Create BaseLayer and TileLayer components for each of the different frames present in a multi-frame image
        Also initializes base tile url and styled tile url
        """

        frame_layers = []

        if 'frames' in self.image_metadata:
            if len(self.image_metadata['frames'])>0:
                
                if any(['Channel' in i for i in self.image_metadata['frames']]):
                    frame_names = [i['Channel'] for i in self.image_metadata['frames']]
                else:
                    frame_names = [f'Frame {i}' for i in range(len(self.image_metadata['frames']))]
                # This is a multi-frame image
                if len(self.image_metadata['frames'])==3:
                    # Treat this as an RGB image by default
                    rgb_url = self.tiles_url+'/?style={"bands": [{"framedelta":0,"palette":"rgba(255,0,0,255)"},{"framedelta":1,"palette":"rgba(0,255,0,255)"},{"framedelta":2,"palette":"rgba(0,0,255,255)"}]}'
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

                        rgb_url = self.tiles_url+'/?style='+json.dumps(rgb_style_dict)
                    else:
                        rgb_url = None

                    # Pre-determining indices:
                    if not rgb_url is None:
                        layer_indices = list(range(0,len(frame_names)+1))
                    else:
                        layer_indices = list(range(0,len(frame_names)))
                    
                    for f_idx,f in enumerate(frame_names):
                        frame_layers.append(
                            dl.BaseLayer(
                                dl.TileLayer(
                                    url = self.tiles_url+'/?style={"bands": [{"palette":["rgba(0,0,0,0)","rgba(255,255,255,255)"],"framedelta":'+str(f_idx)+'}]}',
                                    tileSize = self.image_metadata['tileWidth'],
                                    maxNativeZoom=self.image_metadata['levels']-1,
                                    id = {'type': 'tile-layer','index': layer_indices[f_idx]}
                                ),
                                name = f,
                                checked = f==frame_names[0],
                                id = {'type': 'base-layer','index': layer_indices[f_idx]}
                            )
                        )
                    if rgb_url:
                        frame_layers.append(
                            dl.BaseLayer(
                                dl.TileLayer(
                                    url = rgb_url,
                                    tileSize = self.image_metadata['tileWidth'],
                                    maxNativeZoom=self.image_metadata['levels']-1,
                                    id = {'type': 'tile-layer','index': layer_indices[f_idx+1]},
                                    bounds = [[0,0],[-self.image_metadata['tileWidth'], self.image_metadata['tileWidth']]]
                                ),
                                name = 'RGB Image',
                                checked = False,
                                id = {'type': 'base-layer','index': layer_indices[f_idx+1]}
                            )
                        )
            else:
                frame_layers.append(
                    dl.BaseLayer(
                        dl.TileLayer(
                            url = self.tiles_url,
                            tileSize = self.image_metadata['tileWidth'],
                            maxNativeZoom=self.image_metadata['levels']-1,
                            id = {'type': 'tile-layer','index': 0},
                            bounds = [[0,0],[-self.image_metadata['tileWidth'],self.image_metadata['tileWidth']]]
                        ),
                        name = 'RGB Image',
                        id = {'type': 'base-layer','index': 0}
                    )
                )
        else:
            raise TypeError("Missing 'frames' key in image metadata")
        
        return frame_layers

class SlideImageOverlay(MapComponent):
    """Image overlay on specific coordinates within a SlideMap

    :param MapComponent: General component class for children of SlideMap
    :type MapComponent: None
    """
    def __init__(self,
                 image_path: str,
                 image_crs: list = [0,0],
                 image_properties: Union[dict,None] = {"None": ""}
                ):
        """Constructor method

        :param image_path: Filepath for image to be overlaid on top of SlideMap
        :type image_path: str
        :param image_crs: Top-left coordinates (x,y) for the image, defaults to [0,0]
        :type image_crs: list, optional
        """
        self.image_path = image_path
        self.image_crs = image_crs
        self.image_properties = image_properties

        self.image_bounds = self.get_image_bounds()

    def get_image_bounds(self):
        """Get total bounds of image overlay in original CRS (number of pixels)

        :return: List of image bounds in overlay CRS ([minx, miny, maxx, maxy])
        :rtype: list
        """

        read_image = np.uint8(np.array(Image.open(self.image_path)))
        image_shape = np.shape(read_image)

        return self.image_crs + [self.image_crs[0]+image_shape[1], self.image_crs[1]+image_shape[0]]

class ChannelMixer(MapComponent):
    """ChannelMixer component that allows users to select various frames from their image to overlay at the same time with different color (styles) applied.

    :param MapComponent: General component class for children of SlideMap
    :type MapComponent: None
    """
    def __init__(self,
                 image_metadata: dict,
                 tiles_url: str
                 ):
        """Constructor method

        :param image_metadata: Dictionary containing "frames" data for a given image. "frames" here is a list containing channel names and indices.
        :type image_metadata: dict
        :param tiles_url: URL to refer to for accessing tiles (contains /{z}/{x}/{y}). Allows for "style" parameter to be passed. See large-image documentation: https://girder.github.io/large_image/getting_started.html#styles-changing-colors-scales-and-other-properties
        :type tiles_url: str
        """
        self.image_metadata = image_metadata
        self.tiles_url = tiles_url

        self.process_frames()

        self.title = 'Channel Mixer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()
    
    def process_frames(self):
        """Extracting names for each frame for easy reference
        """
        if 'frames' in self.image_metadata:
            if len(self.image_metadata['frames'])>0:
                self.frame_names = [i['Channel'] if 'Channel' in i else f'Frame {idx}' for idx,i in enumerate(self.image_metadata['frames'])]
            else:
                raise IndexError("No frames found in this image!")
        else:
            raise TypeError("Image is not multi-frame")

    def gen_layout(self):
        """Generating layout for ChannelMixer component

        :return: Interactive components for ChannelMixer component
        :rtype: dash.html.Div.Div
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
                            options = [
                                {
                                    'label': label, 'value': label
                                }
                                for idx,label in enumerate(self.frame_names)
                            ],
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

        return layout

    def get_callbacks(self):
        """Initializing callbacks and adding to DashBlueprint
        """

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
                State({'type': 'channel-mixer-tab','index': ALL},'label_style')
            ],
            [
                Output({'type': 'tile-layer','index': ALL},'url')
            ]
        )(self.update_channel_mix)

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
        for c_idx, c in enumerate(channel_mix_values):
            if not c in current_channels:
                channel_tab = dbc.Tab(
                    id = {'type': 'channel-mixer-tab','index': c_idx},
                    tab_id = c.lower().replace(' ','-'),
                    label = c,
                    activeTabClassName='fw-bold fst-italic',
                    label_style = {'color': 'rgb(0,0,0,255)'},
                    children = [
                        dmc.ColorPicker(
                            id = {'type': 'channel-mixer-color','index': c_idx},
                            format = 'rgba',
                            value = 'rgba(255,255,255,255)',
                            fullWidth=True
                        )
                    ]
                )
            else:
                channel_tab = dbc.Tab(
                    id = {'type': 'channel-mixer-tab','index': c_idx},
                    tab_id = c.lower().replace(' ','-'),
                    label = c,
                    activeTabClassName='fw-bold fst-italic',
                    label_style = current_colors[c_idx],
                    children = [
                        dmc.ColorPicker(
                            id = {'type': 'channel-mixer-color','index': c_idx},
                            format='rgba',
                            value = current_colors[c_idx]['color'],
                            fullWidth = True
                        )
                    ]
                )

            channel_mix_tabs.append(channel_tab)

        channel_tabs = dbc.Tabs(
            id = {'type': 'channel-mixer-tabs','index': 0},
            children = channel_mix_tabs,
            active_tab = c.lower().replace(' ','-')
        )

        return [channel_tabs]

    def update_tab_style(self, color_select):
        """Updating color of tab label based on selection

        :param color_select: "rgba" formatted color selection
        :type color_select: str
        """
        if not ctx.triggered:
            raise exceptions.PreventUpdate
        
        return {'color': color_select}
    
    def update_channel_mix(self, butt_click:list, current_channels:list,current_colors:list):
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
                    "framedelta": self.frame_names.index(current_channels[c])
                }
            )


        styled_urls = []
        if all([i in self.frame_names for i in ['red','green','blue']]):
            # There can be an RGB image by default
            rgb_style_dict = {
                "bands": [
                    {
                        "palette": ["rgba(0,0,0,0)",'rgba('+','.join(['255' if i==c_idx else '0' for i in range(3)]+['0'])+')'],
                        "framedelta": self.frame_names.index(c)
                    }
                    for c_idx,c in enumerate(['red','green','blue'])
                ]
            }

        else:
            rgb_style_dict = None

        styled_urls = []
        for f in self.frame_names:
            f_dict = {
                "bands": [
                    {
                        "palette": ["rgba(0,0,0,0)","rgba(255,255,255,255)"],
                        "framedelta": self.frame_names.index(f)
                    }
                ]
            }
            styled_urls.append(
                self.tiles_url+'/?style='+json.dumps({"bands":f_dict["bands"]+style_dict["bands"]})
            )
        if not rgb_style_dict is None:
            styled_urls.append(
                self.tiles_url+'/?style='+json.dumps({"bands":rgb_style_dict["bands"]+style_dict["bands"]})
            )

        return styled_urls



