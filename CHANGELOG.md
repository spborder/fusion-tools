# Changelog

<!--next-version-placeholder-->
## v3.6.32 (08/12/2025)

- Increasing flexibility of `SlideAnnotation` components

### Features:
- Adding functionality to the editable tag for items in the `SlideAnnotation` component's schema

### Fixes:
- Updating caching so that the current slide's annotations are cached but they are cleared when moving to the next one. Enables usage of the database for annotation components without storing large amounts of memory in `dcc.Store` components

## v3.6.18+ (07/2025)

- Upgrading to Dash 3+
- Removal of dash_treeview_antd (doesn't comply with Dash 3+)
- Navigation to pyproject.toml through Poetry for dependency definitions


## v3.6.0 (06/2025)

### Features:
- `fusionDB` database object added!
    - This database helps organize local slide data, greatly increasing the scalability of locally deployed instances of *FUSION*
    - Sub-versions in 3.6 will add interaction between components and an instance of `fusionDB` to increase performance of more detailed queries
- `HybridSlideMap` and `HybridLargeSlideMap` component added!
    - These components combine `SlideMap` and `MultiFrameSlideMap` classes to allow for both single frame and multi-frame images in the same visualization session
- `WelcomePage` component added!
    - This is more of an example of how new pages can be added, this page provides some information on *fusion-tools* which can be added into a layout
- `SlideAnnotation` component added!
    - This component enables slide-level annotation with both categorical/quantitative labels per-slide as well as manual annotations. 
    - Specify annotation schema using `SlideAnnotationSchema` which can be shared with other users.
- *default_page* argument added to `Visualization` object
    - Get rid of the "Uh oh! Page / not in layout!" 404 page, single page layouts have "main" added by default to open directly onto whatever named page you want to set it to.
- `load_visium_hd` function added to `fusion_tools.utils.shapes`!
    - This function enables loading *10x VisiumHD* experiments at one resolution label (binning)
    - Automatically add extra analyses as properties to each square by passing a list of file paths and names (*include_analysis_path*, *include_analysis_names*)

### Fixes:
- Better handling of girderTokens in `DSAHandler` class, making it easier for users to access Private or access-controlled collections
- Annotation data shifted from sequential requests.get() calls to a clientside_callback using fetch API. Uses requests.get() as a backup.



## v3.4.0 (03/2025)

### Features:
- `DataExtractor` component added!
    - This component enables many different types of data extraction including properties, annotations, images, and masks from individual slides as well as session data (slide metadata and visualization session data)
- Saving sessions!
    - Using the `DataExtractor` component, you can now save your current visualization session and then upload it in the `DatasetBuilder` component to quickly reload.
    - In successive versions, more information from user interactions can be stored in this session and reloaded whenever someone wants to use a previous session.
        - Things like:
            1. Manual ROIs per-slide
            2. Marked structures per-slide
            3. Labeling sessions (`BulkLabels`)

## v3.1.0 (02/2025)

### Features:
- `LargeSlideMap` and `LargeMultiFrameSlideMap` added!
    - These components use server requests to only render the locations within the current viewport beyond a user-defined minimum zoom level. This is useful for slides with a large number of annotations which would inhibit performance to download and render all at once.

### Fixes:
- Small bug fix in `SegmentationDataset` and `ClassificationDataset` referring to non-existent property.

## v3.0.0 (01/2025)

### Features
- DSA Components added!
    - This includes `DSALogin`, `DatasetBuilder`, `DatasetUploader`, `DSAPluginRunner`, `DSAPluginProgress`, and `DSASurvey`

## v2.1.0 -> v2.5.5 (11/2024)

### Features
- Expanded feature extraction options
    - `sub_mask` option enabling extraction of regions within images to calculate features on.
- Expanded functionality for `BulkLabels` component
    - Combine multiple queries using *NOT*, *AND*, and *OR* to refine structure selection.

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

