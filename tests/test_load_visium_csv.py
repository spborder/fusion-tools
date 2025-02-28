"""Loading Visium annotations from CSV
"""

import os
import sys
sys.path.append('./src/')

from fusion_tools.utils.shapes import load_visium

def main():
    
    # This one 
    coords_path = 'C:\\Users\\samuelborder\\Downloads\\coordinates.csv'
    visium_coords = load_visium(coords_path)
    print(len(visium_coords['features']))


if __name__=='__main__':
    main()
