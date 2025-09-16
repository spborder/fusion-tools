"""Testing FeatureAnnotation component
"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import SlideMap, FeatureAnnotation, BulkLabels, SlideAnnotation

import pandas as pd

test_schema = [
    {
        "name": "Test Slide Annotation",
        "description": "This is a test of the SlideAnnotation component",
        "annotations": [
            {
                "name": "Example Text Label",
                "description": "This is an example free text annotation type.",
                "type": "text",
                "roi": True,
                "editable": True
            },
            {
                "name": "Example Numeric Label",
                "description": "This is an example numeric input label",
                "type": "numeric",
                "min": 0,
                "max": 100,
                "roi": False
            },
            {
                "name": "Example Options Label",
                "description": "This is an example of a label with predefined options",
                "type": "options",
                "options": [
                    "Option 1",
                    "Option 2",
                    "Option 3"
                ],
                "multi": False,
                "roi": False
            }
        ]
    }
]

test_feature_schema =  [
    {
        'name': 'Test Class',
        'type': 'class',
        'color': 'rgba(255,0,0,1.0)'
    },
    {
        'name': 'Test Text Label',
        'type': 'text'
    },
    {
        'name': 'Test Options Label',
        'type': 'options',
        'options': [
            'Option 1',
            'Option 2'
        ]
    }
]

def main():

    # Grabbing first item from demo DSA instance
    base_url = 'https://demo.kitware.com/histomicstk/api/v1'
    item_id = ['5bbdeed1e629140048d01bcb','58b480ba92ca9a000b08c89d']
    """
    base_url = os.environ.get('DSA_URL')

    item_id = [
        '6495a4e03e6ae3107da10dc5',
        '6495a4df3e6ae3107da10dc2'
    ]
    """ 

    local_slide_path = '/home/sam/Desktop/Example Data/Simple Histology/histology_image.svs'
    local_slide_anns = local_slide_path.replace('histology_image.svs','histology_annotations.xml')


    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )
    
    vis_session = Visualization(
        local_slides = [local_slide_path],
        local_annotations = [local_slide_anns],
        tileservers=[
            dsa_handler.get_tile_server(i) for i in item_id
        ],
        components = [
            [
                SlideMap(
                    cache = False
                ),
                [
                    FeatureAnnotation(
                        annotations = test_feature_schema,
                        editable = True
                    ),
                    BulkLabels(),
                    SlideAnnotation(
                        preload_schema=test_schema
                    )
                ]
            ]
        ]
    )




    vis_session.start()


if __name__=='__main__':
    main()


