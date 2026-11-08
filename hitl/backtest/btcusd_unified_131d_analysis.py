import sys
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Load Autumn and Summer trade parquets
df_aut = pd.read_parquet('backtest_results/btcusd_long_term_audit/btcusd_long_term_trades.parquet')
df_sum = pd.read_parquet('backtest_results/btcusd_summer_audit/btcusd_summer_trades.parquet')

df_aut['regime'] = 'Autumn (Sep 1 - Nov 8, 2026)'
df_sum['regime'] = 'Summer (Jul 1 - Aug 31, 2026)'

df_all = pd.concat([df_sum, df_aut], ignore_index=True).sort_values('epoch')

print("=" * 95)
print("🚀 BITCOIN (BTCUSD) UNIFIED 131-DAY QUANTITATIVE AUDIT (JULY 1 - NOVEMBER 8, 2026)")
print(f"Total Evaluated Signals: {len(df_all):,} across 131 Continuous 24/7 Calendar Days")
print("=" * 95)

def calc_stats(sub, name):
    fills = sub[sub['status'].isin(['WIN', 'LOSS', 'BREAKEVEN'])].copy()
    n = len(fills)
    if n == 0:
        return {"Name": name, "Signals": len(sub), "Fills": 0, "Wins": 0, "Losses": 0, "BE": 0, "WR%": 0.0, "Net_R": 0.0, "Net_PnL": 0.0, "PF": 0.0}
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
        "Signals": len(sub),
        "Fills": n,
        "Wins": n_w,
        "Losses": n_l,
        "BE": n_be,
        "WR%": round(wr, 1),
        "Net_R": round(net_r, 2),
        "Net_PnL": round(net_pnl, 2),
        "PF": round(pf, 2)
    }

print("\n--- 1. OVERALL PERIOD COMPARISON ---")
rows_period = [
    calc_stats(df_sum, "Summer Out-of-Sample (62 Days)"),
    calc_stats(df_aut, "Autumn Baseline (69 Days)"),
    calc_stats(df_all, "Unified Full Audit (131 Days)")
]
print(pd.DataFrame(rows_period).to_string(index=False))

print("\n--- 2. ARCHETYPE LEADERBOARD (UNIFIED 131 DAYS) ---")
rows_arch = []
for arch, grp in df_all.groupby('archetype_id'):
    rows_arch.append(calc_stats(grp, arch))
print(pd.DataFrame(rows_arch).sort_values('Net_R', ascending=False).to_string(index=False))

print("\n--- 3. SESSION BREAKDOWN (UNIFIED 131 DAYS) ---")
rows_sess = []
for sess, grp in df_all.groupby('session_key'):
    rows_sess.append(calc_stats(grp, sess))
print(pd.DataFrame(rows_sess).sort_values('Net_R', ascending=False).to_string(index=False))

print("\n--- 4. WEEKEND VS WEEKDAY (UNIFIED 131 DAYS) ---")
rows_wend = [
    calc_stats(df_all[df_all['is_weekend'] == False], "Weekday (Mon-Fri)"),
    calc_stats(df_all[df_all['is_weekend'] == True], "Weekend (Sat-Sun)")
]
print(pd.DataFrame(rows_wend).to_string(index=False))

print("\n--- 5. MONTHLY CHRONOLOGICAL TIMELINE ---")
df_all['month'] = pd.to_datetime(df_all['time_utc']).dt.to_period('M')
rows_month = []
for m, grp in df_all.groupby('month'):
    rows_month.append(calc_stats(grp, str(m)))
print(pd.DataFrame(rows_month).to_string(index=False))

print("\n--- 6. EVALUATION OF CONFIGURATIONS ACROSS UNIFIED 131 DAYS ---")
rows_cfg = []
rows_cfg.append(calc_stats(df_all, "0. Raw Baseline (All 131 Days)"))

# Decommission ARCH-009 & ARCH-010
f1 = df_all[~df_all['archetype_id'].isin(['SETUP-ARCH-009', 'SETUP-ARCH-010'])]
rows_cfg.append(calc_stats(f1, "1. Decommission ARCH-009 & ARCH-010"))

# Config 1 + Ban 3 Toxic Sessions (NY Late PM, Asian Early, London Continuation)
f2 = df_all[
    (~df_all['archetype_id'].isin(['SETUP-ARCH-009', 'SETUP-ARCH-010'])) &
    (~df_all['session_key'].isin(['NY_Late_PM', 'Asian_Early', 'London_Continuation']))
]
rows_cfg.append(calc_stats(f2, "2. Config 1 + Ban 3 Toxic Sessions"))

# Curated Archetype-Session Match (Config 3)
c1 = (df_all['archetype_id'] == 'SETUP-ARCH-001') & (df_all['session_key'].isin(['Asian_Early', 'Asian_Late', 'NY_Open', 'NY_Silver_Bullet']))
c2 = (df_all['archetype_id'] == 'SETUP-ARCH-002') & (df_all['session_key'].isin(['London_Open', 'NY_Silver_Bullet']))
c3 = (df_all['archetype_id'] == 'SETUP-ARCH-004') & (df_all['session_key'].isin(['Asian_Late', 'NY_Open']))
c4 = (df_all['archetype_id'] == 'SETUP-ARCH-011') & (df_all['session_key'].isin(['London_Continuation', 'Asian_Late']))
f3 = df_all[c1 | c2 | c3 | c4]
rows_cfg.append(calc_stats(f3, "3. Curated Archetype-Session Match"))

# Config 4: Config 3 Weekday Only
f4 = df_all[(c1 | c2 | c3 | c4) & (df_all['is_weekend'] == False)]
rows_cfg.append(calc_stats(f4, "4. Curated Match (Weekday Mon-Fri Only)"))

# Let's test a Pure Macro Judas Breaker + Silver Bullet Portfolio across all 131 days:
# ARCH-001 in all active killzones + ARCH-002 in London Open/NY SB with HTF Retracement
f_pure_judas = df_all[(df_all['archetype_id'] == 'SETUP-ARCH-001') & (df_all['is_weekend'] == False)]
rows_cfg.append(calc_stats(f_pure_judas, "5. Pure Judas Breakers (ARCH-001 Weekday)"))

print(pd.DataFrame(rows_cfg).to_string(index=False))
