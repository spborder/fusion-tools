import os
import sys

import numpy as np
import pandas as pd

from scipy import stats
from sklearn.metrics import silhouette_score, silhouette_samples



def get_label_statistics(data_df:pd.DataFrame, label_col:str):
    """Get output of statistical test for data and it's labels

    :param data_df: Dataframe containing properties for each group as well as the label column
    :type data_df: pd.DataFrame
    :param label_col: Column containing group information for data
    :type label_col: str
    """

    unique_labels = data_df[label_col].unique().tolist()

    if data_df.shape[1]==2:
        # This means there is one property and the label column
        if len(unique_labels)==2:
            # This is a t-test
            group_a = data_df[data_df[label_col].str.match(unique_labels[0])].loc[:,[i for i in data_df if not i==label_col]].values
            group_b = data_df[data_df[label_col].str.match(unique_labels[1])].loc[:,[i for i in data_df if not i==label_col]].values

            stats_result = stats.ttest_ind(group_a,group_b)
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
                    data_df[data_df[label_col].str.match(u)].loc[:,[i for i in data_df if not i==label_col]].values.flatten()
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

    elif data_df.shape[1]>2:
        if data_df.shape[1]==3:
            # Calculating Pearson's correlation for each group separately
            pearson_r_list = []
            p_value = []
            for u_l in unique_labels:
                # For each label, generate a new table with r
                group_data = data_df[data_df[label_col].str.match(u_l)].values
                group_r,group_p = stats.mstats.pearsonr(group_data[:,0].astype(float),group_data[:,1].astype(float))
                
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








