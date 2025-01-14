"""Test recursive path extraction function
"""


def extract_path_parts(current_parts:list, search_key: list = ['props','children']):

    path_pieces = ()
    if type(current_parts)==list:
        for c in current_parts:
            if type(c)==dict:
                for key,value in c.items():
                    if key in search_key:
                        if type(value)==str:
                            path_pieces += (value,)
                        elif type(value) in [list,dict]:
                            path_pieces += extract_path_parts(value)
            elif type(c)==list:
                path_pieces += extract_path_parts(c)
    else:
        for key,value in current_parts.items():
            if key in search_key:
                if type(value)==str:
                    path_pieces+= (value,)
                elif type(value) in [list,dict]:
                    path_pieces += extract_path_parts(value)

    return path_pieces


test_path_components = [
    {
        'props': {
            'children': [
                {'props': {'children': '/collection'}, 'type': 'A', 'namespace': 'dash_html_components'}, 
                {'props': {'children': '/CODEX/', 'id': {'type': '1-dataset-builder-collection-folder-crumb', 'index': 2}, 'style': {'color': 'rgb(0,0,255)'}}, 'type': 'A', 'namespace': 'dash_html_components'},
                {'props': {'children': 'Lung/', 'id': {'type': '1-dataset-builder-collection-folder-crumb', 'index': 2}, 'style': {'color': 'rgb(0,0,255)'}}, 'type': 'A', 'namespace': 'dash_html_components'}
            ], 
            'direction': 'horizontal'
        }, 
        'type': 'Stack', 
        'namespace': 'dash_bootstrap_components'
    }
]


def main():

    path = extract_path_parts(test_path_components)

    print(path)

if __name__=='__main__':
    main()


