Visualization class
====================

The *Visualization* class is used to initialize any *fusion-tools* instance. This class 
is where you can add locally stored data to your visualization session as well as any 
cloud data by specifying different types of *TileServer*s. For local slides, you have 
to pre-specify either the loaded annotations (preferrably GeoJSON format) or the path 
to the annotation file that can be read in *fusion-tools*. 

You can also specify the layout and combinations of components to use in your dashboard at this point 
using the following hierarchy: Rows-->Columns-->Tabs

.. code-block:: python

    # This layout consists of one row of one component:
    example_row_layout = [
        SlideMap()
    ]

    # This layout consists of one row with two columns:
    example_col_layout = [
        [
            SlideMap(),
            OverlayOptions()
        ]
    ]

    # This layout consists of one row and two columns where the second column 
    # contains two tabs:
    example_layout = [
        [
            SlideMap(),
            [
                OverlayOptions(),
                PropertyViewer()
            ]
        ]
    ]

    # This layout consists of two rows with the same components but inverted in order 
    example_layout = [
        [
            SlideMap(),
            [
                OverlayOptions(),
                PropertyViewer()
            ]
        ],
        [
            [
                OverlayOptions(),
                PropertyViewer()
            ],
            SlideMap()
        ]
    ]

    # And so on.......

Alternatively, you can also define multiple pages with content by specifying a dictionary of page names 
with different page layouts.

.. code-block:: python

    example_page_layout = {
        "page 1": [
            SlideMap()
        ],
        "page 2": [
            [
                SlideMap(),
                [
                    OverlayOptions(),
                    PropertyViewer()
                ]
            ]
        ]
    }

By default this will create a page selector in the *Navbar* at the top of the application, or you can change the url to access 
different pages. (e.g.: access "page 1" by going to "{host}:{port}/app/page-1" and "page 2" by going to "{host}:{port}/app/page-2")

.. automodule:: fusion_tools.visualization
   :members:
   :undoc-members:
   :show-inheritance:

The Visualization Session
-------------------------

The "Visualization Session" refers to all of the information that is currently used by 
interactive components. This includes:

1. Current user details (if any DSA components or *TileServer*s are in use)
2. Local slides (if any *LocalTileServer*s are in use)
3. Current slides (combination of local slides + cloud slides selected from *DatasetBuilder*)

By default, objects that inherit from the *Tool* class do not need to update 
when the session data is updated. However, *DSATool* sub-classes do need to update 
due to changing "current_user" information affecting accessibility of certain 
collections/user folders.

In custom components, you can change this property by setting "session_update" to either 
*True* or *False*.


fusion\_tools.visualization module
------------------------------------

.. automodule:: fusion_tools.visualization
   :members:
   :undoc-members:
   :show-inheritance:
