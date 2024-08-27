"""
Utility functions for visualization components

"""
import os
import sys



def get_pattern_matching_value(input_val):
    """
    Used to extract usable values from components generated using pattern-matching syntax.
    """
    if type(input_val)==list:
        if len(input_val)>0:
            return_val = input_val[0]
            if type(return_val)==list:
                if len(return_val)==0:
                    return_val = None
                
        else:
            return_val = None
    elif input_val is None:
        return_val = input_val
    else:
        return_val = input_val

    return return_val



































