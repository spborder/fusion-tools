"""Testing out GlobalPropertyPlotter component
"""


import os
import sys
sys.path.append('./src/')

from fusion_tools.visualization import Visualization
from fusion_tools.components import GlobalPropertyPlotter
from fusion_tools.handler.dsa_handler import DSAHandler

import pandas as pd

def get_item_ids(base_url):

    visium_collection = '10X_Visium'
    frozen_folders = ['AKI','CKD_DKD','Ref']
    ffpe_folders = ['Diabetic','Reference']

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )

    frozen_items = []
    for f in frozen_folders:
        folder_path = '/collection/'+visium_collection+'/'+f

        folder_items = dsa_handler.get_folder_slides(folder_path)
        # Assigning their group label in the item metadata
        for it in folder_items:
            it['meta'] = it['meta'] | {'Group': f.upper().replace('_DKD','')}
        frozen_items.extend(folder_items)

    cloud_item_names = [i['name'].replace('.tif','').replace('.svs','') for i in frozen_items]

    # Getting data in New Visium folder
    new_visium_folder = '/user/sam123/Public/New Visium'
    new_visium_slides = dsa_handler.get_folder_slides(new_visium_folder)

    for n in new_visium_slides:
        if not n['name'].replace('.tif','').replace('.svs','') in cloud_item_names:
            frozen_items.append(n)

    return frozen_items

def main():
    
    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    #item_ids = [
    #    '64f545302d82d04be3e39eec',
    #    '64f545082d82d04be3e39ee1',
    #    '64f54be52d82d04be3e39f65'
    #]

    item_ids = [i['_id'] for i in get_item_ids(base_url)]
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

