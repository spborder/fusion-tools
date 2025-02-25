"""Testing new plugin+resource selector+plugin runner components
"""

import os
import sys
sys.path.append('./src/')
import json

from fusion_tools.handler.dsa_handler import DSAHandler
from fusion_tools.handler.dsa_handler import DSAPluginRunner

from dash import dcc
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from dash_extensions.enrich import DashProxy, MultiplexerTransform, html

test_plugin = {
    'name': 'NucleiDetection',
    'image': 'dsarchive/histomicstk:latest',
    'input_args': [
        {
            'name': 'inputImageFile',
            'default': {
                'type': 'input_file',
                'name': 'Image'
            },
            'disabled': True
        },
        {
            'name': 'outputNucleiAnnotationFile_folder',
            'default': {
                'type': 'upload_folder'
            },
            'disabled': True
        },
        {
            'name': 'outputNucleiAnnotationFile',
            'default': {
                'value': 'nuclei_annotations.annot'
            },
            'disabled': True
        },
        'nuclei_annotation_format',
        'min_nucleus_area',
        'ignore_border_nuclei',
        'ImageInversionForm'
    ]
}

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

    plugin_runner_component = DSAPluginRunner(
        handler = dsa_handler
    )

    session_data = {
        'current_user': dsa_handler.authenticate_new(
            username = user_name,
            password = p_word
        )
    }

    plugin_runner_component.load(0)
    plugin_runner_component.gen_layout(session_data)

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
    main_app.layout = dmc.MantineProvider(html.Div(
        [
            dcc.Store(
                id = 'anchor-vis-store',
                data = json.dumps(session_data),
                storage_type='memory'
            ),
            dbc.Card([
                dbc.CardHeader(plugin_runner_component.title),
                dbc.CardBody([
                    plugin_runner_component.blueprint.embed(main_app),
                ])
            ])
        ]
    ))

    main_app.run(
        port = '8050',
        debug=True
    )

if __name__=='__main__':
    main()


