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

    test_public_slide = Slide(
        image_filepath = './tests/test_images/histology_image.svs',
        annotations = './tests/test_images/histology_annotations.json',
        public = True
    )

    # Private slide only has annotations in "Layer 1"
    private_anns = load_histomics('./tests/test_images/histology_annotations.json')[0]
    private_anns['properties']['_id'] = '1234'*6

    test_private_slide = Slide(
        image_filepath = './tests/test_images/histology_image.svs',
        annotations = private_anns,
        public = False
    )

    vis = Visualization(
        local_slides = [test_public_slide,test_private_slide],
        components = [
            [
                SlideMap(),
                [
                    OverlayOptions(),
                    PropertyPlotter()
                ]
            ]
        ]
    )

    vis.start()


if __name__=='__main__':
    main()
