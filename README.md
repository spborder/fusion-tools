# fusion-tools
Some utilities, accession, and visualization tools for data derived from FUSION (Functional Unit State Identification in WSIs).


## Installation
```bash
$ pip install fusion-tools
```

## Usage

`fusion-tools` is intended to bring some of the functionality found in FUSION to developers working with whole slide images (WSIs) stored locally. 

One such example would be the LocalTileServer and SlideMap class:
<div align="center">
    <img src="docs/images/local-slide-viewer.PNG">
</div>

```python
from fusion_tools import Visualization
from fusion_tools.tileserver import LocalTileServer
from fusion_tools.components import SlideMap

import threading

path_to_slide = '/path/to/wsi.svs'

tile_server_port = '8050'
tile_server = LocalTileServer(
    local_image_path = path_to_slide
)

new_thread = threading.Thread(target = tile_server.start, name = 'tile-server', args = [tile_server_port])
new_thread.daemon = True
new_thread.start()

vis_session = Visualization(
    components = [
        [
            SlideMap(
                tile_server = tile_server,
                annotations = None
            )
        ]
    ]
)

vis_session.start()

```

The `Visualization` class lets users construct custom layouts of different tools by passing a list containing rows, columns, and tabs. (e.g. [ [column in row 1], [ [ tab 1 in column 2 in row 1, tab 2 in column 2 in row 1] ], [ [ column 1 in row 2 ] ] ] )

<div align="center">
    <img src="docs/images/slide-annotations-layout.PNG">
</div>


```python

import threading
from fusion_tools import Visualization
from fusion_tools.tileserver import LocalTileServer
from fusion_tools.components import SlideMap, OverlayOptions, PropertyViewer
from fusion_tools.utils.shapes import load_aperio


path_to_slide = '/path/to/wsi.svs'
path_to_annotations = '/path/to/aperio_annotations.xml'

annotations = load_aperio(path_to_annotations)

tile_server_port = '8050'
tile_server = LocalTileServer(
    local_image_path = path_to_slide
)

# Starting LocalTileServer
new_thread = threading.Thread(target = tile_server.start, name = 'local_tile_server', args = [tile_server_port])
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

```

You can also access remote tile servers (either through `DSATileServer` or `CustomTileServer`) as well as annotations stored on a [Digital Slide Archive](https://digitalslidearchive.github.io/digital_slide_archive/) instance.

<div align="center">
    <img src="docs/images/remote-slide-annotations.PNG">
</div>


```python

from fusion_tools import Visualization, DSAHandler
from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import SlideMap

# Grabbing first item from demo DSA instance
base_url = 'https://demo.kitware.com/histomicstk/api/v1'
item_id = '5bbdeed1e629140048d01bcb'

# Starting visualization session
tile_server = DSATileServer(
    api_url = base_url,
    item_id = item_id
)

# Starting the DSAHandler to grab information:
dsa_handler = DSAHandler(
    girderApiUrl = base_url
)

# Checking how many annotations this item has:
#print('This item has the following annotations: ')
#print(dsa_handler.query_annotation_count(item=item_id).to_dict('records'))

annotations = dsa_handler.get_annotations(
    item = item_id
)

vis_session = Visualization(
    components = [
        [
            SlideMap(
                tile_server = tile_server,
                annotations = annotations
            )
        ]
    ]
)

vis_session.start()


```







## Contributing

please

## License
`fusion-tools` was created by Samuel Border. It is licensed under the terms of the Apache 2.0 License




