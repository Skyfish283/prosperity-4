def data_cleaning(folder_path: str):
    # Get all CSV files in the folder
    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    
    # Load each CSV into a separate DataFrame, named after the file
    dfs = {}
    for file in csv_files:
        name = os.path.splitext(os.path.basename(file))[0]  # filename without extension
        dfs[name] = pd.read_csv(file, delimiter = ';')
        print(f"Loaded '{name}' — {dfs[name].shape[0]} rows × {dfs[name].shape[1]} cols")
    
    prices = pd.concat([v for k, v in dfs.items() if 'prices' in k])
    cols = ['bid_volume_1','bid_volume_2','bid_volume_3','ask_volume_1','ask_volume_2','ask_volume_3']
    prices[cols] = prices[cols].fillna(0)
    trades = pd.concat([v for k, v in dfs.items() if 'trades' in k])
    prices['mid'] = (prices['bid_price_1'] + prices['ask_price_1'])/2
    prices['swmid'] = (prices['bid_price_1']*prices['ask_volume_1'] + prices['ask_price_1']*prices['bid_volume_1'])/(prices['ask_volume_1'] + prices['bid_volume_1'])
    prices['spread'] = prices['ask_price_1'] - prices['bid_price_1']
    prices['bid_vol'] = prices['bid_volume_1'] + prices['bid_volume_2'] + prices['bid_volume_3']
    prices['ask_vol'] = prices['ask_volume_1'] + prices['ask_volume_2'] + prices['ask_volume_3']
    prices = prices.reset_index(drop = True)
    prices['prev_mid'] = prices.sort_values(['timestamp']).groupby(['product', 'day'])['mid'].shift(1)
    prices['prev_returns'] = (prices['mid'] - prices['prev_mid'])/prices['prev_mid']
    return prices, trades
