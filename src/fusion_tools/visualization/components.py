"""
Functions related to visualization for data derived from FUSION.

- Interactive feature charts
    - View images at points
- Local slide viewers

"""
import os
import large_image.exceptions
from fastapi import FastAPI, APIRouter, Response

import large_image
import pandas as pd
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, dash_table, Patch, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashProxy, DashBlueprint, html, Input, Output, State
from dash_extensions.javascript import assign, arrow_function, Namespace

from fusion_tools.visualization.vis_utils import get_pattern_matching_value

import plotly.express as px
import plotly.graph_objects as go

import numpy as np

from typing_extensions import Union
from PIL import Image
from io import BytesIO
import json
import uvicorn
import requests


class Visualization:
    """
    General holder class used for initialization. Components added after initialization.
    
    Parameters
    --------
    components: list
        list of components to add to the visualization session (one of Tool or Map)
        Hierarchy goes from Row-->Column-->Tab for elements in lists. 
        (e.g. [0] would be one row with one component, 
        [0,1] would be one row with two columns, 
        [[0],[[1,2]]] would be two rows, first row with one column, second row with one column with two tabs)
    

    Examples
    --------
    >>> components = [
        [
            SlideMap(
                tile_server = LocalTileServer('/path/to/slide.svs'),
                annotations = geojson_list
            )
        ],
        [
            [
                OverlayOptions(geojson_list),
                PropertyViewer()
            ]
        ]
    ]

    >>> vis_session = Visualization(components)
    >>> vis_session.start()
        
    """
    def __init__(self,
                 components: list,
                 app_options: dict = {}):
        

        self.components = components
        #self.layout = layout
        self.app_options = app_options

        self.assets_folder = os.getcwd()+'/.fusion_assets/'

        self.default_options = {
            'title': 'FUSION',
            'server': 'default',
            'server_options': {},
            'port': '8080'
        }

        self.viewer_app = DashProxy(
            __name__,
            external_stylesheets = [
                dbc.themes.LUX,
                dbc.themes.BOOTSTRAP,
                dbc.icons.BOOTSTRAP,
                dbc.icons.FONT_AWESOME
            ],
            external_scripts = ['https://cdnjs.cloudflare.com/ajax/libs/chroma-js/2.1.0/chroma.min.js'],
            assets_folder = self.assets_folder,
            prevent_initial_callbacks=True
        )
        self.viewer_app.title = self.app_options['title'] if 'title' in self.app_options else self.default_options['title']
        self.viewer_app.layout = self.gen_layout()
    
    def gen_layout(self):

        layout_children = self.get_layout_children()

        layout = dmc.MantineProvider(
                children = [
                    html.Div(
                        dbc.Container(
                            id = 'vis-container',
                            fluid = True,
                            children = layout_children
                        ),
                        style = self.app_options['app_style'] if 'app_style' in self.app_options else {}
                    )
                ]
        )

        return layout

    def get_layout_children(self):
        """
        Generate children of layout container from input list of components and layout options
        """

        layout_children = []
        for row in self.components:
            row_children = []
            for col in row:
                if not type(col)==list:
                    if isinstance(col,SlideMap):
                        col.blueprint.layout = col.gen_layout(width=f'{int(100/len(row))}vw')

                    row_children.append(
                        dbc.Col(
                            dbc.Card([
                                dbc.CardHeader(
                                    col.title
                                ),
                                dbc.CardBody(
                                    col.blueprint.embed(self.viewer_app)
                                )
                            ])
                        )
                    )
                else:
                    tabs_children = []
                    for tab in col:
                        if isinstance(tab,SlideMap):
                            tab.blueprint.layout = tab.gen_layout(width=f'{int(100/len(row))}vw')
                        tabs_children.append(
                            dbc.Tab(
                                dbc.Card(
                                    dbc.CardBody(
                                        tab.blueprint.embed(self.viewer_app)
                                    )
                                ),
                                label = tab.title,
                                tab_id = tab.title.lower().replace(' ','-')
                            )
                        )

                    row_children.append(
                        dbc.Col(
                            dbc.Tabs(
                                tabs_children
                            )
                        )
                    )

            layout_children.append(
                dbc.Row(
                    row_children
                )
            )

        return layout_children

    def start(self):
        """
        Starting the visualization app based on app_options        
        """
        
        if 'server' in self.app_options:
            if self.app_options['server']=='default':
                self.viewer_app.run_server(
                    host = '0.0.0.0',
                    port = self.app_options['port'] if 'port' in self.app_options else self.default_options['port'],
                    debug = False
                )
        else:
            self.viewer_app.run_server(
                host = '0.0.0.0',
                port = self.app_options['port'] if 'port' in self.app_options else self.default_options['port'],
                debug = False
            )


class TileServer:
    """
    Components which pull information from a slide(s)
    """
    pass

class LocalTileServer(TileServer):
    """
    Tile server from image saved locally. Uses large-image to read and parse image formats (default: [common])
    """
    def __init__(self,
                 local_image_path: str,
                 tile_server_port = '8050'
                 ):

        self.local_image_path = local_image_path

        self.tile_server_port = tile_server_port

        self.tiles_url = f'http://localhost:{self.tile_server_port}/tiles/'+'{z}/{x}/{y}'
        self.regions_url = f'http://locahost:{self.tile_server_port}/tiles/region'

        self.tile_source = large_image.open(self.local_image_path,encoding='PNG')
        self.tiles_metadata = self.tile_source.getMetadata()

        self.router = APIRouter()
        self.router.add_api_route('/',self.root,methods=["GET"])
        self.router.add_api_route('/tiles/{z}/{x}/{y}',self.get_tile,methods=["GET"])
        self.router.add_api_route('/metadata',self.get_metadata,methods=["GET"])
        self.router.add_api_route('/tiles/region',self.get_region,methods=["GET"])
    
    def __str__(self):
        return f'TileServer class for {self.local_image_path} to http://localhost:{self.tile_server_port}'

    def root(self):
        return {'message': "Oh yeah, now we're cooking"}

    def get_tile(self,z:int, x:int, y:int, style = {}):
        try:
            raw_tile = self.tile_source.getTile(
                        x = x,
                        y = y,
                        z = z
                    )
            
        except large_image.exceptions.TileSourceXYZRangeError:
            # This error appears for any negative tile coordinates
            raw_tile = np.zeros((self.tiles_metadata['tileHeight'],self.tiles_metadata['tileWidth']),dtype=np.uint8).tobytes()

        return Response(content = raw_tile, media_type='image/png')
    
    def get_metadata(self):
        return Response(content = json.dumps(self.tiles_metadata),media_type = 'application/json')
    
    def get_region(self, top: int, left: int, bottom:int,right:int):
        """
        Grabbing a specific region in the image based on bounding box coordinates
        """
        image, mime_type = self.tile_source.getRegion(
            region = {
                'left': left,
                'top': top,
                'right': right,
                'bottom': bottom
            }
        )

        return Response(content = image, media_type = 'image/png')

    def start(self, port = 8050):
        app = FastAPI()
        app.include_router(self.router)

        uvicorn.run(app,host='0.0.0.0',port=port)

class RemoteTileServer(TileServer):
    """
    Use for linking visualization with remote tiles API (DSA server)
    """
    def __init__(self,
                 base_url: str
                 ):

        self.base_url = base_url
        self.tiles_url = f'{base_url}/tiles/'+'{z}/{x}/{y}'
        self.regions_url = f'{base_url}/tiles/region'

        self.tiles_metadata = requests.get(
            f'{base_url}/tiles'
        ).json()

    def __str__(self):
        return f'RemoteTileServer for {self.base_url}'

class CustomTileServer(TileServer):
    """
    If using some other tiles endpoint (must pass tileSize and levels in dictionary)
    """
    def __init__(self,
                 tiles_url:str,
                 regions_url:str,
                 image_metadata: dict
                 ):
        
        self.tiles_url = tiles_url
        self.regions_url = regions_url

        assert all([i in image_metadata for i in ['tileWidth','tileHeight','sizeX','sizeY','levels']])
        self.tiles_metadata = image_metadata


class MapComponent:
    """
    Components which are rendered with dash-leaflet components
    """
    pass

class SlideMap(MapComponent):
    def __init__(self,
                 tile_server: TileServer,
                 annotations: Union[dict,list,None]
                ):
        
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
        #self.blueprint.layout = self.gen_layout()

        # Add callback functions here
        self.get_callbacks()

    def get_scale_factors(self):
        """
        Used to adjust overlaid annotations and coordinates so that they fit on the "base" tile (tileWidth x tileHeight)
        
        """

        base_dims = [
            self.image_metadata['sizeX']/(2**(self.image_metadata['levels']-1)),
            self.image_metadata['sizeY']/(2**(self.image_metadata['levels']-1))
        ]

        x_scale = base_dims[0] / self.image_metadata['sizeX']
        y_scale = -(base_dims[1] / self.image_metadata['sizeY'])

        return x_scale, y_scale

    def process_annotations(self):
        """
        Convert geojson or list of geojsons into dash-leaflet components
        """

        annotation_components = []
        if not self.annotations is None:
            if type(self.annotations)==dict:
                self.annotations = [self.annotations]
            
            for st_idx,st in enumerate(self.annotations):

                # Scale annotations to fit within base tile dimensions
                for f in st['features']:
                    f['geometry']['coordinates'] = [[
                        [i[0]*self.x_scale,i[1]*self.y_scale]
                        for i in f['geometry']['coordinates']
                    ]]
                
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

    def gen_layout(self, width: str):
        """
        Generate simple slide viewer layout
        """
        layout = html.Div(
            dl.Map(
                id = {'type': 'slide-map','index': 0},
                crs = 'Simple',
                center = [-self.image_metadata['tileWidth']/2,self.image_metadata['tileWidth']/2],
                zoom = 1,
                style = {'height': '90vh','width': width,'margin': 'auto','display': 'inline-block'},
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
                        id = {'type': 'map-layers-control'},
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
                ]
            )
        )

        return layout

    def get_namespace(self):
        """
        Adding javascript functions to layout
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
                    const class_indices = overlayBounds.unique.map(str => overlayBounds.unique.indexOf(str));
                    var csc = chroma.scale(["blue","red"]).classes(class_indices);
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

                if (overlayVal == overlayVal) {
                    if (typeof overlayVal==='number') {
                        style.fillColor = csc(overlayVal);
                    } else {
                        overlayVal = overlayBounds.unique.indexOf(overlayVal);
                        style.fillColor = csc(overlayVal);
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
                                if (test_val < filter.range[0]) {
                                    returnFeature = returnFeature & false;
                                }
                                if (test_val > filter.range[1]) {
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
        """
        Adding callbacks to this DashBlueprint object
        """
        
        # Getting popup info for clicked feature
        self.blueprint.callback(
            [
                Input({'type':'feature-bounds','index': MATCH},'clickData')
            ],
            [
                Output({'type': 'ftu-popup','index': MATCH},'children')
            ]
        )(self.get_click_popup)

        # 

    def get_click_popup(self, clicked):
        """
        Popuplate popup for clicked feature
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

        popup_div = html.Div(
            dbc.Accordion(
                dbc.AccordionItem(
                    title = 'Properties',
                    children = [
                        make_dash_table(pd.DataFrame.from_records([i['properties'] for i in clicked]))
                    ]
                )
            )
        )

        return popup_div

class MultiFrameSlideMap(SlideMap):
    """
    Used for viewing slides with multiple "frames" (e.g. CODEX images)
    """
    def __init__(self,
                 tile_server: TileServer,
                 annotations: Union[dict,list,None]
                 ):
        super().__init__(tile_server,annotations)
        
        self.title = 'Multi-Frame Slide Map'

        # Changing up the layout so that it generates different tile layers for each frame
    
    def gen_layout(self):
        """
        
        """

        layout = html.Div([

        ])



        return layout
    
    def get_callbacks(self):
        pass

class SlideImageOverlay(MapComponent):
    def __init__(self,
                 image_path: str,
                 image_crs: list = [0,0]
                ):
        
        self.image_path = image_path

        self.title = 'Slide Image Overlay'

        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        pass

    def get_callbacks(self):
        pass




    
class Tool:
    """
    Components which can be added to tabs
    """
    pass

class OverlayOptions(Tool):
    """
    Creates dropdown menu for changing overlay colors based on structure properties

    Parameters
    --------
    geojson_anns: Union[list,dict]
        List or single GeoJSON object containing "property" key 

    reference_object: Union[str,None]
        File path to data file with properties not added to geojson objects but with some reference field which links the two
    
    ignore_list: list = []
        List of properties to ignore and not make usable for generating overlaid heatmaps


    """
    def __init__(self,
                 geojson_anns: Union[list,dict],
                 reference_object: Union[str,None] = None,
                 ignore_list: list = []
                 ):

        self.reference_object = reference_object
        self.overlay_options, self.feature_names, self.overlay_info = self.extract_overlay_options(geojson_anns, reference_object,ignore_list)
        
        self.title = 'Overlay Options'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        # Add callbacks here
        self.get_callbacks()

    
    def extract_overlay_options(self,geojson_anns,reference_object,ignore_list):
        """
        Extract all properties which can be used for overlays
        """

        geojson_properties = []
        feature_names = []
        property_info = {}
        for ann in geojson_anns:
            feature_names.append(ann['properties']['name'])
            for f in ann['features']:
                f_props = list(f['properties'].keys())
                for p in f_props:
                    # Checking for sub-properties: (only going 1 level)
                    if type(f['properties'][p])==dict:
                        sub_props = []
                        for sup in list(f['properties'][p].keys()):
                            sub_prop_name = f'{p} --> {sup}'
                            sub_props.append(sub_prop_name)
                            
                            f_sup_val = f['properties'][p][sup]

                            if not sub_prop_name in property_info:
                                if type(f_sup_val) in [int,float]:
                                    property_info[sub_prop_name] = {
                                        'min': f_sup_val,
                                        'max': f_sup_val,
                                        'distinct': 1
                                    }
                                elif type(f_sup_val) in [str]:
                                    property_info[sub_prop_name] = {
                                        'unique': [f_sup_val],
                                        'distinct': 1
                                    }


                            else:
                                if type(f_sup_val) in [int,float]:
                                    if f_sup_val < property_info[sub_prop_name]['min']:
                                        property_info[sub_prop_name]['min'] = f_sup_val
                                        property_info[sub_prop_name]['distinct']+=1

                                    if f_sup_val > property_info[sub_prop_name]['max']:
                                        property_info[sub_prop_name]['max'] = f_sup_val
                                        property_info[sub_prop_name]['distinct'] += 1

                                elif type(f_sup_val) in [str]:
                                    if not f_sup_val in property_info[sub_prop_name]['unique']:
                                        property_info[sub_prop_name]['unique'].append(f_sup_val)
                                        property_info[sub_prop_name]['distinct']+=1

                        sub_props = [f'{p} --> {sp}' for sp in list(f['properties'][p].keys())]
                    else:
                        sub_props = [p]

                        f_sup_val = f['properties'][p]

                        if not p in property_info:
                            if type(f_sup_val) in [int,float]:
                                property_info[p] = {
                                    'min': f_sup_val,
                                    'max': f_sup_val,
                                    'distinct': 1
                                }
                            else:
                                property_info[p] = {
                                    'unique': [f_sup_val],
                                    'distinct': 1
                                }
                        else:
                            if type(f_sup_val) in [int,float]:
                                if f_sup_val < property_info[p]['min']:
                                    property_info[p]['min'] = f_sup_val
                                    property_info[p]['distinct'] += 1
                                
                                elif f_sup_val > property_info[p]['max']:
                                    property_info[p]['max'] = f_sup_val
                                    property_info[p]['distinct']+=1

                            elif type(f_sup_val) in [str]:
                                if not f_sup_val in property_info[p]['unique']:
                                    property_info[p]['unique'].append(f_sup_val)
                                    property_info[p]['distinct']+=1

                    new_props = [i for i in sub_props if not i in geojson_properties and not i in ignore_list]
                    geojson_properties.extend(new_props)

        #TODO: After loading an experiment, reference the file here for additional properties
        

        return geojson_properties, feature_names, property_info

    def gen_layout(self):
        
        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Overlay Options')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Select options below to adjust overlay color, transparency, and line color for structures on your slide.'
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label(
                                'Select Overlay Property: ',
                                html_for = {'type': 'overlay-drop','index': 0}
                            ),
                            md = 3
                        ),
                        dbc.Col(
                            dcc.Dropdown(
                                options = [
                                    {'label': i, 'value': i}
                                    for i in self.overlay_options
                                ],
                                value = [],
                                multi = False,
                                id = {'type': 'overlay-drop','index': 0}
                            ),
                            md = 9
                        )
                    ]),
                    html.Div(
                        dcc.Store(
                            id = {'type': 'overlay-property-info','index':0},
                            data = json.dumps(self.overlay_info),
                            storage_type='memory'
                        )
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(
                            dbc.Label(
                                'Adjust Overlay Transparency: ',
                                html_for = {'type': 'overlay-trans-slider','index': 0}
                            ),
                            md = 3
                        ),
                        dbc.Col(
                            dcc.Slider(
                                min = 0,
                                max = 100,
                                step = 10,
                                value = 50,
                                id = {'type': 'overlay-trans-slider','index': 0}
                            )
                        )
                    ]),
                    html.Hr(),
                    dbc.Row([
                        dbc.Label('Filter Structures: ',html_for = {'type': 'add-filter-parent','index': 0}),
                        html.Div('Click the icon below to add a filter.')
                    ]),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'add-filter-parent','index': 0},
                            children = []
                        ),
                        html.Div(
                            html.A(html.I(
                                className = 'bi bi-filter-circle fa-2x',
                                n_clicks = 0,
                                id = {'type': 'add-filter-butt','index': 0},
                                style = {'display': 'inline-block','position': 'relative','left': '45%','right':'50%'}
                            ))
                        )
                    ],align='center'),
                    html.Hr(),
                    dbc.Row(
                        dbc.Label('Update Structure Boundary Color',html_for = {'type': 'feature-lineColor-opts','index': 0})
                    ),
                    dbc.Row([
                        dbc.Tabs(
                            id = {'type': 'feature-lineColor-opts','index': 0},
                            children = [
                                dbc.Tab(
                                    children = [
                                        dmc.ColorPicker(
                                            id = {'type': 'feature-lineColor','index': f_idx},
                                            format = 'hex',
                                            value = '#FFFFFF',
                                            fullWidth=True
                                        ),
                                        dbc.Button(
                                            id = {'type': 'feature-lineColor-butt','index': f_idx},
                                            children = ['Update Boundary Color'],
                                            className = 'd-grid col-12 mx-auto',
                                            n_clicks = 0
                                        )
                                    ],
                                    label = f
                                )
                                for f_idx, f in enumerate(self.feature_names)
                            ]
                        )
                    ])
                ])
            )
        ])

    
        return layout

    def get_callbacks(self):

        # Updating overlay color, transparency, line color, and filter
        self.blueprint.callback(
            [
                Input({'type': 'overlay-drop','index': ALL},'value'),
                Input({'type':'overlay-trans-slider','index': ALL},'value'),
                Input({'type':'feature-lineColor-butt','index': ALL},'n_clicks'),
                Input({'type': 'add-filter-parent','index': ALL},'children'),
                Input({'type':'add-filter-selector','index': ALL},'value'),
                Input({'type':'delete-filter','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'feature-bounds','index': ALL},'hideout'),
                Output({'type': 'map-colorbar-div','index': ALL},'children')
            ],
            [
                State({'type': 'overlay-drop','index': ALL},'value'),
                State({'type': 'overlay-trans-slider','index': ALL},'value'),
                State({'type': 'overlay-property-info','index': ALL},'data'),
                State({'type': 'feature-lineColor','index': ALL},'value'),
            ]
        )(self.update_overlays)

        # Adding filters
        self.blueprint.callback(
            [
                Output({'type': 'add-filter-parent','index': ALL},'children',allow_duplicate=True)
            ],
            [
                Input({'type': 'add-filter-butt','index': ALL},'n_clicks'),
                Input({'type': 'add-filter-drop','index': ALL},'value'),
                Input({'type': 'delete-filter','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'overlay-property-info','index': ALL},'data')
            ]
        )(self.add_filter)

    def add_filter(self, add_filter_click, add_filter_value, delete_filter_click,overlay_info_state):
        """
        Add new filter based on selected overlay value
        """
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        add_filter_click = get_pattern_matching_value(add_filter_click)
        add_filter_value = get_pattern_matching_value(add_filter_value)
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))

        if len(list(overlay_info_state.keys()))==0:
            raise exceptions.PreventUpdate

        active_filters = Patch()
        if ctx.triggered_id['type']=='delete-filter':

            values_to_remove = []
            for i,val in enumerate(delete_filter_click):
                if val:
                    values_to_remove.insert(0,i)
            
            for v in values_to_remove:
                del active_filters[v]

        elif ctx.triggered_id['type'] in ['add-filter-drop','add-filter-butt']:
            
            # Initializing dropdown value 
            if add_filter_value is None:
                add_filter_value = list(overlay_info_state.keys())[0]

            overlayBounds = overlay_info_state[add_filter_value]
            if 'min' in overlayBounds:
                # Used for numeric filtering
                values_selector = html.Div(
                    dcc.RangeSlider(
                        id = {'type': 'add-filter-selector','index': add_filter_click},
                        min = overlayBounds['min'],
                        max = overlayBounds['max'],
                        step = 0.01,
                        marks = None,
                        tooltip = {'placement':'bottom','always_visible': True},
                        allowCross = False,
                        disabled = False
                    ),
                    style = {'display': 'inline-block','margin': 'auto','width': '100%'}
                )
            elif 'unique' in overlayBounds:
                # Used for categorical filtering
                values_selector = html.Div(
                    dcc.Dropdown(
                        id = {'type':'add-filter-selector','index': add_filter_click},
                        options = overlayBounds['unique'],
                        value = overlayBounds['unique'],
                        multi = True
                    )
                )
            
            def new_filter_item():
                return html.Div([
                    dbc.Row([
                        dbc.Col(
                            dcc.Dropdown(
                                options = self.overlay_options,
                                value = self.overlay_options[0],
                                placeholder = 'Select property to filter structures',
                                id = {'type': 'add-filter-drop','index': add_filter_click}
                            ),
                            md = 10
                        ),
                        dbc.Col(
                            html.I(
                                id = {'type': 'delete-filter','index': add_filter_click},
                                n_clicks = 0,
                                className = 'bi bi-x-circle-fill fa-2x',
                                style = {'color': 'rgb(255,0,0)'}
                            ),
                            md = 2
                        )
                    ],align='center'),
                    values_selector
                ])
            
            active_filters.append(new_filter_item())

        return [active_filters]

    def parse_added_filters(self, add_filter_parent):
        """
        Getting all filter values from parent div

        add_filter_parent is a list of divs, each one containing two children (Row, Div).
        """
        processed_filters = []

        if not add_filter_parent is None:
            for div in add_filter_parent:
                div_children = div['props']['children']

                filter_name = div_children[0]['props']['children'][0]['props']['children']['props']['value']
                filter_value = div_children[1]['props']['children']['props']['value']

                processed_filters.append({
                    'name': filter_name.split(' --> ')[0] if '-->' in filter_name else filter_name,
                    'value': filter_name.split(' --> ')[1] if '-->' in filter_name else None,
                    'range': filter_value
                })

        return processed_filters

    def update_overlays(self, overlay_value, transp_value, lineColor_butt, filter_parent, filter_value, delete_filter, overlay_state, transp_state, overlay_info_state, lineColor_state):
        """
        Update overlay transparency and color based on property selection

        Adding new values to the "hideout" property of the GeoJSON layers triggers the featureStyle Namespace function
        """

        overlay_value = get_pattern_matching_value(overlay_value)
        transp_value = get_pattern_matching_value(transp_value)
        overlay_state = get_pattern_matching_value(overlay_state)
        transp_state = get_pattern_matching_value(transp_state)
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))

        if ctx.triggered_id['type']=='overlay-drop':
            use_overlay_value = overlay_value
            use_transp_value = transp_state
        else:
            if type(overlay_state)==list:
                if len(overlay_state)==0:
                    use_overlay_value = None
                else:
                    use_overlay_value = overlay_state[0]
            else:
                use_overlay_value = overlay_state

        if ctx.triggered_id['type']=='overlay-trans-slider':
            use_transp_value = transp_value
        else:
            use_transp_value = transp_state

        if ctx.triggered_id['type'] in ['add-filter-parent', 'add-filter-selector','delete-filter']:
            use_overlay_value = overlay_state
            use_transp_value = transp_state

        if ctx.triggered_id['type']=='feature-lineColor-butt':
            use_overlay_value = overlay_state
            use_transp_value = transp_state


        if not use_overlay_value is None:
            if '-->' in use_overlay_value:
                split_overlay_value = use_overlay_value.split(' --> ')

                overlay_prop = {
                    'name': split_overlay_value[0],
                    'value': split_overlay_value[1]
                }
            else:
                overlay_prop = {
                    'name': use_overlay_value,
                    'value': None
                }
        else:
            overlay_prop = {
                'name': None,
                'value': None
            }

        if not use_transp_value is None:
            fillOpacity = use_transp_value/100
        else:
            fillOpacity = 0.5

        if not use_overlay_value is None:
            overlay_bounds = overlay_info_state[use_overlay_value]
        else:
            overlay_bounds = {}

        lineColor = {
            i: j
            for i,j in zip(self.feature_names, lineColor_state)
        }
        
        color_bar_style = {
            'visibility':'visible',
            'background':'white',
            'background':'rgba(255,255,255,0.8)',
            'box-shadow':'0 0 15px rgba(0,0,0,0.2)',
            'border-radius':'10px',
            'width': '400px',
            'padding':'0px 0px 0px 25px'
        }

        if 'min' in overlay_bounds:
            colorbar = [dl.Colorbar(
                colorscale = ['blue','red'],
                width = 300,
                height = 15,
                position = 'bottomleft',
                id = f'colorbar{np.random.randint(0,100)}',
                style = color_bar_style,
                tooltip=True
            )]
        elif 'unique' in overlay_bounds:
            colorbar = [dlx.categorical_colorbar(
                categories = overlay_bounds['unique'],
                colorscale = ['blue','red'],
                style = color_bar_style,
                position = 'bottomleft',
                id = f'colorbar{np.random.randint(0,100)}',
                width = 300,
                height = 15
            )]

        else:
            colorbar = [no_update]

        # Grabbing all filter values from the parent div
        filterVals = self.parse_added_filters(get_pattern_matching_value(filter_parent))

        geojson_hideout = [
            {
                'overlayBounds': overlay_bounds,
                'overlayProp': overlay_prop,
                'fillOpacity': fillOpacity,
                'lineColor': lineColor,
                'filterVals': filterVals 
            }
            for i in range(len(ctx.outputs_list[0]))
        ]

        return geojson_hideout, colorbar


class ChannelMixer(MapComponent):
    def __init__(self,
                 image_metadata: dict,
                 tiles_url: str
                 ):
        
        self.image_metadata = image_metadata

        self.title = 'Channel Mixer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):

        layout = html.Div([

        ])


        return layout

    def get_callbacks(self):
        pass
















class PropertyViewer(Tool):
    def __init__(self,
                 geojson_list: Union[dict,list],
                 reference_object: Union[str,None],
                 ignore_list: list = []
                 ):
        
        self.ignore_list = []
        self.reference_object = reference_object
        self.available_properties = self.extract_overlay_options(geojson_list,reference_object,ignore_list)
    

        self.title = 'Property Viewer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()   
        
    
    def extract_overlay_options(self,geojson_anns,reference_object,ignore_list):
        """
        Extract all properties which can be used for overlays
        """

        geojson_properties = []
        feature_names = []
        for ann in geojson_anns:
            feature_names.append(ann['properties']['name'])
            for f in ann['features']:
                f_props = list(f['properties'].keys())
                for p in f_props:
                    # Checking for sub-properties: (only going 1 level)
                    if type(f['properties'][p])==dict:
                        sub_props = [f'{p} --> {sp}' for sp in list(f['properties'][p].keys())]
                    else:
                        sub_props = [p]
                    
                    geojson_properties.extend([i for i in sub_props if not i in geojson_properties and not i in ignore_list])

        #TODO: After loading an experiment, reference the file here for additional properties
        

        return geojson_properties, feature_names

    def gen_layout(self):
        pass



    def get_callbacks(self):
        pass



class PropertyPlotter(Tool):
    def __init__(self,
                 geojson_list: Union[dict,list],
                 reference_object: Union[str,None],
                 ignore_list: list = []
                 ):

        self.reference_object = reference_object
        self.ignore_list = ignore_list
        self.available_properties = self.extract_overlay_options(geojson_list,reference_object,ignore_list)

        self.title = 'Prperty Plotter'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()



    def extract_overlay_options(self,geojson_anns,reference_object,ignore_list):
        """
        Extract all properties which can be used for overlays
        """

        geojson_properties = []
        feature_names = []
        for ann in geojson_anns:
            feature_names.append(ann['properties']['name'])
            for f in ann['features']:
                f_props = list(f['properties'].keys())
                for p in f_props:
                    # Checking for sub-properties: (only going 1 level)
                    if type(f['properties'][p])==dict:
                        sub_props = [f'{p} --> {sp}' for sp in list(f['properties'][p].keys())]
                    else:
                        sub_props = [p]
                    
                    geojson_properties.extend([i for i in sub_props if not i in geojson_properties and not i in ignore_list])

        #TODO: After loading an experiment, reference the file here for additional properties
        

        return geojson_properties, feature_names

    def get_callbacks(self):
        pass

    def gen_layout(self):
        pass


class FeatureAnnotator(Tool):
    def __init__(self):

        self.title = 'Feature Annotator'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        pass

    def get_callbacks(self):
        pass


class HRAViewer(Tool):
    def __init__(self):

        self.title = 'HRA Viewer'
        self.blueprint = DashBlueprint()
        self.blueprint.layout = self.gen_layout()

        self.get_callbacks()

    def gen_layout(self):
        pass


    def get_callbacks(self):
        pass






