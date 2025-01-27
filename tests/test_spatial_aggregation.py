"""Testing spatial aggregation function (different versions)
"""

import os
import sys
sys.path.append('./src/')
import uuid

from fusion_tools.utils.shapes import spatially_aggregate
from fusion_tools.handler.dsa_handler import DSAHandler

def main():

    # Get annotations (with some overlapping and some not overlapping)
    # Add properties to annotations (multiple different nested levels)
    # Test 1) spatial aggregation, separate=True, summarize=True
    # Test 2) spatial aggregation, separate=False, summarize=True
    # Test 3) spatial aggregation, separate = True, summarize = False
    # Test 4) spatial aggregation, separate = False, summarize = False

    dsa_handler = DSAHandler(
        girderApiUrl='http://ec2-3-230-122-132.compute-1.amazonaws.com:8080/api/v1'
    )

    annotations = dsa_handler.get_annotations(
        item = '64f545302d82d04be3e39eec'
    )

    print(f'len of annotations: {len(annotations)}')
    print([i['properties']['name'] for i in annotations])

    # Clearing properties from the glomeruli:
    glomeruli = annotations[0]
    spots = annotations[1]

    for f_idx, f in enumerate(glomeruli['features']):
        f['properties'] = {
            'name': 'Glomeruli',
            '_id': uuid.uuid4().hex[:24],
            '_index': f_idx
        }
    
    print(glomeruli['features'][0]['properties'])

    ## Test 1: spatial aggregation, separate = True, summary = True
    agg_gloms1 = spatially_aggregate(glomeruli,[spots],separate=True,summarize=True)
    print('--------------------separate = True, summarize = True---------------------------')
    print(agg_gloms1['features'][0]['properties'])
    print('\n\n\n')

    ## Test 2: spatial aggregation, separate = False, summary = True
    agg_gloms2 = spatially_aggregate(glomeruli,[spots],separate=False,summarize=True)
    print('--------------------separate = False, summarize = True---------------------------')
    print(agg_gloms2['features'][0]['properties'])
    print('\n\n\n')

    ## Test 3: spatial aggregation, separate = True, summary = False
    agg_gloms3 = spatially_aggregate(glomeruli,[spots],separate=True,summarize=False)
    print('--------------------separate = True, summarize = False---------------------------')
    print(agg_gloms3['features'][0]['properties'])
    print('\n\n\n')
    
    ## Test 4: spatial aggregation, sepate = False, summary = False
    agg_gloms4 = spatially_aggregate(glomeruli,[spots],separate=False,summarize=False)
    print('--------------------separate = False, summarize = False---------------------------')
    print(agg_gloms4['features'][0]['properties'])
    print('\n\n\n')





if __name__=='__main__':
    main()

