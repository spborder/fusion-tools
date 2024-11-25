"""test recursive property extraction
"""
import json

def read_dict_list(dict_list,main_list = [],sub_list = None):
    for d in dict_list:
        if type(d)==dict:
            title = list(d.keys())[0]
            print(f'title: {title}')

            nested = [{key:val} for key,val in d[title].items() if type(val)==dict]
            non_nested = [{'SubProperty': key, 'Value': val} for key,val in d[title].items() if not type(val)==dict]
            main_list.append(non_nested)
            read_dict_list(nested,main_list,[])
    return main_list


def main():

    test_list = [
        {
            'main_prop': {
                'sub_prop1': {},
                'sub_prop2': {
                    'sub_subprop1': 2
                },
                'sub_prop3': {
                    'sub_subprop1': {
                        'sub_key': 'sub_val',
                        'sub_key2': 'sub_val2'
                    },
                    'sub_subprop2': {
                        'sub_sub_subprop1': 4
                    }
                }
            }
        },
        {
            'main_prop2': {
                'sub_prop2': {
                    'key1': 'val1',
                    'key2': 'val2',
                    'key3': 'val3',
                    'nested_key': {
                        'n_key1': 'n_val1',
                        'n_key2': 'n_val2'
                    }
                }
            }
        }
    ]

    print(json.dumps(test_list,indent=4))

    print(read_dict_list(test_list))



if __name__=='__main__':
    main()


