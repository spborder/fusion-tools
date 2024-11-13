"""Testing get_gene_info
"""

import sys
sys.path.append('./src/')
from fusion_tools.utils.omics import get_gene_info

import pandas as pd
import anndata as ad



def main():
    test = ad.read_h5ad("C:\\Users\\samuelborder\\Desktop\\HIVE_Stuff\\FUSION\\Test Upload\\non_kidney\\secondary_analysis (1).h5ad")
    print(test.var_names)
    print(test.var_names.tolist()[0])
    test_gene_info = get_gene_info(test.var_names.tolist()[0].split('.')[0])

    print(test_gene_info)


if __name__=='__main__':
    main()


