"""Testing welcome page layout
"""
import sys

sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.fusion.welcome import WelcomePage


vis = Visualization(
    components = {
        'Welcome': [WelcomePage()]
    },
    app_options = {
        'port': 8050
    }
)

vis.start()


