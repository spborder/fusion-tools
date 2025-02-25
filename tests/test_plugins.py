"""Testing plugin conductor and plugins
"""

import os
import sys
sys.path.append('./src/')

from fusion_tools.handler.dsa_handler import DSAHandler
from girder_job_sequence.utils import from_list

import requests
import json



def main(args):
    print(args)

    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'

    user_name = os.getenv('DSA_USER')
    p_word = os.getenv('DSA_PWORD')

    # You have to sign in to access the add_plugin() method
    dsa_handler = DSAHandler(
        girderApiUrl=base_url,
        username = user_name,
        password = p_word
    )
    
    if args[1]=='add':
        if len(args)>2:
            plugin_add_list = args[2:]
        else:
            plugin_add_list = [
                'fusionplugins/codex:latest',
                'fusionplugins/general:latest',
                'fusionplugins/visium:latest'
            ]
        
        # This adds the plugins in plugin_add_list, removing previous versions if they are present
        response = dsa_handler.add_plugin(
            image_name = plugin_add_list
        )

        print(response)

    elif args[1]=='run':

        if args[2]=='multifeat':
            # MultiCompartment segmentation --> FeatureExtraction
            job_list = [
                {
                    'docker_image': 'samborder2256/multicomp:latest',
                    'cli': 'MultiCompartmentSegment',
                    'input_args': [
                        {
                            'name': 'files',
                            'value': '6717e743f433060d2884838c'
                        },
                        {
                            'name': 'base_dir',
                            'value': '6717e73cf433060d28848389'
                        },
                        {
                            'name': 'modelfile',
                            'value': '648123761019450486d13dce'
                        }
                    ]
                },
                {
                    'docker_image': 'fusionplugins/general:latest',
                    'cli': 'FeatureExtraction',
                    'input_args': [
                        {
                            'name': 'input_image',
                            'value': "{{'type':'file','item_type':'path','item_query':'/user/sam123/Public/FUSION_Upload_2024_10_22_13_56_05_219929/XY01_IU-21-015F_001.svs','file_type':'fileName','file_query':'XY01_IU-21-015F_001.svs'}}"
                        },
                        {
                            'name': 'extract_sub_compartments',
                            'value': True
                        },
                        {
                            'name': 'hematoxylin_threshold',
                            'value': 150
                        },
                        {
                            'name': 'eosinophilic_threshold',
                            'value': 30
                        },
                        {
                            'name': 'hematoxylin_min_size',
                            'value': 40
                        },
                        {
                            'name': 'eosinophilic_min_size',
                            'value': 20
                        },
                    ]
                }
            ]

        elif args[2]=='codexfeat':
            # Cell segmentation --> FeatureExtraction
            job_list = [
                {
                    'docker_image': 'fusionplugins/codex:latest',
                    'cli': 'CellSegmentation',
                    'input_args': [
                        {
                            'name': 'input_image',
                            'value': '67af56bafcdeba1e293215e4'
                        },
                        {
                            'name': 'input_region',
                            'value': "[1600,1000,2600,2000]"
                        },
                        {
                            'name': 'return_segmentation_region',
                            'value': True
                        }
                    ]
                },
                {
                    'docker_image': 'fusionplugins/general:latest',
                    'cli': 'FeatureExtraction',
                    'input_args': [
                        {
                            'name': 'input_image',
                            'value': '67af56bafcdeba1e293215e4'
                        },
                        {
                            'name': 'extract_sub_compartments',
                            'value': False
                        }
                    ]
                }
            ]

        elif args[2]=='visium':
            # Cell deconvolution --> spot annotation --> feature extraction
            job_list = [
                {
                    'docker_image': 'fusionplugins/visium:latest',
                    'cli': 'CellDeconvolution',
                    'input_args': [
                        {
                            'name': 'counts_file',
                            'value': '67af4e59fcdeba1e293211c2'
                        },
                        {
                            'name': 'organ',
                            'value': 'Azimuth Kidney Reference'
                        }
                    ]
                },
                {
                    'docker_image': 'fusionplugins/visium:latest',
                    'cli': 'SpotAnnotation',
                    'input_args': [
                        {
                            'name': 'counts_file',
                            'value': "{{'type': 'file', 'item_type': '_id','item_query': '67af4e59fcdeba1e293211c0', 'file_type': 'fileName','file_query': 'V10S15-102_XY02_IU-21-019-5_integrated.rds'}}"
                        },
                        {
                            'name': 'input_files',
                            'value': '67af4e59fcdeba1e293211c0'
                        },
                        {
                            'name': 'use_gene_selection',
                            'value': True
                        },
                        {
                            'name': 'gene_selection_method',
                            'value': 'dispersion'
                        },
                        {
                            'name': 'n',
                            'value': 10
                        }
                    ]
                }
            ]
        
        job_sequence = from_list(dsa_handler.gc, job_list)
        for j in job_sequence.jobs:
            print(json.dumps(j.input_args,indent=4))
            #print(json.dumps(j.executable_dict,indent=4))

        job_sequence.start(verbose=True,cancel_on_error=True)
        
    

if __name__=='__main__':
    main(sys.argv)
