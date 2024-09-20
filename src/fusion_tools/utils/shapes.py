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
from skimage import draw
from scipy import ndimage

import pandas as pd

import uuid
import time

from typing_extensions import Union


def load_geojson(geojson_path: str, name:Union[str,None]=None) -> dict:
    """Load GeoJSON annotations from file path. Optionally add names for GeoJSON FeatureCollections

    :param geojson_path: Path to GeoJSON file
    :type geojson_path: str
    :param name: Name for structure present in FeatureCollection, defaults to None
    :type name: Union[str,None], optional
    :return: GeoJSON FeatureCollection dictionary
    :rtype: dict
    """
    assert os.path.exists(geojson_path)

    with open(geojson_path,'r') as f:
        geojson_anns = geojson.load(f)

        f.close()

    if not name is None:
        geojson_anns['properties'] = geojson_anns['properties'] | {'name': name, '_id': uuid.uuid4().hex[:24]}

    return geojson_anns

def load_histomics(json_path: str) -> list:
    """Load large-image annotation from filepath

    :param json_path: Path to large-image formatted annotations
    :type json_path: str
    :return: GeoJSON FeatureCollection formatted annotation
    :rtype: list
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
    """Loading Aperio formatted annotations

    :param xml_path: Path to Aperio formatted annotations (XML)
    :type xml_path: str
    :return: GeoJSON FeatureCollection formatted annotations for each layer in XML
    :rtype: list
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
                    int(float(vert.attrib['Y'])),
                    int(1.0)
                ])
            
            geojson_anns['features'].append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [coords]
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
    """Load csv formatted annotations from filepath

    :param csv_path: Path to CSV file containing annotations
    :type csv_path: str
    :param name: Name for structure contained in CSV file
    :type name: str
    :param shape_cols: Column(s) containing shape information
    :type shape_cols: Union[list,str],
    :param group_by_col: Column to use to group rows together (same value = same feature in resulting GeoJSON)
    :type group_by_col: Union[str,None]
    :param property_cols: Column(s) containing property information for each feature
    :type property_cols: Union[str,list,None]
    :param shape_options: Dictionary containing additional options to construct feature shape
    :type shape_options: dict
    :return: GeoJSON formatted FeatureCollection containing structure shape and properties
    :rtype: dict
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
    """Aligning GeoJSON formatted annotations with an external file containing properties for each feature

    :param geo_ann: GeoJSON formatted annotations to align with external file
    :type geo_ann: dict
    :param prop_df: Property DataFrame or list containing DataFrames to align with GeoJSON
    :type prop_df: Union[pd.DataFrame,list]
    :param prop_cols: Column(s) containing property information in each DataFrame
    :type prop_cols: Union[list,str]
    :param alignment_type: Process to use for aligning rows of property DataFrame to GeoJSON
    :type alignment_type: str
    :return: GeoJSON annotations with aligned properties applied
    :rtype: dict
    """

    if type(prop_df)==pd.DataFrame:
        prop_df = [prop_df]
    if type(prop_cols)==str:
        prop_cols = [prop_cols]
    
    for p in prop_df:
        if alignment_type=='index':
            # Lining up horizontally
            for r in prop_cols:
                if r in p:
                    prop_list = p[r].tolist()
                    for i in range(len(geo_ann['features'])):
                        geo_ann['features'][i]['properties'] = geo_ann['features'][i]['properties'] | {r: prop_list[i]}

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
    """Exporting GeoJSON annotations to a desired format

    :param ann_geojson: Individual or list of GeoJSON formatted annotations
    :type ann_geojson: Union[dict,list]
    :param format: What format to export these annotations to
    :type format: str
    :param save_path: Where to save the exported annotations
    :type save_path: str
    :param ann_options: Additional options to pass to export (used to add an id or layer name for Aperio formatted annotations)
    :type ann_options: dict, optional
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
    """Return properties and/or shapes of features from geo_source that intersect with geo_query

    :param geo_source: Source GeoJSON where you are searching for intersecting features
    :type geo_source: dict
    :param geo_query: Query polygon used to filter source GeoJSON features
    :type geo_query: shapely.geometry.Polygon
    :param return_props: Whether or not to return properties of intersecting features
    :type return_props: bool, optional
    :param return_shapes: Whether or not to return shape information of intersecting features
    :type return_shapes: bool, optional

    :return: Intersecting properties and/or shapes from geo_source
    :rtype: tuple
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

def spatially_aggregate(agg_geo:dict, base_geos: list):
    """Aggregate intersecting feature properties to a provided GeoJSON 

    :param agg_geo: GeoJSON object that is receiving aggregated properties
    :type agg_geo: dict
    :param base_geos: List of GeoJSON objects which are intersecting with agg_geo
    :type base_geos: list
    :return: Updated agg_geo object with new properties from intersecting base_geos
    :rtype: dict
    """

    for b in base_geos:
        if type(b)==dict:
            b_name = b['properties']['name']
            for f in agg_geo['features']:
                f_shape = shape(f['geometry'])
                intersecting_shapes, intersecting_props = find_intersecting(b,f_shape)

                if len(intersecting_shapes['features'])>0:
                    
                    f['properties'][b_name] = {}

                    intersecting_areas = [
                        shape(i['geometry']).intersection(f_shape).area
                        for i in intersecting_shapes['features']
                    ]

                    f['properties'][b_name]['count'] = len(intersecting_shapes['features'])
                    f['properties'][b_name]['area'] = sum(intersecting_areas)

                    intersecting_props_cols = intersecting_props.columns.tolist()
                    numeric_props = intersecting_props.select_dtypes(exclude='object')
                    if not numeric_props.empty:
                        for c in numeric_props.columns.tolist():
                            c_max = numeric_props[c].nanmax()
                            c_min = numeric_props[c].nanmin()
                            c_mean = numeric_props[c].nanmean()
                            c_sum = numeric_props[c].nansum()

                            f['properties'][b_name][f'{c} Max'] = c_max
                            f['properties'][b_name][f'{c} Min'] = c_min
                            f['properties'][b_name][f'{c} Mean'] = c_mean
                            f['properties'][b_name][f'{c} Sum'] = c_sum
                    
                    object_props = intersecting_props.iloc[:,[i for i in range(len(intersecting_props_cols)) if not intersecting_props_cols[i] in numeric_props]]
                    if not object_props.empty:
                        for c in object_props.columns.tolist():
                            col_type = list(set([type(i) for i in object_props[c].tolist()]))

                            if len(col_type)==1:
                                if col_type[0]==str:
                                    c_counts = object_props[c].value_counts().to_dict()
                                    for i,j in c_counts.items():
                                        f['properties'][b_name][i] = j
                                elif col_type[0]==dict:
                                    c_df = pd.DataFrame.from_records(object_props[c].tolist())
                                    f['properties'][b_name][c] = {
                                        'mean': c_df.nanmean(axis=0).to_dict(),
                                        'max': c_df.nanmax(axis=0).to_dict(),
                                        'min': c_df.nanmin(axis=0).to_dict(),
                                        'sum': c_df.nansum(axis=0).to_dict()
                                    }


    return agg_geo

def extract_nested_prop(main_prop_dict: dict, depth: int, path: tuple = (), values_list: list = []):
    """Extracted nested properties up to depth level.

    :param main_prop_dict: Main dictionary containing nested properties. ex: {'main_prop': {'sub_prop1': value1, 'sub_prop2': value2}}
    :type main_prop_dict: dict
    :param depth: Number of levels to extend into nested dictionary
    :type depth: int
    """
    if len(list(main_prop_dict.keys()))>0 and depth>0:
        for keys, values in main_prop_dict.items():
            if depth == 1:
                if type(values) in [int,float,str]:
                    values_list.append({
                        ' --> '.join(list(path+(keys,))): values
                    })
                else:
                    # Skipping properties that are still nested
                    continue
            else:
                if type(values)==dict:
                    extract_nested_prop(values, depth-1, path+ (keys,), values_list)
                else:
                    # Only adding properties to the list one time
                    if not any([' --> '.join(list(path+(keys,))) in list(i.keys()) for i in values_list]):
                        values_list.append({
                            ' --> '.join(list(path+(keys,))): values
                        }) 

    return values_list

def extract_geojson_properties(geo_list: list, reference_object: Union[str,None] = None, ignore_list: Union[list,None]=None, nested_depth:int = 4) -> list:
    """Extract property names and info for provided list of GeoJSON structures.

    :param geo_list: List of GeoJSON dictionaries containing properties
    :type geo_list: list
    :param reference_object: File path to reference object containing more information for each structure, defaults to None
    :type reference_object: Union[str,None], optional
    :param ignore_list: List of properties to hide from the main view, defaults to None
    :type ignore_list: Union[list,None], optional
    :param nested_depth: For properties stored as nested dictionaries, specify desired depth (depth of 2 = {'property_name': {'sub-prop1': val, etc.}}), defaults to 2
    :type nested_depth: int, optional
    :return: List of accessible properties in visualization session.
    :rtype: list
    """

    if ignore_list is None:
        ignore_list = []

    geojson_properties = []
    feature_names = []
    property_info = {}
    for ann in geo_list:
        feature_names.append(ann['properties']['name'])
        for f in ann['features']:
            f_props = [i for i in list(f['properties'].keys()) if not i in ignore_list]
            for p in f_props:
                # Checking for sub-properties
                sub_props = []
                if type(f['properties'][p])==dict:
                    nested_value = extract_nested_prop({p: f['properties'][p]}, nested_depth, (), [])
                    if len(nested_value)>0:
                        for n in nested_value:
                            n_key = list(n.keys())[0]
                            n_value = list(n.values())[0]
                            if not n_key in property_info:
                                sub_props.append(n_key)
                                if type(n_value) in [int,float]:
                                    property_info[n_key] = {
                                        'min': n_value,
                                        'max': n_value,
                                        'distinct': 1
                                    }
                                elif type(n_value) in [str]:
                                    property_info[n_key] = {
                                        'unique': [n_value],
                                        'distinct': 1
                                    }
                            else:
                                if type(n_value) in [int,float]:
                                    if n_value < property_info[n_key]['min']:
                                        property_info[n_key]['min'] = n_value
                                        property_info[n_key]['distinct'] +=1
                                    
                                    if n_value > property_info[n_key]['max']:
                                        property_info[n_key]['max'] = n_value
                                        property_info[n_key]['distinct'] +=1

                                elif type(n_value) in [str]:
                                    if not n_value in property_info[n_key]['unique']:
                                        property_info[n_key]['unique'].append(n_value)
                                        property_info[n_key]['distinct'] +=1

                else:
                    f_sup_val = f['properties'][p]

                    if not p in property_info:
                        sub_props = [p]
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
    
    geojson_properties = sorted(geojson_properties)

    return geojson_properties, feature_names, property_info

# Taken from plotly image annotation tutorial: https://dash.plotly.com/annotations#changing-the-style-of-annotations
def path_to_indices(path):
    """
    From SVG path to numpy array of coordinates, each row being a (row, col) point
    """
    indices_str = [
        el.replace("M", "").replace("Z", "").split(",") for el in path.split("L")
    ]
    return np.rint(np.array(indices_str, dtype=float)).astype(int)

def path_to_mask(path, shape):
    """
    From SVG path to a boolean array where all pixels enclosed by the path
    are True, and the other pixels are False.
    """
    cols, rows = path_to_indices(path).T
    rr, cc = draw.polygon(rows, cols)

    # Clipping values for rows and columns to "shape" (annotations on the edge are counted as dimension+1)
    rr = np.clip(rr,a_min=0,a_max=int(shape[0]-1))
    cc = np.clip(cc,a_min=0,a_max=int(shape[1]-1))

    mask = np.zeros(shape, dtype=bool)
    mask[rr, cc] = True
    mask = ndimage.binary_fill_holes(mask)
    return mask















