"""Defining UploadTypes which are accepted in FUSION
"""

from fusion_tools.handler.dataset_uploader import DSAUploadType

def get_upload_types(args):

    # Basic Type:
    basic_type = DSAUploadType(
        name = "Histology Image",
        input_files = [],
        processing_plugins=[],
        required_metadata=[]
    )

    # 10x Types:
    visium_type = DSAUploadType(
        name = '10x Visium',
        input_files = [],
        processing_plugins=[],
        required_metadata=[]
    )

    xenium_type = DSAUploadType(
        name = '10x Xenium',
        input_files = [],
        processing_plugins=[],
        required_metadata=[]
    )

    hd_type = DSAUploadType(
        name = "10x Visium HD",
        input_files = [],
        processing_plugins=[],
        required_metadata=[]
    )

    # MxIF/CODEX
    mxif_type = DSAUploadType(
        name = "MxIF / CODEX",
        input_files = [],
        processing_plugins = [],
        required_metadata = []
    )

    # HuBMAP Processed Dataset
    hubmap_type = DSAUploadType(
        name = "HuBMAP Processed",
        input_files = [],
        processing_plugins= [],
        required_metadata=[]
    )

    return [
        basic_type,
        visium_type,
        xenium_type,
        hd_type,
        mxif_type,
        hubmap_type
    ]

