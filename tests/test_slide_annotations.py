"""

Testing Visualization session with overlaid annotations derived from various file formats


"""

import os
import sys
import threading
sys.path.append('./src/')
from fusion_tools import Visualization
from fusion_tools.tileserver import LocalTileServer
from fusion_tools.components import SlideMap, OverlayOptions, PropertyViewer
from fusion_tools.utils.shapes import load_aperio, load_geojson, export_annotations


def main():
    print(os.getcwd())
    path_to_slide = '.\\tests\\test_images\\histology_image.svs'
    path_to_annotations = '.\\tests\\test_images\\histology_annotations.xml'

    annotations = load_aperio(path_to_annotations)
    print(f'Loaded {len(annotations)} annotation layers')


    export_format = 'histomics'
    save_path = '.\\tests\\test_images\\histology_annotations.json'

    if not os.path.exists(save_path):
        export_annotations(
            ann_geojson = annotations,
            format = export_format,
            save_path = '.\\tests\\test_images\\histology_annotations.json'
        )
        print('Exported annotations to geojson format')

    # Starting visualization session
    tile_server = LocalTileServer(
        local_image_path=path_to_slide
    )
    new_thread = threading.Thread(target = tile_server.start, name = 'local_tile_server', args = ['8050'])
    new_thread.daemon = True
    new_thread.start()

    vis_session = Visualization(
        components = [
            [
                SlideMap(
                    tile_server = tile_server,
                    annotations = annotations
                ),
                [
                    OverlayOptions(
                        geojson_anns = annotations
                    ),
                    PropertyViewer(
                        geojson_list = annotations
                    )
                ]
            ]
        ]
    )

    vis_session.start()









if __name__=='__main__':
    main()









