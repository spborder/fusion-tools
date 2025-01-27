"""

Making some utility functions for handling --omics data

"""

import os
import sys

import numpy as np
import pandas as pd

from copy import deepcopy
import requests
from typing_extensions import Union

from fusion_tools.utils.shapes import spatially_aggregate

INFO_URL = 'https://mygene.info/v3/'
HRA_URL = 'https://grlc.io/api-git/hubmapconsortium/ccf-grlc/subdir/fusion//?endpoint=https://lod.humanatlas.io/sparql'

def get_gene_info(id:Union[str,list],species: str = 'human', fields:list = ['HGNC','alias','summary'],size:int=5):
    """
    Get information about a given gene id or list of ids.
    By default returns HGNC, alias, and summary
    Can be expanded to include go, pubmed articles, etc.
    """
    acceptable_species = ['human','mouse','rat','fruitfly','nematode','zebrafish','thale-cress','frog','pig']
    assert species in acceptable_species

    # There are actually too many possible fields to mention here
    #acceptable_fields = ['HGNC','alias','summary','go','pubmed']
    #assert all([i in acceptable_fields for i in fields])
    if isinstance(id,str):
        id = id.split('.')[0]
        request_response = requests.get(f'{INFO_URL}gene/{id}?fields={",".join(fields)}&species={species}&dotfield=false&size={size}')
        if request_response.ok:
            return request_response.json()
        else:
            return None
        
    elif isinstance(id,list):
        return_list = []
        for i in id:
            request_response = requests.get(f'{INFO_URL}gene/{i.split(".")[0]}?fields={",".join(fields)}&species={species}&dotfield=false&size={size}')
            if request_response.ok:
                return_list.append(request_response.json())
        
        return return_list

def get_asct(id:Union[str,int]):
    """
    Get Anatomical Structure & Cell Type associated with a given HGNC Id.
    """
    # Have to add on the whole iri here:
    # HGNC id is a number but should be interpreted as a string
    id = f'http://identifiers.org/hgnc/{id}'
    request_response = requests.get(
        f'{HRA_URL.replace("fusion//","fusion//asct_by_biomarker")}&biomarker={id}',
        headers={'Accept':'application/json','Content-Type':'application/json'}
    )
    if request_response.ok:
        return pd.json_normalize(request_response.json()['results']['bindings'],max_level=1)
    else:
        print(f'{HRA_URL.replace("fusion//","fusion//asct_by_biomarker")}&biomarker={id}')
        print('Request not ok!')
        return None
    
def get_cell(id:str):
    """
    Get all the cell types available within a given anatomical structure
    Input has to be an UBERON id "UBERON_######..."
    """

    # Modifiying input id
    id = f'http://purl.odolibrary.org/obo/{id}'
    request_response = requests.get(
        f'{HRA_URL.replace("fusion//","fusion//cell_by_location")}&location={id}',
        headers={'Accept':'application/json','Content-type':'application/json'}
    )

    if request_response.ok:
        return pd.DataFrame(request_response.content)
    else:
        return None

def selective_aggregation(child_geo:dict, parent_geo:dict, include_keys: dict = {}, aggregate_dropped: bool = True, dropped_name: str = 'undefined', re_normalize: bool = True):
    """Selectively aggregate different fields for each intersecting structure. Useful for only aggregating cell types which should be found within a specific structure

    :param child_geo: Child structure to be receiving aggregated properties
    :type child_geo: dict
    :param parent_geo: Parent structure that contains properties that are going to be aggregated within the child geos.
    :type parent_geo: dict
    :param include_keys: Dictionary containing keys for each property that is modified and a list of values which should be included for that key., defaults to {}
    :type include_keys: dict, optional
    :param aggregate_dropped: Whether or not to include dropped values in the final aggregation, defaults to True
    :type aggregate_dropped: bool, optional
    :param dropped_name: Name to use for dropped names that are aggregated. Ignored if aggregate_dropped=False, defaults to 'undefined'
    :type dropped_name: str, optional
    :param re_normalize: Whether or not to re-normalize values after dropping keys., defaults to True
    :type re_normalize: bool, optional
    :return: Child structure with selectively aggregated properties from the parent structure.
    :rtype: dict
    """

    mod_parent = deepcopy(parent_geo)
    for f_idx,f in enumerate(parent_geo['features']):
        for k,v in include_keys.items():
            if k in f['properties']:
                sum_f_k = sum(list(f['properties'][k].values()))

                mod_parent['features'][f_idx]['properties'][k] = {
                    i: f['properties'][i]
                    for i in v
                }
                if aggregate_dropped:
                    mod_parent['features'][f_idx]['properties'][k][dropped_name] = sum_f_k - sum(list(mod_parent['features'][f_idx]['properties'][k].values()))
                if re_normalize:
                    k_sum = sum(list(mod_parent['features'][f_idx]['properties'][k].values()))
                    if k_sum>0:
                        mod_parent['features'][f_idx]['properties'][k] = {
                            i: j / k_sum
                            for i,j in mod_parent['features'][f_idx]['properties'][k].items()
                        }
    
    aggregated_child = spatially_aggregate(child_geo,[mod_parent],separate = False, summarize = False)
    
    return aggregated_child

def group_subtypes(geo_props: dict, name: str, key: dict, keep_zeros: bool = True, normalize: bool = True)->dict:
    """Grouping together properties into an lower-level descriptor

    :param geo_props: Property dict for a single Feature
    :type geo_props: dict
    :param name: Name of property containing "sub-properties" to be aggregated
    :type name: str
    :param key: Dictionary containing keys and values pertaining to sub-properties to be aggregated to each key
    :type key: dict
    :param keep_zeros: Whether or not to keep aggregated properties which sum to zero, defaults to True
    :type keep_zeros: bool, optional
    :param normalize: Whether to normalize this set of keys to sum to 1 or keep as sums, defaults to True
    :type normalize: bool, optional
    :return: Updated property dictionary containing lower-level descriptor and keys
    :rtype: dict
    """
    return_dict = {}
    if name in geo_props:
        sub_props = geo_props[name]
        for k,v in key.items():
            if type(v)==list:
                v_vals = [sub_props[v_i] if v_i in sub_props else 0 for v_i in v]
            elif type(v)==str:
                v_vals = [sub_props[v] if v in sub_props else 0]
            
            if sum(v_vals)==0:
                if keep_zeros:
                    return_dict[k] = 0.0
            else:
                return_dict[k] = sum(v_vals)
        
        if normalize:
            dict_sum = sum(list(return_dict.values()))
            if dict_sum>0:
                norm_dict = {
                    i: j/dict_sum
                    for i,j in return_dict.items()
                }
            else:
                norm_dict = return_dict.copy()

            return norm_dict
        else:
            return return_dict
    else:
        return return_dict


