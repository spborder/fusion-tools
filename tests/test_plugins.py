"""Testing plugin conductor and plugins
"""

import os
import sys
sys.path.append('./src/')

from fusion_tools.handler.dsa_handler import DSAHandler

import requests
import json


def main():

    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'

    user_name = os.getenv('DSA_USER')
    p_word = os.getenv('DSA_PWORD')

    # You have to sign in to access the add_plugin() method
    dsa_handler = DSAHandler(
        girderApiUrl=base_url,
        username = user_name,
        password = p_word
    )
    """
    plugin_add_list = [
        #'fusionplugins/codex:latest',
        'fusionplugins/job_conductor:latest'
    ]
    
    # This adds the plugins in plugin_add_list, removing previous versions if they are present
    response = dsa_handler.add_plugin(
        image_name = plugin_add_list
    )

    print(response)
    """
    # MultiCompartment segmentation --> FeatureExtraction
    job_conductor_inputs = [
        {
            "_id": "65de6baeadb89a58fea10d4c",
            "parameters": {
                "files":"6717e743f433060d2884838c",
                "base_dir": "6717e73cf433060d28848389",
                "modelfile": "648123761019450486d13dce"
            }
        },
        {
            "_id": "67a63efdfcdeba1e292f63b3",
            "parameters": {
                "input_image":"{{'type':'file','item_type':'path','item_query':'/user/sam123/Public/FUSION_Upload_2024_10_22_13_56_05_219929/XY01_IU-21-015F_001.svs','file_type':'name','file_query':'XY01_IU-21-015F_001.svs'}}",
                "extract_sub_compartments": True,
                "hematoxylin_threshold": 150,
                "eosinophilic_threshold": 30,
                "hematoxylin_min_size": 40,
                "eosinophilic_min_size": 20
            }
        }
    ]
    
    response = dsa_handler.run_plugin(
        plugin_id = '67a6841afcdeba1e292f64a8',
        arguments = {
            'job_list': json.dumps(job_conductor_inputs),
            'check_interval': 5,
            'metadata_item': "{{'type':'item','item_type':'path','item_query':'/user/sam123/Public/FUSION_Upload_2024_10_22_13_56_05_219929/XY01_IU-21-015F_001.svs'}}"
        }
    )
    
    print(response.json())
    

if __name__=='__main__':
    main()
