# Changelog

<!--next-version-placeholder-->
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

