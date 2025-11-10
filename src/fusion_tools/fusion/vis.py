"""Generating FUSION (Functional Unit State Identification in WSIs) layout
"""
from fusion_tools.visualization import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import (
    SlideMap,
    HybridSlideMap,
    ChannelMixer,
    OverlayOptions,
    PropertyViewer,
    GlobalPropertyPlotter,
    HRAViewer,
    DataExtractor,
    BulkLabels
)

from fusion_tools.fusion.data_types import get_upload_types
from fusion_tools.fusion.welcome import WelcomePage

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

    initial_items = args['initialItems']

    if not 'default_page' in args['app_options']:
        args['app_options']['default_page'] = 'Welcome'

    fusion_vis = Visualization(
        tileservers=[dsa_handler.get_tile_server(i) for i in initial_items],
        linkage = 'page',
        database = args.get('database',None),
        header = [
            dsa_login_component,
            dsa_plugin_progress,
            dsa_save_session,
        ],
        components = {
            "Welcome": [
                WelcomePage()
            ],
            "Visualization": [
                [
                    #HybridSlideMap(
                    #    cache = True
                    #),
                    SlideMap(),
                    [
                        OverlayOptions(),
                        ChannelMixer(),
                        PropertyViewer(ignore_list=['_id','_index']),
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
