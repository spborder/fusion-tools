# Changelog

<!--next-version-placeholder-->


## v2.1.0 (11/07/2024)

### Features
- Added support for multi-frame RGB images (.ome.tif) (rendering as RGB channels by default)
- Adding support for arbitrary levels of nesting in `PropertyPlotter`

### Fix
- Bug fixes for v2.0 layout in components


## v2.0.0 (11/04/2024)

### Features
- Built-in `LocalTileServer` starting in `Visualization` classes
- Incorporating multiple slides and their annotations into the `SlideMap` component
- "Linkage" added for duplicate components in the same main layout. Allows for comparison of multiple slides at the same time and integrating with other components
- More flexibility added to `.utils.shapes.spatially_aggregate` allowing users to specify whether they want to separate out properties aggregated from different structures and whether they would like a summary for each aggregated property or just the mean. (see ./tests/test_spatial_aggregation.py)

## v1.1.0 (10/23/2024)

### Fix:
- Fixed a bug in Jupyter mode so that the actual port specified in __init__ is the one that is used (previously was hardcoded for 8050).
- Removed "port" argument in `LocalTileServer.start()`, conflicts with "port" argument in __init__

### Features:
- Adding `load_visium` function to `.utils.shapes`. This enables loading an *.h5ad* formatted *10x Visium* dataset. Barcodes for each spot are added by default but users can also pass a list of *var_names* to include in per-spot properties.
- Users can add aligned object props (from `.utils.shapes.align_object_props`) to a sub-property in the annotation

## v1.0.0 (10/21/2024)

### Fix:
- Debugging some items in `ClassificationDataset` and `SegmentationDataset`

### Features:
- Version now starts with 1! 😎


## v0.0.24 (10/16/2024)

### Fix:
- Updating labels returned by `ClassificationDataset` (returning 0.0 for structures that do not include the "label_property")

## v0.0.23 (10/10/2024)

### Features:
- `dataset` module added
    - Implements `SegmentationDataset` and `ClassificationDataset` which are PyTorch-formatted Dataset classes which allow for iteration of annotated structures in a set of slides. `SegmentationDataset` returns images and masks while `ClassificationDataset` returns images and labels (stored in GeoJSON properties). PyTorch installation is not required with this implementation, however, to integrate these datasets into a ML-pipeline one of the image/target/label transforms has to convert the data to a Tensor.

## v0.0.22 (10/08/2024)

### Features:
- FeatureExtraction functionality added with parallelization (non-interactive)


## v0.0.12->v0.0.21 (10/07/2024)

### Fix:
- External testing performed, restructuring of package and setup in response to errors encountered

### Features:
- Support for Jupyter Notebook visualization (excluding JupyterHub hosted over HTTPS)

## v0.0.11 (10/04/2024)

### Fix:
- Fixed adding/deleting manual ROIs (keeping _id property)

### Features:
- Create new annotation layers based off of selected filters in `OverlayOptions`
- Apply labels to properties in `BulkLabels`
- Adding `process_filter_queries` to `shapes` for external access. Allows users to pass a list of spatial and property queries to a GeoJSON and returns a unified FeatureCollection
- Select different colormaps in `OverlayOptions` under "Advanced Overlay Options". This includes all colormaps detailed [here](https://colorbrewer2.org/#type=sequential&scheme=BuGn&n=3)

## v0.0.10 (09/27/2024)

### Fix:
- Fixing callbacks initialization for MultiFrameSlideMap
- Fixing dropdown menus for PropertyViewer with >2 levels of nested properties (now works with arbitrary levels)

### Features
- Switching from in-memory GeoJSON to geobuf for added efficiency with >10k structures
- Manual ROIs now able to be used individually as opposed to as members of one single FeatureCollection

## v0.0.9 (09/24/2024)

### Fix
- Fixing spatial aggregation function for nested properties

### Features
- Adding segmentation, annotation, and bulk labeling functionality


## v0.0.8 (09/18/2024)

### Fix
- Pre-initializing pattern-matching indices for MultiFrameSlideMap base and tile layers
- Fixing dimensions of HRAViewer when added to a column

### Features
- Update markers on the map by selecting data points in a sub-plot in PropertyPlotter
- Now accepting an arbitrary number of levels in nested sub-properties (use the property_depth argument to adjust +/- 4 levels)
- SlideImageOverlay components added alongside GeoJSON annotations. Allows users to overlay images at specific locations or move that image around to find the aligned coordinates.

## v0.0.7 (09/11/2024)

### Features
- Added functionality for selected points in PropertyPlotter
- Added HRAViewer ASCT+B table views for all organs in 7th release

## v0.0.6 (09/09/2024)

### Fix
- Some fixes for PropertyPlotter

### Features
- Adding MultiFrameSlideMap and ChannelMixer components for visualization of multi-frame images
- Added functionality in PropertyPlotter for selected data

## v0.0.5 (08/29/2024)

### Fix
- Fixing GeoJSON coordinates shape from load_aperio

### Features
- Adding more information to feature popups with sub-items for dictionary-type feature data
- Tested DSATileServer 

## v0.0.4 (08/29/2024)

### Features
- Addition of OverlayOptions (overlay color, transparency, line color, and structure filtering), PropertyViewer (regional property visualization) tools
- Updated package structure
- Adding spatial aggregation for manual ROIs drawn on SlideMap components


## v0.0.3 (08/23/2024)

### Fix
- Adding CHANGELOG.md and other documentation


## v0.0.2 (08/23/2024)

### Fix
- Updating folder structure and adding documentation


## v0.0.1 (08/23/2024)

- First release of `fusion-tools`, includes TileServer, LocalSlideViewer, FUSIONHandler, and Accessor for local and cloud-hosted data visualization and access

