"""
Test simple
"""
import sys
sys.path.append('./src/')
from fusion_tools.visualization import Visualization
from fusion_tools.components import SlideMap, HybridSlideMap, OverlayOptions, PropertyPlotter, PropertyViewer

from fusion_tools.tileserver import Slide
from fusion_tools.utils.shapes import load_histomics

def main():
    #test_slide_path = '/home/sam/Desktop/Example Data/HuBMAP Portal/Visium/visium_histology_hires_pyramid.ome.tif'
    #test_ann_path = '/home/sam/Desktop/Example Data/HuBMAP Portal/Visium/secondary_analysis.h5ad'

    test_public_slide = Slide(
        image_filepath = './tests/test_images/histology_image.svs',
        annotations = './tests/test_images/histology_annotations.json',
        public = True
    )

    private_anns = load_histomics('./tests/test_images/histology_annotations.json')[0]
    private_anns['properties']['_id'] = '1234'*6

    test_private_slide = Slide(
        image_filepath = './tests/test_images/histology_image.svs',
        annotations = private_anns,
        public = False
    )

    vis = Visualization(
        #local_slides = ['./tests/test_images/histology_image.svs'],
        #local_annotations = ['./tests/test_images/histology_annotations.json'],
        local_slides = [test_public_slide,test_private_slide],
        components = [
            [
                SlideMap(),
            ]
        ],
        #app_options = {
        #    'host': '0.0.0.0'
        #}
    )

    vis.start()


if __name__=='__main__':
    main()
