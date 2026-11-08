import pandas as pd
import numpy as np

df = pd.read_parquet('backtest_results/btcusd_long_term_audit/btcusd_long_term_trades.parquet')

def calc_stats(sub, name):
    fills = sub[sub['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
    n = len(fills)
    if n == 0:
        return {"Name": name, "Fills": 0, "Wins": 0, "Losses": 0, "BE": 0, "WR%": 0.0, "Net_R": 0.0, "Net_PnL": 0.0, "PF": 0.0}
    wins = fills[fills['status'] == 'WIN']
    losses = fills[fills['status'] == 'LOSS']
    be = fills[fills['status'] == 'BREAKEVEN']
    n_w = len(wins)
    n_l = len(losses)
    n_be = len(be)
    wr = n_w / n * 100
    net_r = fills['rr_realized'].sum()
    net_pnl = fills['realized_pnl_usd'].sum()
    gw = wins['realized_pnl_usd'].sum()
    gl = abs(losses['realized_pnl_usd'].sum())
    pf = gw / gl if gl > 0 else 99.0
    return {
        "Name": name,
        "Fills": n,
        "Wins": n_w,
        "Losses": n_l,
        "BE": n_be,
        "WR%": round(wr, 1),
        "Net_R": round(net_r, 2),
        "Net_PnL": round(net_pnl, 2),
        "PF": round(pf, 2)
    }

print("=== BITCOIN STRATEGY OPTIMIZATION MATRIX ===")
rows = []
rows.append(calc_stats(df, "0. Raw Unfiltered Baseline"))

# Config 1: Decommission ARCH-009 & ARCH-010 (Decommissioned drag)
f1 = df[~df['archetype_id'].isin(['SETUP-ARCH-009', 'SETUP-ARCH-010'])]
rows.append(calc_stats(f1, "1. Decommission ARCH-009 & ARCH-010"))

# Config 2: Config 1 + Ban toxic sessions (NY_Late_PM, Asian_Early, London_Continuation)
f2 = df[
    (~df['archetype_id'].isin(['SETUP-ARCH-009', 'SETUP-ARCH-010'])) &
    (~df['session_key'].isin(['NY_Late_PM', 'Asian_Early', 'London_Continuation']))
]
rows.append(calc_stats(f2, "2. Config 1 + Ban 3 Toxic Sessions"))

# Config 3: Curated High-Conviction Pairs (Archetype + Session Match):
c1 = (df['archetype_id'] == 'SETUP-ARCH-001') & (df['session_key'].isin(['Asian_Early', 'Asian_Late', 'NY_Open', 'NY_Silver_Bullet']))
c2 = (df['archetype_id'] == 'SETUP-ARCH-002') & (df['session_key'].isin(['London_Open', 'NY_Silver_Bullet']))
c3 = (df['archetype_id'] == 'SETUP-ARCH-004') & (df['session_key'].isin(['Asian_Late', 'NY_Open']))
c4 = (df['archetype_id'] == 'SETUP-ARCH-011') & (df['session_key'].isin(['London_Continuation', 'Asian_Late']))
f3 = df[c1 | c2 | c3 | c4]
rows.append(calc_stats(f3, "3. Curated Archetype-Session Match"))

# Config 4: Config 3 with Weekday restriction (Mon-Fri)
f4 = df[(c1 | c2 | c3 | c4) & (df['is_weekend'] == False)]
rows.append(calc_stats(f4, "4. Config 3 Weekday Only (Mon-Fri)"))

# Config 5: High-Conviction Hours (06:00-08:00, 10:00, 14:00, 17:00, 20:00, 23:00 UTC) with ARCH-001/002/004
good_hours = [6, 7, 10, 14, 17, 20, 23]
f5 = df[(df['hour_utc'].isin(good_hours)) & (df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-002', 'SETUP-ARCH-004']))]
rows.append(calc_stats(f5, "5. Peak Golden Hours + Top 3 Archetypes"))

# Config 6: Golden Hours + PRO_EXPANSION Phase Only
f6 = df[(df['hour_utc'].isin(good_hours)) & (df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-002', 'SETUP-ARCH-004'])) & (df['phase'] == 'PRO_EXPANSION')]
rows.append(calc_stats(f6, "6. Golden Hours + PRO_EXPANSION"))

# Config 7: Golden Hours + HTF_RETRACEMENT Phase Only
f7 = df[(df['hour_utc'].isin(good_hours)) & (df['archetype_id'].isin(['SETUP-ARCH-001', 'SETUP-ARCH-002', 'SETUP-ARCH-004'])) & (df['phase'] == 'HTF_RETRACEMENT')]
rows.append(calc_stats(f7, "7. Golden Hours + HTF_RETRACEMENT"))

res_df = pd.DataFrame(rows)
print(res_df.to_string(index=False))
