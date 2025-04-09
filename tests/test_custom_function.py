"""Testing CustomFunction component
"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import SlideMap, CustomFunction

from shapely.geometry import shape

def buffer_shapes(feature, buffer_radius):

    feature_shape = shape(feature['geometry'])
    buffered_shape = feature_shape.buffer(buffer_radius)

    return buffered_shape.__geo_interface__


def main():

    # Grabbing first item from demo DSA instance
    #base_url = 'https://demo.kitware.com/histomicstk/api/v1'
    #item_id = ['5bbdeed1e629140048d01bcb','58b480ba92ca9a000b08c89d']
    base_url = os.environ.get('DSA_URL')

    item_id = [
        '6495a4e03e6ae3107da10dc5',
        '6495a4df3e6ae3107da10dc2'
    ] 


    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )
    
    vis_session = Visualization(
        tileservers=[dsa_handler.get_tile_server(i) for i in item_id],
        components = [
            [
                SlideMap(),
                [
                    CustomFunction(
                        component_title = 'Buffer Shapes',
                        description = 'For a given annotation, perform a buffer operation by a specified value.',
                        urls = [
                            'https://shapely.readthedocs.io/en/stable/manual.html#constructive-methods'
                        ],
                        function = lambda feature,radius: buffer_shapes(feature,radius),
                        input_spec = [
                            {
                                'type': 'Annotation',
                                'forEach': True
                            },
                            {
                                'type': 'integer',
                                'min': -10,
                                'max': 100
                            }
                        ],
                        output_spec = [
                            {
                                'type': 'Annotation'
                            }
                        ]
                    )
                ]
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()


