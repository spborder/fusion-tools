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
   :undoc-members:
   :show-inheritance:

Interactive *DSA* components
---------------------------------

.. automodule:: fusion_tools.handler.login
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: fusion_tools.handler.survey
    :members:
    :undoc-members:
    :show-inheritance:

.. automodule:: fusion_tools.handler.plugin
    :members:
    :undoc-members:
    :show-inheritance:

.. automodule:: fusion_tools.handler.dataset_builder
    :members:
    :undoc-members:
    :show-inheritance:

.. automodule:: fusion_tools.handler.dataset_uploader
    :members:
    :undoc-members:
    :show-inheritance:
    