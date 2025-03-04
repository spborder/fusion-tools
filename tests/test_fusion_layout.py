"""Testing FUSION layout
"""

import os
import sys
sys.path.append('./src/')

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
        'user': dsa_user,
        'pword': dsa_pword,
        'initialItems': initial_items,
        'app_options': {
            'port': 8050
        }
    }

    fusion_vis = get_layout(args_dict)

    fusion_vis.start()

if __name__=='__main__':
    main()
