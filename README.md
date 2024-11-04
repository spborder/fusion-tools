# *fusion-tools*
Modular visualization and analysis dashboard creation for high-resolution microscopy images.


## Installation
```bash
$ pip install fusion-tools
```

## Usage

`fusion-tools` is intended to bring some of the functionality found in FUSION to developers working with whole slide images (WSIs) stored locally. 

One such example would be the `Visualization` and `SlideMap` class:
<div align="center">
    <img src="docs/images/local-slide-viewer.PNG">
</div>

```python
from fusion_tools import Visualization
from fusion_tools.tileserver import LocalTileServer
from fusion_tools.components import SlideMap

vis_session = Visualization(
    local_slides = [path_to_slide]
    components = [
        [
            SlideMap()
        ]
    ]
)

vis_session.start()

```

The `Visualization` class lets users construct custom layouts of different tools by passing a list containing rows, columns, and tabs. (e.g. [ [column in row 1], [ [ tab 1 in column 2 in row 1, tab 2 in column 2 in row 1] ], [ [ column 1 in row 2 ] ] ] ).

By passing a list of paths to locally-stored whole slide images (WSIs), `fusion-tools` automatically generates a `LocalTileServer` which is bundled in with the `Visualization` session to allow for high-resolution image viewing.

<div align="center">
    <img src="docs/images/slide-annotations-layout.PNG">
</div>


```python

from fusion_tools import Visualization
from fusion_tools.components import SlideMap, OverlayOptions, PropertyViewer
from fusion_tools.utils.shapes import load_aperio


path_to_slide = '/path/to/wsi.svs'
path_to_annotations = '/path/to/aperio_annotations.xml'

annotations = load_aperio(path_to_annotations)

vis_session = Visualization(
    local_slides = [path_to_slide],
    local_annotations = [annotations],
    components = [
        [
            SlideMap(),
            [
                OverlayOptions(),
                PropertyViewer()
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

# Starting the DSAHandler to grab information:
dsa_handler = DSAHandler(
    girderApiUrl = base_url
)

# Checking how many annotations this item has:
#print('This item has the following annotations: ')
#print(dsa_handler.query_annotation_count(item=item_id).to_dict('records'))

vis_session = Visualization(
    tileservers = [dsa_handler.get_tile_server(item_id)],
    components = [
        [
            SlideMap()
        ]
    ]
)

vis_session.start()


```

You can also use some of `segmentation` components for adding labels and annotations to structures in the slide.

### Creating annotations on top of structures
<div align="center">
    <img src="docs/images/feature-annotation.PNG">
</div>

### Applying labels to many structures at the same time
<div align="center">
    <img src="docs/images/bulk-labels.PNG">
</div>

```python

from fusion_tools import Visualization, DSAHandler
from fusion_tools.tileserver import DSATileServer
from fusion_tools.components import SlideMap, FeatureAnnotation, BulkLabels

# Grabbing first item from demo DSA instance
base_url = 'https://demo.kitware.com/histomicstk/api/v1'
item_id = '5bbdeed1e629140048d01bcb'

# Starting the DSAHandler to grab information:
dsa_handler = DSAHandler(
    girderApiUrl = base_url
)

# Checking how many annotations this item has:
#print('This item has the following annotations: ')
#print(dsa_handler.query_annotation_count(item=item_id).to_dict('records'))

vis_session = Visualization(
    tileservers = [dsa_handler.get_tile_server(item_id)],
    components = [
        [
            SlideMap(),
            [
                FeatureAnnotation(
                    storage_path = os.getcwd()+'\\tests\\Test_Annotations\\',
                    labels_format = 'json',
                    annotations_format = 'rgb'
                ),
                BulkLabels()
            ]
        ]
    ]
)

vis_session.start()


```



## Contributing

Open to contributions. Feel free to submit a PR or post feature requests in [Issues](https://github.com/spborder/fusion-tools/issues)

### Open Projects:
- Automated segmentation workflow for locally stored images (active-learning, SAM, etc.)
- Monitoring long-running model training/other external processes
- Import anndata spatial --omics dataset (UPDATE (v2.0.0): see `utils.shapes.load_visium` for example loading *10x Visium* dataset)


## License
`fusion-tools` was created by Samuel Border. It is licensed under the terms of the Apache 2.0 License

