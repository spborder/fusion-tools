"""

Extracting nested properties for assembling tree_antd selectors.

Specifications:
    - Should work for arbitrary levels of nesting for each property
    - Should only include unique items

"""
import numpy as np

test_list = ['prop1','prop2','prop3', 'prop2',
             'prop4 --> sub_prop1', 'prop4 --> sub_prop2', 'prop4 --> sub_prop3', 'prop4 --> sub_prop3',
             'prop5 --> sub_prop1 --> sub_sub_prop1', 'prop5 --> sub_prop1 --> sub_sub_prop2', 'prop5 --> sub_prop2']

def generate_property_dict(all_property_list, title: str = 'Features', ignore_list: list = []):

    all_properties = {
        'title': title,
        'key': '0',
        'children': []
    }

    def add_prop_level(level_children, prop, index_list):
        new_keys = {}
        if len(level_children)==0:
            if not prop[0] in ignore_list:
                new_key = f'{"-".join(index_list)}-0'
                p_dict = {
                    'title': prop[0],
                    'key': new_key,
                    'children': []
                }
                l_dict = p_dict['children']
                new_keys[new_key] = prop[0]
                for p_idx,p in enumerate(prop[1:]):
                    if not p in ignore_list:
                        new_key = f'{"-".join(index_list+["0"]*(p_idx+2))}'
                        l_dict.append({
                            'title': p,
                            'key': new_key,
                            'children': []
                        })
                        l_dict = l_dict[0]['children']
                        new_keys[new_key] = ' --> '.join(prop[:p_idx+2])

                level_children.append(p_dict)
        else:
            for p_idx,p in enumerate(prop):
                if not p in ignore_list:
                    if any([p==i['title'] for i in level_children]):
                        title_idx = [i['title'] for i in level_children].index(p)
                        level_children = level_children[title_idx]['children']
                        index_list.append(str(title_idx))
                    else:
                        new_key = f'{"-".join(index_list)}-{len(level_children)}'
                        level_children.append({
                            'title': p,
                            'key': new_key,
                            'children': []
                        })
                        level_children = level_children[-1]['children']
                        index_list.append("0")
                        new_keys[new_key] = ' --> '.join(prop[:p_idx+1])
        
        return new_keys
    
    list_levels = [i.split(' --> ') if '-->' in i else [i] for i in all_property_list]
    unique_levels = list(set([len(i) for i in list_levels]))
    sorted_level_idxes = np.argsort(unique_levels)[::-1]
    property_keys = {}
    for s in sorted_level_idxes:
        depth_count = unique_levels[s]
        props_with_level = [i for i in list_levels if len(i)==depth_count]
        for p in props_with_level:
            feature_children = all_properties['children']
            property_keys = property_keys | add_prop_level(feature_children,p,['0'])
    
    return all_properties, property_keys

def main():

    ignore_list = ['prop3','sub_prop3']
    all_properties, property_keys = generate_property_dict(test_list,ignore_list = ignore_list)
    import json
    print(json.dumps(all_properties,indent=4))
    print(property_keys)




if __name__=='__main__':
    main()

