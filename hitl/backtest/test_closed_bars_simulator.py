"""Pack 4 verification — synthetic bars only, no MT5, no repo data.

Run from the repo root:  python3 hitl/backtest/test_closed_bars_simulator.py
Covers: closed-bars-only screener, SL-first TP/SL precedence, symmetric
spread, commission deduction, breakeven spread accounting, OPEN_AT_END
is_realized=False, canonical 75-minute TTL.
"""
import sys, datetime, types, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

# --- Stub MetaTrader5 + MT5 engine so data_feed can be imported on Linux ---
mt5_stub = types.ModuleType('MetaTrader5')
sys.modules['MetaTrader5'] = mt5_stub
mt5eng_stub = types.ModuleType('hitl.mt5_engine')
class _FakeEngine:
    pass
mt5eng_stub.MT5Engine = _FakeEngine
sys.modules['hitl.mt5_engine'] = mt5eng_stub

from hitl.backtest.evaluator import evaluate_council_decision, CANONICAL_TTL_MINUTES
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.data_feed import _ceil_to_5m_boundary

PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}  {detail}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")

def m1(t, o, h, l, c):
    return {'time': t, 'open': o, 'high': h, 'low': l, 'close': c}

def m5(t, o, h, l, c):
    return {'time': t, 'dt': datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc),
            'open': o, 'high': h, 'low': l, 'close': c, 'tick_volume': 10}

# =====================================================================
print("(i) Forming-bar signal does not fire (closed_bars_only=True)")
# EURUSD 5M bars, base time 2026-11-06 09:00 UTC, 5-min steps.
T0 = int(datetime.datetime(2026, 11, 6, 9, 0, tzinfo=datetime.timezone.utc).timestamp())
bars = []
# bars 0-48: flat range 1.0995 - 1.1015, close 1.1005 (session window)
for i in range(49):
    bars.append(m5(T0 + i*300, 1.1005, 1.1015 if i % 7 == 0 else 1.1010,
                   1.0995 if i % 11 == 0 else 1.1000, 1.1005))
# bar 49-51: drift up
bars.append(m5(T0+49*300, 1.1005, 1.1012, 1.1002, 1.1010))
bars.append(m5(T0+50*300, 1.1010, 1.1014, 1.1008, 1.1012))
bars.append(m5(T0+51*300, 1.1012, 1.1015, 1.1010, 1.1014))
# bar 52: swing high 1.1015, then dip so the last swing low is AFTER the high
bars.append(m5(T0+52*300, 1.1014, 1.1015, 1.1010, 1.1011))
bars.append(m5(T0+53*300, 1.1011, 1.1013, 1.1000, 1.1005))  # swing low 1.1000
bars.append(m5(T0+54*300, 1.1005, 1.1010, 1.1002, 1.1008))
bars.append(m5(T0+55*300, 1.1008, 1.1012, 1.1005, 1.1010))
bars.append(m5(T0+56*300, 1.1010, 1.1011, 1.1008, 1.1010))
# bar 57 (c1 of FVG triplet): high 1.1018
bars.append(m5(T0+57*300, 1.1010, 1.1018, 1.1008, 1.1012))
# bar 58 (c2): body 0.0004, close 1.1020 — below breakout buffer, no breakout
bars.append(m5(T0+58*300, 1.1016, 1.1022, 1.1016, 1.1020))
# bar 59 (FORMING): low 1.1021 > c1 high 1.1018 (FVG gap 0.0003), close 1.1025
#   -> breakout above range high 1.1015 + 0.0008, close > open
bars.append(m5(T0+59*300, 1.1022, 1.1026, 1.1021, 1.1025))
bars_1h = [m5(T0 + i*3600, 1.1005, 1.1010, 1.1000, 1.1005) for i in range(20)]

res_forming = screen_ict_session(list(bars), list(bars_1h), "EURUSD", 9, closed_bars_only=False)
res_closed = screen_ict_session(list(bars), list(bars_1h), "EURUSD", 9, closed_bars_only=True)
print(f"    forming-bar mode: has_setup={res_forming['has_setup']} ({res_forming.get('setup_type')}) "
      f"signal_bar_time={res_forming.get('signal_bar_time')}")
print(f"    closed-bar mode:  has_setup={res_closed['has_setup']} ({res_closed.get('reason','')[:60]}) "
      f"signal_bar_time={res_closed.get('signal_bar_time')}")
check("forming bar fires (old behaviour, explicit opt-in)", res_forming['has_setup'] is True,
      f"setup={res_forming.get('setup_type')}")
check("closed bars: same series does NOT fire", res_closed['has_setup'] is False)
check("closed mode reports signal bar = bar 58 (last closed)",
      res_closed.get('signal_bar_time') == bars[58]['time'], f"got {res_closed.get('signal_bar_time')}")
check("forming mode reports signal bar = bar 59",
      res_forming.get('signal_bar_time') == bars[59]['time'])

# data_feed forward-window boundary
check("ceil 10:30 -> 10:30 (already on boundary)",
      _ceil_to_5m_boundary(datetime.datetime(2026, 11, 6, 10, 30)) == datetime.datetime(2026, 11, 6, 10, 30))
check("ceil 10:32 -> 10:35 (inside signal bar)",
      _ceil_to_5m_boundary(datetime.datetime(2026, 11, 6, 10, 32)) == datetime.datetime(2026, 11, 6, 10, 35))
check("ceil 10:34:30 -> 10:35",
      _ceil_to_5m_boundary(datetime.datetime(2026, 11, 6, 10, 34, 30)) == datetime.datetime(2026, 11, 6, 10, 35))

# =====================================================================
print("(ii) Bar touching both TP and SL is a LOSS (SL-first)")
fwd = [m1(0, 3999.9, 4000.0, 3999.8, 3999.9),   # fill: low+spread 3999.95 <= 4000
       m1(1, 3999.9, 4025.0, 3990.0, 4010.0)]   # high >= TP 4021 AND low <= SL 3993
r = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3993.0, "tp": 4021.0},
                              fwd, "XAUUSD")
print(f"    BUY both-touched: {r['status']} pnl={r['realized_pnl_usd']}")
check("BUY both TP+SL touched -> LOSS", r['status'] == 'LOSS', f"pnl={r['realized_pnl_usd']}")
check("LOSS pnl = -$7.00 risk - $0.10 commission", r['realized_pnl_usd'] == -7.10,
      f"got {r['realized_pnl_usd']}")
fwd_s = [m1(0, 4000.1, 4000.2, 4000.0, 4000.1),  # fill: high >= 4000
         m1(1, 4000.1, 4007.5, 3975.0, 3990.0)]  # high+spread >= SL 4007 AND low+spread <= TP 3979
r = evaluate_council_decision({"decision": "SELL_LIMIT", "entry": 4000.0, "sl": 4007.0, "tp": 3979.0},
                              fwd_s, "XAUUSD")
print(f"    SELL both-touched: {r['status']} pnl={r['realized_pnl_usd']}")
check("SELL both TP+SL touched -> LOSS", r['status'] == 'LOSS')

# =====================================================================
print("(iii) Spread symmetric BUY vs SELL (same bid/ask convention)")
# BUY: fill bar low 3999.85 (ask 4000.00), TP bar high exactly 4021 (bid reaches TP)
fwd_buy = [m1(0, 3999.9, 4000.0, 3999.85, 3999.9),
           m1(1, 4020.0, 4021.0, 4019.0, 4020.5)]
rb = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3993.0, "tp": 4021.0},
                               fwd_buy, "XAUUSD")
# SELL: fill bar high 4000.00 (bid), TP bar low 3978.85 (ask 3979.00 reaches TP)
fwd_sell = [m1(0, 4000.1, 4000.0, 3999.9, 4000.1),
            m1(1, 3980.0, 3981.0, 3978.85, 3979.5)]
rs = evaluate_council_decision({"decision": "SELL_LIMIT", "entry": 4000.0, "sl": 4007.0, "tp": 3979.0},
                               fwd_sell, "XAUUSD")
print(f"    BUY WIN pnl={rb['realized_pnl_usd']}  SELL WIN pnl={rs['realized_pnl_usd']}")
check("BUY WIN and SELL WIN net PnL equal", rb['status'] == 'WIN' and rs['status'] == 'WIN'
      and rb['realized_pnl_usd'] == rs['realized_pnl_usd'] == 20.90,
      f"buy={rb['realized_pnl_usd']} sell={rs['realized_pnl_usd']}")
# SELL TP bar with low exactly at TP does NOT trigger (ask = low+spread > TP)
fwd_sell2 = [m1(0, 4000.1, 4000.0, 3999.9, 4000.1),
             m1(1, 3980.0, 3981.0, 3979.0, 3979.5)]
rs2 = evaluate_council_decision({"decision": "SELL_LIMIT", "entry": 4000.0, "sl": 4007.0, "tp": 3979.0},
                                fwd_sell2, "XAUUSD")
check("SELL TP not hit when ask (low+spread) has not reached TP",
      rs2['status'] != 'WIN', f"status={rs2['status']}")
# BUY SL vs SELL SL equal loss
fwd_buy_sl = [m1(0, 3999.9, 4000.0, 3999.85, 3999.9), m1(1, 3995.0, 3996.0, 3993.0, 3994.0)]
fwd_sell_sl = [m1(0, 4000.1, 4000.0, 3999.9, 4000.1), m1(1, 4005.0, 4007.0, 4004.0, 4006.0)]
rb2 = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3993.0, "tp": 4021.0},
                                fwd_buy_sl, "XAUUSD")
rs3 = evaluate_council_decision({"decision": "SELL_LIMIT", "entry": 4000.0, "sl": 4007.0, "tp": 3979.0},
                                fwd_sell_sl, "XAUUSD")
check("BUY LOSS and SELL LOSS net PnL equal",
      rb2['status'] == 'LOSS' and rs3['status'] == 'LOSS'
      and rb2['realized_pnl_usd'] == rs3['realized_pnl_usd'] == -7.10,
      f"buy={rb2['realized_pnl_usd']} sell={rs3['realized_pnl_usd']}")

# =====================================================================
print("(iv) Commission deducted from a winning trade")
# (already shown in (iii): gross $21.00 -> net $20.90)
check("WIN gross $21.00 - $0.10 commission = $20.90", rb['realized_pnl_usd'] == 20.90)
r0 = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3993.0, "tp": 4021.0},
                               fwd_buy, "XAUUSD", commission_usd=0.0)
check("commission_usd=0.0 restores gross $21.00", r0['realized_pnl_usd'] == 21.00,
      f"got {r0['realized_pnl_usd']}")
check("canonical TTL is 75", CANONICAL_TTL_MINUTES == 75)

# =====================================================================
print("(v) Breakeven exit accounts for spread and commission (was PnL 0.0)")
# BUY: fill bar0; bar1 high 4014 -> MFE 14pts = 2.0R arms BE at END of
# bar1 (active_sl 4000.15); bar2 retraces to low 3999.0 -> BE exit.
# (The old code armed the ratchet from bar1's high and exited on the same
# bar's low; the canonical rule evaluates exits on start-of-bar levels,
# so a retrace bar is required.) Gross +$0.15 spread, -$0.10 commission.
fwd_be = [m1(0, 3999.9, 4000.0, 3999.85, 3999.9),
          m1(1, 4010.0, 4014.0, 4000.10, 4012.0),
          m1(2, 4012.0, 4012.0, 3999.0, 4000.0)]
rbe = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3993.0, "tp": 4021.0},
                                fwd_be, "XAUUSD", breakeven_rr=2.0)
print(f"    BUY BE: {rbe['status']} pnl={rbe['realized_pnl_usd']}")
check("BUY BE status", rbe['status'] == 'BREAKEVEN')
check("BUY BE pnl = +$0.15 spread - $0.10 commission = +$0.05",
      rbe['realized_pnl_usd'] == 0.05, f"got {rbe['realized_pnl_usd']}")
# SELL mirror: bar1 low 3985.5 -> MFE 14.35pts = 2.05R arms BE at END
# of bar1 (active_sl 3999.85); bar2 rallies to high 4000.0 -> ask 4000.15
# >= 3999.85 -> BE exit. (Old data had MFE 13.85pts = 1.98R, just below
# the 2.0 threshold, so the ratchet never armed.)
fwd_be_s = [m1(0, 4000.1, 4000.0, 3999.9, 4000.1),
            m1(1, 3990.0, 3999.90, 3985.5, 3988.0),
            m1(2, 3988.0, 4000.0, 3988.0, 3990.0)]
rbe_s = evaluate_council_decision({"decision": "SELL_LIMIT", "entry": 4000.0, "sl": 4007.0, "tp": 3979.0},
                                  fwd_be_s, "XAUUSD", breakeven_rr=2.0)
print(f"    SELL BE: {rbe_s['status']} pnl={rbe_s['realized_pnl_usd']}")
check("SELL BE pnl = +$0.05 (same as BUY)", rbe_s['status'] == 'BREAKEVEN'
      and rbe_s['realized_pnl_usd'] == 0.05, f"got {rbe_s['realized_pnl_usd']}")

# OPEN_AT_END is flagged unrealised
fwd_open = [m1(0, 3999.9, 4000.0, 3999.85, 3999.9),
            m1(1, 4005.0, 4006.0, 4004.0, 4005.0)]
ro = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3993.0, "tp": 4021.0},
                               fwd_open, "XAUUSD")
check("OPEN_AT_END flagged is_realized=False",
      ro['status'] == 'OPEN_AT_END' and ro.get('is_realized') is False,
      f"status={ro['status']} is_realized={ro.get('is_realized')}")

print(f"\n{PASS} passed, {FAIL} failed")
if __name__ == '__main__':
    sys.exit(1 if FAIL else 0)

