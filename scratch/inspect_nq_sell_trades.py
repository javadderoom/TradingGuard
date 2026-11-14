import pandas as pd

df = pd.read_csv('backtest_results/mt5_native_execution_results.csv')
sells = df[(df['Model'] == 'MODEL-ISB-PC-01') & (df['Type'] == 'SELL_LIMIT')]
print(sells[['ID', 'TriggerTime', 'Entry', 'SL', 'TP', 'Risk_Pts', 'Status', 'Realized_R', 'MFE_R', 'MAE_R', 'Notes']])
