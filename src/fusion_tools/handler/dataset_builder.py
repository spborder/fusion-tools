"""DatasetBuilder Component
"""
import requests
import json
import numpy as np
import pandas as pd

import girder_client

from typing_extensions import Union

from skimage.draw import polygon
from PIL import Image
from io import BytesIO
import base64

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform

from fusion_tools.visualization.vis_utils import get_pattern_matching_value

from fusion_tools.components.base import DSATool



class DatasetBuilder(DSATool):
    """Handler for DatasetBuilder component, enabling selection/deselection of folders and slides to add to current visualization session.

    :param DSATool: Sub-class of Tool specific to DSA components. Updates with session data by default.
    :type DSATool: None
    """
    title = 'Dataset Builder'
    description = 'Search through available collections, folders, and slides to assemble a visualization session.'

    def __init__(self,
                 handler,
                 include_only: Union[list,None] = None
                ):
        
        super().__init__()
        self.include_only = include_only
        self.handler = handler
       
    def gen_collections_dataframe(self,session_data:dict):

        collections_info = []

        user_token = self.get_user_external_token(session_data)
        user_login = self.get_user_external_login(session_data)
        user_id = self.get_user_external_id(session_data)
        
        collections = self.handler.get_collections(session_data.get('user',{}).get('token'))
        for c in collections:
            #slide_count = self.handler.get_collection_slide_count(collection_name = c['name'])
            folder_count = self.handler.get_path_info(path = f'/collection/{c["name"]}', user_token = user_token)
            #if slide_count>0:
            collections_info.append({
                'Collection Name': c['name'],
                'Collection ID': c['_id'],
                #'Number of Slides': slide_count,
                'Number of Folders': folder_count['nFolders'],
                'Last Updated': folder_count['updated']
            } | c['meta'])

        if not user_login is None:
            collections_info.append({
                'Collection Name': f'User: {user_login}',
                'Collection ID': user_id,
                'Number of Folders': 2,
                'Last Updated': '-',
            })
            
        collections_df = pd.DataFrame.from_records(collections_info)

        return collections_df

    def update_layout(self, session_data:dict, use_prefix: bool):
        """Generating DatasetBuilder layout

        :return: Div object containing interactive components for the SlideMap object.
        :rtype: dash.html.Div.Div
        """

        # Adding current session data here
        user_external_token = self.get_user_external_token(session_data)
        user_internal_token = self.get_user_internal_token(session_data)
        starting_slides = []
        starting_slides_components = []
        starting_slide_idx = 0
        for s in session_data['current']:
            if s.get('type')=='remote_item':
                local = False
                user_token = user_external_token
                if not s['url']==self.handler.girderApiUrl:
                    continue
            else:
                local = True
                user_token = user_internal_token

            starting_slides.append(s)
            starting_slides_components.append(
                self.make_selected_slide(
                    slide_info = s,
                    idx = starting_slide_idx,
                    use_prefix = not use_prefix,
                    local_slide = local,
                    user_token = user_token
                )
            )
            starting_slide_idx += 1

        collections_df = self.gen_collections_dataframe(session_data)

        layout = html.Div([
            dbc.Card(
                dbc.CardBody([
                    dbc.Row(
                        html.H3(self.title)
                    ),
                    html.Hr(),
                    dbc.Row(
                        self.description
                    ),
                    html.Hr(),
                    dbc.Row([
                        dcc.Upload(
                            html.Div([
                                'If you have a previous Visualization Session, drag it here or ',
                                html.A('select the file')
                                ]),
                            id = {'type': 'dataset-builder-upload-session','index': 0},
                            accept = 'application/json',
                            style = {
                                'width': '100%',
                                'height': '60px',
                                'lineHeight': '60px',
                                'borderWidth': '1px',
                                'borderStyle': 'dashed',
                                'borderRadius': '5px',
                                'textAlign': 'center',
                                'margin': '10px'
                            },
                            multiple=False
                        )
                    ]),
                    html.Div(
                        dcc.Store(
                            id = {'type':'dataset-builder-data-store','index': 0},
                            storage_type='memory',
                            data = json.dumps({
                                'selected_slides':starting_slides, 
                                'selected_collections': [], 
                                'available_collections': collections_df.to_dict("records")})
                        )
                    ),
                    dbc.Row([
                        html.Div(
                            id = {'type':'dataset-builder-local-slides-div','index': 0},
                            children = [
                                self.make_selectable_dash_table(
                                    dataframe=pd.DataFrame.from_records([
                                        {
                                            'Slide Name': j['name'],
                                            'Slide ID': f'local{j_idx}'
                                        }
                                        for j_idx,j in enumerate(session_data['local'])
                                    ]),
                                    id = {'type':'dataset-builder-slide-table','index': 999},
                                    multi_row= True,
                                    selected_rows = [idx for idx,i in enumerate(session_data['local']) if i in session_data['current']]
                                )
                            ],
                            style = {'marginBottom':'5px'}
                        )
                    ]),
                    html.Hr(),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'dataset-builder-collection-div','index': 0},
                            children = [
                                self.make_selectable_dash_table(
                                    dataframe = collections_df,
                                    id = {'type': 'dataset-builder-collections-table','index': 0},
                                    multi_row = True
                                )
                            ]
                        )
                    ],style={'marginBottom':'10px'}),
                    html.Hr(),
                    dbc.Row([
                        html.Div(
                            id = {'type': 'dataset-builder-collection-contents-div','index':0},
                            children = []
                        )
                    ],style = {'marginBottom':'10px','maxHeight':'70vh','overflow':'scroll'}),
                    html.Div([
                        dmc.Affix([
                            dmc.Accordion([
                                dmc.AccordionItem([
                                    dmc.AccordionControl(
                                        dbc.Stack([
                                            html.I(className='fa-solid fa-microscope',style={'marginRight':'2px'}),
                                            html.H5(f'Visualization Session: ({len(starting_slides)})',style={'textTransform':'none'},id = {'type': 'dataset-builder-vis-session-count','index': 0})
                                        ],direction='horizontal')
                                    ),
                                    dmc.AccordionPanel([
                                        html.Div(
                                            id = {'type':'dataset-builder-selected-slides','index': 0},
                                            children = starting_slides_components,
                                            style = {'maxHeight':'50vh','overflow':'scroll'}
                                        )
                                    ])
                                ],value = 'dataset-builder-vis-session')
                            ],style={'width':'25vw'},radius='lg',variant='separated',chevronPosition='left')
                        ],
                        position = {'bottom':'20','right':'20'})
                    ])
                ])
            )
        ], style = {'maxHeight': '90vh','overflow': 'scroll'})

        if use_prefix:
            PrefixIdTransform(prefix = self.component_prefix).transform_layout(layout)
        
        return layout

    def get_callbacks(self):

        # Callback for collection selection (populating table with collection contents)
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-collections-table','index': ALL},'selected_rows')
            ],
            [
                State({'type':'dataset-builder-data-store','index': ALL},'data'),
                State({'type':'dataset-builder-collection-contents-div','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type':'dataset-builder-collection-contents-div','index': ALL},'children'),
                Output({'type':'dataset-builder-data-store','index': ALL},'data')
            ],
            prevent_initial_call = True
        )(self.collection_selection)

        # Callback for selecting folder from collection-contents-div
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-collection-folder-table','index':MATCH},'selected_rows'),
                Input({'type':'dataset-builder-collection-folder-crumb','index':ALL},'n_clicks')
            ],
            [
                State({'type':'dataset-builder-collection-folder-table','index': MATCH},'data'),
                State({'type': 'dataset-builder-collection-folder-nav-parent','index': MATCH},'children'),
                State({'type':'dataset-builder-data-store','index': ALL},'data'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type':'dataset-builder-collection-folder-div','index': MATCH},'style'),
                Output({'type':'dataset-builder-collection-folder-div','index':MATCH},'children'),
                Output({'type':'dataset-builder-collection-slide-div','index':MATCH},'children'),
                Output({'type':'dataset-builder-collection-folder-nav-parent','index': MATCH},'children')
            ],
            prevent_initial_call = True
        )(self.update_folder_div)

        # Callback for selecting slide(s) to be added to visualization session
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-slide-table','index':ALL},'selected_rows'),
                Input({'type':'dataset-builder-slide-select-all','index':ALL},'n_clicks'),
                Input({'type':'dataset-builder-slide-remove-all','index':ALL},'n_clicks'),
                Input({'type':'dataset-builder-slide-remove-icon','index': ALL},'n_clicks'),
                Input({'type': 'dataset-builder-upload-session','index': ALL},'contents')
            ],
            [
                State({'type': 'dataset-builder-collection-folder-nav-parent','index': ALL},'children'),
                State({'type':'dataset-builder-slide-table','index': ALL},'data'),
                State({'type':'dataset-builder-data-store','index': ALL},'data'),
                State({'type':'dataset-builder-selected-slides','index': ALL},'children'),
                State({'type':'dataset-builder-collection-contents-div','index': ALL},'children'),
                State('anchor-vis-store','data')
            ],
            [
                Output({'type': 'dataset-builder-selected-slides','index': ALL},'children'),
                Output({'type': 'dataset-builder-vis-session-count','index': ALL},'children'),
                Output({'type':'dataset-builder-data-store','index':ALL},'data')
            ]
        )(self.slide_selection)

        # Passing current visualization data to the visualization session for usage in other pages
        self.blueprint.callback(
            [
                Input({'type':'dataset-builder-data-store','index': ALL},'data')
            ],
            [
                State('anchor-vis-store','data')
            ],
            [
                Output('anchor-vis-store','data')
            ]
        )(self.update_vis_store)

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
            columns = [{'name':i,'id':i,'deletable':False} for i in dataframe.columns if not i=='token'],
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

    def organize_folder_contents(self, folder_info:dict, show_empty:bool=True, ignore_histoqc:bool=True,session_data:dict = {})->list:
        """For a given folder selection, return a list of slides(0th) and folders (1th)

        :param folder_info: Folder info dict returned by self.handler.get_path_info(path)
        :type folder_info: dict
        :param show_empty: Whether or not to display folders which contain 0 slides, defaults to False
        :type show_empty: bool, optional
        :param session_data: Current session information
        :type session_data: dict
        :return: List of slides within the current folder as well as folders within that folder
        :rtype: list
        """

        folder_folders = []
        folder_slides = []

        user_token = self.get_user_external_token(session_data)

        # Starting with slides (which will report parent folderId but not that parent's folderId (if applicable))
        if folder_info['_modelType'] in ['folder','collection']:
            all_folder_slides = self.handler.get_folder_slides(
                folder_path = folder_info['_id'],
                folder_type = folder_info['_modelType'],
                ignore_histoqc=ignore_histoqc,
                user_token = user_token
            )

            folder_slides_folders = [i['folderId'] for i in all_folder_slides]
            unique_folders = list(set(folder_slides_folders))
            folders_in_folder = []
            for u in unique_folders:
                if not u==folder_info['_id'] and not u in folders_in_folder:
                    # This is for all folders in this folder
                    # This grabs parent folders of this folder
                    u_folder_info = self.handler.get_folder_info(
                        folder_id=u,
                        user_token = user_token
                    )
                    u_folder_rootpath = self.handler.get_folder_rootpath(
                        u,
                        user_token = user_token
                    )
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
                        path = child_folder_path,
                        user_token = user_token
                    )
                    if not child_folder_path_info['_id'] in folders_in_folder:
                        folders_in_folder.append(child_folder_path_info['_id'])
                        
                        # Adding folder to list if the number of items is above zero or show_empty is True
                        folder_folders.append({
                            'Folder Name': child_folder_path_info['name'],
                            'Folder ID': child_folder_path_info['_id'],
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
                                    'Slide Name': i['name'],
                                    'Slide ID': i['_id'],
                                    'Last Updated':i['updated']
                                } | {k:v for k,v in i['meta'].items() if type(v)==str}
                            )

        else:
            
            folders_in_folder = []
            unique_folders = []
            user_folders = ['Private','Public']
            user_login = self.get_user_external_login(session_data)
            for u_f in user_folders:
                user_folder_info = self.handler.get_path_info(
                    path = f'/user/{folder_info["login"]}/{u_f}',
                    user_token = user_token
                )

                folder_folders.append({
                    'Folder Name': user_folder_info['name'],
                    'Folder ID': user_folder_info['_id'],
                    'Number of Folders': user_folder_info['nFolders'],
                    'Number of Slides': user_folder_info['nItems'],
                    'Last Updated': user_folder_info['updated']
                })

                unique_folders.append(user_folder_info['_id'])


        if show_empty:
            # This is how you get all the empty folders within a folder (does not get child empty folders)
            empty_folders = self.handler.get_folder_folders(
                folder_id = folder_info['_id'],
                folder_type = folder_info['_modelType'],
                user_token = user_token
            )
            
            for f in empty_folders:
                if not f['_id'] in folders_in_folder and not f['_id'] in unique_folders:
                    if not user_token is None:
                        folder_info = self.handler.gc.get(f'/folder/{f["_id"]}/details')
                    else:
                        folder_info = self.handler.gc.get(f'/folder/{f["_id"]}/details?token={user_token}')
                    folder_folders.append(
                        {
                            'Folder Name': f['name'],
                            'Folder ID': f['_id'],
                            'Number of Folders': folder_info['nFolders'],
                            'Number of Slides': folder_info['nItems'],
                            'Last Updated': f['updated']
                        }
                    )


        return folder_slides, folder_folders

    def get_clientside_callbacks(self):

        self.blueprint.clientside_callback(
            """
            async function getThumbnail(thumbs,thumb_store) {
                if (!thumb_store) {
                    throw window.dash_clientside.PreventUpdate;
                }

                const thumbDataUrl = await Promise.all(
                    thumb_store.map(async (t_data) => {
                        const t_json = JSON.parse(t_data.replace('/[\[\]]+/g',""));
                        
                        if (!t_json.done){
                            const res = await fetch(t_json.url,{
                                method: 'GET',
                                headers: { 'Content-Type': 'image/jpeg' }
                            })
                            .then(r => r.blob());


                            let dataUrl = await new Promise(resolve => {
                                let reader = new FileReader();
                                reader.onload = () => resolve(reader.result);
                                reader.readAsDataURL(res);
                            })

                            if (dataUrl.includes('text/html')){
                                dataUrl.replace('text/html','image/jpeg');
                            }

                            return dataUrl;
                        } else {
                            let dataUrl = window.dash_clientside.no_update; 
                            return dataUrl;
                        }
                    })
                )

                thumb_store.map(t=>t.done=true);
                thumb_store.map(t => JSON.stringify(t));

                return [thumbDataUrl, thumb_store];
            }
            """,
            [
                Output({'type': 'dataset-builder-slide-thumbnail','index': ALL},'src'),
                Output({'type': 'dataset-builder-slide-thumb-data','index': ALL},'data')
            ],
            [
                Input({'type': 'dataset-builder-selected-slides','index': ALL},'children'),
                Input({'type': 'dataset-builder-slide-thumb-data','index': ALL},'data')
            ],
            prevent_initial_call = False
        )

    def make_selected_slide(self, slide_info:dict,idx:int,local_slide:bool = False, use_prefix:bool = True, user_token: Union[str,None] = None):
        """Creating a visualization session component for a selected slide

        :param slide_info: Information on the Local or Remote Item
        :type slide_info: dict
        :param local_slide: Whether or not the slide is from the LocalTileServer or if it's in the cloud
        :type local_slide: bool
        :param use_prefix: Whether or not to add the component prefix (initially don't add, when updating the layout do add)
        :type use_prefix: bool
        :param user_token: Token to use in requests
        :type user_token: Union[str,None], optional
        """
        
        if not local_slide:
            item_id = slide_info.get('_id') if '_id' in slide_info else slide_info.get('id')
            try:               
                item_info = self.handler.get_item_info(item_id,user_token)
                thumb_url = self.handler.get_image_thumbnail(item_id, user_token = user_token, return_url = True)

                folder_info = self.handler.get_folder_info(item_info['folderId'], user_token = user_token)
                slide_info = {
                    k:v for k,v in item_info.items() if type(v) in [int,float,str]
                }
            except girder_client.HttpError:
                print(f'Item not found! {item_id}')
                return html.Div()
        else:
            
            #TODO: Deriving thumbnail url from local slide info
            thumb_url = slide_info.get('')

            folder_info = {'name': slide_info.get('filepath').replace(slide_info.get('name'),'')}               

        slide_card = html.Div([
            dbc.Card([
                dbc.CardHeader(f"{folder_info['name']}/{slide_info['name']}"),
                dbc.CardBody([
                    dbc.Stack([
                        html.Div([
                            dcc.Loading(
                                html.Img(
                                    src = '',
                                    alt = 'slide-thumbnail',
                                    width = 256,
                                    id = {'type': f'{self.component_prefix}-dataset-builder-slide-thumbnail','index': idx} if use_prefix else {'type': 'dataset-builder-slide-thumbnail','index': idx}
                                )
                            ),
                            dcc.Store(
                                id = {'type': f'{self.component_prefix}-dataset-builder-slide-thumb-data','index': idx} if use_prefix else {'type': 'dataset-builder-slide-thumb-data','index': idx},
                                data = json.dumps({
                                    "url": thumb_url,
                                    "done": False
                                }),
                                storage_type='memory'
                            )
                        ]),
                        html.A(
                            html.I(
                                id = {'type': f'{self.component_prefix}-dataset-builder-slide-remove-icon','index': idx} if use_prefix else {'type': 'dataset-builder-slide-remove-icon','index': idx},
                                n_clicks = 0,
                                className = 'bi bi-x-circle-fill fa-2x',
                                style = {'color': 'rgb(255,0,0)','marginRight':'2px'}
                            )
                        )
                    ],direction='horizontal',gap=3)
                ])
            ])
        ],style = {'marginBottom': '2px','width':'25vw'})
        
        return slide_card        

    def collection_selection(self, collection_rows, builder_data, collection_div_children,session_data):
        """Callback for when one/multiple collections are selected from the collections table

        :param collection_rows: Row indices of selected collections
        :type collection_rows: list
        :param builder_data: Data store on available collections and currently included slides
        :type builder_data: list
        :param collection_div_children: Child cards created by collection_selection
        :type collection_div_children: list
        :param session_data: Current session information
        :type session_data: dict
        :return: Children of collection-contents-div (items/folders within selected collections)
        :rtype: list
        """
        selected_collections = get_pattern_matching_value(collection_rows)
        builder_data = json.loads(get_pattern_matching_value(builder_data))
        session_data = json.loads(session_data)

        collection_card_indices = self.get_component_indices(collection_div_children)

        user_external_token = self.get_user_external_token(session_data)

        if selected_collections is None and len(builder_data['selected_collections'])==0:
            return ['Select a Collection to get started'], no_update
        elif selected_collections is None and len(builder_data['selected_collections'])>0:
            selected_collections = []

        if len(selected_collections)==1 and len(builder_data['selected_collections'])==0:
            collection_contents = []
        else:
            collection_contents = Patch()

        def add_collection_card(collection_info,idx):
            # For each collection, grab all items and unique folders (as well as those that are not nested in a folder)
            if not 'User: ' in collection_info["Collection Name"]:
                folder_path = f'/collection/{collection_info["Collection Name"]}'
            else:
                folder_path = f'/user/{collection_info["Collection Name"].replace("User: ","")}'
            
            folder_slides, folder_folders = self.organize_folder_contents(
                folder_info = self.handler.get_path_info(
                    folder_path,
                    user_token = user_external_token
                ),
                session_data = session_data
            )

            if len(folder_slides)>0:

                # Checking if any of the slides are already present in the "selected_slides"
                current_selected_slides = builder_data['selected_slides']
                current_selected_slide_ids = [i.get('id') for i in current_selected_slides]
                selected_rows = [
                    idx for idx,i in enumerate(folder_slides)
                    if i['Slide ID'] in current_selected_slide_ids
                ]

                non_nested_df = pd.DataFrame.from_records(folder_slides)
                non_nested_table = self.make_selectable_dash_table(
                    dataframe=non_nested_df,
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-slide-table','index': idx},
                    multi_row=True,
                    selected_rows=selected_rows
                )

            else:
                non_nested_table= html.Div()

            if len(folder_folders)>0:
                folder_table = self.make_selectable_dash_table(
                    dataframe=pd.DataFrame.from_records(folder_folders),
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-table','index': idx},
                    multi_row=False
                )
            else:
                folder_table = html.Div()

            new_card = html.Div(
                dbc.Card([
                    dbc.CardHeader(f'Collection: {collection_info["Collection Name"]}'),
                    dbc.CardBody([
                        html.H6(
                            children = [
                                dbc.Stack([
                                    html.A('/collection' if not 'User: ' in collection_info['Collection Name'] else '/user'),
                                    html.A(
                                        f'/{collection_info["Collection Name"].replace("User: ","")}/',
                                        id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-crumb','index': idx},
                                        style = {'color': 'rgb(0,0,255)'}
                                    )
                                ],direction='horizontal')
                            ],
                            id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-nav-parent','index': idx},
                            style = {'textTransform':'none','display':'inline'}
                        ),
                        html.Hr(),
                        html.Div([
                            folder_table
                        ], id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-div','index': idx}),
                        html.Hr(),
                        html.Div([
                            non_nested_table
                        ], style = {'marginTop':'10px'},id = {'type': f'{self.component_prefix}-dataset-builder-collection-slide-div','index': idx}),
                        html.Div(
                            dbc.Stack([
                                dbc.Button(
                                    'Select All!',
                                    className = 'd-grid col-6 mx-auto',
                                    n_clicks = 0,
                                    color = 'success',
                                    id = {'type':f'{self.component_prefix}-dataset-builder-slide-select-all','index': idx}
                                ),
                                dbc.Button(
                                    'Remove All',
                                    className = 'd-grid col-6 mx-auto',
                                    n_clicks = 0,
                                    color = 'danger',
                                    id = {'type': f'{self.component_prefix}-dataset-builder-slide-remove-all','index':idx}
                                )
                            ],direction='horizontal',style = {'marginTop':'10px'})
                            if len(folder_slides)>0 else []
                        )
                    ]),
                ]),
                style = {'marginBottom':'10px'},
                id = {'type': f'{self.component_prefix}-dataset-builder-collection-card-div','index': idx}
            )
            
            return new_card
        
        if len(selected_collections)>0:
            if len(list(set(selected_collections).difference(builder_data['selected_collections'])))>0:
                # Adding a new collection
                new_collection_idx = list(set(selected_collections).difference(builder_data['selected_collections']))[0]
                new_component_idx = max(collection_card_indices)+1 if len(collection_card_indices)>0 else 0

                collection_contents.append(add_collection_card(builder_data['available_collections'][new_collection_idx],new_component_idx))
            elif len(list(set(builder_data['selected_collections']).difference(selected_collections)))>0:
                # Removing a collection
                rem_collection_idx = list(set(builder_data['selected_collections']).difference(selected_collections))[0]
                del collection_contents[builder_data['selected_collections'].index(rem_collection_idx)]

        else:
            collection_contents = ['Select a Collection to get started!']

        builder_data['selected_collections'] = selected_collections
        builder_data = json.dumps(builder_data)
            
        return [collection_contents], [builder_data]

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
                                path_pieces += (value,)
                            elif type(value) in [list,dict]:
                                path_pieces += self.extract_path_parts(value)
                elif type(c)==list:
                    path_pieces += self.extract_path_parts(c)
        elif type(current_parts)==dict:
            for key,value in current_parts.items():
                if key in search_key:
                    if type(value)==str:
                        path_pieces += (value,)
                    elif type(value) in [list,dict]:
                        path_pieces += self.extract_path_parts(value)

        return path_pieces

    def get_clicked_part(self, current_parts: Union[list,dict])->list:
        """Get the "n_clicks" value for components which have "id". If they have "id" but not "n_clicks", assign 0

        :param current_parts: Either a list or dictionary containing components
        :type current_parts: Union[list,dict]
        :return: List of values corresponding to "n_clicks" 
        :rtype: list
        """
        
        n_clicks_list = []
        if type(current_parts)==list:
            for c in current_parts:
                if type(c)==dict:
                    if 'id' in list(c.keys()):
                        if 'n_clicks' in list(c.keys()):
                            n_clicks_list.append(c['n_clicks'])
                        else:
                            n_clicks_list.append(0)
                    else:
                        for key,value in c.items():
                            if key=='props':
                                n_clicks_list += self.get_clicked_part(value)
                            elif key=='n_clicks':
                                n_clicks_list.append(value)
                elif type(c)==list:
                    n_clicks_list += self.get_clicked_part(c)
        elif type(current_parts)==dict:
            if 'id' in list(current_parts.keys()):
                if 'n_clicks' in list(current_parts.keys()):
                    n_clicks_list.append(current_parts['n_clicks'])
                else:
                    n_clicks_list.append(0)
            else:
                for key,value in current_parts.items():
                    if type(value)==dict:
                        if key=='props':
                            n_clicks_list += self.get_clicked_part(value)
                        elif key=='n_clicks':
                            n_clicks_list.append(value)
                    elif type(value)==list:
                        n_clicks_list += self.get_clicked_part(value)

        return n_clicks_list

    def get_component_indices(self, components: Union[list,dict])->list:
        
        index_list = []
        if type(components)==list:
            for c in components:
                if type(c)==dict:
                    for key,value in c.items():
                        if key=='id':
                            index_list.append(value['index'])
                        elif key in ['props','children']:
                            index_list += self.get_component_indices(value)
                elif type(c)==list:
                    index_list += self.get_component_indices(c)

        elif type(components)==dict:
            for key,value in components.items():
                if key=='id':
                    index_list.append(value['index'])
                elif key in ['props','children']:
                    index_list += self.get_component_indices(value)

        return index_list

    def update_folder_div(self,folder_row,crumb_click,collection_folders,current_crumbs,builder_data,session_data):
        """Selecting a folder from the collection's folder table

        :param folder_row: Selected folder (list of 1 index)
        :type folder_row: list
        :param crumb_click: If one of the folder path parts was clicked it will trigger this.
        :type crumb_click: int
        :param collection_folders: Current data in the collection's folder table
        :type collection_folders: list
        :param current_crumbs: List of current path parts that can be selected to go up a folder
        :type current_crumbs: list
        :param builder_data: Current contents of data store for dataset-builder, used for determining if a slide is already selected
        :type builder_data: list
        :param session_data: Current session information
        :type session_data: str
        :return: Sub-folder and slide selection tables for further selection
        :rtype: tuple
        """

        path_parts = self.extract_path_parts(current_crumbs)
        new_crumbs = []
        for i in path_parts:
            if not i in ['/collection','/user']:
                new_crumbs.append(
                    html.A(
                        i,
                        id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-crumb','index': ctx.triggered_id['index']},
                        style = {'color': 'rgb(0,0,255)'}
                    )
                )
            else:
                new_crumbs.append(
                    html.A(i)
                )

        session_data = json.loads(session_data)
        builder_data = json.loads(get_pattern_matching_value(builder_data))
        user_external_token = self.get_user_external_token(session_data)

        if 'dataset-builder-collection-folder-table' in ctx.triggered_id['type']:
            
            # Triggers callback when creating new folder table
            if len(folder_row)==0:
                return no_update, no_update, no_update

            new_folder_name = collection_folders[folder_row[0]]['Folder Name']
            folder_table_style = {'display':'inline-block','width':'100%'}
            
            new_crumbs += [
                html.A(
                    new_folder_name + '/',
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-crumb','index': ctx.triggered_id['index']},
                    style = {'color': 'rgb(0,0,255)'}
                )
            ]
            
            folder_path = ''.join(list(path_parts+(new_folder_name,)))
            folder_info = self.handler.get_path_info(
                path = folder_path,
                user_token = user_external_token
            )
            
            folder_slides, folder_folders = self.organize_folder_contents(
                folder_info=folder_info,
                session_data = session_data
            )

            if len(folder_folders)>0:
                folder_table = self.make_selectable_dash_table(
                    dataframe = pd.DataFrame.from_records(folder_folders),
                    id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-table','index': ctx.triggered_id['index']},
                    multi_row=False
                )
            else:
                folder_table_style = {'display':'none'}
                folder_table = no_update

                
            if len(folder_slides)>0:
                current_selected_slides = builder_data['selected_slides']
                current_selected_slide_ids = [i.get('id') for i in current_selected_slides]
                selected_rows = [
                    idx for idx,i in enumerate(folder_slides)
                    if i['Slide ID'] in current_selected_slide_ids
                ]

                slides_table = html.Div([
                    self.make_selectable_dash_table(
                        dataframe=pd.DataFrame.from_records(folder_slides),
                        id = {'type': f'{self.component_prefix}-dataset-builder-slide-table','index': ctx.triggered_id['index']},
                        multi_row=True,
                        selected_rows= selected_rows
                    ),
                    dbc.Stack([
                        dbc.Button(
                            'Select All!',
                            className = 'd-grid col-6 mx-auto',
                            n_clicks = 0,
                            color = 'success',
                            id = {'type':f'{self.component_prefix}-dataset-builder-slide-select-all','index': ctx.triggered_id['index']}
                        ),
                        dbc.Button(
                            'Remove All',
                            className = 'd-grid col-6 mx-auto',
                            n_clicks = 0,
                            color = 'danger',
                            id = {'type': f'{self.component_prefix}-dataset-builder-slide-remove-all','index':ctx.triggered_id['index']}
                        )
                    ],direction='horizontal',style = {'marginTop':'10px'})
                ])
            else:
                slides_table = html.Div()


        elif 'dataset-builder-collection-folder-crumb' in ctx.triggered_id['type']:
            n_clicks = [0]+self.get_clicked_part(current_crumbs)
            n_click_idx = np.argmax(n_clicks)
            if n_click_idx==len(current_crumbs)-1:
                folder_table_style = no_update
                folder_table = no_update
            else:
                folder_table_style = {'display':'inline-block','width':'100%'}
                new_crumbs = new_crumbs[:n_click_idx+1]
                
                new_path = ''.join(list(path_parts)[:n_click_idx+1])[:-1]
                folder_info = self.handler.get_path_info(
                    path = new_path
                )
                
                folder_slides, folder_folders = self.organize_folder_contents(
                    folder_info=folder_info,
                    session_data = session_data
                )

                if len(folder_folders)>0:
                    folder_table = self.make_selectable_dash_table(
                        dataframe = pd.DataFrame.from_records(folder_folders),
                        id = {'type': f'{self.component_prefix}-dataset-builder-collection-folder-table','index': ctx.triggered_id['index']},
                        multi_row=False
                    )
                else:
                    folder_table = no_update
                    folder_table_style = {'display':'none'}

                    
                if len(folder_slides)>0:

                    current_selected_slides = builder_data['selected_slides']
                    current_selected_slide_ids = [i.get('id') for i in current_selected_slides]
                    selected_rows = [
                        idx for idx,i in enumerate(folder_slides)
                        if i['Slide ID'] in current_selected_slide_ids
                    ]

                    slides_table = html.Div([
                        self.make_selectable_dash_table(
                            dataframe=pd.DataFrame.from_records(folder_slides),
                            id = {'type': f'{self.component_prefix}-dataset-builder-slide-table','index': ctx.triggered_id['index']},
                            multi_row=True,
                            selected_rows=selected_rows
                        ),
                        dbc.Stack([
                            dbc.Button(
                                'Select All!',
                                className = 'd-grid col-6 mx-auto',
                                n_clicks = 0,
                                color = 'success',
                                id = {'type':f'{self.component_prefix}-dataset-builder-slide-select-all','index': ctx.triggered_id['index']}
                            ),
                            dbc.Button(
                                'Remove All',
                                className = 'd-grid col-6 mx-auto',
                                n_clicks = 0,
                                color = 'danger',
                                id = {'type': f'{self.component_prefix}-dataset-builder-slide-remove-all','index':ctx.triggered_id['index']}
                            )
                        ],direction='horizontal',style = {'marginTop':'10px'})
                    ])
                else:
                    slides_table = html.Div()
                
        new_crumbs = dbc.Stack(new_crumbs,direction='horizontal')

        return folder_table_style, folder_table, slides_table, new_crumbs

    def slide_selection(self, slide_rows, slide_all, slide_rem_all, slide_rem, upload_session, current_crumbs, slide_table_data, builder_data, current_slide_components, current_collection_components, session_data):

        builder_data = json.loads(get_pattern_matching_value(builder_data))
        session_data = json.loads(session_data)

        user_external_token = self.get_user_external_token(session_data)
        user_internal_token = self.get_user_internal_token(session_data)

        current_slide_indices = list(set(self.get_component_indices(current_slide_components)))
        current_collection_indices = list(set(self.get_component_indices(current_collection_components)))
        slide_table_data = [i for i in slide_table_data if not len(i)==0]
        slide_rows = [i for i in slide_rows if not len(i)==0]

        # When slide-table is not in layout
        if not ctx.triggered_id:
            raise exceptions.PreventUpdate
        
        active_folders = []
        for p in current_crumbs:
            path = ''.join(list(self.extract_path_parts(p)))
            active_folders.append(path)

        current_selected_slides = builder_data['selected_slides']
        current_selected_slide_ids = [i.get('id') if 'id' in i else i.get('_id') for i in current_selected_slides]
        current_local_slide_ids = [i.get('id') for i in session_data.get('local')]
        selected_slides = Patch()
        
        if 'dataset-builder-slide-table' in ctx.triggered_id['type']:
            # This part has to get triggered for both selection and de-selection of rows in a slide-table
            table_selected_slides = []
            not_selected_slides = []
            for s_r,slide_table in zip(slide_rows,slide_table_data):
                if not s_r is None:
                    table_selected_slides.extend([slide_table[i] for i in s_r])
                    not_selected_slides.extend([slide_table[i] for i in range(len(slide_table)) if not i in s_r])

            new_slides = list(set([i['Slide ID'] for i in table_selected_slides]).difference(current_selected_slide_ids))
            new_slide_info = []
            for s_idx,s in enumerate(new_slides):
                
                if s in current_local_slide_ids:
                    local = True
                    user_token = user_internal_token
                    slide_info = session_data.get('local')[current_local_slide_ids.index(s)]
                else:
                    local = False
                    user_token = user_external_token
                    slide_info = self.handler.get_item_info(s,user_external_token)

                new_slide_component = self.make_selected_slide(
                    slide_info = slide_info,
                    idx = max(current_slide_indices)+s_idx+1 if len(current_slide_indices)>0 else s_idx,
                    user_token = user_token,
                    local_slide=local
                )

                selected_slides.append(new_slide_component)
                new_slide_info.append(slide_info)

            current_selected_slides.extend(new_slide_info)
            new_rem_slides = list(set(current_selected_slide_ids) & set([i['Slide ID'] for i in not_selected_slides]))

            for d_idx,d in enumerate(new_rem_slides):
                del selected_slides[current_selected_slide_ids.index(d)]
                del current_selected_slides[current_selected_slide_ids.index(d)]           

        elif 'dataset-builder-slide-select-all' in ctx.triggered_id['type']:
            # This part only gets triggered when n_clicks is greater than 0 (ignore trigger on creation)
            if any([i['value'] for i in ctx.triggered]):
                select_all_idx = ctx.triggered_id['index']
                select_all_slides = slide_table_data[current_collection_indices.index(select_all_idx)]
                new_slides = list(set([i['Slide ID'] for i in select_all_slides]).difference(current_selected_slide_ids))
                
                new_slide_info = []
                for s_idx, new_slide_id in enumerate(new_slides):
                    if new_slide_id in current_local_slide_ids:
                        local = True
                        user_token = session_data.get('user').get('token')
                        slide_info = session_data.get('local')[current_local_slide_ids.index(new_slide_id)]
                    else:
                        local = False
                        user_token = user_external_token
                        slide_info = self.handler.get_item_info(new_slide_id,user_external_token)

                    selected_slides.append(
                        self.make_selected_slide(
                            slide_id = slide_info,
                            local_slide = local,
                            idx = max(current_slide_indices)+s_idx+1 if len(current_slide_indices)>0 else s_idx
                        )
                    )
                    new_slide_info.append(slide_info)

                current_selected_slides.extend(new_slide_info)

            else:
                raise exceptions.PreventUpdate

        elif 'dataset-builder-slide-remove-all' in ctx.triggered_id['type']:
            # This part only gets triggered when n_clicks is greater than 0 (ignore trigger on creation)
            if any([i['value'] for i in ctx.triggered]):
                remove_all_idx = ctx.triggered_id['index']
                remove_all_slides = slide_table_data[current_collection_indices.index(remove_all_idx)]

                new_rem_slides = list(set(current_selected_slide_ids) & set([i['Slide ID'] for i in remove_all_slides]))
                for d_idx,d in enumerate(new_rem_slides):
                    del selected_slides[current_selected_slide_ids.index(d)]
                    del current_selected_slides[current_selected_slide_ids.index(d)]

            else:
                raise exceptions.PreventUpdate      
            
        elif 'dataset-builder-slide-remove-icon' in ctx.triggered_id['type']:
            rem_idx = current_slide_indices.index(ctx.triggered_id['index'])
            del selected_slides[rem_idx]
            del current_selected_slides[rem_idx]

        elif 'dataset-builder-upload-session' in ctx.triggered_id['type']:
            upload_session = get_pattern_matching_value(upload_session)
            content_type, content_string = upload_session.split(',')
            try:
                decoded = json.loads(base64.b64decode(content_string))  
            except:
                raise exceptions.PreventUpdate

            if not 'current' in decoded:
                raise exceptions.PreventUpdate

            new_cloud_slides = []
            new_local_slides = []
            keep_slides = []
            for s_idx,s in enumerate(decoded['current']):
                if s.get('type')=='remote_item':
                    if s['url']==self.handler.girderApiUrl:
                        # Getting the id of the DSA slide from this same instance
                        slide_id = s['id']

                        if not slide_id in current_selected_slide_ids:
                            new_cloud_slides.append(s)
                        else:
                            keep_slides.append(s)
                    else:
                        continue
                else:

                    if s['id'] in current_local_slide_ids:
                        keep_slides.append(s)
                    else:
                        new_local_slides.append(s)
            
            # Now removing unneeded slides
            new_local_slide_ids = [i.get('id') for i in new_local_slides]
            new_cloud_slide_ids = [i.get('id') for i in new_cloud_slides]
            keep_slide_ids = [i.get('id') for i in keep_slides]

            remove_slide_ids = [i for i in current_selected_slide_ids if not i in new_local_slide_ids+new_cloud_slide_ids+keep_slide_ids]

            for d_idx, d in enumerate(remove_slide_ids):
                del selected_slides[current_selected_slide_ids.index(d)]
                del current_selected_slides[current_selected_slide_ids.index(d)]

            new_slide_info = new_local_slides + new_cloud_slides
            for new_idx, new_slide in enumerate(new_slide_info):

                current_selected_slides.append(new_slide)
                if new_slide.get('id') in new_local_slide_ids:
                    local = True
                    user_token = session_data.get('user').get('token')
                else:
                    local = False
                    user_token = user_external_token

                selected_slides.append(
                    self.make_selected_slide(
                        slide_info = new_slide,
                        user_token = user_token,
                        idx = new_idx,
                        local_slide = local
                    )
                )

        else:
            raise exceptions.PreventUpdate
        
        # Need folder id, rootpath, slide info, 
        builder_data['selected_slides'] = current_selected_slides
        builder_data = json.dumps(builder_data)

        # Updated count of included slides:
        included_slide_count = f'Visualization Session ({len(current_selected_slides)})'

        return [selected_slides], [included_slide_count], [builder_data]

    def update_vis_store(self, new_slide_data, session_data):
        """Updating current visualization session based on selected slide(s)

        :param new_slide_data: New slides to be added to the Visualization Session
        :type new_slide_data: list
        :param session_data: Current Visualization Session data
        :type session_data: str
        :return: Updated Visualization Session 
        :rtype: str
        """
        
        new_slide_data = get_pattern_matching_value(new_slide_data)
        if new_slide_data is None:
            raise exceptions.PreventUpdate
        
        new_slide_data = json.loads(get_pattern_matching_value(new_slide_data))
        session_data = json.loads(session_data)

        user_external_token = self.get_user_external_token(session_data)
        user_internal_id = self.get_user_internal_id(session_data)

        prev_vis_data_in_handler = []
        for i in session_data['current']:
            if i.get('type')=='remote_item':
                if i['url']==self.handler.girderApiUrl:
                    prev_vis_data_in_handler.append(i)
                else:
                    continue
            else:
                prev_vis_data_in_handler.append(i)

        # Adding new slides to session_data
        new_slide_info = []
        local_slide_ids = [i.get('id') for i in session_data.get('local')]
        for s in new_slide_data['selected_slides']:

            if not s.get('id') in local_slide_ids:
                new_slide_info.append(
                    {
                        'name': s.get('name',''),
                        'id': s.get('_id',''),
                        'remote_id': s.get('_id'),
                        'url': self.handler.girderApiUrl,
                        'type': 'remote_item'
                    }
                )

                # Adding access to UserAccess table
                self.database.add_access(
                    item_id = s.get('_id'),
                    user_id = user_internal_id
                )

            else:
                new_slide_info.append(
                    session_data['local'][local_slide_ids.index(s.get('id'))]
                )
        
        prev_slides_in_handler = [i['id'] for i in prev_vis_data_in_handler]
        new_slides_in_handler = [i['id'] for i in new_slide_info]

        if sorted(prev_slides_in_handler)==sorted(new_slides_in_handler):
            return no_update
        else:
            new_slides = [new_slide_info[idx] for idx,i in enumerate(new_slides_in_handler) if not i in prev_slides_in_handler]
            rem_slides = [prev_slides_in_handler[idx] for idx,i in enumerate(prev_slides_in_handler) if not i in new_slides_in_handler]

            for s_idx,s in enumerate(session_data['current']):
                if s['id'] in rem_slides:
                    del session_data['current'][s_idx]
            
            session_data['current'].extend(new_slides)

            return json.dumps(session_data)






