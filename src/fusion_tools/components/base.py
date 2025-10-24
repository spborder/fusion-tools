"""
Base component for FUSION layouts
"""
from typing_extensions import Union
import pandas as pd

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dash_table
from dash_extensions.enrich import (
    DashBlueprint, html, 
    MultiplexerTransform, PrefixIdTransform, BlockingCallbackTransform
)
from dash_extensions.javascript import Namespace

class BaseComponent:
    """
    Base component other components inherit from to initialize basic properties and methods
    """

    title = ''
    description = ''
    component_prefix = None
    database = None
    session_update = None
    assets_folder = None
    js_namespace = None

    def __str__(self):
        return self.title

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
    
    def add_database(self, database:None):
        """Adding a database to the component, connects to the running database for this application.

        :param database: Instance of fusionDB provided by Visualization.get_layout_children()
        :type database: None
        """

        self.database = database
    
    def add_assets_folder(self, assets_folder:str):
        """Adding an assets folder from the Visualization component

        :param assets_folder: String corresponding to assets folder path
        :type assets_folder: str
        """

        self.assets_folder = assets_folder

    def load(self, component_prefix:int):

        self.component_prefix = component_prefix
        self.blueprint = DashBlueprint(
            transforms = [
                PrefixIdTransform(
                    prefix = f'{self.component_prefix}',
                    escape = lambda input_id: self.prefix_escape(input_id)
                ),
                MultiplexerTransform(),
                BlockingCallbackTransform()
            ]
        )

        self.get_callbacks()
        self.get_namespace()
        self.get_clientside_callbacks()

    def get_callbacks(self):
        pass

    def get_clientside_callbacks(self):
        pass

    def get_namespace(self):
        pass

    def gen_layout(self, session_data:dict):

        self.blueprint.layout = self.update_layout(session_data, use_prefix = False)
    
    def update_layout(self, session_data:dict, use_prefix: bool):

        layout = html.Div()

        if use_prefix:
            PrefixIdTransform(prefix = f'{self.component_prefix}').transform_layout(layout)

        return layout

    def make_dash_table(self, df:pd.DataFrame, id: Union[dict,None] = None, editable: bool = False, deletable: bool = False, selectable: bool = True):
        
        return_table = dash_table.DataTable(
            id = id if not id is None else {},
            columns = [{'name':i,'id':i,'deletable':deletable,'selectable':selectable} for i in df],
            data = df.to_dict('records'),
            editable=editable,                                        
            sort_mode='multi',
            sort_action = 'native',
            page_current=0,
            page_size=5,
            style_cell = {
                'overflow':'hidden',
                'textOverflow':'ellipsis',
                'maxWidth':0
            },
            tooltip_data = [
                {
                    column: {'value':str(value),'type':'markdown'}
                    for column, value in row.items()
                } for row in df.to_dict('records')
            ],
            tooltip_duration = None
        )

        return return_table

    def get_user_external_token(self, session_data):
        try:
            user_token = session_data.get('user',{}).get('external',{}).get('token')
        except:
            user_token = None
        return user_token

    def get_user_external_login(self, session_data):
        try:
            user_login = session_data.get('user',{}).get('external',{}).get('login','Guest')
        except:
            user_login = None
        return user_login

    def get_user_external_id(self, session_data):

        try:
            user_id = session_data.get('user',{}).get('external',{}).get('_id')
            if user_id is None:
                user_id = session_data.get('user',{}).get('external',{}).get('id')
        except:
            user_id = None
        return user_id

    def get_user_internal_token(self, session_data):

        try:
            user_token = session_data.get('user',{}).get('token')
        except:
            user_token = None

        return user_token

    def get_user_internal_login(self, session_data):
        
        try:
            user_login = session_data.get('user',{}).get('login')
        except:
            user_login = None

        return user_login

    def get_user_internal_id(self,session_data):
        
        try:
            user_id = session_data.get('user',{}).get('id')
        except:
            user_id = None

        return user_id

    def get_session_id(self, session_data):

        try:
            session_id = session_data.get('session',{}).get('id')
        except:
            session_id = None

        return session_id

    def update_request_str(self, req_str: str, **query_params):

        print(f'{req_str=}')
        for k,v in query_params.items():
            if v is None:
                continue

            if '?' in req_str:
                sep = '&'
            else:
                sep = '?'
            
            req_str += f'{sep}{k}={v}'
        
        return req_str


class BaseSchema:
    """
    Schemas created in FUSION should inherit from this class
    """
    @classmethod
    def from_dict(cls, dict):
        return cls(**dict)


class Tool(BaseComponent):
    """General class for interactive components that visualize, edit, or perform analyses on data.
    """
    session_update = False


class MultiTool(Tool):
    """General class for a Tool which works on multiple slides at once
    """
    session_update = True


#TODO: Anything else that can be bundled with handler?
class Handler:
    pass

class DSATool(MultiTool):
    """A sub-class of Tool specific to DSA components. 
    The only difference is that these components always update relative to the session data.

    :param Tool: General class for components that perform visualization and analysis of data.
    :type Tool: None
    """

    pass


class MapComponent(MultiTool):
    """General class for components added to SlideMap
        For more information see dash-leaflet: https://www.dash-leaflet.com/

    """

    def get_scale_factors(self, image_metadata: dict):
        """Function used to initialize scaling factors applied to GeoJSON annotations to project annotations into the SlideMap CRS (coordinate reference system)

        :return: x and y (horizontal and vertical) scale factors applied to each coordinate in incoming annotations
        :rtype: float
        """
        if not any([i is None for i in [image_metadata.get('sizeX'), image_metadata.get('sizeY'), image_metadata.get('levels')]]):
            base_dims = [
                image_metadata['sizeX']/(2**(image_metadata['levels']-1)),
                image_metadata['sizeY']/(2**(image_metadata['levels']-1))
            ]

            x_scale = base_dims[0] / image_metadata['sizeX']
            y_scale = -(base_dims[1]) / image_metadata['sizeY']


            return x_scale, y_scale
        return 1.0, 1.0





