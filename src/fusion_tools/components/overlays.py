"""

Components which handle overlay colormapping/filtering/general handling on SlideMap components.

"""

import json
import geojson
import numpy as np
import uuid


# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
from dash_extensions.javascript import Namespace, arrow_function

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import ( 
    process_filters_queries,
)
from fusion_tools.components.base import Tool, MultiTool

import time


class OverlayOptions(Tool):
    """OverlayOptions Tool which enables editing overlay visualization properties including line color, fill color, and filters.

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """

    title = 'Overlay Options'
    description = 'Select options below to adjust overlay color, transparency, and line color for structures on your slide.'

    def __init__(self,
                 ignore_list: list = ["_id", "_index"],
                 property_depth: int = 4
                 ):
        """Constructor method

        :param ignore_list: List of properties to exclude from visualization. These can include any internal or private properties that are not desired to be viewed by the user or used for filtering/overlay colors., defaults to []
        :type ignore_list: list, optional
        :param property_depth: Depth at which to search for nested properties. Properties which are nested further than this will be ignored.
        :type property_depth: int, optional
        """

        super().__init__()
        self.ignore_list = ignore_list
        self.property_depth = property_depth
            
    def load(self,component_prefix:int):

        self.component_prefix = component_prefix

        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(prefix = f'{component_prefix}'),
                MultiplexerTransform()
            ]
        )

        #TODO: This is an interesting case where the component references another components js_namespace
        self.js_namespace = Namespace("fusionTools","slideMap")

        # Add callbacks here
        self.get_callbacks()

    def gen_layout(self, session_data:dict):
        """Generating OverlayOptions layout, added to DashBlueprint() object to be embedded in larger layout.
        """

        adv_colormaps = [
            'Custom Palettes',
            'blue->red',
            'white->black',
            'Sequential Palettes',
            'OrRd', 'PuBu', 'BuPu', 
            'Oranges', 'BuGn', 'YlOrBr', 
            'YlGn', 'Reds', 'RdPu', 
            'Greens', 'YlGnBu', 'Purples', 
            'GnBu', 'Greys', 'YlOrRd', 
            'PuRd', 'Blues', 'PuBuGn', 
            'Diverging Palettes',
            'Viridis', 'Spectral', 'RdYlGn', 
            'RdBu', 'PiYG', 'PRGn', 'RdYlBu', 
            'BrBG', 'RdGy', 'PuOr', 
            'Qualitative Palettes',
            'Set2', 'Accent', 'Set1', 
            'Set3', 'Dark2', 'Paired', 
            'Pastel2', 'Pastel1',
        ]

        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3(self.title)
                    ),
                    html.Hr(),
                    dbc.Row(
                        self.description
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
                                options = [],
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
                            data = json.dumps({}),
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
                        )
                    ],align='center'),
                    dbc.Row([
                        dbc.Col([
                            html.Div([
                                html.A(
                                    html.I(
                                        className = 'bi bi-filter-circle fa-2x',
                                        n_clicks = 0,
                                        id = {'type': 'add-filter-butt','index': 0},
                                    )
                                ),
                                dbc.Tooltip(
                                    target = {'type': 'add-filter-butt','index': 0},
                                    children = 'Click to add a filter'
                                )
                            ])
                        ],md = 2),
                        dbc.Col([
                            html.Div([
                                html.A(
                                    html.I(
                                        className = 'fa-solid fa-layer-group fa-2x',
                                        n_clicks = 0,
                                        id = {'type': 'create-layer-from-filter','index': 0},
                                    )
                                ),
                                dbc.Tooltip(
                                    target = {'type': 'create-layer-from-filter','index': 0},
                                    children = 'Create new layer from filters'
                                )
                            ])
                        ],md = 2)
                    ],align='center', justify='center'),
                    html.Hr(),
                    dbc.Row(
                        dbc.Label('Update Structure Boundary Color',html_for = {'type': 'feature-lineColor-opts','index': 0})
                    ),
                    dbc.Row([
                        dbc.Tabs(
                            id = {'type': 'feature-lineColor-opts','index': 0},
                            children = []
                        )
                    ],style = {'marginBottom':'10px'}),
                    dbc.Row([
                        dbc.Accordion(
                            id = {'type':'adv-overlay-accordion','index': 0},
                            start_collapsed = True,
                            children = [
                                dbc.AccordionItem(
                                    title = dcc.Markdown('*Advanced Overlay Options*'),
                                    children = [
                                        dbc.Card([
                                            dbc.CardBody([
                                                html.Div([
                                                    dbc.InputGroup([
                                                        dbc.Input(
                                                            id = {'type': 'adv-overlay-colorbar-width','index': 0},
                                                            placeholder = 'Colorbar Width',
                                                            type = 'number',
                                                            value = 300,
                                                            min = 0,
                                                            max = 1000,
                                                            step = 50
                                                        ),
                                                        dbc.InputGroupText(
                                                            'pixels'
                                                        )
                                                    ]),
                                                    dbc.FormText(
                                                        'Width of colorbar'
                                                    ),
                                                    html.Hr(),
                                                    dbc.Select(
                                                        id = {'type': 'adv-overlay-colormap','index': 0},
                                                        placeholder = 'Select colormap options',
                                                        options = [
                                                            {'label': i, 'value': i, 'disabled': ' ' in i}
                                                            for i in adv_colormaps
                                                        ],
                                                        value = 'blue->red'
                                                    )
                                                ]),
                                                html.Div(
                                                    children = [
                                                        dbc.Button(
                                                            'Update Overlays!',
                                                            className = 'd-grid col-12 mx-auto',
                                                            id = {'type': 'adv-overlay-butt','index': 0},
                                                            n_clicks = 0
                                                        )
                                                    ],
                                                    style = {'marginTop':'10px'}
                                                )
                                            ])
                                        ])
                                    ]
                                ),
                                dbc.AccordionItem(
                                    title = dcc.Markdown('*Manual ROI Options*'),
                                    children = [
                                        dbc.Card([
                                            dbc.CardBody([
                                                # Whether to separate structures or not
                                                # Whether to summarize or not
                                                dmc.Switch(
                                                    size = 'lg',
                                                    radius = 'lg',
                                                    label = 'Separate Intersecting Structures',
                                                    onLabel="ON",
                                                    offLabel="OFF",
                                                    description = "Separates aggregated properties by which structure they are derived from",
                                                    id = {'type': 'manual-roi-separate-switch','index':0}
                                                ),
                                                html.Hr(),
                                                dmc.Switch(
                                                    size = 'lg',
                                                    radius = 'lg',
                                                    label = "Summarize Aggregated Properties",
                                                    onLabel = "ON",
                                                    offLabel = "OFF",
                                                    description = "Whether to report summaries of aggregated properties or just the MEAN",
                                                    id = {'type': 'manual-roi-summarize-switch','index': 0}
                                                )
                                            ])
                                        ])
                                    ]
                                ),
                                dbc.AccordionItem(
                                    title = dcc.Markdown('*Export Layers*'),
                                    children = [
                                        dbc.Card([
                                            dbc.CardBody([
                                                html.Div([
                                                    dbc.Button(
                                                        'Export Current Layers',
                                                        id = {'type': 'export-current-layers','index': 0},
                                                        n_clicks = 0,
                                                        className = 'd-grid col-12 mx-auto'
                                                    ),
                                                    dcc.Download(
                                                        id = {'type': 'export-current-layers-data','index': 0}
                                                    )
                                                ])
                                            ])
                                        ])
                                    ]
                                )
                            ]
                        )
                    ])
                ])
            )
        ],style = {'maxHeight': '100vh','overflow':'scroll'})

        self.blueprint.layout = layout

    def get_callbacks(self):
        """Initializing callbacks for OverlayOptions Tool
        """

        # Updating for new slide selection:
        self.blueprint.callback(
            [
                Input({'type': 'map-annotations-info-store','index': ALL},'data')
            ],
            [
                Output({'type': 'overlay-drop','index': ALL},'options'),
                Output({'type': 'overlay-property-info','index': ALL},'data'),
                Output({'type': 'add-filter-parent','index': ALL},'children'),
                Output({'type': 'feature-lineColor-opts','index': ALL},'children')
            ]
        )(self.update_slide)

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
                State({'type': 'feature-overlay','index': ALL},'name'),
                State({'type': 'adv-overlay-colorbar-width','index': ALL},'value'),
                State({'type': 'adv-overlay-colormap','index': ALL},'value'),
                State({'type': 'feature-bounds','index': ALL},'hideout')
            ]
        )(self.update_overlays)

        # Updating overlays based on additional options
        self.blueprint.callback(
            [
                Input({'type':'adv-overlay-butt','index': ALL},'n_clicks')
            ],
            [
                Output({'type':'feature-bounds','index': ALL},'hideout'),
                Output({'type': 'map-colorbar-div','index': ALL},'children')
            ],
            [
                State({'type': 'adv-overlay-colorbar-width','index': ALL},'value'),
                State({'type': 'adv-overlay-colormap','index': ALL},'value'),
                State({'type': 'feature-bounds','index': ALL},'hideout')
            ]
        )(self.adv_update_overlays)

        # Adding filters
        self.blueprint.callback(
            [
                Output({'type': 'add-filter-parent','index': ALL},'children',allow_duplicate=True)
            ],
            [
                Input({'type': 'add-filter-butt','index': ALL},'n_clicks'),
                Input({'type': 'delete-filter','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'overlay-property-info','index': ALL},'data'),
                State({'type': 'overlay-drop','index': ALL},'options')
            ]
        )(self.add_filter)

        # Changing the filter selector based on dropdown selection
        self.blueprint.callback(
            [
                Input({'type': 'add-filter-drop','index': MATCH},'value')
            ],
            [
                Output({'type': 'add-filter-selector-div','index': MATCH},'children')
            ],
            [
                State({'type': 'overlay-property-info','index': ALL},'data')
            ]
        )(self.update_filter_selector)

        # Opening create layer options from filter (if any filters are specified)
        self.blueprint.callback(
            [
                Input({'type':'create-layer-from-filter','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'map-layers-control','index': ALL},'children'),
                Output({'type': 'map-annotations-store','index': ALL},'data')
            ],
            [
                State({'type': 'add-filter-parent','index': ALL},'children'),
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'feature-overlay','index': ALL},'name'),
                State({'type': 'feature-lineColor','index': ALL},'value'),
                State({'type': 'adv-overlay-colormap','index': ALL},'value'),
            ]
        )(self.create_layer_from_filter)

        # Adding new structures to the line color selector
        self.blueprint.callback(
            [
                Input({'type': 'feature-overlay','index':ALL},'name')
            ],
            [
                Output({'type': 'feature-lineColor-opts','index': ALL},'children')
            ]
        )(self.add_structure_line_color)

        # Exporting current layers
        self.blueprint.callback(
            [
                Input({'type': 'export-current-layers','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'export-current-layers-data','index': ALL},'data')
            ],
            [
                State({'type': 'map-annotations-store','index': ALL},'data'),
                State({'type': 'map-slide-information','index':ALL},'data')
            ]
        )(self.export_layers)

    def update_slide(self, new_annotations_info:list):
        
        if not any([i['value'] for i in ctx.triggered]):
            return [[]], [json.dumps({})], [[]], [[]]

        new_annotations_info = json.loads(get_pattern_matching_value(new_annotations_info))
        overlay_options = new_annotations_info['available_properties']
        feature_names = new_annotations_info['feature_names']
        overlay_info = new_annotations_info['property_info']

        drop_options = [
            {
                'label': i,
                'value': i
            }
            for i in overlay_options
        ]

        property_info = json.dumps(overlay_info)
        filter_children = []
        feature_lineColor_children = [
            dbc.Tab(
                children = [
                    dmc.ColorPicker(
                        id = {'type': f'{self.component_prefix}-feature-lineColor','index': f_idx},
                        format = 'hex',
                        value = '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255)),
                        fullWidth=True
                    ),
                    dbc.Button(
                        id = {'type': f'{self.component_prefix}-feature-lineColor-butt','index': f_idx},
                        children = ['Update Boundary Color'],
                        className = 'd-grid col-12 mx-auto',
                        n_clicks = 0
                    )
                ],
                label = f
            )
            for f_idx, f in enumerate(feature_names)
        ]

        return [drop_options], [property_info],[filter_children], [feature_lineColor_children]
 
    def add_filter(self, add_filter_click, delete_filter_click,overlay_info_state,overlay_options):
        """Adding a new filter to apply to GeoJSON features

        :param add_filter_click: Add filter icon clicked
        :type add_filter_click: _type_
        :param delete_filter_click: Delete filter icon (x) clicked
        :type delete_filter_click: _type_
        :param overlay_info_state: Summary information on properties for GeoJSON features
        :type overlay_info_state: _type_
        :raises exceptions.PreventUpdate: Stop callback execution
        :raises exceptions.PreventUpdate: No information provided for GeoJSON properties, cancels adding new filter.
        :return: List of current filters applied to GeoJSON features
        :rtype: list
        """
        
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        add_filter_click = get_pattern_matching_value(add_filter_click)
        overlay_options = get_pattern_matching_value(overlay_options)
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))
        #TODO: See if these can be added as an "OR" or "AND" to get more specific filtering 
        if len(list(overlay_info_state.keys()))==0:
            raise exceptions.PreventUpdate

        active_filters = Patch()
        if 'delete-filter' in ctx.triggered_id['type']:

            values_to_remove = []
            for i,val in enumerate(delete_filter_click):
                if val:
                    values_to_remove.insert(0,i)
            
            for v in values_to_remove:
                del active_filters[v]

        elif 'add-filter-butt' in ctx.triggered_id['type']:
            
            # Initializing dropdown value 
            overlayBounds = overlay_info_state[overlay_options[0]['label']]
            if 'min' in overlayBounds:
                # Used for numeric filtering
                values_selector = html.Div(
                    dcc.RangeSlider(
                        id = {'type': f'{self.component_prefix}-add-filter-selector','index': add_filter_click},
                        min = overlayBounds['min']-0.01,
                        max = overlayBounds['max']+0.01,
                        value = [overlayBounds['min'],overlayBounds['max']],
                        step = 0.01,
                        marks = None,
                        tooltip = {'placement':'bottom','always_visible': True},
                        allowCross = True,
                        disabled = False
                    ),
                    id = {'type': f'{self.component_prefix}-add-filter-selector-div','index': add_filter_click},
                    style = {'display': 'inline-block','margin': 'auto','width': '100%'}
                )
            elif 'unique' in overlayBounds:
                # Used for categorical filtering
                values_selector = html.Div(
                    dcc.Dropdown(
                        id = {'type':f'{self.component_prefix}-add-filter-selector','index': add_filter_click},
                        options = overlayBounds['unique'],
                        value = overlayBounds['unique'],
                        multi = True
                    ),
                    id = {'type': f'{self.component_prefix}-add-filter-selector-div','index': add_filter_click}
                )
            
            def new_filter_item():
                return html.Div([
                    dbc.Row([
                        dbc.Col(
                            dcc.Dropdown(
                                options = overlay_options,
                                value = overlay_options[0],
                                placeholder = 'Select property to filter structures',
                                id = {'type': f'{self.component_prefix}-add-filter-drop','index': add_filter_click}
                            ),
                            md = 10
                        ),
                        dbc.Col([
                            html.I(
                                id = {'type': f'{self.component_prefix}-delete-filter','index': add_filter_click},
                                n_clicks = 0,
                                className = 'bi bi-x-circle-fill fa-2x',
                                style = {'color': 'rgb(255,0,0)'}
                            ),
                            dbc.Tooltip(
                                target = {'type': f'{self.component_prefix}-delete-filter','index': add_filter_click},
                                children = 'Delete this filter'
                            )
                            ],
                            md = 2
                        )
                    ],align='center'),
                    values_selector
                ])
            
            active_filters.append(new_filter_item())

        return [active_filters]
    
    def update_filter_selector(self, add_filter_value, overlay_info_state):
        """Updating the filter selector (either a RangeSlider or Dropdown component depending on property type)


        :param add_filter_value: Selected property to be used for filters.
        :type add_filter_value: str
        :param overlay_info_state: Current information on GeoJSON feature properties (contains "min" and "max" for numeric properties and "unique" for categorical properties)
        :type overlay_info_state: list
        :raises exceptions.PreventUpdate: Stop callback execution
        :return: Filter selector. Either a dropdown menu for categorical properties or a dcc.RangeSlider for selecting a range of values between the minimum and maximum for that property
        :rtype: _type_
        """

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))
        overlayBounds = overlay_info_state[add_filter_value]
        if 'min' in overlayBounds:
            # Used for numeric filtering
            values_selector = dcc.RangeSlider(
                id = {'type': f'{self.component_prefix}-add-filter-selector','index': ctx.triggered_id['index']},
                min = overlayBounds['min']-0.01,
                max = overlayBounds['max']+0.01,
                value = [overlayBounds['min'],overlayBounds['max']],
                step = 0.01,
                marks = None,
                tooltip = {'placement':'bottom','always_visible': True},
                allowCross = True,
                disabled = False
            )
        
        elif 'unique' in overlayBounds:
            # Used for categorical filtering
            values_selector = dcc.Dropdown(
                id = {'type':f'{self.component_prefix}-add-filter-selector','index': ctx.triggered_id['index']},
                options = overlayBounds['unique'],
                value = overlayBounds['unique'],
                multi = True
            )

        return values_selector

    def parse_added_filters(self, add_filter_parent:list)->list:
        """Getting all filter values from parent div


        :param add_filter_parent: List of dictionaries containing component information from dynamically added filters.
        :type add_filter_parent: list
        :return: List of filter values to apply to current GeoJSON features.
        :rtype: list
        """
        processed_filters = []

        if not add_filter_parent is None:
            for div in add_filter_parent:
                div_children = div['props']['children']
                filter_name = div_children[0]['props']['children'][0]['props']['children']['props']['value']

                if 'value' in div_children[1]['props']['children']['props']:
                    filter_value = div_children[1]['props']['children']['props']['value']
                else:
                    filter_value = div_children[1]['props']['children']['props']['children']['props']['value']

                processed_filters.append({
                    'name': filter_name,
                    'range': filter_value
                })

        return processed_filters

    def update_overlays(self, overlay_value, transp_value, lineColor_butt, filter_parent, filter_value, delete_filter, overlay_state, transp_state, overlay_info_state, lineColor_state, overlay_names, colormap_width, colormap_val, current_hideout):
        """Update overlay transparency and color based on property selection

        Adding new values to the "hideout" property of the GeoJSON layers triggers the featureStyle Namespace function

        :param overlay_value: Value to use as a basis for generating colors (range of colors for numeric properties and list of colors for categorical properties)
        :type overlay_value: list
        :param transp_value: Transparency value for each feature.
        :type transp_value: list
        :param lineColor_butt: Whether the button to update the lineColor property was clicked.
        :type lineColor_butt: list
        :param filter_parent: Parent Div containing filter information
        :type filter_parent: list
        :param filter_value: Whether the callback is triggered by a new filter value being selected
        :type filter_value: list
        :param delete_filter: Whether the callback is triggered by a filter being deleted
        :type delete_filter: list
        :param overlay_state: State of overlay dropdown if not triggered by new overlay value selection
        :type overlay_state: list
        :param transp_state: State of transparency slider if not triggered by transparency slider adjustment
        :type transp_state: list
        :param overlay_info_state: Information on overlay properties for current GeoJSON features
        :type overlay_info_state: list
        :param lineColor_state: Current selected lineColors to apply to current GeoJSON features
        :type lineColor_state: list
        :param colormap_width: Current colorbar width
        :type colormap_width: list
        :param colormap_val: Current colormap applied to overlays,
        :type colormap_val: list
        :param current_hideout: Current hideout properties assigned to each GeoJSON layer
        :type current_hideout: list
        :return: List of dictionaries added to the GeoJSONs' "hideout" property (used by Namespace functions) and a colorbar based on overlay value.
        :rtype: tuple
        """

        start = time.time()
        overlay_value = get_pattern_matching_value(overlay_value)
        transp_value = get_pattern_matching_value(transp_value)
        overlay_state = get_pattern_matching_value(overlay_state)
        transp_state = get_pattern_matching_value(transp_state)
        colormap_val = get_pattern_matching_value(colormap_val)
        colormap_width = get_pattern_matching_value(colormap_width)
        overlay_info_state = json.loads(get_pattern_matching_value(overlay_info_state))

        if 'overlay-drop' in ctx.triggered_id['type']:
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

        if 'overlay-trans-slider' in ctx.triggered_id['type']:
            use_transp_value = transp_value
        else:
            use_transp_value = transp_state

        if any([i in ctx.triggered_id['type'] for i in ['add-filter-parent', 'add-filter-selector','delete-filter']]):
            use_overlay_value = overlay_state
            use_transp_value = transp_state

        if 'feature-lineColor-butt' in ctx.triggered_id['type']:
            use_overlay_value = overlay_state
            use_transp_value = transp_state


        if not use_overlay_value is None:
            overlay_prop = {
                'name': use_overlay_value,
            }
        else:
            overlay_prop = {
                'name': None,
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
            for i,j in zip(overlay_names, lineColor_state)
        }
        
        color_bar_style = {
            'visibility':'visible',
            'background':'white',
            'background':'rgba(255,255,255,0.8)',
            'box-shadow':'0 0 15px rgba(0,0,0,0.2)',
            'border-radius':'10px',
            'width': f'{colormap_width+100}px',
            'padding':'0px 0px 0px 25px'
        }

        if 'min' in overlay_bounds:
            colorbar = [
                dl.Colorbar(
                    colorscale = colormap_val if not '->' in colormap_val else colormap_val.split('->'),
                    width = colormap_width,
                    height = 15,
                    position = 'bottomleft',
                    id = f'colorbar{np.random.randint(0,100)}',
                    min = overlay_bounds.get('min'),
                    max = overlay_bounds.get('max'),
                    style = color_bar_style,
                    tooltip=True
                )
            ]
        elif 'unique' in overlay_bounds:
            colorbar = [
                dlx.categorical_colorbar(
                    categories = overlay_bounds['unique'],
                    colorscale = colormap_val if not '->' in colormap_val else colormap_val.split('->'),
                    style = color_bar_style,
                    position = 'bottomleft',
                    id = f'colorbar{np.random.randint(0,100)}',
                    width = colormap_width,
                    height = 15
                )
            ]

        else:
            colorbar = [no_update]

        # Grabbing all filter values from the parent div
        filterVals = self.parse_added_filters(get_pattern_matching_value(filter_parent))

        geojson_hideout = [
            j | {
                'overlayBounds': overlay_bounds,
                'overlayProp': overlay_prop,
                'fillOpacity': fillOpacity,
                'lineColor': lineColor,
                'filterVals': filterVals,
            }
            for i,j in zip(range(len(ctx.outputs_list[0])),current_hideout)
        ]

        #print(f'Time for update_overlays: {time.time() - start}')

        return geojson_hideout, colorbar

    def adv_update_overlays(self, butt_click: list, colorbar_width:list, colormap_val:list, current_feature_hideout:list):
        """Update some additional properties of the overlays and display.

        :param butt_click: Button clicked to update overlay properties 
        :type butt_click: list
        :param colorbar_width: Width of colorbar in pixels
        :type colorbar_width: list
        :param colormap_val: Colormap option to pass to chroma
        :type colormap_val: list
        :param current_feature_hideout: Current hideout properties for all structures
        :type current_feature_hideout: list
        :return: Updated colorbar width, line width, and colormap
        :rtype: tuple
        """

        if not any([i['value'] for i in ctx.triggered]) or len(current_feature_hideout)==0:
            raise exceptions.PreventUpdate

        new_hideout = [no_update]*len(ctx.outputs_list[1])

        colorbar_width = get_pattern_matching_value(colorbar_width)
        colormap_val = get_pattern_matching_value(colormap_val)

        # Updating colorbar width and colormap:
        overlay_bounds = current_feature_hideout[0]['overlayBounds']

        if not colorbar_width==0:
            color_bar_style = {
                'visibility':'visible',
                'background':'white',
                'background':'rgba(255,255,255,0.8)',
                'box-shadow':'0 0 15px rgba(0,0,0,0.2)',
                'border-radius':'10px',
                'width': f'{colorbar_width+100}px',
                'padding':'0px 0px 0px 25px'
            }

            if 'min' in overlay_bounds:
                colorbar_div_children = [dl.Colorbar(
                    colorscale = colormap_val,
                    width = colorbar_width,
                    height = 15,
                    position = 'bottomleft',
                    id = f'{self.component_prefix}-colorbar{np.random.randint(0,100)}',
                    style = color_bar_style,
                    tooltip=True
                )]
            elif 'unique' in overlay_bounds:
                colorbar_div_children = [dlx.categorical_colorbar(
                    categories = overlay_bounds['unique'],
                    colorscale = colormap_val,
                    style = color_bar_style,
                    position = 'bottomleft',
                    id = f'{self.component_prefix}-colorbar{np.random.randint(0,100)}',
                    width = colorbar_width,
                    height = 15
                )]

            else:
                colorbar_div_children = [no_update]
        else:
            colorbar_div_children = [html.Div()]

        # Updating line width:
        new_hideout = [i | {'colorMap': colormap_val} for i in current_feature_hideout]

        return new_hideout, colorbar_div_children

    def create_layer_from_filter(self, icon_click:list, current_filters:list, current_annotations:list, current_overlay_names:list, line_colors: list, colormap: list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        current_filters = get_pattern_matching_value(current_filters)
        colormap = get_pattern_matching_value(colormap)

        if not current_filters is None:
            filter_list = self.parse_added_filters(current_filters)
            if len(filter_list)>0:

                current_annotations = json.loads(get_pattern_matching_value(current_annotations))
                filtered_geojson, filter_reference_list = process_filters_queries(filter_list,[],['all'],current_annotations)
                filtered_geojson['properties'] = {
                    'name': f'Filtered {len([i for i in current_overlay_names if "Filtered" in i])}',
                    '_id': uuid.uuid4().hex[:24]
                }

                line_colors_dict = {
                    i:j
                    for i,j in zip(current_overlay_names,line_colors)
                }
                line_colors_dict[filtered_geojson['properties']['name']] = '#%02x%02x%02x' % (np.random.randint(0,255),np.random.randint(0,255),np.random.randint(0,255))

                for f in filtered_geojson['features']:
                    f['properties']['name'] = filtered_geojson['properties']['name']

                if len(filtered_geojson['features'])>0:
                    new_children = Patch()
                    new_children.append(
                        dl.Overlay(
                            dl.LayerGroup(
                                dl.GeoJSON(
                                    data = filtered_geojson,
                                    id = {'type': f'{self.component_prefix}-feature-bounds','index': len(current_overlay_names)+1},
                                    options = {
                                        'style': self.js_namespace("featureStyle")
                                    },
                                    filter = self.js_namespace('featureFilter'),
                                    hideout = {
                                        'overlayBounds': {},
                                        'overlayProp': {},
                                        'fillOpacity': 0.5,
                                        'lineColor': line_colors_dict,
                                        'filterVals': [],
                                        'colorMap': colormap
                                    },
                                    hoverStyle = arrow_function(
                                        {
                                            'weight': 5,
                                            'color': '#9caf00',
                                            'dashArray': ''
                                        }
                                    ),
                                    zoomToBounds=False,
                                    children = [
                                        dl.Popup(
                                            id = {'type': f'{self.component_prefix}-feature-popup','index': len(current_overlay_names)+1},
                                            autoPan = False,
                                        )
                                    ]
                                )
                            ),
                            name = filtered_geojson['properties']['name'], checked = True, id = {'type': f'{self.component_prefix}-feature-overlay','index': len(current_overlay_names)}
                        )
                    )

                    current_annotations.append(filtered_geojson)

                    return [new_children], [json.dumps(current_annotations)]
                else:
                    raise exceptions.PreventUpdate
            else:
                raise exceptions.PreventUpdate
        else:
            raise exceptions.PreventUpdate

    def add_structure_line_color(self, overlay_names:list):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        line_color_tabs = Patch()
        line_color_tabs.append(
            dbc.Tab(
                children = [
                    dmc.ColorPicker(
                        id = {'type': f'{self.component_prefix}-feature-lineColor','index': len(overlay_names)},
                        format = 'hex',
                        value = '#FFFFFF',
                        fullWidth=True
                    ),
                    dbc.Button(
                        id = {'type': f'{self.component_prefix}-feature-lineColor-butt','index': len(overlay_names)},
                        children = ['Update Boundary Color'],
                        className = 'd-grid col-12 mx-auto',
                        n_clicks = 0
                    )
                ],
                label = overlay_names[-1]
            )
        )

        return [line_color_tabs]

    def export_layers(self, button_click, current_layers,slide_information):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        slide_information = json.loads(get_pattern_matching_value(slide_information))

        # Scaling annotations:
        current_layers = json.loads(get_pattern_matching_value(current_layers))
        scaled_layers = []
        for c in current_layers:
            scaled_layer = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]/slide_information['x_scale'],c[1]/slide_information['y_scale']),g),c)
            scaled_layers.append(scaled_layer)
        
        string_layers = json.dumps(scaled_layers)
        
        return [{'content': string_layers,'filename': 'fusion-tools-current-layers.json'}]








