*Digital Slide Archive (DSA)*
================================

`Digital Slide Archive (DSA) <https://github.com/DigitalSlideArchive/digital_slide_archive>`_ is an open-source 
resource for organization of large whole slide images (WSIs) as well as providing an interface (`HistomicsUI <https://github.com/DigitalSlideArchive/HistomicsUI>`_)
for image annotation and running computational analyses. It provides a RESTful API which enables programmatic 
access of data that is stored on a given *DSA* instance as well as handling POST, GET, PUT, etc. requests.

*fusion-tools* provides several components which integrate with a running *DSA* instance to provide alternative 
interfaces for visualizing data, stored within image annotations, in conjunction with Histology images. Furthermore,
*fusion-tools* provides a format for defining upload templates (*UploadType*s) that allow adminstrators to pre-specify 
files, metadata, and processing steps used for a specific type of data. While it does not implement every possible process 
that is implemented in *DSA* (for example, copying/moving items, modifying user details, and several others), *fusion-tools* 
may be a valuable resource for developers that use *DSA* to design custom visualization and interaction pages (in Python) 
to share with collaborators as well as integrating plugins with specific sets of inputs to user-interactions.

fusion\_tools.handler module
---------------------------------

.. automodule:: fusion_tools.handler.dsa_handler
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

