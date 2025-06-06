"""Testing fusion with multiple workers
"""

import os
import sys
sys.path.append('./src/')

import waitress
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

from fusion_tools.fusion.vis import get_layout

def main():
    dsa_url = os.environ.get('DSA_URL')
    dsa_user = os.environ.get('DSA_USER')
    dsa_pword = os.environ.get('DSA_PWORD')

    if all([i is None for i in [dsa_url,dsa_user,dsa_pword]]):
        raise Exception('Need to initialize with at least the environment variable: DSA_URL')

    initial_items = [
        '6495a4e03e6ae3107da10dc5',
        '6495a4df3e6ae3107da10dc2'
    ] 

    args_dict = {
        'girderApiUrl': dsa_url,
        'user': dsa_user,# Optional
        'pword': dsa_pword,# Optional
        'initialItems': initial_items,
        'app_options': {
            'port': 8050,
        }
    }

    fusion_vis = get_layout(args_dict)

    return fusion_vis

if __name__=='__main__':
    app = main()
    waitress.serve(app.viewer_app.server, host = '0.0.0.0', port = 8050, threads=10)



