"""

Testing visualization functionality

"""

import os
import sys

import pandas as pd

from src.fusion_tools.handler import FUSIONHandler
from src.fusion_tools.visualization import FeatureViewer


def main():


    feature_path = ''
    feature_df = pd.read_csv(feature_path)

    fusion_handler = FUSIONHandler(
        girderApiUrl = os.environ.get('DSA_URL'),
        username = os.environ.get('DSA_USER'),
        password = os.environ.get('DSA_PWORD')
    )

    feature_viewer = FeatureViewer(
        feature_df = feature_df,
        item_id = '',
        mode = '',
        mode_col = '',
        fusion_handler=fusion_handler,
        viewer_title = 'Test Feature Viewer'
    )





if __name__=='__main__':
    main()


