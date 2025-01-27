"""Test parsing CLI XML
"""

import os
import sys

import lxml.etree
import requests
import lxml
import json

parameter_tags = ['integer','float','double','boolean','string','integer-vector','float-vector','double-vector','string-vector',
                  'integer-enumeration','float-enumeration','double-enumeration','string-enumeration','file','directory','image',
                  'geometry','point','pointfile','region','table','transform']

# Additional options (which don't appear on a lot of the plugins we've made)
# constraints (not for use in vector or enumeration)
#   # includes minimum, maximum, step (which can be 0)

# slicer schema includes examples of text output from CLI, (specifying --returnparameterfile file_name)
# but I don't think that goes anywhere on Girder

def main():

    api_url = 'http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1/'
    plugin_id = '63e6bc1da00b00eade3047c1'
    girder_token = ''
    xml_req = requests.get(
        api_url+f'slicer_cli_web/cli/{plugin_id}/xml?token={girder_token}'
    )

    xml_data = lxml.etree.fromstring(xml_req.content)
    print(f"Number of parameters: {len(xml_data.findall('parameters'))}")
    print(xml_data.find('title').text)
    print(xml_data.find('description').text)
    xml_params = xml_data.findall('parameters')
    
    # Parameters are broken into groups with names (first one is IO)
    for param in xml_data.iterfind('parameters'):
        # .keys() on an element returns the "attrib" names
        #param_attribs = param.keys()
        # .items() returns (name,value) sequence of "attrib"s
        # .get(key,default=None) will return the value of the "attrib" "key" if it's present, otherwise will return "default"
        is_advanced = param.get('advanced',default=False)
        if is_advanced:
            print(f'{param.find("label").text} is an advanced set of parameters!')
        else:
            print(f'{param.find("label").text} is not an advanced set of parameters!')

        print(param.find('description').text)
        print('---------------------------------')
        for sub_el in param:
            if sub_el.tag in parameter_tags:
                print(f'Input param: {sub_el.find("label").text} is of the type: {sub_el.tag}')
                default_value = sub_el.find('default')
                if not default_value is None:
                    print(f'default value: {default_value.text}')
                else:
                    print('No default value')

                if 'enumeration' in sub_el.tag:
                    print('Enumeration options:')
                    for opt_idx,opt in enumerate(sub_el.iterfind('element')):
                        print(f'Option: {opt_idx}: {opt.text}')


if __name__=='__main__':
    main()




































