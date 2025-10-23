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
from fusion_tools import asyncio_db_loop
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
        self.router.add_api_route('/user', lambda: self.get_from_table("user"), methods=["GET"],tags = ['user'])
        #self.router.add_api_route('/user/me', lambda: self.get_from_table("user"), methods=["GET"],tags = ['user'])
        self.router.add_api_route('/user/authenticate',self.authenticate, methods = ["GET"],tags=['user'])
        self.router.add_api_route('/user/{id}', lambda id: self.get_from_table("user",id), methods=["GET"],tags = ['user'])

        # VisSession 
        self.router.add_api_route('/vis_session', lambda: self.get_from_table("vis_session"), methods=["GET"], tags = ['vis_session'])
        self.router.add_api_route('/vis_session/{id}', lambda id: self.get_from_table("vis_session",id), methods=["GET"], tags = ['vis_session'])

        # Item
        self.router.add_api_route('/item', lambda: self.get_from_table("item"), methods=["GET"],tags=['item'])
        self.router.add_api_route('/item/{id}', lambda id: self.get_from_table("item",id), methods=["GET"],tags=['item'])

        # Layer
        self.router.add_api_route('/layer', lambda: self.get_from_table("layer"), methods=["GET"],tags = ['layer'])
        self.router.add_api_route('/layer/{id}', lambda id: self.get_from_table("layer",id), methods=["GET"],tags = ['layer'])

        # Structure
        self.router.add_api_route('/structure', lambda: self.get_from_table("structure"), methods=["GET"],tags = ['structure'])
        self.router.add_api_route('/structure/{id}', lambda id: self.get_from_table("structure",id), methods=["GET"],tags = ['structure'])

        # ImageOverlay
        self.router.add_api_route('/image_overlay', lambda: self.get_from_table("image_overlay"), methods=["GET"], tags = ['image_overlay'])
        self.router.add_api_route('/image_overlay/{id}', lambda id: self.get_from_table("image_overlay",id), methods=["GET"], tags = ['image_overlay'])

        # Annotation
        self.router.add_api_route('/annotation', lambda: self.get_from_table("annotation"), methods=["GET"], tags = ['annotation'])
        self.router.add_api_route('/annotation/{id}', lambda id: self.get_from_table("annotation",id), methods=["GET"], tags = ['annotation'])

        # Data
        self.router.add_api_route('/data', lambda: self.get_from_table("data"), methods=["GET"], tags = ['data'])
        self.router.add_api_route('/data/{id}', lambda id: self.get_from_table("data",id), methods=["GET"], tags = ['data'])

    @asyncio_db_loop
    def search_db(self, search_kwargs, size, offset):
        
        loop = asyncio.get_event_loop()
        search_output = loop.run_until_complete(
            asyncio.gather(
                self.database.search(
                    search_kwargs = search_kwargs,
                    size = size,
                    offset = offset
                )
            )
        )

        return search_output[0].copy()

    def get_from_table(self, table_name: str, id: str | None = None, request: Request | None = None) -> list:
        """Getting one or more elements from a specific table in the database

        :param table_name: Name of table to GET from
        :type table_name: str
        :param id: ID of specific element in table to GET
        :type id: str | None
        :param request: Query parameters, etc.
        :type request: Request
        """

        token = None
        size = None
        offset = 0
        if not request is None:
            if request.query_params.get('token'):
                token = request.query_params.get('token')
            if request.query_params.get('size'):
                size = request.query_params.get('size')
            if request.query_params.get('offset'):
                offset = request.query_params.get('offset')

        if not token is None:
            user_filter = {
                'user': {
                    'token': token
                }
            }
        else:
            user_filter = {}

        if id is not None:
            id_filter = {
                table_name: {
                    'id': id
                }
            }
        else:
            id_filter = {}

        search_output = self.search_db(
            search_kwargs = {
                'type': table_name,
                'filter': id_filter | user_filter 
            },
            size = size,
            offset = offset
        )

        return search_output

    def authenticate(self, login:str, password:str) -> dict:

        auth_check = self.database.check_user_login_password(login,password)

        return auth_check


