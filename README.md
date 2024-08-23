# fusion-tools
Some utilities, accession, and visualization tools for data derived from FUSION (Functional Unit State Identification in WSIs).


## Installation
```bash
$ pip install fusion-tools
```

## Usage

`fusion-tools` is intended to bring some of the functionality found in FUSION to developers working with whole slide images (WSIs) stored locally. 

One such example would be the TileServer and LocalSlideViewer class:
<div align="center">
    <img src="docs/images/local-slide-viewer.PNG">
</div>

```python
from fusion_tools.visualization import TileServer, LocalSlideViewer

import threading

path_to_slide = '/path/to/wsi.svs'

tile_server_port = '8050'
tile_server = TileServer(
    local_image_path = path_to_slide
)

new_thread = threading.Thread(target = tile_server.start, name = 'tile-server', args = [tile_server_port])
new_thread.daemon = True
new_thread.start()

slide_viewer = LocalSlideViewer(
    tile_server_port = tile_server_port,
    app_port = '8080'
)

```

## Contributing

please

## License
`fusion-tools` was created by Samuel Border. It is licensed under the terms of the Apache 2.0 License










