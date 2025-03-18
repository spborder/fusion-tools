""""
Testing property plotter using remote slide with rich annotation properties
"""
import sys
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import LargeSlideMap,SlideMap,OverlayOptions, PropertyPlotter, HRAViewer

def main():

    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    item_id = '67ae1826fcdeba1e292f7057'

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )
    
    vis_session = Visualization(
        tileservers = [dsa_handler.get_tile_server(item_id)],
        components = [
            [
                SlideMap(),
                [
                    OverlayOptions(),
                    PropertyPlotter(),
                    HRAViewer()
                ]
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()

