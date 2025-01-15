"""Testing DatasetBuilder component
"""

import os
import sys
sys.path.append('./src/')

from fusion_tools import Visualization
from fusion_tools.components import SlideMap, OverlayOptions, PropertyPlotter
from fusion_tools.handler import DSAHandler, DSAUploadType, SurveyType


# This is an example upload type for an image and a file
simple_upload_type = DSAUploadType(
    name = 'Basic Upload',
    input_files = [
        {
            'name': 'Image',
            'description': 'This is any image you would like to upload to the DSA instance',
            'accepted_types': ['.png','.jpg','.svs','.tiff','.tif'],
            'preprocessing_plugins': None,
            'main': True,
            'required': True 
        },
        {
            'name': 'Associated File',
            'description': 'This is any other file type that you want added to the "files" of the uploaded image.',
            'accepted_types': ['.png','.csv','.xlsx','.txt'],
            'preprocessing_plugins': None,
            'main': False,
            'required': False
        }
    ],
    processing_plugins = [
        {
            'name': 'NucleiDetection',
            'image': 'dsarchive/histomicstk:latest',
        }
    ],
    required_metadata = [
        {
            'key': 'Image Type',
            'values': ['Histology','Fluorescence','Unknown'],
            'required': True
        },
        {
            'key': 'Image Label',
            'values': ['Label 1','Label 2','Label 3'],
            'required': False
        },
        'Extra Metadata'
    ]
)



def main():
    # Creates a two page application with a different set of slides on each page

    base_dir = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\'
    local_slide_list = [
        base_dir+'XY01_IU-21-015F_001.svs',
        base_dir+'XY01_IU-21-015F.svs',
        base_dir+'new Visium\\V12U21-010_XY02_21-0069.tif',
    ]
    local_annotations_list = [
        base_dir+'XY01_IU-21-015F_001.xml',
        None,
        base_dir+'new Visium\\V12U21-010_XY02_21-0069.h5ad',
    ]

    dsa_handler = DSAHandler(
        girderApiUrl = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    )

    dsa_items_list = [
        '64f545082d82d04be3e39ee1',
        '64f54be52d82d04be3e39f65'
    ]

    dsa_tileservers = [dsa_handler.get_tile_server(i) for i in dsa_items_list]
    dsa_dataset_builder = dsa_handler.create_dataset_builder()
    dsa_login = dsa_handler.create_login_component()
    dsa_uploader = dsa_handler.create_uploader(
        upload_types = [
            simple_upload_type
        ]
    )

    vis_sess = Visualization(
        local_slides = local_slide_list,
        local_annotations = local_annotations_list,
        tileservers = dsa_tileservers,
        linkage = 'page',
        components = {
             "Visualization": [
                [
                    SlideMap(),
                    OverlayOptions()
                ]   
            ],
            "Dataset Builder": [
                dsa_dataset_builder
            ],
            'Dataset Uploader': [
                dsa_uploader
            ]
        },
        header = [
            dsa_login
        ],
        app_options={
            'port': 8050
        }
    )

    vis_sess.start()










if __name__=='__main__':
    main()


