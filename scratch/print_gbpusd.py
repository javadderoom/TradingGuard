import pandas as pd
from zoneinfo import ZoneInfo

tehran_tz = ZoneInfo("Asia/Tehran")
df = pd.read_parquet("backtest_results/cache/M1_GBPUSD_o_2026.parquet")
df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
df.set_index("dt", inplace=True)
ohlc = df.resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()

mask = (ohlc.index >= "2026-11-12 00:00:00+00:00") & (ohlc.index <= "2026-11-12 16:00:00+00:00")
sub = ohlc[mask]
print("=== GBPUSD 5M BARS 2026-11-12 ===")
for t, row in sub.iterrows():
    t_tehran = t.tz_convert(tehran_tz)
    print(f"UTC {t.strftime('%H:%M')} | Tehran {t_tehran.strftime('%H:%M')} | O={row['open']:.5f} H={row['high']:.5f} L={row['low']:.5f} C={row['close']:.5f}")
