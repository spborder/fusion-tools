"""Example CustomComponent added to visualization session
"""

import os
import sys
sys.path.append('./src/')

import numpy as np
import pandas as pd

from dash import dcc, callback, ctx, ALL, MATCH, exceptions, no_update, Patch, dash_table
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform
from dash_extensions.javascript import assign
import dash_leaflet as dl

from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.utils.shapes import find_intersecting, extract_geojson_properties

from sklearn.cluster import DBSCAN
from shapely.geometry import box, shape
from umap import UMAP

from fusion_tools import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import SlideMap, Tool


def gen_clusters(feature_data, feature_cols, eps = 0.3, min_samples = 10):
    """
    Implementation of DBSCAN for generating cluster labels and noise labels
    """

    if feature_data.shape[0]<min_samples:
        return None

    quant_data = feature_data.loc[:,[i for i in feature_cols if i in feature_data.columns]].values

    feature_data_means = np.nanmean(quant_data,axis=0)
    feature_data_stds = np.nanstd(quant_data,axis=0)

    scaled_data = (quant_data-feature_data_means)/feature_data_stds
    scaled_data[np.isnan(scaled_data)] = 0.0
    scaled_data[~np.isfinite(scaled_data)] = 0.0

    umap_data = UMAP().fit_transform(scaled_data)

    clusterer = DBSCAN(eps = eps, min_samples = min_samples).fit(umap_data)
    cluster_labels = clusterer.labels_
    string_labels = [f'Cluster {i}' if not i==-1 else 'Noise' for i in cluster_labels]

    return string_labels

class ClusterComponent(Tool):
    """Find intersecting structures in a map, extract features, cluster, and display cluster labels
    """
    def __init__(self):
        """You can initialize data to the component here, or get data as the result of a callback.
        """
        
        super().__init__()

    def __str__(self):
        return 'Cluster Component'

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix
        # Add a title to display on top of the component in a layout
        self.title = 'Cluster Component'

        # The DashBlueprint() allows for these components to be embedded in a larger layout, 
        # linking callbacks to other components that are also in the main layout.
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        # Adding interactivity through callbacks
        self.get_callbacks()

    def gen_layout(self,session_data:dict):
        
        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3('Cluster Component')
                    ),
                    html.Hr(),
                    dbc.Row(
                        'Extract properties of intersecting structures, then run a clustering algorithm to find groups'
                    ),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dcc.Loading(
                                dbc.Button(
                                    'Get Properties From Current Structures!',
                                    n_clicks = 0,
                                    className = 'd-grid col-12 mx-auto',
                                    id = {'type': 'cluster-properties-button','index': 0}
                                )
                            )
                        ])
                    ]),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'cluster-properties-parent','index':0},
                                children = [
                                    'Click the "Get Properties" button to get started.'
                                ]
                            )
                        ])
                    ])
                ])
            )
        ])

        self.blueprint.layout = layout
    
    def get_callbacks(self):
        """Adding callbacks to the blueprint
        """

        self.blueprint.callback(
            [
                Input({'type': 'cluster-properties-button','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'cluster-properties-parent','index': ALL},'children')
            ],
            [
                State({'type': 'feature-bounds','index': ALL},'data'),
                State({'type': 'slide-map','index': ALL},'bounds')
            ]
        )(self.get_data_callback)

        self.blueprint.callback(
            [
                Input({'type': 'cluster-properties-cluster-button','index': ALL},'n_clicks')
            ],
            [
                Output({'type':'map-marker-div','index': ALL},'children')
            ],
            [
                State({'type': 'cluster-properties-table','index': ALL},'data')
            ]
        )(self.cluster_properties)

    def get_data_callback(self, button_click, current_features, slide_map_bounds):
        """Getting properties from current features

        :param button_click: Button clicked
        :type button_click: list
        :param current_features: Current GeoJSON FeatureCollections in the SlideMap
        :type current_features: list
        :param slide_map_bounds: Boundary coordinates for the current viewport
        :type slide_map_bounds: list
        """
        slide_map_bounds = get_pattern_matching_value(slide_map_bounds)
        # Converting slide map bounds into a shapely Polygon
        current_bounds = box(slide_map_bounds[0][1],slide_map_bounds[0][0],slide_map_bounds[1][1],slide_map_bounds[1][0])
        # Finding intersecting shapes and properties from the map
        property_tables = []
        for g_idx,g in enumerate(current_features):
            intersecting_shapes, intersecting_properties = find_intersecting(g, current_bounds)

            # Cleaning up nested columns:
            intersecting_properties = intersecting_properties.select_dtypes(exclude='object')
            intersecting_properties['bbox'] = [list(shape(i['geometry']).bounds) for i in intersecting_shapes['features']]

            property_tables.append(
                html.Div([
                    dbc.Row([
                        f'{g["properties"]["name"]}: {len(intersecting_properties)}'
                    ]),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col([
                            dash_table.DataTable(
                                id = {'type': f'{self.component_prefix}-cluster-properties-table','index': g_idx},
                                columns = [{'name': i,'id': i,'deletable': False} for i in intersecting_properties.columns],
                                data = intersecting_properties.to_dict('records'),
                                filter_action = 'native',
                                sort_action = 'native',
                                sort_mode = 'multi',
                                style_table = {
                                    'overflowX':'auto',
                                    'maxWidth': '800px'
                                },
                                tooltip_data = [
                                    {
                                        column: {'value':str(value), 'type': 'markdown'}
                                        for column,value in row.items()
                                    } for row in intersecting_properties.to_dict('records')
                                ],
                                tooltip_duration = None
                            )
                        ],style = {'maxHeight': '400px','overflow': 'scroll'})
                    ]),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(
                            dcc.Loading(
                                dbc.Button(
                                    f'Cluster {g["properties"]["name"]}',
                                    n_clicks = 0,
                                    className = 'd-grid col-12 mx-auto',
                                    id = {'type': f'{self.component_prefix}-cluster-properties-cluster-button','index': g_idx}
                                )
                            )
                        )
                    ])
                ],style = {'maxHeight': '100vh','overflow': 'scroll'})
            )


        return [property_tables]

    def cluster_properties(self, button_click, current_data):
        """Run clustering of provided data and return set of labels on map

        :param button_click: Button clicked
        :type button_click: list
        :param current_data: Current property data in table
        :type current_data: list
        """
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        colorscale = 'blue->red'
        
        current_data = pd.DataFrame.from_records(current_data[ctx.triggered_id['index']])
        if current_data.shape[0]>10:
            cluster_labels = gen_clusters(
                feature_data=current_data,
                feature_cols = [i for i in current_data if not i=='bbox']
            )
        else:
            cluster_labels = [f'Cluster 1' for i in range(0,current_data.shape[0])]

        feature_bboxes = current_data['bbox'].tolist()
        feature_coords = [[(i[0]+i[2])/2, (i[1]+i[3])/2] for i in feature_bboxes]

        unique_clusters = list(set(cluster_labels))
        cluster_colors = [f'rgb({np.random.randint(0,255)},{np.random.randint(0,255)},{np.random.randint(0,255)})' if not i=='Noise' else 'rgb(0,0,0)' for i in unique_clusters]

        cluster_labels = [
            cluster_colors[unique_clusters.index(i)]
            for i in cluster_labels
        ]


        cluster_markers_list = [
            dl.CircleMarker(
                center = c_coords[::-1],
                radius = 5,
                color = c_color,
                children = [
                    dl.Tooltip(
                        unique_clusters[cluster_colors.index(c_color)] if not c_color=='rgb(0,0,0)' else 'Noise'
                    )
                ]
            )
            for c_coords,c_color in zip(feature_coords,cluster_labels)
        ]

        cluster_markers_list += [
            dl.Colorbar(
                colorscale=cluster_colors,
                width = 20,
                height = 150,
                min = 0,
                max = len(unique_clusters),
                unit = 'Cluster'
            )
        ]


        return [cluster_markers_list]



def main():

    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    item_id = '64f545302d82d04be3e39eec'

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )

    vis_session = Visualization(
        tileservers=[dsa_handler.get_tile_server(item_id)],
        components = [
            [
                SlideMap(),
                [
                    ClusterComponent()
                ]
            ]
        ]
    )

    vis_session.start()


if __name__=="__main__":
    main()

