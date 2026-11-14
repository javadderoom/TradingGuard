import pandas as pd

df = pd.read_csv('backtest_results/mt5_native_execution_results.csv')
for model in df['Model'].unique():
    sub = df[df['Model'] == model]
    print(f"=== {model} ===")
    for t_type in sorted(sub['Type'].unique()):
        s_type = sub[sub['Type'] == t_type]
        wins = len(s_type[s_type['Status'] == 'WIN'])
        losses = len(s_type[s_type['Status'].str.contains('LOSS')])
        be = len(s_type[s_type['Status'] == 'BREAKEVEN'])
        exp = len(s_type[s_type['Status'] == 'EXPIRED'])
        net_r = s_type['Realized_R'].sum()
        gp = s_type[s_type['Realized_R'] > 0]['Realized_R'].sum()
        gl = abs(s_type[s_type['Realized_R'] < 0]['Realized_R'].sum())
        pf = gp / gl if gl > 0 else (99.0 if gp > 0 else 0.0)
        print(f"   {t_type:10s}: {len(s_type):2d} orders ({exp} exp) | {wins}W - {losses}L - {be}BE | Net R: {net_r:+.2f}R | PF: {pf:.2f}")
