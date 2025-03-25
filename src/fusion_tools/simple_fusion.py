"""Quickly generate a simple visualization layout
"""
from fusion_tools.visualization import Visualization
from fusion_tools.components import SlideMap, MultiFrameSlideMap, OverlayOptions, ChannelMixer
from typing_extensions import Union

def get_vis(slide_paths: Union[list,str], annotations: Union[list,str,dict,None]=None, multi_frame: bool = False, port:int=8050, in_jupyter:bool = False):

    if not multi_frame:
        vis_obj = Visualization(
            local_slides=slide_paths,
            local_annotations=annotations,
            components = [
                [
                    SlideMap(),
                    OverlayOptions()
                ]
            ],
            app_options={
                'port': port,
                'jupyter': in_jupyter
            }
        )
    else:
        vis_obj = Visualization(
            local_slides=slide_paths,
            local_annotations=annotations,
            components = [
                [
                    MultiFrameSlideMap(),
                    [
                        ChannelMixer(),
                        OverlayOptions(),   
                    ]
                ]
            ],
            app_options={
                'port': port,
                'jupyter': in_jupyter
            }
        )


    return vis_obj
