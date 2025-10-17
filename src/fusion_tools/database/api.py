"""

API associated with running application, accessing select elements in fusionDB


"""

import os
import sys

from fastapi import FastAPI, APIRouter, Response, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
import large_image
import requests
import json
from typing import Annotated
from typing_extensions import Union

from copy import deepcopy
import numpy as np
import uvicorn

import asyncio

from shapely.geometry import box, shape

from fusion_tools.database.database import fusionDB 



class fusionAPI:
    def __init__(self,
                database: Union[fusionDB,None],
                cors_options: dict = {}):

        self.database = database
        self.cors_options = cors_options

        # - GET all rows in tables
        # - GET,PUT,POST,OPTIONS by id, each row in tables in models.py

        self.router = APIRouter()

        # User
        self.router.add_api_route('/user', methods=["GET"])
        self.router.add_api_route('/user/me', methods=["GET"])
        self.router.add_api_route('/user/{id}', methods=["GET"])

        # VisSession 
        self.router.add_api_route('/vis_session', methods=["GET"])
        self.router.add_api_route('/vis_session/{id}', methods=["GET"])


        # Item
        self.router.add_api_route('/item', methods=["GET"])
        self.router.add_api_route('/item/{id}', methods=["GET"])


        # Layer
        self.router.add_api_route('/layer', methods=["GET"])
        self.router.add_api_route('/layer/{id}', methods=["GET"])


        # Structure
        self.router.add_api_route('/structure', methods=["GET"])
        self.router.add_api_route('/structure/{id}', methods=["GET"])


        # ImageOverlay
        self.router.add_api_route('/image_overlay', methods=["GET"])
        self.router.add_api_route('/image_overlay/{id}', methods=["GET"])


        # Annotation
        self.router.add_api_route('/annotation', methods=["GET"])
        self.router.add_api_route('/annotation/{id}', methods=["GET"])


        # Data
        self.router.add_api_route('/data', methods=["GET"])
        self.router.add_api_route('/data/{id}', methods=["GET"])



    






















