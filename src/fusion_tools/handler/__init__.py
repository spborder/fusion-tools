from fusion_tools.components import Tool

class Handler:
    pass

class DSATool(Tool):
    """A sub-class of Tool specific to DSA components. 
    The only difference is that these components always update relative to the session data.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """
    def __init__(self):

        super().__init__()
        self.session_update = True


