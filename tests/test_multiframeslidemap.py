"""

Testing MultiFrameSlideMap

"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization
from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.components import MultiFrameSlideMap, ChannelMixer


def main():

    # Grabbing first item from demo DSA instance
    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    item_id = '66b0d60452d091f0af6ef839'

    # Starting the DSAHandler to grab information:
    dsa_handler = DSAHandler(
        girderApiUrl = base_url
    )

    # Checking how many annotations this item has:
    #print('This item has the following annotations: ')
    #print(dsa_handler.query_annotation_count(item=item_id).to_dict('records'))

    vis_session = Visualization(
        tileservers = [dsa_handler.get_tile_server(item_id)],
        components = [
            [
                MultiFrameSlideMap(),
                ChannelMixer()
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()









