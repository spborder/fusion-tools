"""
Handler for requests made to a running FUSION instance.

"""

import os
import sys

import girder_client

import requests
import json
import numpy as np

from typing_extensions import Union

from skimage.draw import polygon
from PIL import Image
from io import BytesIO


class FUSIONHandler:
    def __init__(self,
                 girderApiUrl: str,
                 username: str,
                 password: str):
        
        self.girderApiUrl = girderApiUrl
        self.username = username
        self.password = password

        self.gc = girder_client.GirderClient(apiUrl=self.girderApiUrl)
        self.gc.authenticate(
            username = self.username,
            password=self.password
        )

        # Token used for authenticating requests
        self.user_token = self.gc.get(f'/token/session')['token']

    def get_image_region(self, item_id: str, coords_list: list, style: Union[dict,None] = None)->np.ndarray:
        """
        Grabbing image region from list of bounding box coordinates
        """

        image_array = np.zeros((256,256))

        if style is None:
            image_array = np.uint8(
                np.array(
                    Image.open(
                        BytesIO(
                            requests.get(
                                self.gc.urlBase+f'/item/{item_id}/tiles/region?token={self.user_token}&left={coords_list[0]}&top={coords_list[1]}&right={coords_list[2]}&bottom={coords_list[3]}'
                            ).content
                        )
                    )
                )
            )
        
        else:
            print('Adding style parameters are in progress')
            raise NotImplementedError

        return image_array

    def make_boundary_mask(self, exterior_coords: list) -> np.ndarray:
        """
        Making a binary mask given a set of coordinates, scales coordinates to fit within bounding box.
        
        Expects coordinates in x,y format
        """
        x_coords = [i[0] for i in exterior_coords]
        y_coords = [i[1] for i in exterior_coords]

        min_x = min(x_coords)
        max_x = max(x_coords)
        min_y = min(y_coords)
        max_y = max(y_coords)
        
        scaled_coords = [[int(i[0]-min_x), int(i[1]-min_y)] for i in exterior_coords]

        boundary_mask = np.zeros((int(max_y-min_y),int(max_x-min_x)))

        row,col = polygon(
            [i[1] for i in scaled_coords],
            [i[0] for i in scaled_coords],
            (int(max_y-min_y), int(max_x-min_x))
        )

        boundary_mask[row,col] = 1

        return boundary_mask



