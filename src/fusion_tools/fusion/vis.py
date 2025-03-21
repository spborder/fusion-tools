"""Generating FUSION (Functional Unit State Identification in WSIs) layout
"""
from fusion_tools.visualization import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import (
    SlideMap,
    MultiFrameSlideMap,
    ChannelMixer,
    OverlayOptions,
    PropertyViewer,
    GlobalPropertyPlotter,
    HRAViewer,
    DataExtractor,
    BulkLabels
)

from fusion_tools.fusion.data_types import get_upload_types


def get_layout(args):

    # Initialize DSA Handler
    dsa_handler = DSAHandler(
        girderApiUrl=args['girderApiUrl'],
        username = args['user'],
        password=args['pword']
    )

    dsa_login_component = dsa_handler.create_login_component()
    
    dsa_plugin_progress = dsa_handler.create_plugin_progress()

    dsa_dataset_builder = dsa_handler.create_dataset_builder()

    dsa_dataset_uploader = dsa_handler.create_uploader(
        upload_types = get_upload_types()
    )

    dsa_save_session = dsa_handler.create_save_session()

    user_surveys = []
    #dsa_user_surveys = [dsa_handler.create_survey(i) for i in user_surveys]

    initial_items = args['initialItems']

    fusion_vis = Visualization(
        tileservers=[dsa_handler.get_tile_server(i) for i in initial_items],
        linkage = 'page',
        header = [
            dsa_login_component,
            dsa_plugin_progress,
            dsa_save_session,
            #dsa_user_surveys
        ],
        components = {
            "Visualization": [
                [
                    SlideMap(),
                    [
                        OverlayOptions(),
                        PropertyViewer(ignore_list=['_id','_index']),
                        GlobalPropertyPlotter(ignore_list = ['_id','_index']),
                        HRAViewer(),
                        BulkLabels(),
                        DataExtractor()
                    ]
                ]
            ],
            "MultiFrame Visualization": [
                [
                    MultiFrameSlideMap(),
                    [
                        ChannelMixer(),
                        OverlayOptions(),
                        PropertyViewer(ignore_list = ['_id','_index']),
                        GlobalPropertyPlotter(ignore_list = ['_id','_index']),
                        HRAViewer(),
                        BulkLabels(),
                        DataExtractor()
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
