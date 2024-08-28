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

import uuid

from typing_extensions import Union


def load_geojson(geojson_path: str, name = None) -> dict:
    """
    Load geojson annotations from filepath
    """
    assert os.path.exists(geojson_path)

    with open(geojson_path,'r') as f:
        geojson_anns = geojson.load(f)

        f.close()

    if not name is None:
        geojson_anns['properties'] = geojson_anns['properties'] | {'name': name, '_id': uuid.uuid4().hex[:24]}

    return geojson_anns

def load_histomics(json_path: str) -> list:
    """
    Load histomics annotations from filepath
    """
    assert os.path.exists(json_path)

    with open(json_path,'r') as f:
        json_anns = json.load(f)

        f.close()
    
    #TODO: update for non-polyline annotations

    if type(json_anns)==dict:
        json_anns = [json_anns]

    geojson_list = []
    for ann in json_anns:

        geojson_anns = {
            'type': 'FeatureCollection',
            'properties': ann['annotation']['name'],
            'features': [
                {
                    'type':'Feature',
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [
                            el['points']
                        ]
                    },
                    'properties': el['user'] if 'user' in el else {} | {'name': f'{ann["annotation"]["name"]}_{el_idx}', '_id': ann['annotation']['_id']}
                }
                for el_idx,el in enumerate(ann['annotation']['elements'])
            ]
        }

        geojson_list.append(geojson_anns)

    return geojson_list

def load_aperio(xml_path: str) -> list:
    """
    Load Aperio annotations from filepath
    """
    assert os.path.exists(xml_path)

    tree = ET.parse(xml_path)
    structures_in_xml = tree.getroot().findall('Annotation')
    
    geojson_list = []
    for ann_idx in range(0,len(structures_in_xml)):

        geojson_anns = {
            'type': "FeatureCollection",
            "features": [],
            'properties': {
                'name': f'Layer{ann_idx+1}',
                '_id': uuid.uuid4().hex[:24]
            }
        }
        this_structure = tree.getroot().findall(f'Annotation[@Id="{str(ann_idx+1)}"]/Regions/Region')

        for obj in this_structure:
            vertices = obj.findall('./Vertices/Vertex')
            coords = []
            for vert in vertices:
                coords.append([
                    int(float(vert.attrib['X'])),
                    int(float(vert.attrib['Y']))
                ])
            
            geojson_anns['features'].append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': coords
                },
                'properties': {
                    'name': f'Layer{ann_idx+1}'
                }
            })

        geojson_list.append(geojson_anns)

    return geojson_list

def load_polygon_csv(
        csv_path: str, 
        name: str,
        shape_cols: Union[list,str], 
        group_by_col: Union[str,None],
        property_cols: Union[str,list,None],
        shape_options: dict) -> dict:
    """
    Load csv formatted annotations from filepath
    shape_cols: should be x,y (names of columns for x and then y coordinates)
    group_by_col: name of column to group features by (used to determine which coordinates belong to the same structure for non-point annotations)
    property_cols: list of columns containing properties
    shape_options: dict with "radius" for point annotations (can be number or column that has number)
    """
    assert os.path.exists(csv_path)

    if type(shape_cols)==str:
        shape_cols = [shape_cols]

    if type(property_cols)==str:
        property_cols = [property_cols]


    geojson_anns = {
        'type': 'FeatureCollection',
        'features': [],
        'properties': {
            'name': name,
            '_id': uuid.uuid4().hex[:24]
        }
    }
    csv_anns = pd.read_csv(csv_path)

    if not group_by_col is None:
        groups = csv_anns[group_by_col].unique().tolist()

        for g in groups:

            g_rows = csv_anns[csv_anns[group_by_col].str.match(g)]
            if len(shape_cols)==2:
                x_coords = g_rows[shape_cols[0]].tolist()
                y_coords = g_rows[shape_cols[1]].tolist()

                coord_list = list(zip(x_coords,y_coords))
            elif len(shape_cols)==1:
                # Just make sure that they're x,y format
                coord_list = json.loads(g_rows[shape_cols[0]])

            props = {}
            if not property_cols is None:
                for p in property_cols:
                    g_prop = g_rows[p].unique().to_dict()
                    props[p] = g_prop

            geojson_anns['features'].append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon' if len(coord_list)>1 else 'Point',
                    'coordinates': [coord_list]
                },
                'properties': props
            })

    else:
        # Each row is one structure
        for g in csv_anns.shape[0]:
            
            if len(shape_cols)==2:
                x_coord = csv_anns.iloc[g,shape_cols[0]].tolist()[0]
                y_coord = csv_anns.iloc[g,shape_cols[1]].tolist()[0]
                coords = list(zip(x_coord,y_coord))

            elif len(shape_cols)==1:
                coords = json.loads(csv_anns.iloc[g,shape_cols[0]].tolist()[0])
            
            props = {}
            if not property_cols is None:
                g_row = csv_anns.iloc[g,:].to_dict()
                props = {
                    i: g_row[i]
                    for i in property_cols
                }

            geojson_anns['features'].append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon' if len(coords)>1 else 'Point',
                    'coordinates': [coords]
                },
                'properties': props
            })
            

    return geojson_anns

def align_object_props(
        geo_ann: dict, 
        prop_df: Union[pd.DataFrame, list],
        prop_cols: Union[list,str],
        alignment_type: str) -> dict:
    """
    Align object annotations with those in another file
    alignment_type options: 
        - "index" = row index--> feature index
        - "{property}" = prop_df[{property}] --> feature['properties'][{property}] matching
        - "bbox" = prop_df["bbox"] --> shape(feature['geometry']).bounds matching
    """

    if type(prop_df)==pd.DataFrame:
        prop_df = [prop_df]
    if type(prop_cols)==str:
        prop_cols = [prop_cols]
    
    for p in prop_df:
        if alignment_type=='index':
            # Lining up horizontally
            for r in prop_cols:
                prop_dict = p[r].to_dict()
                for i in range(len(geo_ann['features'])):
                    geo_ann['features'][i]['properties'] = geo_ann['features'][i]['properties'] | prop_dict

        elif alignment_type in p:
            # Lining up by column/property name
            align_vals = p[alignment_type].tolist()
            align_geo = [i['properties'][alignment_type] for i in geo_ann['features']]

            for a_idx,a in enumerate(align_vals):
                if a in align_geo:
                    add_props = p.iloc[a_idx,:].to_dict()
                    geo_ann['features'][align_geo.index(a)]['properties'] = geo_ann['features'][align_geo.index(a)]['properties'] | add_props




    return geo_ann

def export_annotations(
        ann_geojson: Union[dict,list], 
        format: str, 
        save_path: str,
        ann_options: dict = {}):
    """
    Exporting geojson annotations to desired format
    """
    assert format in ['geojson','aperio','histomics']

    if format in ['histomics','geojson']:
        if format=='geojson':
            if type(ann_geojson)==dict:
                ann_geojson = [ann_geojson]
            
            for ann_idx,ann in enumerate(ann_geojson):
                if 'name' in ann['properties']:
                    ann_name = ann['properties']['name']
                else:
                    ann_name = f'Structure_{ann_idx}'
                with open(save_path.replace('.geojson',f'{ann_name}.geojson'),'w') as f:
                    json.dump(ann_geojson,f)

                    f.close()

        elif format=='histomics':
            
            if type(ann_geojson)==dict:
                ann_geojson = [ann_geojson]

            histomics_anns = []
            for ann_idx,ann in enumerate(ann_geojson):
                ann_dict = {
                    'annotation': {
                        'name': ann['properties']['name'] if 'name' in ann['properties'] else f'Structure_{ann_idx}',
                        'elements': []
                    }
                }
                for f_idx, f in enumerate(ann['features']):
                    ann_dict['annotation']['elements'].append(
                        {
                            'type': 'polyline',
                            'points': [i+[0] for i in f['geometry']['coordinates']],
                            'user': f['properties']
                        }
                    )

                histomics_anns.append(ann_dict)

            with open(save_path,'w') as f:
                json.dump(histomics_anns,f)

                f.close()

    elif format=='aperio':

        if 'id' not in ann_options:
            ann_options['id'] = '1'
        if 'name' not in ann_options:
            ann_options['name'] = 'Layer1'

        output_xml = ET.Element('Annotations')
        output_xml = ET.SubElement(
            output_xml,
            'Annotation',
            attrib={
                'Type': '4',
                'Visible': '1',
                'ReadOnly': '0',
                'Incremental': '0',
                'LineColorReadOnly': '0',
                'Id': ann_options['id'],
                'NameReadOnly': '0',
                'LayerName': ann_options['name']
            }
        )

        output_xml = ET.SubElement(
            output_xml,
            'Regions'
        )

        for g_idx,g in enumerate(ann_geojson['features']):

            region = ET.SubElement(
                output_xml,
                'Region',
                attrib = {
                    'NegativeROA': '0',
                    'ImageFocus': '-1',
                    'DisplayId': str(g_idx+1),
                    'InputRegionId': '0',
                    'Analyze': '0',
                    'Type': '0',
                    'Id': str(g_idx+1)
                }
            )

            vertices = ET.SubElement(region,'Vertices')
            
            for vert in g['geometry']['coordinates']:
                ET.SubElement(vertices,'Vertex',attrib={'X': str(vert[0]),'Y': str(vert[1]),'Z':'0'})

            ET.SubElement(
                vertices,
                'Vertex',
                attrib = {
                    'X': str(g['geometry']['coordinates'][0][0]),
                    'Y': str(g['geometry']['coordinates'][0][1]),
                    'Z': '0'
                }
            )


        xml_string = ET.tostring(output_xml,encoding='unicode',pretty_print=True)
        with open(save_path,'w') as f:
            f.write(xml_string)

            f.close()

def find_intersecting(geo_source:dict, geo_query:Polygon, return_props:bool = True, return_shapes:bool = True):
    """
    Return properties and/or shapes of features from geo_1 that intersect with geo_2
    
    Parameters
    --------
    geo_source: dict
        GeoJSON dictionary containing "FeatureCollection" with "features" key

    geo_query: dict
        GeoJSON dictionary containing "FeatureCollection" with "features" key

    return_props: bool = True
        Whether to return properties of features from geo_source that intersect with geo_query

    return_shapes: bool = True
        Whether to return shape (geometries) of features from geo_source that intersect with geo_query
    
    """
    assert return_props or return_shapes

    # Automatically assigned properties by Leaflet (DO NOT ADD "cluster" AS A PROPERTY)
    ignore_properties = ['geometry','cluster','id']
    geo_source = gpd.GeoDataFrame.from_features(geo_source['features'])

    geo_source_intersect = geo_source[geo_source.intersects(geo_query)]
    geo_source_intersect_columns = geo_source_intersect.columns.tolist()
    geo_source_intersect_props = geo_source_intersect.iloc[:,[i for i in range(len(geo_source_intersect_columns)) if not geo_source_intersect_columns[i] in ignore_properties]]
    
    geo_intersect_geojson = json.loads(geo_source_intersect['geometry'].to_json())

    if return_props and return_shapes:
        return geo_intersect_geojson, geo_source_intersect_props
    elif return_props:
        return geo_source_intersect_props
    elif return_shapes:
        return geo_intersect_geojson



























