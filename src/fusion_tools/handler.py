"""
Handler for requests made to a running FUSION instance.

"""

import os
import sys

import girder_client

import requests
import json


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

    
















