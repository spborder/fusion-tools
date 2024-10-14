"""
Prepping training data interactively: 

    - Load SlideMap and OverlayOptions
    - Filter structures according to desired characteristics (Main_Cell_Types --> IMM ==1 in this case)
    - Export annotations (one will be all cells, the other will be all cells that are immune cells)

"""


import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization, DSAHandler
from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import SlideMap,OverlayOptions, PropertyViewer, PropertyPlotter, HRAViewer
from fusion_tools.utils.shapes import load_histomics


import pandas as pd

def main():

    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    item_id = '66a161a33ea2cd3894c85de3'

    # Starting visualization session
    tile_server = DSATileServer(
        api_url = base_url,
        item_id = item_id
    )

    annotations = load_histomics('C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\Xenium_Data\\Cells.json')

    vis_session = Visualization(
        components = [
            [
                SlideMap(
                    tile_server = tile_server,
                    annotations = annotations
                ),
                [
                    OverlayOptions(
                        geojson_anns=annotations,
                        ignore_list = ['Cell Id']
                    ),
                ]
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()

