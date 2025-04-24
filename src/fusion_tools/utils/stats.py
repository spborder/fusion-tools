import os
import sys

import numpy as np
import pandas as pd

from scipy import stats
from statsmodels.stats.multitest import multipletests
from sklearn.metrics import silhouette_score, silhouette_samples



def get_label_statistics(data_df:pd.DataFrame, label_col:str):
    """Get output of statistical test for data and it's labels

    :param data_df: Dataframe containing properties for each group as well as the label column
    :type data_df: pd.DataFrame
    :param label_col: Column containing group information for data
    :type label_col: str
    """

    unique_labels = data_df[label_col].unique().tolist()
    unique_labels_count = data_df[label_col].value_counts().to_dict()

    unique_labels = [u for u,count in unique_labels_count.items() if count>1]

    p_value = None
    results = None

    if data_df.shape[1]==2:
        # This means there is one property and the label column
        if len(unique_labels)==2:
            # This is a t-test
            group_a = data_df[data_df[label_col].str.match(unique_labels[0])].loc[:,[i for i in data_df if not i==label_col]].values.astype(float)
            group_b = data_df[data_df[label_col].str.match(unique_labels[1])].loc[:,[i for i in data_df if not i==label_col]].values.astype(float)

            try:
                stats_result = stats.ttest_ind(group_a,group_b)
            except TypeError:
                return p_value, results
            
            t_statistic = stats_result.statistic
            p_value = stats_result.pvalue
            confidence_interval = stats_result.confidence_interval(confidence_level=0.95)

            results = pd.DataFrame({
                't Statistic': t_statistic,
                'p Value': p_value,
                '95% Confidence Interval (Lower)': confidence_interval.low,
                '95% Confidence Interval (Upper)': confidence_interval.high
            },index=[0]).round(decimals=4)

        elif len(unique_labels)>2:
            # This is a one-way ANOVA (Analysis of Variance)
            group_data = []
            for u in unique_labels:
                group_data.append(
                    data_df[data_df[label_col].str.match(u)].loc[:,[i for i in data_df if not i==label_col]].values.flatten().tolist()
                )
            
            stats_result = stats.f_oneway(*group_data)
            f_stat = stats_result.statistic
            p_value = stats_result.pvalue

            anova_df = pd.DataFrame({
                'F Statistic': f_stat,
                'p Value':p_value
            },index = [0]).round(decimals=4)

            tukey_result = stats.tukey_hsd(*group_data)
            _ = tukey_result.confidence_interval(confidence_level = 0.95)

            # tukey_result is a TukeyHSDResult object, have to assemble the outputs manually because scipy developers are experiencing a gas leak.
            tukey_data = []
            for i in range(tukey_result.pvalue.shape[0]):
                for j in range(tukey_result.pvalue.shape[0]):
                    if i != j:
                        row_dict = {
                            'Comparison': ' vs. '.join([unique_labels[i],unique_labels[j]]),
                            'Statistic': f'{tukey_result.statistic[i,j]:>10.3f}',
                            'p-value': f'{tukey_result.pvalue[i,j]:>10.3f}',
                            'Lower CI': f'{tukey_result._ci.low[i,j]:>10.3f}',
                            'Upper CI': f'{tukey_result._ci.high[i,j]:>10.3f}'
                        }
                        tukey_data.append(row_dict)

            tukey_df = pd.DataFrame(tukey_data).round(decimals=4)
            
            results = {
                'anova': anova_df,
                'tukey': tukey_df
            }

        else:
            p_value = np.inf
            results = {}

    elif data_df.shape[1]>2:
        if data_df.shape[1]==3:
            # Calculating Pearson's correlation for each group separately
            pearson_r_list = []
            p_value = []
            property_col_idxes = [i for i in range(data_df.shape[1]) if not data_df.columns.tolist()[i]==label_col]
            for u_l in unique_labels:
                # For each label, generate a new table with r
                group_data = data_df[data_df[label_col].str.match(u_l)].values
                group_r,group_p = stats.mstats.pearsonr(
                    group_data[:,property_col_idxes[0]].astype(float),
                    group_data[:,property_col_idxes[1]].astype(float)
                )
                
                pearson_r_list.append(group_r)
                p_value.append(group_p)

            results = pd.DataFrame(
                data = {
                    'Label': unique_labels,
                    'Pearson r': pearson_r_list, 
                    'p-value':p_value
                }
            ).round(decimals=4)

        elif data_df.shape[1]>3:
            # This calculates silhouette score for each group
            overall_silhouette = round(
                silhouette_score(
                    data_df.loc[:,[i for i in data_df if not i==label_col]].values,
                    data_df[label_col].tolist()
                ),
                4
            )

            samples_silhouette_scores = silhouette_samples(
                data_df.loc[:,[i for i in data_df if not i==label_col]].values,
                data_df[label_col].tolist()
            )
            sil_dict = {'Label':[],'Silhouette Score':[]}
            for u_l in unique_labels:
                sil_dict['Label'].append(u_l)
                sil_dict['Silhouette Score'].append(np.nanmean(samples_silhouette_scores[[i==u_l for i in data_df[label_col].tolist()]]))

            p_value = None
            results = {
                'overall_silhouette': overall_silhouette,
                'samples_silhouette': pd.DataFrame(sil_dict)
            }

    return p_value, results

def run_wilcox_rank_sum(data_df: pd.DataFrame, label_col:str, p_val_thresh: float = 0.05):
    """Run Wilcox Rank-Sum test to find significantly different features for each label

    :param data_df: Dataframe containing property columns and label column
    :type data_df: pd.DataFrame
    :param label_col: Name of column to use for labels
    :type label_col: str
    :param p_val_thresh: Threshold value used to exclude non-significant properties
    :type p_val_thresh: float, optional
    """

    unique_labels = data_df[label_col].unique().tolist()
    results_list = []
    raw_p_val_list = []
    # Only running on numeric columns
    label_vals = data_df[label_col].tolist()
    data_df = data_df.select_dtypes(exclude='object')
    data_df[label_col] = label_vals

    column_names = [i for i in data_df.columns.tolist() if not i==label_col]
    for u_idx, u in enumerate(unique_labels):
        # Getting label and non-label data
        u_data = data_df[data_df[label_col].str.match(u)]
        non_u_data = data_df[~data_df[label_col].str.match(u)]

        # Dropping label column
        u_data = u_data.drop(columns=[label_col])
        non_u_data = non_u_data.drop(columns=[label_col])

        for c in column_names:
            wilcox_result = stats.ranksums(
                u_data[c].values,
                non_u_data[c].values,
                nan_policy='omit'
            )

            if wilcox_result.pvalue<=p_val_thresh:
                results_list.append(
                    {
                        'Group': u,
                        'Property': c,
                        'p Value': '{:0.3e}'.format(wilcox_result.pvalue),
                        'statistic': '{:0.3e}'.format(wilcox_result.statistic)
                    }
                )

                raw_p_val_list.append(wilcox_result.pvalue)

    if len(raw_p_val_list)>0:
        # Running Bonferroni correction for multiple tests
        reject, adjusted_p_vals, alpha_sidak, alpha_bonferroni = multipletests(
            pvals = np.array(raw_p_val_list)
        )

        for result, adj in zip(results_list,adjusted_p_vals.tolist()):
            result['p Value Adjusted'] = '{:0.3e}'.format(adj)

    return results_list


