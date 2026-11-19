import sqlite3
import json
import datetime
from pathlib import Path
import MetaTrader5 as mt5

print("=== 1. CHECKING MT5 TRADE HISTORY FOR LAST WEEK (NOV 9 - NOV 14) ===")
if mt5.initialize():
    t_from = datetime.datetime(2026, 11, 9, 0, 0)
    t_to = datetime.datetime(2026, 11, 14, 0, 0)
    deals = mt5.history_deals_get(t_from, t_to)
    orders = mt5.history_orders_get(t_from, t_to)
    print(f"Total MT5 orders in history: {len(orders) if orders else 0}")
    print(f"Total MT5 deals in history: {len(deals) if deals else 0}")
    if deals:
        for d in deals:
            t_dt = datetime.datetime.fromtimestamp(d.time)
            print(f"Deal {d.ticket}: {d.symbol} Type={d.type} Vol={d.volume} Price={d.price} Profit=${d.profit:.2f} Comm=${d.commission:.2f} Time={t_dt} Comment={d.comment}")
    if orders:
        for o in orders:
            t_dt = datetime.datetime.fromtimestamp(o.time_setup)
            print(f"Order {o.ticket}: {o.symbol} Type={o.type} State={o.state} Vol={o.volume_initial} Price={o.price_open} SL={o.sl} TP={o.tp} Time={t_dt} Comment={o.comment}")

print("\n=== 2. CHECKING COUNCIL DECISIONS LOG ===")
council_log = Path("hitl/memory/council_decisions_log.json")
if council_log.exists():
    try:
        with open(council_log, "r", encoding="utf-8") as f:
            cdata = json.load(f)
            print(f"Council decisions count: {len(cdata)}")
            # Filter for last week
            for item in cdata:
                ts = item.get("timestamp") or item.get("created_at") or ""
                if "2026-11-09" <= ts[:10] <= "2026-11-14":
                    print("  Decision:", ts, item.get("symbol"), item.get("decision"), item.get("setup_id"), item.get("archetype"))
    except Exception as e:
        print("Error reading council log:", e)

print("\n=== 3. CHECKING SQLITE DB TRADES ===")
db_path = Path("tradingguard.db")
if db_path.exists():
    try:
        conn = sqlite3.connect("tradingguard.db")
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cur.fetchall()]
        print("Tables in tradingguard.db:", tables)
        for tbl in tables:
            cur.execute(f"PRAGMA table_info({tbl});")
            cols = [c[1] for c in cur.fetchall()]
            print(f"  Table: {tbl} (columns: {cols})")
            if "trade" in tbl.lower() or "session" in tbl.lower():
                cur.execute(f"SELECT * FROM {tbl} ORDER BY id DESC LIMIT 15;")
                rows = cur.fetchall()
                print(f"  Recent rows in {tbl}: {len(rows)}")
                for r in rows:
                    print("    ", r)
    except Exception as e:
        print("DB Error:", e)
