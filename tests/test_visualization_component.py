"""
Testing new Visualization structure

"""

import os
import sys
sys.path.append('./src/')

from fusion_tools import Visualization
from fusion_tools.components import SlideMap, OverlayOptions, PropertyViewer
from fusion_tools.tileserver import DSATileServer
from fusion_tools.handler import DSAHandler


def main():
 
    # Test 1) Visualization with slides and annotations as input arguments that is then 
    # extended to all components where that is required  
    # Test 2) TileServers with multiple slides, switching between slides and 
    # their respective annotations. (DSA and Local)
    # Test 3) Reconfigure "start" function to allow for expanded app_options and 
    # servers. Try and bundle LocalTileServer.start() in here as well to run silently/verbosely

    # There should be some option for just creating a server which has images and their annotations
    # and then referencing them with something similar to the DSAHandler (LocalDataHandler?).
    # Should allow for a DSAHandler class with some list of names/item Ids.

    # Main thing is that there should be a way to establish that one set of annotations belongs to one slide

    local_slide_list = [
        'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\XY01_IU-21-015F_001.svs',
        'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\XY01_IU-21-015F.svs',
    ]
    local_annotations_list = [
        'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\XY01_IU-21-015F_001.xml',
        None,
    ]

    dsa_handler = DSAHandler(
        girderApiUrl = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    )

    dsa_items_list = [
        '64f545082d82d04be3e39ee1',
        '64f54be52d82d04be3e39f65'
    ]

    dsa_tileservers = [dsa_handler.get_tile_server(i) for i in dsa_items_list]
    
    vis_sess = Visualization(
        local_slides = local_slide_list,
        local_annotations = local_annotations_list,
        tileservers = dsa_tileservers,
        components = [
            [
                SlideMap(),
                SlideMap()
            ],
        ]
    )

    vis_sess.start()



if __name__=='__main__':
    main()

