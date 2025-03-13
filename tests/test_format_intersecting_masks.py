"""Testing formatting intersecting masks
"""

import os
import sys
import json
sys.path.append('./src/')

from fusion_tools.utils.images import format_intersecting_masks


def main():

    path_to_test_all_annotations = 'C:\\Users\\samuelborder\\Downloads\\fusion-tools-current-layers.json'
    path_to_manual_roi = 'C:\\Users\\samuelborder\\Downloads\\Manual ROI 1.json'

    with open(path_to_test_all_annotations,'r') as f:
        all_anns = json.load(f)
        f.close()

    with open(path_to_manual_roi,'r') as f:
        manual_ann = json.load(f)
        f.close()

    mask_format = 'one-hot-labels'
    intersecting_masks = format_intersecting_masks(
        manual_ann,
        all_anns,
        mask_format
    )
    
    import matplotlib.pyplot as plt

    if not mask_format=='rgb':
        for m in intersecting_masks:
            for i in range(m.shape[-1]):
                plt.imshow(m[:,:,i])
                plt.show()
    else:
        for m in intersecting_masks:
            plt.imshow(m)
            plt.show()

if __name__=='__main__':
    main()