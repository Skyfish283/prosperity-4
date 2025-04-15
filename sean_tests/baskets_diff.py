import pandas as pd
import numpy as np
import math
from typing import *

def basket_prod_diff(csv_file, basket, products_mults : Dict[str, int], thresholds : List[float]):
    df = pd.read_csv(csv_file, sep=';')
    basket_prices = df.loc[df['product'] == basket, 'mid_price'].reset_index(drop=True)
    # initialse sum of product prices series
    sum_products_prices = pd.Series(0.0, index = basket_prices.index)
    for product, mult in products_mults.items():
        product_prices = df.loc[df['product'] == product, 'mid_price'].reset_index(drop=True)
        sum_products_prices += product_prices * mult
    percentage_diff = (basket_prices - sum_products_prices) / sum_products_prices * 100
    # create a boolean series for each threshold
    thresholds_str = map(str, thresholds)
    bool_df = pd.DataFrame(0, index = percentage_diff.index, columns = thresholds_str)
    for threshold in thresholds:
        if threshold < 0:
            bool_df[str(threshold)] = np.where(percentage_diff < threshold, 1, 0)
        elif threshold >= 0:
            bool_df[str(threshold)] = np.where(percentage_diff > threshold, 1, 0)
    for col in bool_df:
        pass
        print(f"Value counts of boolean df for threshold {col} % and {basket}:")
        print(bool_df[col].value_counts())
    return bool_df

thresholds = [-0.3, -0.2, -0.1, -0.05, 0.05, 0.1, 0.2, 0.3]
csv_list_day2 = ['sean_tests/prices_day_-1.csv', 'sean_tests/prices_day_0.csv',
                     'sean_tests/prices_day_1.csv']
for csv in csv_list_day2:
    print(f"======================== Analysing {csv} ========================")
    basket_prod_diff(csv, 'PICNIC_BASKET1', {'CROISSANTS' : 6, 'JAMS': 3, 'DJEMBES' : 1}, thresholds)
    #basket_prod_diff(csv, 'PICNIC_BASKET2', {'CROISSANTS' : 4, 'JAMS': 2}, thresholds)

