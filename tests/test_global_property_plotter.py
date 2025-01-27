"""Testing out GlobalPropertyPlotter component
"""


import os
import sys
sys.path.append('./src/')

from fusion_tools import Visualization
from fusion_tools.components import GlobalPropertyPlotter
from fusion_tools.handler.dsa_handler import DSAHandler

import pandas as pd



def main():
    
    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    item_ids = [
        '64f545302d82d04be3e39eec',
        '64f545082d82d04be3e39ee1',
        '64f54be52d82d04be3e39f65'
    ]

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )

    dsa_tileserver = [
        dsa_handler.get_tile_server(i)
        for i in item_ids
    ]
    
    vis_session = Visualization(
        tileservers = dsa_tileserver,
        components = [
            GlobalPropertyPlotter()
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()

