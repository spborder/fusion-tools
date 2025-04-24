"""Testing DatasetBuilder component
"""

import os
import sys
sys.path.append('./src/')

from fusion_tools.visualization import Visualization
from fusion_tools.components import SlideMap, MultiFrameSlideMap, ChannelMixer, OverlayOptions, BulkLabels, PropertyViewer, PropertyPlotter, FeatureAnnotation, HRAViewer, DataExtractor
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.handler.dataset_uploader import DSAUploadType
from fusion_tools.handler.survey import SurveyType

# This is an example upload type for an image and a file
simple_upload_type = DSAUploadType(
    name = 'Basic Upload',
    description = 'This is a test upload type consisting of an image and an associated file',
    input_files = [
        {
            'name': 'Image',
            'description': 'This is any image you would like to upload to the DSA instance',
            'accepted_types': ['png','jpg','svs','tiff','tif'],
            'preprocessing_plugins': None,
            'type': 'item',
            'required': True,
        },
        {
            'name': 'Associated File',
            'description': 'This is any other file type that you want added to the "files" of the uploaded image.',
            'accepted_types': ['csv','xlsx','txt'],
            'preprocessing_plugins': None,
            'type': 'file',
            'parent': 'Image',
            'required': False,
        },
        {
            'name': 'Annotation',
            'description': 'This is an annotation file that is processed and added to the uploaded image',
            'accepted_types': ['xml','json','geojson'],
            'preprocessing_plugins': None,
            'type': 'annotation',
            'parent': 'Image',
            'required': False
        }
    ],
    processing_plugins = [
        {
            'name': 'NucleiDetection',
            'image': 'dsarchive/histomicstk:latest',
            'input_args': [
                {
                    'name': 'inputImageFile',
                    'default': {
                        'type': 'upload_file',
                        'name': 'Image'
                    },
                    'disabled': True
                },
                {
                    'name': 'outputNucleiAnnotationFile_folder',
                    'default': {
                        'type': 'upload_folder',
                        'name': 'Image'
                    },
                    'disabled': True
                },
                {
                    'name': 'outputNucleiAnnotationFile',
                    'default': {
                        'type': 'output_file',
                        'fileName': {
                            'name': 'Image',
                            'ext': '.annot'
                        },
                        'folderId': {
                            'name': 'Image'
                        }
                    },
                    'disabled': True
                },
                'nuclei_annotation_format',
                'min_nucleus_area',
                'ignore_border_nuclei',
                'ImageInversionForm'
            ]
        }
    ],
    required_metadata = [
        {
            'name': 'Image Type',
            'values': ['Histology','Fluorescence','Unknown'],
            'required': True,
            'item': 'Image'
        },
        {
            'name': 'Image Label',
            'values': ['Label 1','Label 2','Label 3'],
            'required': False,
            'item': 'Image'
        },
        {
            'name':'Extra Metadata',
            'required': False,
            'item': 'Image'
        }
    ]
)

sequence_upload_type = DSAUploadType(
    name = 'Sequential Processing Upload',
    description='This plugin requires multiple plugins to be run in sequence',
    input_files = [
        {
            'name': 'Image',
            'description': 'This is any image you would like to upload to the DSA instance',
            'accepted_types': ['png','jpg','svs','tiff','tif'],
            'preprocessing_plugins': None,
            'type': 'item',
            'required': True,
        },
    ],
    processing_plugins=[
        [
            {
                'name': 'MultiCompartmentSegment',
                'image': 'samborder2256/multicomp:latest',
                'input_args': [
                    {
                        'name': 'files',
                        'default': {
                            'type':'upload_file',
                            'name': 'Image'
                        },
                        'disabled': True
                    },
                    {
                        'name': 'base_dir',
                        'default': {
                            'type': 'upload_folder',
                            'name': 'Image'
                        },
                        'disabled': True
                    },
                    {
                        'name': 'modelfile',
                        'default': {
                            'value': '648123761019450486d13dce'
                        },
                        'disabled': True
                    }
                ]
            },
            {
                'name': 'FeatureExtraction',
                'image': 'fusionplugins/general:latest',
                'input_args': [
                    {
                        'name': 'input_image',
                        'default': {
                            'type': 'upload_file',
                            'name': 'Image'
                        },
                        'disabled': True
                    },
                    {
                        'name': 'extract_sub_compartments',
                        'default': {
                            'value': True
                        },
                        'disabled': True
                    },
                    'hematoxylin_threshold',
                    'eosinophilic_threshold',
                    'hematoxylin_min_size',
                    'eosinophilic_min_size'
                ]
            }
        ],
        {
            'name': 'NucleiDetection',
            'image': 'dsarchive/histomicstk:latest',
            'input_args': [
                {
                    'name': 'inputImageFile',
                    'default': {
                        'type': 'upload_file',
                        'name': 'Image'
                    },
                    'disabled': True
                },
                {
                    'name': 'outputNucleiAnnotationFile_folder',
                    'default': {
                        'type': 'upload_folder',
                        'name': 'Image'
                    },
                    'disabled': True
                },
                {
                    'name': 'outputNucleiAnnotationFile',
                    'default': {
                        'type': 'output_file',
                        'fileName': {
                            'name': 'Image',
                            'ext': '.annot'
                        },
                        'folderId': {
                            'name': 'Image'
                        }
                    },
                    'disabled': True
                },
                'nuclei_annotation_format',
                'min_nucleus_area',
                'ignore_border_nuclei',
                'ImageInversionForm'
            ]
        }
    ]
)


def main():
    # Creates a multi-page application with a different set of slides on each page

    base_dir = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\'
    local_slide_list = [
        base_dir+'XY01_IU-21-015F_001.svs',
        base_dir+'XY01_IU-21-015F.svs',
        base_dir+'new Visium\\V12U21-010_XY02_21-0069.tif',
        base_dir+'KPMP_Atlas_V2\\V10S14-085_XY01_20-0038\\V10S14-085_XY01_20-0038_lowres_image.tiff'
    ]

    # This can be set to False or removed, testing the upload overlaid annotations
    testing_upload = False
    local_annotations_list = [
        base_dir+'XY01_IU-21-015F_001.xml' if not testing_upload else None,
        None,
        base_dir+'new Visium\\V12U21-010_XY02_21-0069.h5ad',
        None
    ]

    dsa_handler = DSAHandler(
        girderApiUrl = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    )

    dsa_items_list = [
        '64f545082d82d04be3e39ee1',
        '64f54be52d82d04be3e39f65',
        '64d3c6f3287cfdce1e9c4d88'
    ]

    dsa_tileservers = [dsa_handler.get_tile_server(i) for i in dsa_items_list]
    dsa_dataset_builder = dsa_handler.create_dataset_builder()
    dsa_login = dsa_handler.create_login_component()
    dsa_plugin_progress = dsa_handler.create_plugin_progress()
    dsa_uploader = dsa_handler.create_uploader(
        upload_types = [
            simple_upload_type,
            sequence_upload_type
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
                    [
                        OverlayOptions(),
                        PropertyViewer(),
                        PropertyPlotter(),
                        HRAViewer(),
                        FeatureAnnotation(
                            storage_path = os.getcwd()+'\\tests\\Test_Annotations\\',
                            annotations_format = 'rgb'
                        ),
                        BulkLabels(),
                        DataExtractor()
                    ]
                ]   
            ],
            "MultiFrame Visualization": [
                [
                    MultiFrameSlideMap(),
                    ChannelMixer()
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
            dsa_login,
            dsa_plugin_progress
        ],
        app_options={
            'port': 8050,
        }
    )

    vis_sess.start()

if __name__=='__main__':
    main()


