import pandas as pd
import numpy as np

print("=== STATISTICAL ANALYSIS: LIQUIDITY SWEEP VS BOS ON GOLD ===")
df = pd.read_parquet('scratch/gold_breach_events_2026.parquet')

print(f"Total events: {len(df)}")

# Filter directional outcomes: SWEEP_REVERSAL vs BOS_CONTINUATION
df_dir = df[df['outcome'].isin(['SWEEP_REVERSAL', 'BOS_CONTINUATION'])].copy()
df_dir['is_sweep'] = (df_dir['outcome'] == 'SWEEP_REVERSAL').astype(int)

print(f"Directional sample size: {len(df_dir)} (Sweeps: {(df_dir['is_sweep']==1).sum()}, BOS: {(df_dir['is_sweep']==0).sum()})")
baseline_sweep_rate = df_dir['is_sweep'].mean() * 100
print(f"Baseline Sweep Rate in Directional subset: {baseline_sweep_rate:.2f}%\n")

# 1. Close Location Analysis
print("--- 1. IMPACT OF CLOSE LOCATION ---")
close_ct = pd.crosstab(df['close_loc'], df['outcome'], normalize='index') * 100
print("Across ALL events (including CHOP):")
print(close_ct.round(2))

close_dir_ct = pd.crosstab(df_dir['close_loc'], df_dir['outcome'], normalize='index') * 100
close_counts = pd.crosstab(df_dir['close_loc'], df_dir['outcome'])
print("\nAcross Directional events (Sweep vs BOS):")
print(pd.concat([close_counts, close_dir_ct.round(2)], axis=1))

# 2. Wick Ratio Analysis
print("\n--- 2. IMPACT OF WICK RATIO ---")
df_dir['wick_bin'] = pd.cut(df_dir['wick_ratio'], bins=[0.0, 0.20, 0.35, 0.50, 0.65, 1.0], labels=['<20%', '20-35%', '35-50%', '50-65%', '>65%'])
wick_dir_ct = pd.crosstab(df_dir['wick_bin'], df_dir['outcome'], normalize='index') * 100
wick_counts = pd.crosstab(df_dir['wick_bin'], df_dir['outcome'])
print(pd.concat([wick_counts, wick_dir_ct.round(2)], axis=1))

# 3. Penetration Depth relative to ATR
print("\n--- 3. IMPACT OF PENETRATION DEPTH (relative to 5M ATR) ---")
df_dir['pen_bin'] = pd.cut(df_dir['pen_to_atr'], bins=[0.0, 0.25, 0.50, 1.0, 2.0, 10.0], labels=['<0.25 ATR', '0.25-0.5 ATR', '0.5-1.0 ATR', '1.0-2.0 ATR', '>2.0 ATR'])
pen_dir_ct = pd.crosstab(df_dir['pen_bin'], df_dir['outcome'], normalize='index') * 100
pen_counts = pd.crosstab(df_dir['pen_bin'], df_dir['outcome'])
print(pd.concat([pen_counts, pen_dir_ct.round(2)], axis=1))

# 4. Tick Volume Ratio
print("\n--- 4. IMPACT OF TICK VOLUME SURGE ---")
df_dir['vol_bin'] = pd.cut(df_dir['vol_ratio'], bins=[0.0, 0.75, 1.25, 2.0, 100.0], labels=['Low (<0.75x)', 'Normal (0.75-1.25x)', 'High (1.25-2.0x)', 'Climactic (>2.0x)'])
vol_dir_ct = pd.crosstab(df_dir['vol_bin'], df_dir['outcome'], normalize='index') * 100
vol_counts = pd.crosstab(df_dir['vol_bin'], df_dir['outcome'])
print(pd.concat([vol_counts, vol_dir_ct.round(2)], axis=1))

# 5. Session Time Impact
print("\n--- 5. IMPACT OF TRADING SESSION ---")
sess_dir_ct = pd.crosstab(df_dir['session'], df_dir['outcome'], normalize='index') * 100
sess_counts = pd.crosstab(df_dir['session'], df_dir['outcome'])
print(pd.concat([sess_counts, sess_dir_ct.round(2)], axis=1))

# 6. Daily ADR % Consumed
print("\n--- 6. IMPACT OF DAILY ADR % CONSUMED ---")
df_dir['adr_bin'] = pd.cut(df_dir['adr_consumed_pct'], bins=[0.0, 40.0, 75.0, 100.0, 500.0], labels=['Early (<40%)', 'Mid (40-75%)', 'Near Exhaustion (75-100%)', 'Exhausted (>100%)'])
adr_dir_ct = pd.crosstab(df_dir['adr_bin'], df_dir['outcome'], normalize='index') * 100
adr_counts = pd.crosstab(df_dir['adr_bin'], df_dir['outcome'])
print(pd.concat([adr_counts, adr_dir_ct.round(2)], axis=1))

# 7. Follow-Through Confirmation: Next Bar MSS (Bar T+1)
print("\n--- 7. IMPACT OF BAR T+1 CONFIRMATION (Instant MSS vs Extension) ---")
mss_dir_ct = pd.crosstab(df_dir['next_mss'], df_dir['outcome'], normalize='index') * 100
mss_counts = pd.crosstab(df_dir['next_mss'], df_dir['outcome'])
print(pd.concat([mss_counts, mss_dir_ct.round(2)], axis=1))

ext_dir_ct = pd.crosstab(df_dir['next_ext'], df_dir['outcome'], normalize='index') * 100
ext_counts = pd.crosstab(df_dir['next_ext'], df_dir['outcome'])
print(pd.concat([ext_counts, ext_dir_ct.round(2)], axis=1))

# 8. Level Type
print("\n--- 8. IMPACT OF LEVEL TYPE ---")
lvl_dir_ct = pd.crosstab(df_dir['level_type'], df_dir['outcome'], normalize='index') * 100
lvl_counts = pd.crosstab(df_dir['level_type'], df_dir['outcome'])
print(pd.concat([lvl_counts, lvl_dir_ct.round(2)], axis=1))

# 9. Confluence Matrix Discovery
print("\n================================================================================")
print("  MULTI-FEATURE CONFLUENCE DISCOVERY: PREDICTING SWEEP (REVERSAL) WITH HIGH ODDS ")
print("================================================================================")

# Rule 1: Textbook Sweep Rejection
# Candle closed INSIDE (or marginal probe) + Wick Ratio >= 50% + Next Bar MSS
rule_sweep_1 = (df_dir['close_loc'].isin(['INSIDE', 'MARGINAL_OUTSIDE'])) & (df_dir['wick_ratio'] >= 0.50) & (df_dir['next_mss'] == True)
sample_r1 = df_dir[rule_sweep_1]
sw_rate_r1 = sample_r1['is_sweep'].mean() * 100 if len(sample_r1) > 0 else 0
print(f"Rule 1 (Wick >= 50% + Close Inside/Marginal + Next Bar MSS):")
print(f"  Count: {len(sample_r1)} | Sweep Reversals: {(sample_r1['is_sweep']==1).sum()} | BOS Continuations: {(sample_r1['is_sweep']==0).sum()}")
print(f"  Sweep Probability: {sw_rate_r1:.1f}% (vs {baseline_sweep_rate:.1f}% baseline)\n")

# Rule 2: ADR Exhaustion Sweep
# ADR >= 85% + Wick Ratio >= 40% + Level is PDH/PDL or Asian Extreme
rule_sweep_2 = (df_dir['adr_consumed_pct'] >= 80.0) & (df_dir['wick_ratio'] >= 0.40) & (df_dir['level_type'].isin(['PDH', 'PDL', 'ASIAN_HIGH', 'ASIAN_LOW']))
sample_r2 = df_dir[rule_sweep_2]
sw_rate_r2 = sample_r2['is_sweep'].mean() * 100 if len(sample_r2) > 0 else 0
print(f"Rule 2 (ADR >= 80% Exhaustion + Wick >= 40% on Major Level):")
print(f"  Count: {len(sample_r2)} | Sweep Reversals: {(sample_r2['is_sweep']==1).sum()} | BOS Continuations: {(sample_r2['is_sweep']==0).sum()}")
print(f"  Sweep Probability: {sw_rate_r2:.1f}% (vs {baseline_sweep_rate:.1f}% baseline)\n")

# Rule 3: Textbook Break of Structure (BOS Continuation)
# Candle closed STRONG_OUTSIDE + Wick Ratio < 25% + Body Ratio >= 60% + Next Bar Extension
rule_bos_1 = (df_dir['close_loc'] == 'STRONG_OUTSIDE') & (df_dir['wick_ratio'] < 0.25) & (df_dir['body_ratio'] >= 0.55) & (df_dir['next_ext'] == True)
sample_bos1 = df_dir[rule_bos_1]
bos_rate_1 = (1.0 - sample_bos1['is_sweep'].mean()) * 100 if len(sample_bos1) > 0 else 0
print(f"Rule 3 (Strong Close Outside + Wick < 25% + Body >= 55% + Next Bar Extends):")
print(f"  Count: {len(sample_bos1)} | BOS Continuations: {(sample_bos1['is_sweep']==0).sum()} | Sweep Reversals: {(sample_bos1['is_sweep']==1).sum()}")
print(f"  BOS Continuation Probability: {bos_rate_1:.1f}% (vs {100-baseline_sweep_rate:.1f}% baseline)\n")

# Rule 4: Pro-Trend Session Breakout
# Strong Close Outside + Pro H1 Trend + Early Session (ADR < 60%) + London/NY Open
rule_bos_2 = (df_dir['close_loc'] == 'STRONG_OUTSIDE') & (df_dir['is_pro_trend'] == True) & (df_dir['adr_consumed_pct'] < 60.0) & (df_dir['session'].isin(['LONDON_OPEN', 'NY_OPEN']))
sample_bos2 = df_dir[rule_bos_2]
bos_rate_2 = (1.0 - sample_bos2['is_sweep'].mean()) * 100 if len(sample_bos2) > 0 else 0
print(f"Rule 4 (Pro-Trend H1 + Early Session ADR < 60% + Strong Close Outside in London/NY Open):")
print(f"  Count: {len(sample_bos2)} | BOS Continuations: {(sample_bos2['is_sweep']==0).sum()} | Sweep Reversals: {(sample_bos2['is_sweep']==1).sum()}")
print(f"  BOS Continuation Probability: {bos_rate_2:.1f}% (vs {100-baseline_sweep_rate:.1f}% baseline)\n")
