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

        self.annotation_components = self.process_annotations()

        self.title = 'Slide Map'
        self.blueprint = DashBlueprint()        
        self.blueprint.layout = self.gen_layout()

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

    def process_annotations(self):
        """Process incoming annotations and generate dl.Overlay components applied to the SlideMap

        :return: List of dl.Overlay components containing dl.GeoJSON objects where "data" contains the corresponding scaled GeoJSON information 
        :rtype: list
        """

        annotation_components = []
        if not self.annotations is None:
            if type(self.annotations)==dict:
                self.annotations = [self.annotations]
            
            for st_idx,st in enumerate(self.annotations):

                # Scale annotations to fit within base tile dimensions
                st = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]*self.x_scale,c[1]*self.y_scale, c[2]), g), st)

                if 'properties' not in st:
                    st['properties'] = {}
                    if 'name' in st['features'][0]['properties']:
                        st['properties']['name'] = st['features'][0]['properties']['name']
                    else:
                        st['properties']['name'] = f'Structure {st_idx}'
                
                annotation_components.append(
                    dl.Overlay(
                        dl.LayerGroup(
                            dl.GeoJSON(
                                data = st,
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
                        name = st['properties']['name'], checked = True, id = {'type':'feature-overlay','index':st_idx}
                    )
                )

        return annotation_components

    def gen_layout(self):
        """Generating SlideMap layout

        :return: Div object containing interactive components for the SlideMap object.
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
                                draw = dict(polyline=False, line=False, circle = False, circlemarker=False),
                                position='topleft'
                            )
                        ]
                    ),
                    html.Div(
                        id = {'type': 'map-colorbar-div','index': 0},
                        children = []
                    ),
                    dl.LayersControl(
                        id = {'type': 'map-layers-control','index': 0},
                        children = self.annotation_components
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
                    )
                ]
            )
        )

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
                const {overlayBounds, overlayProp, fillOpacity, lineColor, filterVals} = context.hideout;
                var style = {};
                if ("min" in overlayBounds) {
                    var csc = chroma.scale(["blue","red"]).domain([overlayBounds.min,overlayBounds.max]);
                } else if ("unique" in overlayBounds) {
                    var class_indices = overlayBounds.unique.map(str => overlayBounds.unique.indexOf(str));
                    var csc = chroma.scale(["blue","red"]).colors(class_indices.length);
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
                        if (overlayProp.name in feature.properties) {
                            if (overlayProp.value) {
                                if (overlayProp.value in feature.properties[overlayProp.name]) {
                                    var overlayVal = feature.properties[overlayProp.name][overlayProp.value];
                                } else {
                                    var overlayVal = Number.Nan;
                                }
                            } else {
                                var overlayVal = feature.properties[overlayProp.name];
                            }
                        } else {
                            var overlayVal = Number.Nan;
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
                const {overlayBounds, overlayProp, fillOpacity, lineColor, filterVals} = context.hideout;

                var returnFeature = true;
                if (filterVals) {
                    for (let i = 0; i < filterVals.length; i++) {
                        // Iterating through filterVals list
                        var filter = filterVals[i];
                        if (filter.name) {
                            if (filter.name in feature.properties) {
                                if (filter.value) {
                                    if (filter.value in feature.properties[filter.name]) {
                                        var testVal = feature.properties[filter.name][filter.value];
                                    } else {
                                        returnFeature = returnFeature & false;
                                    }
                                } else {
                                    var testVal = feature.properties[filter.name];
                                }
                            } else {
                                returnFeature = returnFeature & false;
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
                } else {
                    return returnFeature;
                }
                
                return returnFeature;
                
                }
                """,
            name = 'featureFilter'
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
                Input({'type':'edit-control','index': ALL},'geojson')
            ],
            [
                Output({'type': 'map-layers-control','index': ALL},'children')
            ]
        )(self.add_manual_roi)

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

        popup_div = html.Div(
            dbc.Accordion(
                children = accordion_children
            )
        )

        return popup_div
    
    def make_geojson_layers(self, geojson_list:list) -> list:
        """Creates new dl.Overlay() dl.GeoJSON components from list of GeoJSON FeatureCollection objects

        :param geojson_list: List of GeoJSON FeatureCollection objects
        :type geojson_list: list
        :return: Overlay components on SlideMap.
        :rtype: list
        """

        annotation_components = []
        for st_idx,st in enumerate(geojson_list):
            annotation_components.append(
                dl.Overlay(
                    dl.LayerGroup(
                        dl.GeoJSON(
                            data = st,
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
                    name = st['properties']['name'], checked = True, id = {'type':'feature-overlay','index':st_idx}
                )
            )

        return annotation_components

    def add_manual_roi(self,new_geojson:list) -> list:
        """Adding a manual region of interest (ROI) to the SlideMap using dl.EditControl() tools including polygon, rectangle, and markers.

        :param new_geojson: Incoming GeoJSON object that is emitted by dl.EditControl() following annotation on SlideMap
        :type new_geojson: list
        :raises exceptions.PreventUpdate: new_geojson input is None
        :raises exceptions.PreventUpdate: No new features are added, this can occur after deletion of previous manual ROIs.
        :return: List of new children to dl.LayerControl() consisting of overlaid GeoJSON components.
        :rtype: list
        """
        new_geojson = get_pattern_matching_value(new_geojson)
        if not new_geojson is None:
            new_geojson['properties'] = {
                'name': 'Manual ROI',
                '_id': uuid.uuid4().hex[:24]
            }

            if not self.annotations is None:

                if len(new_geojson['features'])>0:
                    new_geojson = spatially_aggregate(new_geojson, self.annotations)
                    new_children = self.make_geojson_layers(self.annotations+[new_geojson])
                else:
                    new_children = self.make_geojson_layers(self.annotations)

                return [new_children]
            else:
                if len(new_geojson['features'])>0:
                    new_children = self.make_geojson_layers([new_geojson])
                    return [new_children]
                
                else:
                    raise exceptions.PreventUpdate
        else:
            raise exceptions.PreventUpdate


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
        super().__init__(tile_server,annotations)

        
        self.title = 'Multi-Frame Slide Map'

        # Changing up the layout so that it generates different tile layers for each frame
    
    def gen_layout(self):
        """Generating layout for MultiFrameSlideMap

        :return: Layout added to DashBlueprint object to be embedded in larger layout.
        :rtype: dash.html.Div.Div
        """
        layout = html.Div([

        ])



        return layout
    
    def get_callbacks(self):
        pass

class SlideImageOverlay(MapComponent):
    """Image overlay on specific coordinates within a SlideMap

    :param MapComponent: General component class for children of SlideMap
    :type MapComponent: None
    """
    def __init__(self,
                 image_path: str,
                 image_crs: list = [0,0]
                ):
        """Constructor method

        :param image_path: Filepath for image to be overlaid on top of SlideMap
        :type image_path: str
        :param image_crs: Top-left coordinates (x,y) for the image, defaults to [0,0]
        :type image_crs: list, optional
        """
        self.image_path = image_path

        self.title = 'Slide Image Overlay'

        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        pass

    def get_callbacks(self):
        pass

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

        self.title = 'Channel Mixer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        """Generating layout for ChannelMixer component

        :return: Interactive components for ChannelMixer component
        :rtype: dash.html.Div.Div
        """
        layout = html.Div([

        ])


        return layout

    def get_callbacks(self):
        pass

    









