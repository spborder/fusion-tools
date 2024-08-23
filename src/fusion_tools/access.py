"""
Functions related to access of data derived from FUSION

- Query available data in FUSION instance
    - Count of slides, names of annotations, annotation names per slide, slide metadata
- Extract
    - annotations (various formats, regions, full), images (regions, full, thumbnails), files

"""

import os
import sys
import json
import requests

import girder_client

import pandas as pd
import anndata as ad
import geojson

import geopandas as gpd

from typing_extensions import Union


class Accessor:
    def __init__(self,
                 fusion_handler):
        
        self.fusion_handler = fusion_handler

    def query_annotation_count(self, item:Union[str,list]) -> dict:
        """
        Get count of annotations for a given item
        """

        if type(item)==str:
            item = [item]

        ann_counts = []
        for it in item:
            item_dict = {}
            if '/' in it:
                item_info = self.get_path_info(it)
            else:
                item_info = self.fusion_handler.gc.get(f'/item/{it}')

            item_dict['name'] = item_info['name']
            item_dict['id'] = item_info['_id']
            item_anns = self.fusion_handler.gc.get(f'/annotation',parameters={'itemId':it})

            if len(item_anns)>0:
                for ann in item_anns:
                    # Only grabbing centroids to make it a little more lightweight
                    ann_centroids = self.fusion_handler.gc.get(f'/annotation/{ann["_id"]}',parameters={'centroids': True})
                    ann_count = len(ann_centroids['annotation']['elements'])

                    item_dict[ann['annotation']['name']] = ann_count

            ann_counts.append(item_dict)

        ann_counts_df = pd.DataFrame.from_records(ann_counts).fillna(0)

        return ann_counts_df
    
    def get_path_info(self, item_path: str) -> dict:
        """
        Get item information from path
        """

        # First searching for the "resource"
        assert any([i in item_path for i in ['collection','user']])

        resource_find = self.fusion_handler.gc.get('/resource/lookup',parameters={'path': item_path})

        return resource_find
    
    def get_folder_slide_count(self, folder_path: str, ignore_histoqc = True) -> list:
        """
        Get number of slide items in a folder
        """

        if '/' in folder_path:
            folder_info = self.get_path_info(folder_path)
        else:
            folder_info = self.fusion_handler.gc.get(f'/folder/{folder_path}')

        folder_items = self.fusion_handler.gc.get(f'/resource/{folder_info["_id"]}',
                                                  parameters = {
                                                      'type': folder_info["type"],
                                                      'limit': 0 
                                                  })

        if len(folder_items)>0:
            if ignore_histoqc:
                folders_in_folder = list(set([i['folderId'] for i in folder_items]))
                folder_names = [
                    self.fusion_handler.gc.get(f'/folder/{i}')['name']
                    for i in folders_in_folder
                ]

                if 'histoqc_outputs' not in folder_names:
                    ignore_folders = []
                else:
                    ignore_folders = [folders_in_folder[i] for i in range(len(folder_names)) if folder_names[i]=='histoqc_outputs']

            else:
                ignore_folders = []

            folder_image_items = [i for i in folder_items if 'largeImage' in i and not i['folderId'] in ignore_folders]

        else:
            folder_image_items = []

        return folder_image_items

    
