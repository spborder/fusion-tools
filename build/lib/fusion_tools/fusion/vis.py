"""Generating FUSION (Functional Unit State Identification in WSIs) layout
"""
from fusion_tools import Visualization
from fusion_tools.handler import DSAHandler
from fusion_tools.components import (
    MultiFrameSlideMap,
    ChannelMixer,
    OverlayOptions,
    PropertyViewer,
    GlobalPropertyPlotter,
    HRAViewer,
    FeatureAnnotation,
    BulkLabels
)


def get_layout(*args):

    # Initialize DSA Handler
    dsa_handler = DSAHandler(
        girderApiUrl=args['girderApiUrl'],
        username = args['user'],
        password=args['pword']
    )

    dsa_login_component = dsa_handler.create_login_component()

    dsa_dataset_builder = dsa_handler.create_dataset_builder(
        include = args['dataset_builder_include']
    )

    dsa_dataset_uploader = dsa_handler.create_uploader(
        uploader_types = []
    )

    user_surveys = []
    dsa_user_surveys = [dsa_handler.create_survey(i) for i in user_surveys]

    initial_items = args['initialItems']

    fusion_vis = Visualization(
        tileservers=[dsa_handler.get_tile_server(i) for i in initial_items],
        linkage = 'page',
        header = [
            dsa_login_component,
            dsa_user_surveys
        ],
        components = {
            "Visualization": [
                [
                    MultiFrameSlideMap()
                ],
                [
                    [
                        OverlayOptions(),
                        ChannelMixer(),
                        PropertyViewer(ignore_list=['_id','_index']),
                        GlobalPropertyPlotter(ignore_list = ['_id','_index']),
                        HRAViewer(),
                        BulkLabels()
                    ]
                ]
            ],
            "Dataset Builder": [
                dsa_dataset_builder
            ],
            "Dataset Uploader": [
                dsa_dataset_uploader
            ]
        },
        app_options = args['app_options']
    )

    return fusion_vis
