"""

Components which deal with access of external APIs for data/embeddable widgets


"""

import os
import sys
import json
import numpy as np
import pandas as pd

from io import BytesIO
import requests

# Dash imports
import dash
dash._dash_renderer._set_react_version('18.2.0')
from dash import dcc, callback, ctx, ALL, MATCH, exceptions, Patch, no_update, dash_table
from dash.dash_table.Format import Format, Scheme
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
#import dash_treeview_antd as dta
from dash_extensions.enrich import DashBlueprint, html, Input, Output, State, PrefixIdTransform, MultiplexerTransform, BlockingCallbackTransform
from dash_extensions.javascript import Namespace, arrow_function

# fusion-tools imports
from fusion_tools.visualization.vis_utils import get_pattern_matching_value
from fusion_tools.components.base import Tool

import time
from tqdm import tqdm


class HRAViewer(Tool):
    """HRAViewer Tool which enables hierarchy visualization for organs, cell types, biomarkers, and proteins in the Human Reference Atlas

    For more information on the Human Reference Atlas (HRA), see: https://humanatlas.io/. Thanks Bruce!

    :param Tool: General class for interactive components that visualize, edit, or perform analyses on data.
    :type Tool: None
    """

    title = 'HRA Viewer'
    description = 'Select one of the embedded components below or select an organ to view the ASCT+B table for that organ'

    def __init__(self):
        """Constructor method
        """
        
        super().__init__()

        self.hra_collection = "https://purl.humanatlas.io/collection/hra"

        try:
            self.asct_b_release = self.get_latest_asctb()

            self.organ_table_options = [
                {'label': f'{i} ASCT+B Table', 'value': i, 'disabled': False}
                for i in list(self.asct_b_release.keys())
            ]

            self.show_asct_b_error = False

        except Exception as e:
            print(f'Error initializing HRAViewer: {e}')
            self.asct_b_release = None
            self.organ_table_options = []

            self.show_asct_b_error = True

    def fetch_json(self, purl_str: str):
        """Run GET request and return JSON data

        :param purl_str: String URL for request
        :type purl_str: str
        """

        response = requests.get(purl_str, headers = {'Accept': 'application/json'})
        response.raise_for_status()

        return response.json()
    
    def is_asctb_table(self, digital_object:str):
        """Check if digital object string is for an ASCT+B table

        :param digital_object: String corresponding to digital object
        :type digital_object: str
        """

        return (
            digital_object.startswith("https://purl.humanatlas.io/asct-b/")
            and "crosswalk" not in digital_object
        )

    def get_latest_asctb(self):
        """Get latest set of ASCT+B tables from Human Atlas collections
        """

        hra_collections = self.fetch_json(self.hra_collection)
        digital_objects = hra_collections["metadata"]["had_member"]

        iter_objects = sorted(filter(self.is_asctb_table,digital_objects))
        tables = {}
        with tqdm(iter_objects) as pbar:
            for purl in iter_objects:
                table_name = purl.split("/")[-2].replace('-','_')
                table_data = self.fetch_json(purl)
                table_attribution = self.fetch_json(purl.replace("purl","lod"))

                pbar.set_description(f'On: {table_name}')

                table_metadata = {
                    'version': table_attribution.get('version','v1.0'),
                    'creation_data': table_attribution.get('creation_date',''),
                    'doi': table_attribution.get('was_derived_from',{}).get('doi',''),
                    'citation': table_attribution.get('citiation',''),
                    'description': table_attribution.get('was_derived_from',{}).get('description',''),
                    'authors': [
                        {
                            'fullName': i.get('fullName',''),
                            'firstName': i.get('firstName',''),
                            'lastName': i.get('lastName',''),
                            'orcid': i.get('orcid','')
                        }
                        for i in table_attribution.get('was_derived_from',{}).get('creators',[])
                    ],
                    'reviewers': [
                        {
                            'fullName': i.get('fullName',''),
                            'firstName': i.get('firstName',''),
                            'lastName': i.get('lastName',''),
                            'orcid': i.get('orcid','')
                        }
                        for i in table_attribution.get('was_derived_from',{}).get('reviewers',[])
                    ]
                }

                table_rows = table_data['data']['asctb_record']

                organ_table = []
                for o_idx,o in enumerate(table_rows):
                    an_structs = o.get('anatomical_structure_list',[])
                    c_types = o.get('cell_type_list',[])
                    g_markers = o.get('gene_marker_list',[])
                    p_markers = o.get('protein_marker_list',[])

                    as_cols = [
                        {
                            f'{j.get("id","").split("#")[-1].split("-")[-1]}': j.get("ccf_pref_label","-"),
                            f'{j.get("id","").split("#")[-1].split("-")[-1]} ID': j.get("source_concept","-")
                        }
                        for j in an_structs
                    ]

                    ct_cols = [
                        {
                            f'{j.get("id","").split("#")[-1].split("-")[-1]}': j.get("ccf_pref_label","-"),
                            f'{j.get("id","").split("#")[-1].split("-")[-1]} ID': j.get("source_concept","-")
                        }
                        for j in c_types
                    ]

                    gm_cols = [
                        {
                            f'{j.get("id","").split("#")[-1].split("-")[-1]}': j.get("ccf_pref_label","-"),
                            f'{j.get("id","").split("#")[-1].split("-")[-1]} ID': j.get("source_concept","-")
                        }
                        for j in g_markers
                    ]

                    pm_cols = [
                        {
                            f'{j.get("id","").split("#")[-1].split("-")[-1]}': j.get("ccf_pref_label","-"),
                            f'{j.get("id","").split("#")[-1].split("-")[-1]} ID': j.get("source_concept","-")
                        }
                        for j in p_markers
                    ]

                    row_data = {}
                    for col in as_cols+ct_cols+gm_cols+pm_cols:
                        row_data = row_data | col

                    organ_table.append(row_data)


                tables[table_name] = {
                    'organ_table': organ_table,
                    'metadata': table_metadata
                }
                pbar.update(1)
            
        return tables

    def gen_layout(self, session_data: dict):
        """Generate layout for HRA Viewer component
        """

        layout = html.Div([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row(
                        dbc.Col(html.H3(self.title))
                    ),
                    html.Hr(),
                    dbc.Row(
                        dbc.Col(self.description)
                    ),
                    html.Hr(),
                    html.Div(
                        id = {'type': 'hra-viewer-error-div','index': 0},
                        children = [
                            dbc.Alert(
                                color = 'danger',
                                children = [
                                    dbc.Row([
                                        dbc.Col([
                                            f'Error loading ASCT+B Tables'
                                        ],md = 8),
                                        dbc.Col([
                                            html.A(
                                                html.I(
                                                    className = 'fa-solid fa-rotate fa-2x',
                                                    n_clicks = 0,
                                                    id = {'type': 'hra-viewer-refresh-icon','index': 0}
                                                )
                                            ),
                                            dbc.Tooltip(
                                                target = {'type': 'hra-viewer-refresh-icon','index': 0},
                                                children = 'Click to re-try grabbing ASCT+B tables'
                                            )],
                                            md = 4
                                        )
                                    ])
                                ]
                            )
                        ] if self.show_asct_b_error else []
                    ),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('HRA View Select: ',html_for = {'type': 'hra-viewer-drop','index': 0})
                        ],md=2),
                        dbc.Col([
                            dcc.Dropdown(
                                options = [
                                    {'label': 'FTU Explorer','value': 'FTU Explorer','disabled': False},
                                ] + self.organ_table_options,
                                value = [],
                                multi = False,
                                id = {'type': 'hra-viewer-drop','index': 0}
                            )
                        ], md = 10)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div(
                                id = {'type': 'hra-viewer-parent','index': 0},
                                children = [],
                            )
                        ])
                    ],align='center')
                ])
            ])
        ],style = {'width': '100%'})

        self.blueprint.layout = layout

    def get_callbacks(self):
        """Initializing callbacks and attaching to DashBlueprint
        """

        self.blueprint.callback(
            [
                Input({'type': 'hra-viewer-drop','index': ALL},'value')
            ],
            [
                Output({'type': 'hra-viewer-parent','index': ALL},'children')
            ]
        )(self.update_hra_viewer)

        self.blueprint.callback(
            [
                Input({'type': 'hra-viewer-refresh-icon','index': ALL},'n_clicks')
            ],
            [
                Output({'type': 'hra-viewer-error-div','index': ALL},'children'),
                Output({'type': 'hra-viewer-drop','index': ALL},'options')
            ]
        )(self.refresh_asctb_tables)

    def get_organ_table(self, organ:str):
        """Grabbing ASCT+B Table for a specific organ

        :param organ: Name of organ to get table for
        :type organ: str
        """
        
        if organ in self.asct_b_release:
            new_table = pd.DataFrame.from_records(self.asct_b_release[organ]['organ_table']).fillna('-')
            sorted_cols = sorted([i for i in new_table if 'AS' in i]) + sorted([i for i in new_table if 'CT' in i]) + sorted([i for i in new_table if 'BM' in i]) + sorted([i for i in new_table if 'P' in i])
            new_table = new_table.reindex(sorted_cols,axis=1)
            
            table_attribution = self.asct_b_release[organ]['metadata']

        else:
            new_table = None
            table_attribution = None

        return new_table, table_attribution

    def update_hra_viewer(self, viewer_drop_value):
        """Updating the HRAViewer component based on selected view

        :param viewer_drop_value: Selected component from dropdown (one of FTU Explorer or {organ} ASCT+B Table)
        :type viewer_drop_value: list
        """
        """
        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        """

        viewer_drop_value = get_pattern_matching_value(viewer_drop_value)

        if viewer_drop_value is None:
            raise exceptions.PreventUpdate

        viewer_children = no_update
        if viewer_drop_value=='FTU Explorer':

            viewer_children = html.Iframe(
                srcDoc = '''
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="utf-8" />
                        <title>FTU Ui Small Web Component</title>
                        <meta name="viewport" content="width=device-width, initial-scale=1" />
                        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&display=swap" rel="stylesheet" />
                        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet" />
                        <link
                        rel="stylesheet"
                        href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
                        />
                        <link href="https://cdn.humanatlas.io/ui/ftu-ui-small-wc/styles.css" rel="stylesheet" />
                        <script src="https://cdn.humanatlas.io/ui/ftu-ui-small-wc/wc.js" defer></script>
                    </head>
                    <body style="margin: 0">
                        <hra-ftu-ui-small
                        base-href="https://cdn.humanatlas.io/ui/ftu-ui-small-wc/"
                        selected-illustration="https://purl.humanatlas.io/2d-ftu/kidney-renal-corpuscle"
                        datasets="assets/TEMP/ftu-datasets.jsonld"
                        summaries="assets/TEMP/ftu-cell-summaries.jsonld"
                        >
                        </hra-ftu-ui-small>
                    </body>
                    </html>
                ''',
                style = {
                    'height': '1000px','width': '100%','overflow': 'scroll'
                }
            )
        
        if not self.asct_b_release is None:
            if viewer_drop_value in self.asct_b_release:
                
                organ_table, table_attribution = self.get_organ_table(viewer_drop_value)
                organ_table[list(organ_table)] = organ_table[list(organ_table)].astype(str)

                
                if not organ_table is None and not table_attribution is None:
                    
                    reviewers_and_authors = [
                        dbc.Row([
                            dbc.Col([
                                dbc.Label(
                                    html.H4('Authors:'),
                                    html_for={'type': f'{self.component_prefix}-hra-viewer-authors','index': 0}
                                )
                            ])
                        ]),
                        dbc.Row([
                            dbc.Col([
                                html.Div(
                                    dmc.AvatarGroup(
                                        id = {'type': f'{self.component_prefix}-hra-viewer-authors','index': 0},
                                        children = [
                                            html.A(
                                                dmc.Tooltip(
                                                    dmc.Avatar(
                                                        ''.join([n[0] for n in author.get('fullName').split()]),
                                                        radius = 'xl',
                                                        size = 'lg',
                                                        color = f'rgb({np.random.randint(0,255)},{np.random.randint(0,255)},{np.random.randint(0,255)})'
                                                    ),
                                                    label = author.get('fullName'),
                                                    position = 'bottom'
                                                ),
                                                href = f'https://orcid.org/{author.get("orcid")}',
                                                target = '_blank'
                                            )
                                            for author in table_attribution['authors']
                                        ]
                                    )
                                )
                            ])
                        ],style={'marginBottom': '5px'},align='center'),
                        dbc.Row([
                            dbc.Col(
                                dbc.Label(
                                    html.H6(
                                        'Reviewers: '
                                    ),
                                    html_for={'type': f'{self.component_prefix}-hra-viewer-reviewers','index': 0}
                                )
                            )
                        ]),
                        dbc.Row([
                            dbc.Col([
                                html.Div(
                                    dmc.AvatarGroup(
                                        id = {'type': f'{self.component_prefix}-hra-viewer-reviewers','index': 0},
                                        children = [
                                            html.A(
                                                dmc.Tooltip(
                                                    dmc.Avatar(
                                                        ''.join([n[0] for n in reviewer.get('fullName').split()]),
                                                        radius = 'xl',
                                                        size = 'md',
                                                        color = f'rgb({np.random.randint(0,255)},{np.random.randint(0,255)},{np.random.randint(0,255)})'
                                                    ),
                                                    label = reviewer.get('fullName'),
                                                    position = 'bottom'
                                                ),
                                                href = f'https://orcid.org/{reviewer.get("orc_id")}',
                                                target = '_blank'
                                            )
                                            for reviewer in table_attribution['reviewers']
                                        ]
                                    )
                                )]
                            )
                        ],style = {'marginBottom':'5px'})
                    ]

                    organ_dash_table = [
                        dash_table.DataTable(
                            id = {'type':f'{self.component_prefix}-hra-viewer-table','index': 0},
                            columns = [{'name':i,'id':i,'deletable':False,'selectable':True} for i in organ_table.columns],
                            data = organ_table.to_dict('records'),
                            editable = False,
                            filter_action='native',
                            sort_action='native',
                            sort_mode='multi',
                            style_table = {
                                'overflowX': 'auto',
                                'maxWidth': '800px'
                            },
                            tooltip_data = [
                                {
                                    column: {'value': str(value),'type':'markdown'}
                                    for column,value in row.items()
                                } for row in organ_table.to_dict('records')
                            ],
                            tooltip_duration = None
                        )
                    ]
                    
                    data_doi = dbc.Row([
                            dbc.Col(
                                dmc.NavLink(
                                    label = html.Div(f'Data DOI: {table_attribution.get("doi","").split("/")[-1]}',style={'align':'center'}),
                                    href = table_attribution.get('doi',''),
                                    target = '_blank'
                                ),
                                md = 12
                            )
                        ],align = 'center')
                

                    viewer_children = dbc.Row([
                        dbc.Col([
                            html.Div([
                                html.Div(reviewers_and_authors),
                                html.Hr(),
                                dbc.Row([
                                    dbc.Col([
                                        html.Div(
                                            organ_dash_table,
                                            style = {'maxHeight': '500px','overflow': 'scroll','width': '100%'}
                                        )
                                    ],md = 'auto')
                                ]),
                                html.Hr(),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label(
                                            html.H6('Table Data Sources:'),
                                            html_for={'type':f'{self.component_prefix}-hra-viewer-table-sources','index':0}
                                        )
                                    ],md=12)
                                ]),
                                data_doi,
                                dbc.Row([
                                    dbc.Col(
                                        dbc.Label('Date: ',html_for = {'type': f'{self.component_prefix}-hra-viewer-date','index': 0}),
                                        md = 4
                                    ),
                                    dbc.Col(
                                        table_attribution.get('creation_data',''),
                                        md = 8
                                    )
                                ],align='center'),
                                dbc.Row([
                                    dbc.Col(
                                        dbc.Label('Version Number: ',html_for = {'type':f'{self.component_prefix}-hra-viewer-version','index': 0}),
                                        md = 4
                                    ),
                                    dbc.Col(
                                        table_attribution.get('version',''),
                                        md = 8
                                    )
                                ],align='center')
                            ])
                        ],
                        width = True)
                    ],style={'width':'100%'})

                else:
                    viewer_children = dbc.Alert(f'Unable to get ASCT+B Table for {viewer_drop_value}',color='warning')
            else:
                viewer_children = dbc.Alert(f'Unable to get ASCT+B Table for {viewer_drop_value}',color='warning')

        return [viewer_children]

    def refresh_asctb_tables(self, refresh_clicked):

        if not any([i['value'] for i in ctx.triggered]):
            raise exceptions.PreventUpdate
        
        try:
            self.asct_b_release = self.get_latest_asctb()

            self.organ_table_options = [
                {'label': f'{i} ASCT+B Table', 'value': i, 'disabled': False}
                for i in self.asct_b_release['Organ'].tolist()
            ]

            return_options = {'label': 'FTU Explorer','value': 'FTU Explorer','disabled': False} + self.organ_table_options
            return_error_div = dbc.Alert(
                'Success',
                color = 'success',
                dismissable=True
            )
        except Exception as e:
            print(e)
            return_options = no_update
            return_error_div = dbc.Alert(
                color = 'danger',
                children = [
                    dbc.Row([
                        dbc.Col([
                            f'Error loading ASCT+B Tables'
                        ],md = 8),
                        dbc.Col([
                            html.A(
                                html.I(
                                    className = 'fa-solid fa-rotate fa-2x',
                                    n_clicks = 0,
                                    id = {'type': f'{self.component_prefix}-hra-viewer-refresh-icon','index': 0}
                                )
                            ),
                            dbc.Tooltip(
                                target = {'type': f'{self.component_prefix}-hra-viewer-refresh-icon','index': 0},
                                children = 'Click to re-try grabbing ASCT+B tables'
                            )],
                            md = 4
                        )
                    ])
                ]
            )
    

        return [return_error_div],[return_options]








