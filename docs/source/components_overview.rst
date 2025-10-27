Components Overview
=======================

Here you'll find documentation for each of the individual components and an overview on their usage. 

Map Components
---------------

These components control how a slide and associated annotations are viewed.

Slide Map
^^^^^^^^^

This component is used for visualization of high resolution images and their associated annotations.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/UJ2KDGSDeSs?si=8Xf1yWvkFXpQpypS" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.maps::SlideMap
   :members:



MultiFrame Slide Map
^^^^^^^^^^^^^^^^^^^^

This component is used for a subset of images containing multiple "frames" (using large-image convention) or channels. Different from the default SlideMap component,
the MultiFrameSlideMap component allows users to view different channels separately from the same LayersControl component in the upper right-hand side of the map.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/kVdPVM-4KlA?si=YxN-r-OtAR7GPEXc" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.maps::MultiFrameSlideMap
   :members:



Overlay Options
^^^^^^^^^^^^^^^

This component is used for controlling the color that is applied to annotation overlays as well as controlling which structures are filtered for visualization purposes. 

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/4ej-5Nca1IA?si=3peYI6hfnUp_7r7G" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.tools::OverlayOptions
   :members:



Channel Mixer
^^^^^^^^^^^^^

This component is used to control artificial color that is applied to grayscale image channels. 

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/neDJrCVz9-E?si=P7obUYMKsqeOZUAm" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.maps::ChannelMixer
   :members:


Slide Image Overlay
^^^^^^^^^^^^^^^^^^^

This component allows for overlaying images on another image and moving it around.

.. raw:: html
   
   <iframe width="560" height="315" src="https://www.youtube.com/embed/8F7HcBhLvh0?si=tSc-Hu2YhIhyShma" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.maps::SlideImageOverlay
   :members:



Plotting Components
-------------------

PropertyViewer
^^^^^^^^^^^^^^

This plotting component allows for visualization of different structure properties within the current viewport of the current slide.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/pGaQhTTW9fs?si=jOzl1ip1pOMRnEUW" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.tools::PropertyViewer
   :members:



PropertyPlotter
^^^^^^^^^^^^^^^

This plotting component allows for visualization of all structure properties in the current slide.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/W7FrlIxUvPU?si=xzwGX-QK-KIToBoO" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.tools::PropertyPlotter
   :members:


GlobalPropertyPlotter
^^^^^^^^^^^^^^^^^^^^^

This plotting component allows for visualization of structure properties from multiple different slides in the "current" portion of the visualization session.




Human Reference Atlas Components
--------------------------------

This component allows for selection of different organs and viewing their Anatomical Structures, Cell Types, and Biomarkers (ASCT+B) tables as well as the FTU Explorer embedded component.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/YT3XJ-8yeBI?si=pKJQ60tGACah2VJH" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>


.. autoclass:: fusion_tools.components.tools::HRAViewer
   :members:


Annotation Components
---------------------

FeatureAnnotation
^^^^^^^^^^^^^^^^^

This component lets users annotate individual structures including either text/numeric labels or hand-drawn annotations.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/EyUyVU1PQ0Q?si=YHVHKIUu1pcfkWlT" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.segmentation::FeatureAnnotation
   :members:



BulkLabels
^^^^^^^^^^

This component lets users apply the same label to multiple structures in a slide based on a combination of spatial and property queries.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/IxYa5O6ZjBo?si=WzWCST6QvSKFG6Ow" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.components.segmentation::BulkLabels
   :members:


SlideAnnotation
^^^^^^^^^^^^^^^

This component lets users label individual slides based on qualitative criteria as well as provide GeoJSON-formatted annotations of regions of slides 
that contribute to that label.


Download Components
-------------------

DataExtractor
^^^^^^^^^^^^^

This component enables extracting different types of data from the current slide as well as session-related information useful for revisiting prior analyses.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/jlLkwKMvHiQ?si=0KkiGyhn0jH_BTIq" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>


.. autoclass:: fusion_tools.components.tools::DataExtractor
   :members:
   



Designing Custom Components
---------------------------

Custom components can be integrated into *fusion-tools* layouts by defining *DashBlueprint* objects inside a class which inherits from *Tool* which can be imported from *fusion_tools.components.base*.

CustomFunction
^^^^^^^^^^^^^^

This component enables simplified deployment of some Python function which incorporates data from a `SlideMap`. 
For example, if you had a function that took as input an image and a mask of a structure on a slide, you would 
first specify a `FUSIONFunction` like so:

.. code-block:: python

   from fusion_tools.components import FUSIONFunction

   def mask_image(image,mask):
      # Function masks out regions of the image outside of the mask
      masked_image = np.multiply(image,np.repeats(mask[...,None],axis=-1,repeats=3))

      return masked_image


   example_function = FUSIONFunction(
      title = 'Example Function',
      description = 'This is an example of a function deployed through FUSION.',
      urls = [],
      function = lambda image, mask: mask_image(image,mask),
      function_type = 'structure',
      input_spec = [
         {
            'name': 'image',
            'description': 'Image of structure in SlideMap',
            'type': 'image'
         },
         {
            'name': 'mask',
            'description': 'Mask of structure in SlideMap',
            'type': 'mask'
         }
      ],
      output_spec = [
         {
            'name': 'Masked Image',
            'type': 'image',
            'description': 'This is what the masked image looks like!'
         }
      ]
   )

Available function types are structure, layer, and ROI. For each function type, "input_spec" items can have types:

- Automatically populated:
   - image, mask, annotation
- Interactive:
   - string, boolean, options, numeric, region

Now add this function to a layout like so:

.. code-block:: python

   from fusion_tools.visualization import Visualization
   from fusion_tools.components import SlideMap, CustomFunction

   vis = Visualization(
      components = [
         [
            SlideMap(),
            CustomFunction(
               title = 'Example Functions',
               description = 'Trying out a custom function',
               custom_function = [
                  example_function
               ]
            )
         ]
      ]
   )

   vis.start()

Anything added in the "input_spec" as an image, mask, or annotation is automatically populated with the image, mask, or annotation 
associated with a given structure. Other input spec types create interactive components to pass a specific type of input to the function.

Outputs of the function are then rendered in a separate component and "type" values can include image, numeric, string, or function.

"Function"-type outputs should be lambda functions that take two inputs, output (the all of the outputs from the function) and output_index 
which is only used if generating interactive components. If outputs are generated which you want to be interactive, 
add the callbacks to the "output_callbacks" argument of `FUSIONFunction` like so:

.. code-block:: python

   output_callbacks = [
      {
         'inputs': [],
         'outputs': [],
         'states': [],
         'function': lambda inputs,states: some_function(inputs,states)
      }
   ]

Where "inputs" is a list of `Input()` objects, "outputs" is a list of `Output()` objects, and "states" is a list of `State()` objects 
as in a typical *Dash* callback.

