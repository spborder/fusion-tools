"""Test dash_table with dropdowns in specific cells
"""


from dash import Dash, dash_table, html
import pandas as pd
from collections import OrderedDict


app = Dash(__name__)

df = pd.DataFrame(OrderedDict([
    ('row_id', [1,2,3,4]),
    ('climate', ['Sunny', 'Snowy', 'Sunny', 'Rainy']),
    ('temperature', [13, 43, 50, 30]),
    ('city', ['NYC', 'Montreal', 'Miami', 'NYC'])
]))

required_metadata = [
    {
        'name': 'Image Type',
        'values': ['Histology','Fluorescence','Unknown'],
        'required': True
    },
    {
        'name': 'Image Label',
        'values': ['Label 1','Label 2','Label 3'],
        'required': False
    },
    {
        'name': 'Extra'
    }
]

df = pd.DataFrame(
    {'Key': i['name'], 'Value': '', 'row_id': idx}
    for idx,i in enumerate(required_metadata)
)
use_drop = [0,1]
print(df)


app.layout = html.Div([
    dash_table.DataTable(
        id='table-dropdown',
        data=df.to_dict('records'),
        columns=[
            {'id': 'Key', 'name': 'Key'},
            {'id': 'Value', 'name': 'Value', 'presentation': 'dropdown'},
        ],
        editable=True,
        row_deletable = True,
        style_data_conditional = [
            {
                'if': {
                    'filter_query': '{row_id} eq '+str(t),
                },
                'border': '2px solid rgb(255,0,0)'
            }
            for t in use_drop
        ],
        dropdown_conditional=[
            {
                'if': {
                    'column_id': 'Value',
                    'filter_query': '{row_id} eq '+str(j_idx)
                },
                'options': [
                    {'label': i, 'value': i}
                    for i in j['values']
                ]
            }
            for j_idx,j in enumerate(required_metadata)
            if 'values' in j
        ]
    ),
    html.Div(id='table-dropdown-container')
])


if __name__ == '__main__':
    app.run_server(debug=True)