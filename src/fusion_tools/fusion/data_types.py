"""Defining UploadTypes which are accepted in FUSION
"""

from fusion_tools.handler.dataset_uploader import DSAUploadType, WSI_TYPES, ANN_TYPES

def get_upload_types():

    # Basic Type:
    kidney_basic_type = DSAUploadType(
        name = "Kidney Histology Image",
        description= 'This is a kidney histology image upload with the option to add annotations. Glomeruli, sclerotic glomeruli, tubules, and cortical and medullary interstitium are first segmented using DL and then pathomic features are calculated.',
        input_files = [
            {
                'name': 'Image',
                'description': 'This is any kidney histology image you would like to upload.',
                'accepted_types': WSI_TYPES,
                'preprocessing_plugins': None,
                'type': 'item',
                'required': True
            },
            {
                'name': 'Annotation',
                'description': 'This is an annotation file that is processed and added to the uploaded image.',
                'accepted_types': ANN_TYPES,
                'preprocessing_plugins': None,
                'type': 'annotation',
                'parent': 'Image',
                'required': False
            }
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
                                'type': 'upload_file',
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
                            }
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
                            }
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
            ]
        ],
        required_metadata=[]
    )

    # Basic Type:
    basic_type = DSAUploadType(
        name = "General Histology Image",
        description= 'This is a histology image upload with the option to add annotations. Glomeruli, sclerotic glomeruli, tubules, and cortical and medullary interstitium are first segmented using DL and then pathomic features are calculated.',
        input_files = [
            {
                'name': 'Image',
                'description': 'This is any histology image you would like to upload.',
                'accepted_types': WSI_TYPES,
                'preprocessing_plugins': None,
                'type': 'item',
                'required': True
            },
            {
                'name': 'Annotation',
                'description': 'This is an annotation file that is processed and added to the uploaded image.',
                'accepted_types': ANN_TYPES,
                'preprocessing_plugins': None,
                'type': 'annotation',
                'parent': 'Image',
                'required': False
            }
        ],
        processing_plugins=[
            {
                'name': 'FeatureExtraction',
                'image': 'fusionplugins/general:latest',
                'input_args': [
                    {
                        'name': 'input_image',
                        'default': {
                            'type': 'upload_file',
                            'name': 'Image'
                        }
                    },
                    {
                        'name': 'extract_sub_compartments',
                        'default': {
                            'value': True
                        }
                    },
                    {
                        'name': 'hematoxylin_threshold',
                        'default': {
                            'value': 150
                        }
                    },
                    {
                        'name': 'eosinophilic_threshold',
                        'default': {
                            'value': 30
                        }
                    },
                    {
                        'name': 'hematoxylin_min_size',
                        'default': {
                            'value': 40
                        }
                    },
                    {
                        'name': 'eosinophilic_min_size',
                        'default': {
                            'value': 20
                        }
                    },
                ]
            }
        ],
        required_metadata=[
            {
                'name': 'Organ',
                'required': True,
                'item': 'Image'
            }
        ]
    )

    # 10x Types:
    visium_type = DSAUploadType(
        name = '10x Visium',
        description = 'This upload type is for 10x Visium spatial transcriptomics samples. It includes one histology image and information related to the transcript counts per-"spot".',
        input_files = [
            {
                'name': 'Image',
                'description': 'This is the full-resolution image associated with this upload. If the full-resolution image is not available, upload the "hires_image" and the "scalefactors_json.json" file to appropriately scale coordinates.',
                'accepted_types': WSI_TYPES,
                'preprocessing_plugins': None,
                'type': 'item',
                'required': True
            },
            {
                'name': 'Counts',
                'description': 'This is the file containing per-spot gene counts',
                'accepted_types': ['h5','h5ad','csv','rds','RDS'],
                'preprocessing_plugins': None,
                'type': 'file',
                'parent': 'Image',
                'required': True
            },
            {
                'name': 'Structures',
                'description': 'If you have annotated any additional structures on the histology image, upload those annotations here.',
                'accepted_types': ANN_TYPES,
                'preprocessing_plugins': None,
                'type': 'annotation',
                'parent': 'Image',
                'required': False
            },
            {
                'name': 'Tissue Spot Positions',
                'description': 'If using outputs of the "spaceranger" pipeline, upload the "tissue_positions.csv" file here.',
                'accepted_types': ['csv'],
                'type': 'file',
                'parent': 'Image',
                'required': False
            },
            {
                'name': 'Scale Factors',
                'description': 'If using the "hires" image, upload the "scalefactors_json.json" file here.',
                'accepted_types': ['json'],
                'preprocessing_plugins': None,
                'type': 'file',
                'parent': 'Image',
                'required': False
            },
            {
                'name': 'Genes List File',
                'description': 'If you want to include specific genes which are not included in the "most variable" genes, upload CSV file containing one column with those gene IDs.',
                'accepted_types': ['csv'],
                'preprocessing_plugins': None,
                'type': 'file',
                'parent': 'Image',
                'required': False
            }
        ],
        processing_plugins=[
            [
                {
                    'name': 'CellDeconvolution',
                    'image': 'fusionplugins/visium:latest',
                    'input_args': [
                        {
                            'name': 'counts_file',
                            'default': {
                                'type': 'upload_file',
                                'name': 'Counts'
                            },
                            'disabled': True
                        },
                        'organ'
                    ]
                },
                {
                    'name': 'SpotAnnotation',
                    'image': 'fusionplugins/visium:latest',
                    'input_args': [
                        {
                            'name': 'counts_file',
                            'default': {
                                'type': 'intermediate_file',
                                'transform': {
                                    'base': 'Counts',
                                    'ext': '_integrated.rds'
                                }
                            },
                            'disabled': True
                        },
                        {
                            'name': 'input_files',
                            'default': {
                                'type': 'upload_file',
                                'name': 'Image'
                            },
                            'disabled': True
                        },
                        {
                            'name': 'spot_coords',
                            'default': {
                                'type': 'upload_file',
                                'name': 'Tissue Spot Positions'
                            },
                            'disabled': True
                        },
                        {
                            'name': 'scale_factors',
                            'default': {
                                'type': 'upload_file',
                                'name': 'Scale Factors'
                            },
                            'disabled': True
                        },
                        {
                            'name': 'gene_list_file',
                            'default': {
                                'type': 'upload_file',
                                'name': 'Genes List File'
                            },
                            'disabled': True
                        },
                        'use_gene_selection',
                        'gene_selection_method',
                        'n'
                    ]
                }
            ]
        ],
        required_metadata=[
            {
                'name': 'Organ',
                'required': True,
                'item': 'Image'
            }
        ]
    )

    xenium_type = DSAUploadType(
        name = '10x Xenium',
        description='This is for 10x Xenium samples. It includes a morphology (DAPI) image and, optionally, a histology image as well as cell centroids/boundaries and assigned "group" labels or other information for each segmented cell.',
        input_files = [
            {
                'name': 'Morphology Image',
                'description': 'This is the morphology image showing the location of nuclei in the sample at different levels.',
                'accepted_types': ['tif','tiff'],
                'preprocessing_plugins': None,
                'type': 'item',
                'required': True
            },
            {
                'name': 'Histology Image',
                'description': 'This is a histology image from the same section used for alignment of derived cell segmentations.',
                'accepted_types': WSI_TYPES,
                'preprocessing_plugins': None,
                'type': 'item',
                'required': False
            },
            {
                'name': 'Cell Segmentations',
                'description': 'This is a file containing either cell centroids and areas or the boundaries of segmented cells.',
                'accepted_types': ['csv'],
                'preprocessing_plugins': None,
                'type': 'annotation',
                'parent': 'Morphology Image',
                'required': True
            },
            {
                'name': 'Cell Groups',
                'description': 'This is a csv file containing one column with "cell_id" and then other columns which are added to per-cell properties (could be cell group labels or any other measurement).',
                'accepted_types': ['csv'],
                'preprocessing_plugins': None,
                'type': 'file',
                'parent': 'Morphology Image',
                'required': False
            }
        ],
        processing_plugins=[
            {
                'name': '',
                'image': '',
                'input_args': [
                    {

                    }
                ]
            }
        ],
        required_metadata=[
            {
                'name': 'Organ',
                'required': True,
                'item': 'Image'
            }
        ]
    )

    hd_type = DSAUploadType(
        name = "10x Visium HD",
        description = 'This is for the 10x Visium HD data type.',
        input_files = [
            {
                'name': 'Image',
                'description': '',
                'accepted_types': WSI_TYPES,
                'preprocessing_plugins': None,
                'type': 'item',
                'required': True
            }
        ],
        processing_plugins=[],
        required_metadata=[
            {
                'name': 'Organ',
                'required': True,
                'item': 'Image'
            }
        ]
    )

    # MxIF/PhenoCycler
    mxif_type = DSAUploadType(
        name = "MxIF / PhenoCycler",
        description = 'This is for a multiplexed - immunofluorescence (mxIF) type image containing several different fluorescence channels for different markers. If available, you may also choose to align this image with a same-section histology image.',
        input_files = [
            {
                'name': 'IF Image',
                'description': 'This is a single multi-frame immunofluorescence image containing aligned channels.',
                'accepted_types': ['tif','tiff'],
                'preprocessing_plugins': None,
                'type': 'item',
                'required': True
            },
            {
                'name': 'Histology Image',
                'description': 'This is a same-section histology image which the IF image is aligned to during processing.',
                'accepted_types': WSI_TYPES,
                'preprocessing_plugins': None,
                'type': 'item',
                'required': False
            },
            {
                'name': 'IF Annotations',
                'description': 'If any structures have been segmented from the IF image, upload them here.',
                'accepted_types': ANN_TYPES,
                'preprocessing_plugins': None,
                'type': 'annotation',
                'parent': 'IF Image',
                'required': False
            },
            {
                'name': 'Histology Annotations',
                'description': 'If any structures were segmented from the histology image, upload them here.',
                'accepted_types': ANN_TYPES,
                'preprocessing_plugins': None,
                'type': 'annotation',
                'parent': 'Histology Image',
                'required': False
            }
        ],
        processing_plugins = [
            [
                {
                    'image': 'fusionplugins/codex:latest',
                    'name': 'CellSegmentation',
                    'input_args': [
                        {
                            'name': 'input_image',
                            'default': {
                                'type': 'upload_file',
                                'name': 'IF Image'
                            }
                        }
                    ]
                },
                {
                    'image': 'fusionplugins/general:latest',
                    'name': 'FeatureExtraction',
                    'input_args': [
                        {
                            'name': 'input_image',
                            'default': {
                                'type': 'upload_file',
                                'name': 'IF Image'
                            }
                        }
                    ]
                }
            ],
            {
                'image': 'fusionplugins/general:latest',
                'name': 'FeatureExtraction',
                'input_args': [
                    {
                        'name': 'input_image',
                        'default': {
                            'type': 'upload_file',
                            'name': 'Histology Image'
                        }
                    },
                    {
                        'name': 'extract_sub_compartments',
                        'default': {
                            'value': True
                        }
                    },
                    'hematoxylin_threshold',
                    'eosinophilic_threshold',
                    'hematoxylin_min_size',
                    'eosinophilic_min_size'
                ]
            }
        ],
        required_metadata = [
            {
                'name': 'Organ',
                'required': True,
                'item': 'Image'
            }
        ]
    )

    # HuBMAP Processed Dataset
    hubmap_type = DSAUploadType(
        name = "HuBMAP Processed",
        description='This is for a dataset which has been processed by the Human Biomolecular Atlas Program (HuBMAP).',
        input_files = [
            {
                'name': 'Image',
                'description': '',
                'accepted_types': WSI_TYPES,
                'preprocessing_plugins': None,
                'type': 'item',
                'required': True
            }
        ],
        processing_plugins= [
            {
                'name': '',
                'image': '',
                'input_args': []
            }
        ],
        required_metadata=[
            {
                'name': 'Organ',
                'required': True,
                'item': 'Image'
            },
            {
                'name': 'Sample ID',
                'required': True,
                'item': 'Image'
            },
            {
                'name': 'Assay Type',
                'required': True,
                'item': 'Image'
            }
        ]
    )

    return [
        basic_type,
        kidney_basic_type,
        visium_type,
        xenium_type,
        hd_type,
        mxif_type,
        hubmap_type
    ]

