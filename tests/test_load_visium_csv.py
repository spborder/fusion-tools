"""Loading Visium annotations from CSV
"""

import os
import sys
sys.path.append('./src/')
import json

from fusion_tools.utils.shapes import load_visium

def main():
    
    # 
    base_dir = 'C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\KPMP_Atlas_V2\\'
    coords_path = base_dir+'V10S14-085_XY01_20-0038\\V10S14-085_XY01_20-0038_spot_info.csv'
    scale_factors = coords_path.replace('_spot_info.csv','_scalefactors.json')

    with open(scale_factors,'r') as f:
        scales = json.load(f)
        f.close()

    visium_coords = load_visium(
        coords_path,
        include_var_names=['DCT1'],
        scale_factor=scales['lowres']
    )
    print(len(visium_coords['features']))
    print(visium_coords['features'][0]['properties'])



if __name__=='__main__':
    main()
