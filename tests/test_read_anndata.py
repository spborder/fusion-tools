"""Testing out reading spatial --omics experimental data from h5ad/zarr format
"""

import os
import sys
sys.path.append('./src/')
import numpy as np

import anndata as ad

import pandas as pd

import large_image_source_zarr
import large_image
import zarr
from PIL import Image

import matplotlib.pyplot as plt
from fusion_tools.utils.shapes import load_label_mask

def main():
    
    # Example data:
    file_path = 'C:\\Users\\samuelborder\\Downloads\\secondary_analysis.h5ad'
    ad_data = ad.read_h5ad(file_path)

    # Extracting spatial coordinates
    coordinates = pd.DataFrame(
        data = ad_data.obsm['spatial'],
        index = ad_data.obs_names,
        columns = ['imagecol','imagerow']
    )
    print(f'Number of observations: {ad_data.n_obs}')
    print('-----------------------')

    # Extracting names of transcripts recorded:
    print(ad_data.var_names)
    print('--------------')
    print(f'Number of variables: {ad_data.n_vars}')
    print('---------')

    # Extracting names of obs
    print(ad_data.obs_names)
    print('---------------')

    # Test reading zarr
    cosmx_zarr = 'C:\\Users\\samuelborder\\Downloads\\data.zarr'
    cosmx_data = zarr.open(cosmx_zarr,mode='r')
    print(cosmx_data.tree())

    cosmx_image = zarr.open(cosmx_zarr+'\\images\\1_image\\0')
    print(dir(cosmx_image))
    print(cosmx_image.attrs.asdict())
    print(cosmx_image.shape)
    print(type(cosmx_image[:,:,:]))
    
    cosmx_numpy = cosmx_image[:,:,:]
    print(np.shape(cosmx_numpy))

    cosmx_numpy = np.moveaxis(cosmx_numpy,source=0,destination=-1)

    cosmx_labels = zarr.open(cosmx_zarr+'\\labels\\1_labels\\0')
    labels_numpy = cosmx_labels[:,:]

    plt.imshow(labels_numpy)
    plt.show()
    plt.imshow(cosmx_numpy)
    plt.show()

    #test_zarr = 'C:\\Users\\samuelborder\\Downloads\\WD1.1_17-03_WT_MP.ome.zarr.zip'
    #zarr_zarr = zarr.open(test_zarr)
    #print(zarr_zarr.tree())
    #l_i_cosmx = large_image_source_zarr.open(test_zarr)
    #print(l_i_cosmx)

    #test_ad_zarr = ad.read_zarr(cosmx_zarr)
    #print(test_ad_zarr)

    #l_i_cosmx = large_image_source_zarr.open(cosmx_zarr+'\\images\\')
    #print(l_i_cosmx)




if __name__=='__main__':
    main()

