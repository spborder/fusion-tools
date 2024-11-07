"""Testing out extracting nested properties from a dictionary
"""

import os
import sys
sys.path.append('./src/')

from fusion_tools.utils.shapes import extract_nested_prop


test_dict = {
    'main_prop': {
        'sub_prop1': 1,
        'sub_prop2': {
            'sub_subprop1': 2
        },
        'sub_prop3': {
            'sub_subprop1': 3,
            'sub_subprop2': {
                'sub_sub_subprop1': 4
            }
        }
    }
}

for d in range(0,7):
    print(f'-------------depth: {d}-------------')
    value = extract_nested_prop(test_dict, d)
    for v in value:
        print(v)



