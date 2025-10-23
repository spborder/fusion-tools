"""
Utility functions for data derived from FUSION

"""

import os
import sys
import json
import geojson
import lxml.etree as ET
from copy import deepcopy
from math import floor, pi

import numpy as np

import rasterio
import rasterio.features
import geopandas as gpd
from shapely.geometry import Polygon, Point, shape
from skimage import draw
from scipy import ndimage

import pandas as pd
#import anndata as ad
import large_image

from tqdm import tqdm

import uuid

from typing_extensions import Union
import time


def load_annotations(file_path: str, name:Union[str,None]=None,**kwargs) -> dict:
    assert os.path.exists(file_path)

    file_extension = file_path.split(os.sep)[-1].split('.')[-1]
    try:
        if file_extension=='xml':
            annotations = load_aperio(file_path)
        elif file_extension in ['json','geojson']:
            try:
                annotations = load_geojson(file_path,name)
            except:
                annotations = load_histomics(file_path)
        elif file_extension=='parquet':
            annotations = load_parquet(file_path)
        
        elif file_extension=='csv':
            annotations = load_polygon_csv(file_path,name,**kwargs)
        elif file_extension in ['tif','png','jpg','tiff']:
            annotations = load_label_mask(file_path,name)
        elif file_extension in ['h5ad']:
            annotations = load_visium(file_path,**kwargs)
        else:
            annotations = None

    except:
        annotations = None

    return annotations

def load_parquet(parquet_path:str, geometry_cols:Union[list,None]=None):

    parquet_anns = gpd.read_parquet(parquet_path,columns = geometry_cols)
    geojson_anns = json.loads(parquet_anns.to_geo_dict(show_bbox=True))

    geojson_anns['properties'] = {
        'name': parquet_path.split(os.sep)[-1],
        '_id': uuid.uuid4().hex[:24]
    }

    return geojson_anns

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
        geojson_anns = json.load(f)
        f.close()

    if type(geojson_anns)==list:
        for g in geojson_anns:
            if not 'properties' in g:
                g['properties'] = {}
            else:
                if 'name' in g['properties'] and name is None:
                    name = g['properties']['name']

            geo_id = uuid.uuid4().hex[:24] if not '_id' in g['properties'] else g['properties']['_id']
            g['properties'] = g['properties'] | {'name': name if not name is None else geo_id, '_id': geo_id}

            for f_idx, f in enumerate(g['features']):
                f['properties'] = f['properties'] | {'name': name if not name is None else geo_id, '_id': uuid.uuid4().hex[:24], '_index': f_idx}

    elif type(geojson_anns)==dict:
        if not 'properties' in geojson_anns:
            geojson_anns['properties'] = {}

        geo_id = uuid.uuid4().hex[:24] if not '_id' in geojson_anns['properties'] else geojson_anns['properties']['_id']
        geojson_anns['properties'] = geojson_anns['properties'] | {'name': name if not name is None else geo_id, '_id': geo_id}

        for f_idx, f in enumerate(geojson_anns['features']):
            f['properties'] = f['properties'] | {'name': name if not name is None else geo_id, '_id': uuid.uuid4().hex[:24], '_index': f_idx}

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

    geojson_list = histomics_to_geojson(json_anns)

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
    geojson_list = aperio_to_geojson(tree.getroot())

    return geojson_list

def aperio_to_geojson(xml_tree) -> list:
    
    structures_in_xml = xml_tree.findall('Annotation')
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
        this_structure = xml_tree.findall(f'Annotation[@Id="{str(ann_idx+1)}"]/Regions/Region')

        for obj_idx,obj in enumerate(this_structure):
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
                    'coordinates': [coords]
                },
                'properties': {
                    'name': f'Layer{ann_idx+1}',
                    '_id': uuid.uuid4().hex[:24],
                    '_index': obj_idx
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

        for g_idx,g in enumerate(groups):

            g_rows = csv_anns[csv_anns[group_by_col].str.match(g)]
            if len(shape_cols)==2:
                x_coords = g_rows[shape_cols[0]].tolist()
                y_coords = g_rows[shape_cols[1]].tolist()

                coord_list = list(zip(x_coords,y_coords))
            elif len(shape_cols)==1:
                # Just make sure that they're x,y format
                coord_list = json.loads(g_rows[shape_cols[0]])

            if len(list(shape_options.keys()))>0:
                if 'radius' in shape_options:
                    # buffering to create circle with set radius:
                    if len(coord_list)>3:
                        pre_poly = Polygon(coord_list)
                    elif len(coord_list)==2:
                        pre_poly = Point(*coord_list)

                    post_poly = pre_poly.buffer(shape_options['radius'])
                    coord_list = [list(i) for i in list(post_poly.exterior.coords)]

            props = {}
            if not property_cols is None:
                for p in property_cols:
                    g_prop = g_rows[p].unique().to_dict()
                    props[p] = g_prop

            geojson_anns['features'].append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon' if len(coord_list)>3 else 'Point',
                    'coordinates': [coord_list]
                },
                'properties': props | {'name': name, '_id': uuid.uuid4().hex[:24], '_index': g_idx}
            })

    else:
        # Each row is one structure
        for g in range(csv_anns.shape[0]):
            
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
                'properties': props | {'name': name, '_id': uuid.uuid4().hex[:24], '_index': g}
            })
            

    return geojson_anns

def load_label_mask(label_mask: np.ndarray, name: str) -> dict:

    full_geo = {
        'type': 'FeatureCollection',
        'features': [],
        'properties': {'name': name,'_id': uuid.uuid4().hex[:24]}
    }

    for geo, val in rasterio.features.shapes(label_mask, mask = label_mask>0):
        feature = {
            'type': 'Feature',
            'geometry': geo,
            'properties': {'name': name, '_id': uuid.uuid4().hex[:24], '_index': int(val)}
        }
        full_geo['features'].append(feature)

    return full_geo

def load_visium(visium_path:str, include_var_names:list = [], include_obs: list = [], mpp:Union[float,None]=None, scale_factor: Union[float,str,None] = None, verbose:bool = True):
    """Loading 10x Visium Spot annotations from an h5ad file or csv file containing spot center coordinates. Adds any of the variables
    listed in var_names and also the barcodes associated with each spot (if the path is an h5ad file).

    :param visium_path: Path to the h5ad (anndata) formatted Visium data or csv file containing "imagerow" and "imagecol" columns
    :type visium_path: str
    :param include_var_names: List of additional variables to add to the generated annotations (barcode is added by default), defaults to []
    :type include_var_names: list, optional
    :param mpp: If the Microns Per Pixel (MPP) is known for this image then pass it here to save time calculating spot diameter., defaults to None
    :type mpp: Union[float,None], optional
    """

    assert os.path.exists(visium_path)

    if type(scale_factor)==str:
        assert os.path.exists(scale_factor)

        with open(scale_factor,'r') as f:
            scale_factor_hires = json.load(f)
            f.close()
        
        scale_factor_hires = scale_factor_hires["tissue_hires_scalef"]
    elif type(scale_factor)==float:
        scale_factor_hires = scale_factor
    else:
        scale_factor_hires = None

    anndata_object = None
    if 'h5ad' in visium_path:
        # This is for AnnData formatted Visium data
        import anndata as ad
        anndata_object = ad.read_h5ad(visium_path)

        if 'spatial' in anndata_object.obsm_keys():

            spot_coords = pd.DataFrame(
                data = anndata_object.obsm['spatial'],
                index = anndata_object.obs_names,
                columns = ['imagecol','imagerow']
            )
        elif all([i in anndata_object.obs_keys() for i in ['imagecol','imagerow']]):
            spot_coords = pd.DataFrame(
                data = {
                    'imagecol': anndata_object.obs['imagecol'],
                    'imagerow': anndata_object.obs['imagerow']
                },
                index = anndata_object.obs_names
            )
    elif 'csv' in visium_path:
        spot_df = pd.read_csv(visium_path)
        if all([i in spot_df for i in ['imagecol','imagerow']]):
            # This is Visium in the 10x V1 structure (from Seurat)
            spot_coords = pd.read_csv(visium_path,index_col=0).loc[:,['imagecol','imagerow']]
        elif all([i in spot_df for i in ['x','y']]):
            # This is Visium in the 10x V2 structure (from Seurat)
            spot_coords = pd.read_csv(visium_path,index_col=0).loc[:,['x','y']]
        elif all([i in spot_df for i in ['pxl_col_in_fullres','pxl_row_in_fullres']]):
            # This is the tissue_positions.csv file that is output by spaceranger
            spot_coords = pd.read_csv(visium_path,index_col=0)
            spot_coords = spot_coords[spot_coords["in_tissue"]==1].loc[:,['pxl_col_in_fullres','pxl_row_in_fullres']]
            spot_df = spot_df[spot_df["in_tissue"]==1]
            spot_df = spot_df.reset_index(drop=True)

        spot_df.index = spot_coords.index
        # Adding other columns in the provided CSV file 
        spot_coords = pd.concat([spot_coords,spot_df.loc[:,[i for i in spot_df if not i in spot_coords.columns.tolist()+['Unnamed: 0']]]],axis=1,ignore_index=True)
        #spot_coords.columns = spot_df.columns.tolist()
        spot_coords.columns = [i for i in spot_df.columns.tolist() if not i == 'Unnamed: 0']

    # Quick way to calculate how large the radius of each spot should be (minimum distance will be 100um between adjacent spot centroids )
    if mpp is None:
        if verbose:
            print(f'Finding MPP scale for {spot_coords.shape[0]} spots')
        spot_centers = spot_coords.values[:,:2].astype(float)
        distance = np.sqrt(
            np.square(
                spot_centers[:,0]-spot_centers[:,0].reshape(-1,1)
            ) + 
            np.square(
                spot_centers[:,1]-spot_centers[:,1].reshape(-1,1)
            )
        )

        min_dist = np.min(distance[distance>0])
        mpp = 1 / (min_dist/100)

        if verbose:
            print(f'MPP Found! {mpp}')

    # For 55um spot radius
    spot_pixel_radius = int((1/mpp)*55*0.5)

    spot_annotations = {
        'type': 'FeatureCollection',
        'features': [],
        'properties': {
            'name': 'Spots',
            '_id': uuid.uuid4().hex[:24]
        }
    }

    if 'h5ad' in visium_path:
        if len(include_var_names)>0:
            include_vars = [i for i in include_var_names if i in anndata_object.var_names]
        else:
            include_vars = []

        if len(include_obs)>0:
            include_obs = [i for i in include_obs if i in anndata_object.obs_keys()]
        else:
            include_obs = []
    else:
        include_obs = [i for i in include_obs if i in spot_coords]
        include_vars = [i for i in include_var_names if i in spot_coords]
    
    barcodes = list(spot_coords.index)
    if not verbose:
        for idx in range(spot_coords.shape[0]):
            spot = Point(*spot_coords.iloc[idx,0:2].tolist()).buffer(spot_pixel_radius)

            additional_props = {}
            for i in include_vars:
                if not anndata_object is None:
                    additional_props[i] = float(anndata_object.X[idx,list(anndata_object.var_names).index(i)])
                else:
                    try:
                        additional_props[i] = float(spot_coords.loc[barcodes[idx],i])
                    except ValueError:
                        if not '{' in spot_coords.loc[barcodes[idx],i]:
                            additional_props[i] = spot_coords.loc[barcodes[idx],i]
                        else:
                            additional_props[i] = json.loads(spot_coords.loc[barcodes[idx],i].replace("'",'"'))
            
            for j in include_obs:
                if not anndata_object is None:
                    add_prop = anndata_object.obs[j].iloc[idx]
                else:
                    add_prop = spot_coords.loc[idx,j].values

                try:
                    additional_props[i] = float(add_prop)
                except ValueError:
                    if not '{' in add_prop:
                        additional_props[i] = add_prop
                    else:
                        additional_props[i] = json.loads(add_prop.replace("'",'"'))
        
            spot_feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [list(spot.exterior.coords)]
                },
                'properties': {
                    'name': 'Spots',
                    '_id': uuid.uuid4().hex[:24],
                    '_index': idx,
                    'barcode': barcodes[idx]
                } | additional_props
            }

            spot_annotations['features'].append(spot_feature)
    else:
        with tqdm(range(spot_coords.shape[0])) as pbar:
            for idx in range(spot_coords.shape[0]):
                pbar.set_description(f'Working on Spot: {idx+1}/{spot_coords.shape[0]}')

                spot = Point(*spot_coords.iloc[idx,0:2].tolist()).buffer(spot_pixel_radius)

                additional_props = {}
                for i in include_vars:
                    if not anndata_object is None:
                        additional_props[i] = float(anndata_object.X[idx,list(anndata_object.var_names).index(i)])
                    else:
                        try:
                            additional_props[i] = float(spot_coords.loc[barcodes[idx],i])
                        except ValueError:
                            if not '{' in spot_coords.loc[barcodes[idx],i]:
                                additional_props[i] = spot_coords.loc[barcodes[idx],i]
                            else:
                                additional_props[i] = json.loads(spot_coords.loc[barcodes[idx],i].replace("'",'"'))
                
                for j in include_obs:
                    if not anndata_object is None:
                        add_prop = anndata_object.obs[j].iloc[idx]
                    else:
                        add_prop = spot_coords.loc[idx,j].values

                    try:
                        additional_props[i] = float(add_prop)
                    except ValueError:
                        if not '{' in add_prop:
                            additional_props[i] = add_prop
                        else:
                            additional_props[i] = json.loads(add_prop.replace("'",'"'))

                spot_feature = {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [list(spot.exterior.coords)]
                    },
                    'properties': {
                        'name': 'Spots',
                        '_id': uuid.uuid4().hex[:24],
                        '_index': idx,
                        'barcode': barcodes[idx]
                    } | additional_props
                }

                spot_annotations['features'].append(spot_feature)

                pbar.update(1)


    if not scale_factor_hires is None:
        spot_properties = spot_annotations['properties']
        spot_annotations = geojson.utils.map_geometries(lambda g: geojson.utils.map_tuples(lambda c: (c[0]*scale_factor_hires,c[1]*scale_factor_hires),g),spot_annotations)
        spot_annotations['properties'] = spot_properties

    return spot_annotations

def load_visiumhd(visiumhd_path:str, resolution_level:int,include_analysis_path:Union[str,list,None]=None, include_analysis_name:Union[str,list,None]=None, verbose:bool = True):
    """Generating annotations for a VisiumHD dataset

    :param visiumhd_path: Path to "binned_outputs"
    :type visiumhd_path: str
    :param resolution_level: Number representing the length of one side of the square
    :type resolution_level: int
    :param include_analysis_path: Path to various analyses performed on these ROIs, can either be output of spaceranger or any csv file with "barcode" column to be used for alignment., defaults to None
    :type include_analysis_path: Union[str,list,None], optional
    :param include_analysis_name: Name to use for each included analysis, if none are provided, name is inferred from {path}.split(os.sep)[-2]., defaults to None
    :type include_analysis_name: Union[str,list,None], optional
    """

    # Creating the path for one resolution level
    visiumhd_path = os.path.join(visiumhd_path,f'square_{"".join(["0"]*(3-len(str(resolution_level)))+[i for i in str(resolution_level)])}')

    # Loading analyses
    if not include_analysis_path is None:
        if type(include_analysis_path)==str:
            include_analysis_path = [include_analysis_path]
        
        if include_analysis_name is None:
            include_analysis_name = [j.split(os.sep)[-2] for j in include_analysis_path]
        elif type(include_analysis_name)==str:
            include_analysis_name = [include_analysis_name]
        elif type(include_analysis_name)==list:
            if not len(include_analysis_name)==len(include_analysis_path):
                raise ValueError('Number of analysis names is not equal to the number of analyses provided')

        analysis_list = []
        for u,n in zip(include_analysis_path,include_analysis_name):
            analysis_data = pd.read_csv(u)
            analysis_list.append({
                'name': n,
                'data': analysis_data
            })

    tissue_positions_path = os.path.join(visiumhd_path,'spatial','tissue_positions.parquet')
    scale_factors_path = os.path.join(visiumhd_path,'spatial','scalefactors_json.json')

    with open(scale_factors_path,'r') as f:
        scale_factors = json.load(f)
        f.close()

    tissue_positions = pd.read_parquet(tissue_positions_path)

    for an in analysis_list:
        an_data = an['data']
        an_data.columns = ['barcode',an['name']]
        tissue_positions = pd.merge(tissue_positions,an_data)

    square_um_area = resolution_level**2
    square_pixel_area = square_um_area * (1/(scale_factors['microns_per_pixel']**2))
    square_radius = floor((square_pixel_area/pi)**0.5)

    if verbose:
        visiumhd_geos = {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [
                            list(Point(f['pxl_col_in_fullres'],f['pxl_row_in_fullres']).buffer(square_radius,cap_style=3).simplify(0.5).exterior.coords)
                        ]
                    },
                    'properties': {
                        'name': resolution_level,
                        '_id': uuid.uuid4().hex[:24],
                        '_index': f_idx
                    } | {k['name']: f.get(k['name']) for k in analysis_list}
                }
                for f_idx,f in tqdm(tissue_positions.iterrows(),total = tissue_positions.shape[0])
            ],
            'properties':{
                'name': resolution_level,
                '_id': uuid.uuid4().hex[:24]
            }
        }
    else:
        visiumhd_geos = {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [
                            list(Point(f['pxl_col_in_fullres'],f['pxl_row_in_fullres']).buffer(square_radius,cap_style=3).simplify(0.5).exterior.coords)
                        ]
                    },
                    'properties': {
                        'name': resolution_level,
                        '_id': uuid.uuid4().hex[:24],
                        '_index': f_idx
                    } | {k['name']: f.get(k['name']) for k in analysis_list}
                }
                for f_idx,f in tissue_positions.iterrows()
            ],
            'properties':{
                'name': resolution_level,
                '_id': uuid.uuid4().hex[:24]
            }
        }


    return visiumhd_geos

def detect_histomics(query_annotations:Union[list,dict]):
    """Check whether a list/dict of annotations are in histomics format

    :param query_annotations: Input query annotation
    :type query_annotations: Union[list,dict]
    """

    if type(query_annotations)==dict:
        query_annotations = [query_annotations]
    
    result = False
    for q in query_annotations:
        if type(q)==dict:
            if 'annotation' in q:
                result = True
    
    return result

def detect_geojson(query_annotations:Union[list,dict]):
    """Check whether a list/dict of annotations are in GeoJSON format

    :param query_annotations: Input query annotation
    :type query_annotations: Union[list,dict]
    """
    if type(query_annotations)==dict:
        query_annotations = [query_annotations]
    
    result = False
    for q in query_annotations:
        if type(q)==dict:
            if 'type' in q:
                if q['type']=='FeatureCollection':
                    result = True
    
    return result

def detect_image_overlay(query_annotations:Union[list,dict]):
    """Checking whether a list/dict of annotations contain an image overlay"""
    if type(query_annotations)==dict:
        query_annotations=[query_annotations]
    
    result = False

    for q in query_annotations:
        if type(q)==dict:
            if 'image_bounds' in q:
                result = True

    return result

def histomics_to_geojson(json_anns: Union[list,dict]):
    
    if type(json_anns)==dict:
        json_anns = [json_anns]

    geojson_list = []
    for ann in json_anns:
        ann_id = uuid.uuid4().hex[:24]
        if '_id' in ann:
            ann_id = ann['_id']
        elif '_id' in ann['annotation']:
            ann_id = ann['annotation']['_id']

        geojson_anns = {
            'type': 'FeatureCollection',
            'properties': {
                'name': ann['annotation']['name'],
                '_id': ann_id
            },
            'features': []
        }

        for el_idx, el in enumerate(ann['annotation']['elements']):
            if el['type']=='polyline':
                coords = [el['points']]
            elif el['type']=='rectangle':
                coords = [[
                    [
                        el['center'][0] - el['width'], el['center'][1] - el['height']
                    ],
                    [
                        el['center'][0] + el['width'], el['center'][1] - el['height']
                    ],
                    [
                        el['center'][0] + el['width'], el['center'][1] + el['height']
                    ],
                    [
                        el['center'][0] - el['width'], el['center'][1] + el['height']
                    ],
                    [
                        el['center'][0] - el['width'], el['center'][1] + el['height']
                    ]
                ]]
            else:
                continue
                
            props_dict = {
                'name': ann['annotation']['name'],
                '_id': uuid.uuid4().hex[:24],
                '_index': el_idx
            }

            if 'user' in el:
                props_dict = el['user'] | props_dict

            geojson_anns['features'].append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': coords
                },
                'properties': props_dict
            })

        geojson_list.append(geojson_anns)

    return geojson_list

def geojson_to_histomics(geojson_anns: Union[list,dict]):

    if type(geojson_anns)==dict:
        geojson_anns = [geojson_anns]
    
    histomics_anns = []
    for g in geojson_anns:
        if 'properties' in g:
            g_name = g['properties']['name']
        else:
            g_name = ''

        histomics_ann = {
            'annotation': {
                'name': g_name,
                'elements': [
                    {
                        'type': 'polyline',
                        'user': f['properties'],
                        'closed': True,
                        'points': [list(i)+[0] if type(i)==tuple else i+[0] for i in f['geometry']['coordinates'][0]]
                    }
                    if all([len(i)==2 for i in f['geometry']['coordinates'][0]])
                    else
                    {
                        'type': 'polyline',
                        'user': f['properties'],
                        'closed': True,
                        'points': [list(i) if type(i)==tuple else i for i in f['geometry']['coordinates'][0]]
                    }
                    for f in g['features']
                ]
            }
        }
        histomics_anns.append(histomics_ann)
    
    return histomics_anns

def align_object_props(
        geo_ann: dict, 
        prop_df: Union[pd.DataFrame, list],
        prop_cols: Union[list,str],
        alignment_type: str,
        prop_key: Union[None,str]=None) -> dict:
    """Aligning GeoJSON formatted annotations with an external file containing properties for each feature

    :param geo_ann: GeoJSON formatted annotations to align with external file
    :type geo_ann: dict
    :param prop_df: Property DataFrame or list containing DataFrames to align with GeoJSON
    :type prop_df: Union[pd.DataFrame,list]
    :param prop_cols: Column(s) containing property information in each DataFrame
    :type prop_cols: Union[list,str]
    :param alignment_type: Process to use for aligning rows of property DataFrame to GeoJSON
    :type alignment_type: str
    :param prop_key: Name of property to assign to the new aligned property (only one)
    :param prop_key: Union[None,str], optional
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
            if prop_key is None:
                for r in prop_cols:
                    if r in p:
                        prop_list = p[r].tolist()
                        for i in range(len(geo_ann['features'])):
                            geo_ann['features'][i]['properties'] = geo_ann['features'][i]['properties'] | {r: prop_list[i]}
            else:
                for i in range(len(geo_ann['features'])):
                    prop_dict = {
                        k:v
                        for k,v in p.iloc[i,:].to_dict().items()
                        if k in prop_cols
                    }
                    geo_ann['features'][i]['properties'] = geo_ann['features'][i]['properties'] | {prop_key: prop_dict}

        elif alignment_type in p:
            # Lining up by column/property name
            align_vals = p[alignment_type].tolist()
            align_geo = [i['properties'][alignment_type] for i in geo_ann['features']]

            for a_idx,a in enumerate(align_vals):
                if a in align_geo:
                    add_props = {
                        k:v
                        for k,v in p.iloc[a_idx,:].to_dict().items()
                        if k in prop_cols
                    }
                    if prop_key is None:
                        geo_ann['features'][align_geo.index(a)]['properties'] = geo_ann['features'][align_geo.index(a)]['properties'] | add_props
                    else:
                        geo_ann['features'][align_geo.index(a)]['properties'] = geo_ann['features'][align_geo.index(a)]['properties'] | {prop_key: add_props}

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
                            'closed': True,
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

def find_intersecting(geo_source:Union[dict,str], geo_query:Polygon, return_props:bool = True, return_shapes:bool = True):
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

    if type(geo_source)==str:
        geo_source = json.loads(geo_source)[0]

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

def spatially_aggregate(child_geo:dict, parent_geos: list, separate: bool = True, summarize: bool = True, ignore_list: list = ["_id","_index"]):
    """Aggregate intersecting feature properties to a provided GeoJSON 

    :param child_geo: GeoJSON object that is receiving aggregated properties
    :type child_geo: dict
    :param parent_geos: List of GeoJSON objects which are intersecting with child_geo
    :type parent_geos: list
    :return: Updated child_geo object with new properties from intersecting parent_geos
    :rtype: dict
    """

    start = time.time()
    agg_geo = deepcopy(child_geo)
    base_gdf = [gpd.GeoDataFrame.from_features(i['features']) for i in parent_geos]
    base_names = [i['properties']['name'] for i in parent_geos]
    for a in agg_geo['features']:
        a_shape = shape(a['geometry'])
        agg_props = {}
        for b_idx,b in enumerate(base_gdf):
            b_intersect = b.sindex.query(a_shape,predicate='intersects')
            if len(b_intersect)>0:
                agg_props[base_names[b_idx]] = []
                for c in b_intersect:
                    c_dict = b.iloc[c,:].to_dict()
                    c_dict = {
                        i:j
                        for i,j in c_dict.items()
                        if not i in ['geometry']+ignore_list
                    }
                    proc_c = {}
                    for key,val in c_dict.items():
                        if type(val)==dict:
                            nested_levels = find_nested_levels({key: val})
                            nested_props = extract_nested_prop(main_prop_dict = {key: val}, depth=nested_levels, path=(), values_list = [])
                            for n in nested_props:
                                proc_c = proc_c | n
                        elif type(val) in [int,float,str]:
                            proc_c = proc_c | {key:val}
                    
                    agg_props[base_names[b_idx]].append(proc_c)

        if all([len(agg_props[i])==0 for i in agg_props]):
            # This structure doesn't intersect with anything so skip it
            continue

        if separate:
            for name in list(agg_props.keys()):
                a['properties'][name] = {}
                name_df = pd.DataFrame.from_records(agg_props[name])
                numeric_df = name_df.select_dtypes(exclude='object')
                if summarize:
                    mean_props = numeric_df.mean(axis=0).to_dict()
                    median_props = numeric_df.median(axis=0).to_dict()
                    max_props = numeric_df.max(axis=0).to_dict()
                    min_props = numeric_df.min(axis=0).to_dict()
                    sum_props = numeric_df.sum(axis=0).to_dict()

                    props = numeric_df.columns.tolist()
                    for p in props:
                        nested_mean = mean_props[p]
                        nested_median = median_props[p]
                        nested_max = max_props[p]
                        nested_min = min_props[p]
                        nested_sum = sum_props[p]
                        
                        nested_dict = {
                            'Mean': nested_mean,
                            'Median': nested_median,
                            'Max': nested_max,
                            'Min': nested_min,
                            'Sum': nested_sum
                        }

                        #TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                        sub_keys = reversed(p.split(' --> '))
                        for p_idx,part in enumerate(sub_keys):
                            nested_dict = {part: nested_dict}

                        a['properties'][name] = merge_dict(a['properties'][name], nested_dict)

                else:
                    mean_props = numeric_df.mean(axis=0).to_dict()
                    props = numeric_df.columns.tolist()
                    for p in props:
                        mean_dict = mean_props[p]
                        #TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                        for part in reversed(p.split(' --> ')):
                            mean_dict = {part: mean_dict}

                        a['properties'][name] = merge_dict(a['properties'][name],mean_dict)

                # Adding the non-numeric properties
                non_numeric_df = name_df.select_dtypes(include='object')
                for non in non_numeric_df:
                    counts_dict = non_numeric_df[non].value_counts().to_dict()
                    a['properties'][name] = merge_dict(a['properties'][name], {non:{'Count': counts_dict}})

        else:
            merged_df = pd.concat([pd.DataFrame.from_records(agg_props[i]) for i in agg_props],axis=0,ignore_index=True)
            numeric_df = merged_df.select_dtypes(exclude='object')

            if summarize:
                mean_props = numeric_df.mean(axis=0).to_dict()
                median_props = numeric_df.median(axis=0).to_dict()
                max_props = numeric_df.max(axis=0).to_dict()
                min_props = numeric_df.min(axis=0).to_dict()
                sum_props = numeric_df.sum(axis=0).to_dict()

                props = numeric_df.columns.tolist()
                for p in props:
                    nested_mean = mean_props[p]
                    nested_median = median_props[p]
                    nested_max = max_props[p]
                    nested_min = min_props[p]
                    nested_sum = sum_props[p]

                    nested_dict = {
                        'Mean': nested_mean,
                        'Median': nested_median,
                        'Max': nested_max,
                        'Min': nested_min,
                        'Sum': nested_sum
                    }

                    #TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                    sub_keys = reversed(p.split(' --> '))
                    for part in sub_keys:
                        nested_dict = {part: nested_dict}
                    
                    a['properties'] = merge_dict(a['properties'],nested_dict)

            else:
                mean_props = numeric_df.mean(axis=0).to_dict()
                props = numeric_df.columns.tolist()
                for p in props:
                    mean_dict = mean_props[p]
                    #TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                    for part in reversed(p.split(' --> ')):
                        mean_dict = {part: mean_dict}

                    a['properties'] = merge_dict(a['properties'],mean_dict)

            # Adding the non-numeric properties
            non_numeric_df = merged_df.select_dtypes(include='object')
            for non in non_numeric_df:
                counts_dict = non_numeric_df[non].value_counts().to_dict()
                
                # This one has to change the name because string properties in base can't be merged as dicts
                a['properties'] = merge_dict(a['properties'],{f'{non}_Aggregated':{'Count': counts_dict}})

    end = time.time()
    #print(f'Time for spatial aggregation: {end-start}')

    return agg_geo

def find_nested_levels(nested_dict)->int:
    """Find number of levels for nested dictionary

    :param nested_dict: dictionary containing nested values
    :type nested_dict: dict
    :return: number of levels for nested dictionary
    :rtype: int
    """
    if not isinstance(nested_dict, dict) or not nested_dict:
        return 0
    
    max_depth = 0
    
    stack = [(nested_dict, 1)]
    
    while stack:
        current_dict, depth = stack.pop()
        max_depth = max(max_depth, depth)
        
        for val in current_dict.values():
            if isinstance(val,dict):
                stack.append((val, depth+1))
    
    return max_depth

def extract_nested_prop(main_prop_dict: dict, depth: int, path: tuple = (), values_list: list = None, _seen:set = None):
    """Extracted nested properties up to depth level.

    :param main_prop_dict: Main dictionary containing nested properties. ex: {'main_prop': {'sub_prop1': value1, 'sub_prop2': value2}}
    :type main_prop_dict: dict
    :param depth: Number of levels to extend into nested dictionary
    :type depth: int
    """
    if values_list is None:
        values_list = []
    
    if _seen is None:
        _seen = set()
    
    if not main_prop_dict or depth<=0:
        return values_list

    stack = [(main_prop_dict, depth, path)]
    
    #Doing a DFS based traversal. 
    while stack:
        cur_dict, cur_depth, cur_path = stack.pop()
        
        for key, val in cur_dict.items():
            new_path = cur_path + (key, )
            
            #You're at the leaf node or the final non-nested dict
            if cur_depth == 1:
                if isinstance(val, (int,float, str)):
                    joined = " --> ".join(new_path)
                    #Check if you already saw this value
                    if joined not in _seen:
                        _seen.add(joined)
                        values_list.append({joined: val})
                
                elif isinstance(val, list):
                    extract_listed_prop(val,new_path, values_list, _seen)

            else:
                if isinstance(val, dict):
                    stack.append((val,cur_depth-1, new_path))
                elif isinstance(val, list):
                    extract_listed_prop(val,new_path,values_list, _seen)
                elif isinstance(val, (int,float,str)):
                    joined = " --> ".join(new_path)
                    if joined not in _seen:
                        _seen.add(joined)
                        values_list.append({joined:val})
    

    return values_list


def extract_listed_prop(main_list: list, path: tuple = (), values_list: list = None,_seen:set = None):

    if values_list is None:
        values_list = []
    
    if _seen is None:
        _seen = set()
    
    for idx, item in enumerate(main_list):
        item_key = f"Value {idx}"
        new_path = path + (item_key, )
        
        if isinstance(item, (int, float, str)):
            joined = " --+ ".join(new_path)
            if joined not in _seen:
                _seen.add(joined)
                values_list.append({joined: item})
                
        elif isinstance(item, dict):
            nested_depth = find_nested_levels({item_key: item})
            extract_nested_prop({item_key: item}, nested_depth, new_path, values_list, _seen)
        
        elif isinstance(item, list):
            extract_listed_prop(item,new_path, values_list, _seen)

    return values_list

def merge_dict(a:dict, b:dict, path = []):

    # https://stackoverflow.com/questions/7204805/deep-merge-dictionaries-of-dictionaries-in-python
    for key in b:
        if key in a:
            if isinstance(a[key],dict) and isinstance(b[key],dict):
                merge_dict(a[key],b[key],path+[str(key)])
            elif a[key] != b[key]:
                #raise Exception(f'Conflict at {".".join(path+[str(key)])}')
                continue
        else:
            a[key] = b[key]
    return a

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

    if type(geo_list)==dict:
        geo_list = [geo_list]
    elif type(geo_list)==list:
        if not all([type(i)==dict for i in geo_list]):
            fixed_list = []
            for a in geo_list:
                if type(a)==dict:
                    fixed_list.append(a)
                elif type(a)==list:
                    fixed_list.extend(a)
            geo_list = fixed_list
            
    start = time.time()
    geojson_properties = []
    feature_names = []
    property_info = {}
    for ann in geo_list:
        if ann is None:
            continue
        if not 'properties' in ann:
            continue
        if len(list(ann['properties'].keys()))==0:
            continue
        feature_names.append(ann['properties']['name'])
        for f in ann['features']:
            f_props = [i for i in list(f['properties'].keys()) if not i in ignore_list]
            for p in f_props:
                # Checking for sub-properties
                sub_props = []
                if type(f['properties'][p]) in [dict,list]:
                    # Pulling out nested properties (either dictionaries or lists or lists of dictionaries or dictionaries of lists, etc.)
                    if type(f['properties'][p]) ==dict:
                        nested_value = extract_nested_prop({p: f['properties'][p]}, nested_depth, (), [])
                    elif type(f['properties'][p])==list:
                        nested_value = extract_listed_prop(f['properties'][p],(p,),[])

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

                elif type(f['properties'][p]) in [int,float,str]:
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
    end = time.time()

    #print(f'Time for extracting GeoJSON properties: {end-start}')

    return geojson_properties, feature_names, property_info

def structures_within_poly(original:dict, query:Polygon):

    og_geo = gpd.GeoDataFrame.from_features(original['features'])
    result_geo = json.loads(og_geo[og_geo.intersects(query)].to_json())

    return result_geo

def process_filters_queries(filter_list:list, spatial_list:list, structures:list, all_geo_list:list):
    """Filter GeoJSON list based on lists of both spatial and property filters.

    :param filter_list: List of property filters (keys = name: "name of property", range: "either a list of categorical values or min-max for quantitative")
    :type filter_list: list
    :param spatial_list: List of spatial filters (keys= type: "predicate", structure: "name of structure that is basis of predicate")
    :type spatial_list: list
    :param structures: List of included structures in final GeoJSON
    :type structures: list
    :param all_geo_list: List of GeoJSON objects to search
    :type all_geo_list: list
    :return: Filtered GeoJSON where all included structures are included as one FeatureCollection and a reference list containing original structure name and index
    :rtype: tuple
    """
    # First getting the listed structures:
    
    start = time.time()
    if not structures == ['all']:
        structure_filtered = [gpd.GeoDataFrame.from_features(i['features']) for i in all_geo_list if i['properties']['name'] in structures]
        name_order = [i['properties']['name'] for i in all_geo_list if i['properties']['name'] in structures]
    else:
        structure_filtered = [gpd.GeoDataFrame.from_features(i['features']) for i in all_geo_list]
        name_order = [i['properties']['name'] for i in all_geo_list]

    end = time.time()
    #print(f'Time for creating GeoDataFrames from selected names: {end-start}')

    # Now going through spatial queries
    start = time.time()
    filter_reference_list = {
        n: {}
        for n in name_order
    }
    if len(spatial_list)>0:
        remainder_structures = []

        for s,name in zip(structure_filtered,name_order):
            intermediate_gdf = s.copy()

            # only used for OR mods
            include_list = [(False,)]*intermediate_gdf.shape[0]
            for s_q in spatial_list:
                sq_geo = [i for i in all_geo_list if i['properties']['name']==s_q['structure']][0]
                sq_structure = gpd.GeoDataFrame.from_features(sq_geo['features'])

                if not s_q['type'] == 'nearest':
                    if 'mod' in s_q:
                        if s_q['mod']=='not':
                            intermediate_gdf = gpd.sjoin(
                                left_df = intermediate_gdf, 
                                right_df = sq_structure, 
                                how = 'left', 
                                predicate = s_q['type']
                            ).drop_duplicates(subset = '_id_left')

                            # Updating include_list (removing items)
                            include_list = [i for d,i in zip(intermediate_gdf['_id_right'].isna().tolist(),include_list) if not d]
                            include_list = [i+(True,) for i in include_list]


                            intermediate_gdf = intermediate_gdf.loc[intermediate_gdf['_id_right'].isna()]
                            
                        elif s_q['mod']=='and':
                            intermediate_gdf = gpd.sjoin(
                                left_df = intermediate_gdf,
                                right_df = sq_structure,
                                how = 'left',
                                predicate = s_q['type']
                            ).drop_duplicates(subset = '_id_left')

                            # Updating include_list (removing items)
                            include_list = [i for d,i in zip(intermediate_gdf['_id_right'].notna().tolist(),include_list) if d]
                            include_list = [i+(True,) for i in include_list]
                            
                            intermediate_gdf = intermediate_gdf.loc[intermediate_gdf['_id_right'].notna()]


                        elif s_q['mod']=='or':
                            or_gdf = gpd.sjoin(
                                left_df = intermediate_gdf,
                                right_df = sq_structure,
                                how = 'left',
                                predicate = s_q['type']
                            ).drop_duplicates(subset = '_id_left')
                            current_remove = or_gdf['_id_right'].isna().tolist()
                            include_list = [i+(not j,) for i,j in list(zip(include_list,current_remove))]
                            
                    else:
                        intermediate_gdf = gpd.sjoin(
                            left_df = intermediate_gdf,
                            right_df = sq_structure,
                            how = 'left',
                            predicate = s_q['type']
                        ).drop_duplicates(subset = '_id_left')

                        # Updating include_list (removing items)
                        include_list = [i for d,i in zip(intermediate_gdf['_id_right'].isna().tolist(),include_list) if not d]
                        include_list = [i+(True,) for i in include_list]

                        intermediate_gdf = intermediate_gdf.loc[intermediate_gdf['_id_right'].notna()]

                else:
                    if 'mod' in s_q:
                        if s_q['mod']=='not':
                            intermediate_gdf = gpd.sjoin_nearest(
                                left_df = intermediate_gdf, 
                                right_df = sq_structure,
                                how = 'left',
                                max_distance = s_q['distance']
                            ).drop_duplicates(subset='_id_left')

                            # Updating include_list (removing items)
                            include_list = [i for d,i in zip(intermediate_gdf['_id_right'].isna().tolist(),include_list) if not d]
                            include_list = [i+(True,) for i in include_list]


                            intermediate_gdf = intermediate_gdf.loc[intermediate_gdf['_id_right'].isna()]

                        elif s_q['mod']=='and':
                            intermediate_gdf = gpd.sjoin_nearest(
                                left_df = intermediate_gdf, 
                                right_df = sq_structure,
                                how = 'left',
                                max_distance = s_q['distance']
                            ).drop_duplicates(subset='_id_left')

                            # Updating include_list (removing items)
                            include_list = [i for d,i in zip(intermediate_gdf['_id_right'].isna().tolist(),include_list) if not d]
                            include_list = [i+(True,) for i in include_list]

                            intermediate_gdf = intermediate_gdf.loc[intermediate_gdf['_id_right'].notna()]
                        
                        elif s_q['mod']=='or':
                            or_gdf = gpd.sjoin_nearest(
                                left_df = intermediate_gdf, 
                                right_df = sq_structure,
                                how = 'left',
                                max_distance = s_q['distance']
                            ).drop_duplicates(subset='_id_left')

                            current_remove = or_gdf['_id_right'].isna().tolist()
                            include_list = [i+(not j,) for i,j in list(zip(include_list,current_remove))]
                            
                    else:

                        intermediate_gdf = gpd.sjoin_nearest(
                            left_df = intermediate_gdf, 
                            right_df = sq_structure,
                            how = 'left',
                            max_distance = s_q['distance']
                        ).drop_duplicates(subset='_id_left')

                        # Updating include_list (removing items)
                        include_list = [i for d,i in zip(intermediate_gdf['_id_right'].isna().tolist(),include_list) if not d]
                        include_list = [i+(True,) for i in include_list]

                        intermediate_gdf = intermediate_gdf.loc[intermediate_gdf['_id_right'].notna()]
                    

                intermediate_gdf = intermediate_gdf.drop([i for i in ['index_left','index_right'] if i in intermediate_gdf], axis = 1)
                intermediate_gdf = intermediate_gdf.drop([i for i in intermediate_gdf if '_right' in i],axis=1)
                intermediate_gdf.columns = [i.replace('_left','') if '_left' in i else i for i in intermediate_gdf]

            # Applying the OR mods
            intermediate_gdf = intermediate_gdf.loc[[any(i) for i in include_list]]
            remainder_structures.append(intermediate_gdf)
    else:
        remainder_structures = structure_filtered

    end = time.time()
    #print(f'Time for spatial queries: {end-start}')

    # Combining into one GeoJSON
    start = time.time()
    combined_geojson = {
        'type': 'FeatureCollection',
        'features': []
    }
    for g,name in zip(remainder_structures,name_order):
        g_json = g.to_geo_dict(show_bbox=True)
        filter_reference_list[name] = {
            i+len(combined_geojson['features']):j['properties']['_index']
            for i,j in enumerate(g_json['features'])
        }
        combined_geojson['features'].extend(g_json['features'])

    end = time.time()
    #print(f'Time for generating combined geojson: {end-start}')

    # Going through property filters:
    start = time.time()
    if len(filter_list)>0:
        filtered_geojson = {
            'type': 'FeatureCollection',
            'features': []
        }

        mod_list = []
        for m in filter_list:
            if 'mod' in m:
                mod_list.append(m['mod'])
            else:
                mod_list.append('and')

        for feat_idx, feat in enumerate(combined_geojson['features']):
            include_list = []

            for f,m in zip(filter_list,mod_list):
                #TODO: Update this for different types of nested props (--+ = list, --# = external reference object)
                filter_name_parts = f['name'].split(' --> ')

                feat_props = feat['properties'].copy()
                feat_props = {i.replace('_left',''):j for i,j in feat_props.items()}

                for filt in filter_name_parts:
                    if feat_props:
                        if filt in feat_props:
                            feat_props = feat_props[filt]
                        else:
                            feat_props = False
                
                if feat_props:
                    if all([type(i) in [int,float] for i in f['range']]):
                        if f['range'][0]<=feat_props and feat_props<=f['range'][1]:
                            include_list.append(True)
                        else:
                            include_list.append(False)
                    
                    elif all([type(i)==str for i in f['range']]):
                        if feat_props in f['range']:
                            include_list.append(True)
                        else:
                            include_list.append(False)
                
                else:
                    include_list.append(False)
                                
            
            include = None
            for m,i in zip(mod_list,include_list):
                if not include is None:
                    if m == 'and':
                        include = include & i
                    elif m == 'or': 
                        include = include | i
                    elif m == 'not':
                        include = include & (not i)
                else:
                    if not m == 'not':
                        include = i
                    else:
                        include = not i

            if include:
                filtered_geojson['features'].append(feat)
            else:
                for name in filter_reference_list:
                    if feat_idx in filter_reference_list[name].values():
                        del filter_reference_list[name][list(filter_reference_list[name].keys())[list(filter_reference_list[name].values()).index(feat_idx)]]

    else:
        filtered_geojson = combined_geojson
    
    end = time.time()
    #print(f'Time for property filters: {end-start}')

    final_filter_reference_list = []
    for n in filter_reference_list:
        for combined_idx in filter_reference_list[n]:
            final_filter_reference_list.append(
                {'name': n, 'feature_index': filter_reference_list[n][combined_idx]}
            )

    return filtered_geojson, final_filter_reference_list

# Taken from plotly image annotation tutorial: https://dash.plotly.com/annotations#changing-the-style-of-annotations
def path_to_indices(path):
    """
    From SVG path to numpy array of coordinates, each row being a (row, col) point
    """
    indices_str = [
        el.replace("M", "").replace("Z", "").split(",") for el in path.split("L")
    ]
    return np.rint(np.array(indices_str, dtype=float)).astype(int)

def indices_to_path(indices):
    """
    From numpy array of coordinates to path string for adding to plotly figure layout
    """    
    path_str = d = ''.join(['%s%d,%d' % (['M', 'L'][idx>0], i[0], i[1]) for idx, i in enumerate(indices)]) + f'L{indices[0][0]},{indices[0][1]}Z'

    return path_str

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




