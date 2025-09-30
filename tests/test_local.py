"""
Test simple
"""
import sys
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.components import SlideMap, HybridSlideMap, OverlayOptions, PropertyPlotter, PropertyViewer

def main():
    #test_slide_path = '/home/sam/Desktop/Example Data/HuBMAP Portal/Visium/visium_histology_hires_pyramid.ome.tif'
    #test_ann_path = '/home/sam/Desktop/Example Data/HuBMAP Portal/Visium/secondary_analysis.h5ad'

    vis = Visualization(
        local_slides = ['./tests/test_images/histology_image.svs'],
        local_annotations = ['./tests/test_images/histology_annotations.json'],
        components = [
            [
                SlideMap(),
            ]
        ],
        app_options = {
            'host': '192.168.86.24'
        }
    )

    vis.start()


if __name__=='__main__':
    main()
