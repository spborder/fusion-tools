"""

Testing property plotter using remote slide with rich annotation properties


"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization, DSAHandler
from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import SlideMap, OverlayOptions, PropertyViewer, PropertyPlotter


def main():

    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    item_id = '6495a4e03e6ae3107da10dc5'

    # Starting visualization session
    tile_server = DSATileServer(
        api_url = base_url,
        item_id = item_id
    )

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )


    annotations = dsa_handler.get_annotations(
        item = item_id
    )

    vis_session = Visualization(
        components = [
            [
                SlideMap(
                    tile_server = tile_server,
                    annotations = annotations
                ),
                [
                    OverlayOptions(
                        geojson_anns=annotations
                    ),
                    PropertyViewer(
                        geojson_list=annotations
                    ),
                    PropertyPlotter(
                        geojson_list=annotations
                    )
                ]
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()

