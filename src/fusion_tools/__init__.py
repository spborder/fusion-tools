"""Base classes for tools
"""
from typing_extensions import Union

class Tool:
    """General class for interactive components that visualize, edit, or perform analyses on data.
    """
    def __init__(self):
        # Property referring to how the layout is updated with a change in the 
        # visualization session
        self.session_update = False

    def prefix_escape(self,input_id: Union[str,dict])->bool:
        """Specifying the default prefix escape for all blueprints. Basic specification is to ignore "anchor" or ids that already have a prefix

        :param input_id: Input component id either for a layout or a callback
        :type input_id: Union[str,dict]
        :return: True indicates that this id should not receive a prefix transform, False indicates that it should receive a prefix
        :rtype: bool
        """

        if type(input_id)==dict:
            if 'anchor' in input_id['type']:
                return True
            try:
                current_comp_id = int(input_id['type'][0])
                has_id = True
            except ValueError:
                has_id = False
            
            if has_id:
                return True

        elif 'anchor' in input_id:
            return True
        return False
    

class MultiTool:
    """General class for a Tool which works on multiple slides at once
    """
    def __init__(self):
        # Property referring to how the layout is updated with a change in the 
        # visualization session
        self.session_update = True

    def prefix_escape(self,input_id: Union[str,dict])->bool:
        """Specifying the default prefix escape for all blueprints. Basic specification is to ignore "anchor" or ids that already have a prefix

        :param input_id: Input component id either for a layout or a callback
        :type input_id: Union[str,dict]
        :return: True indicates that this id should not receive a prefix transform, False indicates that it should receive a prefix
        :rtype: bool
        """

        if type(input_id)==dict:
            if 'anchor' in input_id['type']:
                return True
            try:
                current_comp_id = int(input_id['type'][0])
                has_id = True
            except ValueError:
                has_id = False
            
            if has_id:
                return True

        elif 'anchor' in input_id:
            return True
        return False
    
    
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
        self.session_update = True
    
    def prefix_escape(self,input_id: Union[str,dict])->bool:
        """Specifying the default prefix escape for all blueprints. Basic specification is to ignore "anchor" or ids that already have a prefix

        :param input_id: Input component id either for a layout or a callback
        :type input_id: Union[str,dict]
        :return: True indicates that this id should not receive a prefix transform, False indicates that it should receive a prefix
        :rtype: bool
        """

        if type(input_id)==dict:
            if 'anchor' in input_id['type']:
                return True
            try:
                current_comp_id = int(input_id['type'][0])
                has_id = True
            except ValueError:
                has_id = False
            
            if has_id:
                return True

        elif 'anchor' in input_id:
            return True
        return False
    

