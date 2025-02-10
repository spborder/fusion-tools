"""Base classes for tools
"""

class Tool:
    """General class for interactive components that visualize, edit, or perform analyses on data.
    """
    def __init__(self):
        # Property referring to how the layout is updated with a change in the 
        # visualization session
        self.session_update = False
    

class MultiTool:
    """General class for a Tool which works on multiple slides at once
    """
    def __init__(self):
        # Property referring to how the layout is updated with a change in the 
        # visualization session
        self.session_update = True
    
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


class MapComponent:
    """General class for components added to SlideMap
        For more information see dash-leaflet: https://www.dash-leaflet.com/

    """
    def __init__(self):
        # Property referring to how the layout is updated with a change in the 
        # visualization session
        self.session_update = False
    


