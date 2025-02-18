"""
Creating a file/directory/item selector component
"""

import os
import sys
sys.path.append('./src/')
import json

import pandas as pd

from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.visualization.vis_utils import get_pattern_matching_value

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform, DashProxy

from typing_extensions import Union
from fusion_tools import DSATool

class DSAResourceSelector(DSATool):
    def __init__(self,
                 handler,
                 selector_type:str,
                 select_count: Union[int,None]
                 ):
        
        super().__init__()

        self.handler = handler
        self.selector_type = selector_type
        self.select_count = select_count

    def __str__(self):
        return 'DSA Resource Selector'

    def load(self, component_prefix: int):

        self.component_prefix = component_prefix

        self.title = 'DSA Resource Selector'
        self.blueprint = DashBlueprint(
            transforms=[
                PrefixIdTransform(prefix=f'{self.component_prefix}'),
                MultiplexerTransform()
            ]
        )

        self.get_callbacks()

    def get_collection_table(self, session_data:dict):
        
        # Getting user folders if a user is present
        if "current_user" in session_data:
            user_folders = [
                "Private",
                "Public"
            ]
        else:
            user_folders = []

        # Getting collection names
        if "current_user" in session_data:
            self.handler.gc.setToken(session_data["current_user"]["token"])
            collection_list = self.handler.gc.get('/collection')
        else:
            collection_list = self.handler.gc.get('/collection')

        if len(user_folders)>0:
            collection_list+=[{'name': 'User Folders','_modelType': 'user', '_id': session_data['current_user']['_id']}]

        collection_table = html.Div(
            id = {'type': 'dsa-resource-selector-folder-div','index': 0},
            children = [
                dbc.Stack([
                    html.H5(
                        id = {'type': 'dsa-resource-selector-current-resource-path','index': 0},
                        children = [
                            html.A(
                                'Collections and User Folders',
                                id = {'type': 'dsa-resource-selector-path-part','index': 0},
                                style = {'color': 'rgb(0,0,255)'}
                            )
                        ]
                    ),
                    html.Div(
                        self.make_selectable_dash_table(
                            dataframe = pd.DataFrame.from_records([{'Name': i['name'], 'Type': i['_modelType'], '_id': i['_id']} for i in collection_list]),
                            id = {'type': 'dsa-resource-selector-resource-table','index': 0},
                            multi_row = False,
                            selected_rows = []
                        ),
                        id = {'type': 'dsa-resource-selector-resource-table-div','index': 0}
                    )
                ])
            ]
        )

        return collection_table

    def update_layout(self, session_data: dict, use_prefix:bool):

        collection_table = self.get_collection_table(session_data)

        layout = html.Div([
            html.H4(
                id = {'type': 'dsa-resource-selector-current-user','index': 0},
                children = [
                    f'Showing available resources for: {session_data["current_user"]["login"]}' if "current_user" in session_data else "Showing only publically available resources"
                ]
            ),
            html.Hr(),
            dcc.Store(
                id = {'type': 'dsa-resource-selector-selected-resources','index': 0},
                data = json.dumps({'resource_list':[]}),
                storage_type='memory'
            ),
            html.Div(
                id = {'type': 'dsa-resource-selector-div','index': 0},
                children = [
                    dbc.Stack([
                        collection_table
                    ])
                ]
            )
        ])

        return layout

    def gen_layout(self, session_data:dict):

        self.blueprint.layout = self.update_layout(session_data,use_prefix=False)

    def make_selectable_dash_table(self, dataframe:pd.DataFrame, id:dict, multi_row:bool = True, selected_rows: list = []):
        """Generate a selectable DataTable to add to the layout

        :param dataframe: Pandas DataFrame containing columns/rows of interest
        :type dataframe: pd.DataFrame
        :param id: Dictionary containing "type" and "index" keys for interactivity
        :type id: dict
        :param multi_row: Whether to allow selection of multiple rows in the table or just single, defaults to True
        :type multi_row: bool, optional
        :return: dash_table.DataTable component to be added to layout
        :rtype: dash_table.DataTable
        """

        #Optional: Can hide "ID" columns by adding any column containing "ID" to a list of "hidden_columns"

        dataframe = pd.json_normalize(dataframe.to_dict('records'))
        selectable_table = dash_table.DataTable(
            id = id,
            columns = [{'name':i,'id':i,'deletable':False} for i in dataframe.columns],
            data = dataframe.to_dict('records'),
            editable = False,
            filter_action='native',
            sort_action = 'native',
            sort_mode = 'multi',
            column_selectable = 'single',
            row_selectable = 'multi' if multi_row else 'single',
            row_deletable = False,
            selected_rows = selected_rows,
            page_action='native',
            page_current=0,
            page_size=10,
            style_cell = {
                'overflow':'hidden',
                'textOverflow':'ellipsis',
                'maxWidth':0                
            },
            tooltip_data = [
                {
                    column: {'value':str(value),'type':'markdown'}
                    for column, value in row.items()
                } for row in dataframe.to_dict('records')
            ],
            tooltip_duration = None
        )

        return selectable_table

    def extract_path_parts(self, current_parts:Union[list,dict], search_key: list = ['props','children'])->tuple:
        """Recursively extract pieces of folder paths stored as clickable components.

        :param current_parts: list or dictionary containing html.A or dbc.Stack of html.A components.
        :type current_parts: Union[list,dict]
        :param search_key: Property keys to search for in nested dicts, defaults to ['props','children']
        :type search_key: list, optional
        :return: Tuple containing all the parts of the folder path
        :rtype: tuple
        """
        path_pieces = ()
        if type(current_parts)==list:
            for c in current_parts:
                if type(c)==dict:
                    for key,value in c.items():
                        if key in search_key:
                            if type(value)==str:
                                path_pieces += (value.replace('/',''),)
                            elif type(value) in [list,dict]:
                                path_pieces += self.extract_path_parts(value)
                elif type(c)==list:
                    path_pieces += self.extract_path_parts(c)
        elif type(current_parts)==dict:
            for key,value in current_parts.items():
                if key in search_key:
                    if type(value)==str:
                        path_pieces += (value.replace('/',''),)
                    elif type(value) in [list,dict]:
                        path_pieces += self.extract_path_parts(value)

        return path_pieces

    def organize_folder_contents(self, folder_info:dict, show_empty:bool=False, ignore_histoqc:bool=True)->list:
        """For a given folder selection, return a list of slides(0th) and folders (1th)

        :param folder_info: Folder info dict returned by self.handler.get_path_info(path)
        :type folder_info: dict
        :param show_empty: Whether or not to display folders which contain 0 slides, defaults to False
        :type show_empty: bool, optional
        :return: List of slides within the current folder as well as folders within that folder
        :rtype: list
        """

        folder_folders = []
        folder_slides = []

        # Starting with slides (which will report parent folderId but not that parent's folderId (if applicable))
        if folder_info['_modelType'] in ['folder','collection']:
            if folder_info['_modelType']=='folder':
                all_folder_slides = self.handler.get_folder_slides(
                    folder_path = folder_info['_id'],
                    folder_type = folder_info['_modelType'],
                    ignore_histoqc=ignore_histoqc
                )
            else:
                all_folder_slides = []

            folder_slides_folders = [i['folderId'] for i in all_folder_slides]
            unique_folders = list(set(folder_slides_folders))
            folders_in_folder = []
            for u in unique_folders:
                if not u==folder_info['_id'] and not u in folders_in_folder:
                    # This is for all folders in this folder
                    # This grabs parent folders of this folder
                    u_folder_info = self.handler.get_folder_info(folder_id=u)
                    u_folder_rootpath = self.handler.get_folder_rootpath(u)
                    # Folders in order from collection-->child folder-->etc.
                    folder_ids = [i['object']['_id'] for i in u_folder_rootpath]

                    if any([i['object']['_modelType']=='collection' for i in u_folder_rootpath]):
                        base_model = 'collection'
                    else:
                        base_model = 'user'

                    if folder_ids[-1]==folder_info['_id']:
                        child_folder_path = f'/{base_model}/'+'/'.join([i['object']['name'] if i['object']['_modelType'] in ['folder','collection'] else i['object']['login'] for i in u_folder_rootpath]+[u_folder_info['name']])
                    else:
                        # Folder that is immediate child of current folder:
                        child_folder_idx = folder_ids.index(folder_info['_id'])
                        child_folder_path = f'/{base_model}/'+'/'.join([i['object']['name'] if i['object']['_modelType'] in ['folder','collection'] else i['object']['login'] for i in u_folder_rootpath[:child_folder_idx+2]])


                    child_folder_path_info = self.handler.get_path_info(
                        path = child_folder_path
                    )
                    if not child_folder_path_info['_id'] in folders_in_folder:
                        folders_in_folder.append(child_folder_path_info['_id'])
                        
                        # Adding folder to list if the number of items is above zero or show_empty is True
                        folder_folders.append({
                            'Name': child_folder_path_info['name'],
                            '_id': child_folder_path_info['_id'],
                            'Type': child_folder_path_info['_modelType'],
                            'Number of Folders': child_folder_path_info['nFolders'],
                            'Number of Slides': child_folder_path_info['nItems'],
                            'Last Updated': child_folder_path_info['updated']
                        } | child_folder_path_info['meta'])

                elif u==folder_info['_id']:
                    # This means that there are some slides that are direct children (not in a sub-folder) in this folder. 
                    # This adds them all at once
                    for i in all_folder_slides:
                        if i['folderId']==folder_info['_id']:
                            folder_slides.append(
                                {
                                    'Name': i['name'],
                                    '_id': i['_id'],
                                    'Type': i['_modelType'],
                                    'Last Updated':i['updated']
                                } | {k:v for k,v in i['meta'].items() if type(v)==str}
                            )

        else:
            
            user_folders = ['Private','Public']
            for u_f in user_folders:
                user_folder_info = self.handler.get_path_info(
                    path = f'/user/{folder_info["login"]}/{u_f}'
                )

                folder_folders.append({
                    'Name': user_folder_info['name'],
                    '_id': user_folder_info['_id'],
                    'Type': user_folder_info['_modelType'],
                    'Number of Folders': user_folder_info['nFolders'],
                    'Number of Slides': user_folder_info['nItems'],
                    'Last Updated': user_folder_info['updated']
                })

        if show_empty:
            # This is how you get all the empty folders within a folder (does not get child empty folders)
            empty_folders = self.handler.get_folder_folders(
                folder_id = folder_info['_id'],
                folder_type = folder_info['_modelType']
            )
            
            for f in empty_folders:
                if not f['_id'] in folders_in_folder and not f['_id'] in unique_folders:
                    folder_info = self.handler.gc.get(f'/folder/{f["_id"]}/details')
                    folder_folders.append(
                        {
                            'Name': f['name'],
                            '_id': f['_id'],
                            'type': f['_modelType'],
                            'Number of Folders': folder_info['nFolders'],
                            'Number of Slides': folder_info['nItems'],
                            'Last Updated': f['updated']
                        }
                    )


        return folder_slides, folder_folders

    def get_callbacks(self):

        # Updating resource list based on selection (from table, from crumbs), return internal folders/slides
        self.blueprint.callback(
            [
                Input({'type': 'dsa-resource-selector-resource-table','index': ALL},'selected_rows'),
                Input({'type': 'dsa-resource-selector-path-part','index': ALL},'n_clicks')
            ],
            [
                State({'type': 'dsa-resource-selector-resource-table','index': ALL},'data'),
                State({'type': 'dsa-resource-selector-current-resource-path','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dsa-resource-selector-resource-table-div','index': ALL},'children'),
                Output({'type': 'dsa-resource-selector-current-resource-path','index':ALL},'children'),
                Output({'type': 'dsa-resource-selector-selected-resources','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.update_resource_selection)

    def update_resource_selection(self, table_selected_rows, table_path_clicked, table_data, current_path_parts, session_data):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        print(ctx.triggered)

        table_data = get_pattern_matching_value(table_data)
        current_path_parts = list(self.extract_path_parts(get_pattern_matching_value(current_path_parts)))

        table_selected_rows = get_pattern_matching_value(table_selected_rows)
        
        session_data = json.loads(session_data)

        if 'dsa-resource-selector-resource-table' in ctx.triggered_id['type']:
            # This is so that it works for multiple selected rows as well
            selected_resource = [table_data[i] for i in table_selected_rows]
            print(f'Selected Resource: {selected_resource}')
            resource_type = [i['Type'] for i in selected_resource]
            if not all([r==self.selector_type for r  in resource_type]):
                # This means another table should be added:
                resource_folders, resource_slides = self.organize_folder_contents(
                    folder_info = {
                        '_id': selected_resource[0]['_id'],
                        '_modelType': selected_resource[0]['Type']
                    },
                    show_empty = True,
                    ignore_histoqc=True
                )

                new_crumbs = current_path_parts + [selected_resource[0]['Name']]


        elif 'dsa-resource-selector-path-part' in ctx.triggered_id['type']:
            selected_resource = current_path_parts[ctx.triggered_id['index']]
            print(f'Selected Resource: {selected_resource}')
            if ctx.triggered_id['index']<len(current_path_parts)-1:
                if ctx.triggered_id['index']>0:
                    new_path = '/'.join(current_path_parts[:ctx.triggered_id['index']])
                    print(f'new path: {new_path}')

                    path_info = self.handler.get_path_info(new_path,user_token = session_data['current_user']['token'])

                    resource_folders, resource_slides = self.organize_folder_contents(
                        folder_info = path_info,
                        show_empty = True,
                        ignore_histoqc=True
                    )

                    new_crumbs = current_path_parts[:ctx.triggered_id['index']]



                elif ctx.triggered_id==0:

                    resource_folders = self.get_collection_table(session_data)
                    PrefixIdTransform(prefix=f'{self.component_prefix}').transform_layout(resource_folders)
                    
                    resource_slides = []

                    new_crumbs = current_path_parts[0]

            else:
                new_crumbs = current_path_parts


        updated_resource_table = [no_update]
        
        updated_resource_path = [
            dbc.Stack([
                html.A(
                    c+'/',
                    n_clicks = 0,
                    id = {'type': f'{self.component_prefix}-dsa-resource-selector-path-part','index': c_idx},
                    style = {'color': 'rgb(0,0,255)'}
                )
                for c_idx,c in enumerate(new_crumbs)
            ],direction='horizontal')
        ]
        updated_resource_data = [no_update]

        return updated_resource_table, updated_resource_path, updated_resource_data




def main():

    base_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'

    user_name = os.getenv('DSA_USER')
    p_word = os.getenv('DSA_PWORD')

    # You have to sign in to access the add_plugin() method
    dsa_handler = DSAHandler(
        girderApiUrl=base_url,
        username = user_name,
        password = p_word
    )

    resource_selector_component = DSAResourceSelector(
        handler = dsa_handler,
        selector_type = 'item',
        select_count = None
    )


    session_data = {
        'current_user': dsa_handler.authenticate_new(
            username = user_name,
            password = p_word
        )
    }

    resource_selector_component.load(0)
    resource_selector_component.gen_layout(session_data)

    main_app = DashProxy(
        __name__,
        external_stylesheets = [
            dbc.themes.LUX,
            dbc.themes.BOOTSTRAP,
            dbc.icons.BOOTSTRAP,
            dbc.icons.FONT_AWESOME,
            dmc.styles.ALL,
        ],
        transforms = [
            MultiplexerTransform()
        ]
    )
    main_app.layout = html.Div(
        [
            dcc.Store(
                id = 'anchor-vis-store',
                data = json.dumps(session_data),
                storage_type='memory'
            ),
            dbc.Card([
                dbc.CardHeader(resource_selector_component.title),
                dbc.CardBody(
                    resource_selector_component.blueprint.embed(main_app)
                )
            ])
        ]
    )

    main_app.run(
        port = '8050'
    )





if __name__=='__main__':
    main()


