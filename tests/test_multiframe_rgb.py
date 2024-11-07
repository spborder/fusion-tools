"""

Testing multi-frame RGB .ome.tif formatted image


"""
import sys
sys.path.append('./src/')
import anndata as ad


from fusion_tools.utils.shapes import load_visium
from fusion_tools import Visualization
from fusion_tools.components import MultiFrameSlideMap,SlideMap, OverlayOptions, PropertyViewer, PropertyPlotter


def main():

    slide_paths = ['C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\non_kidney\\visium_histology_hires_pyramid.ome.tif']
    annotation_paths = ['C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\non_kidney\\secondary_analysis (1).h5ad']

    processed_anns = load_visium(annotation_paths[0],include_obs=['leiden','n_genes','n_counts','Tissue Coverage Fraction'])

    vis_session = Visualization(
        local_slides = slide_paths,
        local_annotations = [processed_anns],
        components = [
            [
                SlideMap(),
                [
                    OverlayOptions(),
                    PropertyViewer(),
                    PropertyPlotter()
                ]
            ]
        ]
    )

    vis_session.start()



if __name__=='__main__':
    main()
