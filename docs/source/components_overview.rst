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
   

Digital Slide Archive (DSA) Integrated Components
-------------------------------------------------

DSALoginComponent
^^^^^^^^^^^^^^^^^

This component controls logging-in and authentication of users to a connected DSA instance.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/9fY7JI6ESwA?si=WLIYr5fandIDwauc" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>


.. autoclass:: fusion_tools.handler.login::DSALoginComponent
   :members:


DSASession
^^^^^^^^^^

This component controls saving visualization sessions and saving them as files to an attached DSA instance.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/iL24kA1iMV4?si=BDTeGQWlc2h6deJG" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.handler.save_session::DSASession
   :members:


DatasetBuilder
^^^^^^^^^^^^^^

This component allows for selection of different slides in various collections/folders in an attached DSA instance as well as locally-hosted slides.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/BqXS19wbyxc?si=IlhcPq1fYTm_9qLa" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.handler.dataset_builder::DatasetBuilder
   :members:



DSAUploader
^^^^^^^^^^^

This component controls formatted uploads to an attached DSA instance.

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube.com/embed/_wkRoArpV9k?si=AfQGQhK-sPlxKls7" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

.. autoclass:: fusion_tools.handler.dataset_uploader::DSAUploader
   :members:


DSAPluginGroup
^^^^^^^^^^^^^^

This component holds multiple DSA plugin input components as well as a button for "running" that plugin based on input values.

.. autoclass:: fusion_tools.handler.plugin::DSAPluginGroup
   :members:


DSAPluginProgress
^^^^^^^^^^^^^^^^^

This component lets users monitor the progress of their running/completed plugins in DSA and cancel individual jobs.

.. autoclass:: fusion_tools.handler.plugin::DSAPluginProgress
   :members:



DSAPluginRunner
^^^^^^^^^^^^^^^

This component lets users select plugins and specify their inputs prior to hitting "run".

.. autoclass:: fusion_tools.handler.plugin::DSAPluginRunner
   :members:


DSAResourceSelector
^^^^^^^^^^^^^^^^^^^

This is a general component embedded in other DSA components that enables parsing through folders/collections/user folders.

.. autoclass:: fusion_tools.handler.resource_selector::DSAResourceSelector
   :members:

Designing Custom Components
---------------------------

Custom components can be integrated into *fusion-tools* layouts by defining *DashBlueprint* objects inside a class which inherits from *Tool* which can be imported from *fusion_tools*.

CustomFunction
^^^^^^^^^^^^^^

This component lets users define a *lambda* function which can be applied to either individual structures in the current slide, automatically 
extracting image, mask, etc.









