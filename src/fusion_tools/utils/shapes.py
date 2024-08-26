"""
Utility functions for data derived from FUSION

"""

import os
import sys
import json
import geojson
import lxml.etree as ET

import numpy as np

import geopandas as gpd
from shapely.geometry import Polygon, Point, shape
import pandas as pd


from typing_extensions import Union


def load_geojson(geojson_path: str) -> dict:
    """
    Load geojson annotations from filepath
    """
    assert os.path.exists(geojson_path)

    with open(geojson_path,'r') as f:
        geojson_anns = geojson.load(f)

        f.close()

    return geojson_anns

def load_histomics(json_path: str) -> dict:
    """
    Load histomics annotations from filepath
    """
    assert os.path.exists(json_path)

    with open(json_path,'r') as f:
        json_anns = json.load(f)

        f.close()
    
    #TODO: update for non-polyline annotations

    if isinstance(json_anns,dict):
        geojson_anns = {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [
                            el['points']
                        ]
                    },
                    'properties': {
                        'user': el['user'] if 'user' in el else {}
                    }
                }
                for el in json_anns['annotation']['elements']
            ]
        }
    elif isinstance(json_anns,list):

        geojson_anns = {
            'type': 'FeatureCollection',
            'features': []
        }
        for ann in json_anns:
            geojson_anns['features'].extend(
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [
                            el['points']
                        ]
                    },
                    'properties': el['user'] if 'user' in el else {}
                }
                for el in ann['annotation']['elements']
            )

    return geojson_anns

def load_xml(xml_path: str):
    """
    Load Aperio annotations from filepath
    """
    pass

def load_polygon_csv(csv_path: str, shape_cols: list, property_cols: list):
    """
    Load csv formatted annotations from filepath
    """
    pass

def align_object_props(
        geo_df: Union[gpd.GeoSeries, gpd.GeoDataFrame], 
        prop_df: Union[pd.DataFrame, list],
        alignment_type: str):
    """
    Align object annotations with those in another file
    """
    pass

def export_annotations(
        ann_geojson: dict, 
        format: str, 
        save_path: str):
    """
    Exporting geojson annotations to desired format
    """
    pass























































































