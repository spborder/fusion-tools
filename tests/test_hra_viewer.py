"""Testing HRAViewer component
"""

import os
import sys
sys.path.append('./src/')
from fusion_tools import Visualization
from fusion_tools.components import HRAViewer


def main():

    vis_session = Visualization(
        components = [
            [
                HRAViewer()
            ]
        ]
    )

    vis_session.start()


if __name__=='__main__':
    main()













