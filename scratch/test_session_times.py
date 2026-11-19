import sys
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_UTC = datetime.timezone.utc

def get_session_times(d: datetime.date):
    lon_local = datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_LONDON)
    lon_utc = lon_local.astimezone(TZ_UTC)
    is_uk_dst = bool(lon_local.dst())

    ny_local = datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_NEW_YORK)
    ny_utc = ny_local.astimezone(TZ_UTC)
    is_us_dst = bool(ny_local.dst())

    nyse_local = datetime.datetime(d.year, d.month, d.day, 9, 30, tzinfo=TZ_NEW_YORK)
    nyse_utc = nyse_local.astimezone(TZ_UTC)

    return {
        "date": d,
        "is_uk_dst": is_uk_dst,
        "is_us_dst": is_us_dst,
        "london_open_utc": lon_utc,
        "ny_open_utc": ny_utc,
        "nyse_open_utc": nyse_utc,
        "london_open_hour_utc": lon_utc.hour,
        "ny_open_hour_utc": ny_utc.hour,
        "nyse_open_hour_utc": nyse_utc.hour,
        "nyse_open_minute_utc": nyse_utc.minute,
    }

print("Summer 2026-07-15:", get_session_times(datetime.date(2026, 7, 15)))
print("Winter 2026-11-10:", get_session_times(datetime.date(2026, 11, 10)))
