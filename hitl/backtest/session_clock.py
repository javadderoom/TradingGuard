"""
TradingGuard HITL - Institutional Session Clock & Seasonal DST Synchronizer
Handles dynamic Daylight Saving Time (DST) shifts across London (BST/GMT),
New York (EDT/EST), and Tehran (permanent UTC+3:30, no DST).

Schedules:
- Summer (BST / EDT):
  - London Open: 08:00 local = 07:00 UTC = 10:30 Tehran
  - NY Open:     08:00 local = 12:00 UTC = 15:30 Tehran
- Winter (GMT / EST):
  - London Open: 08:00 local = 08:00 UTC = 11:30 Tehran
  - NY Open:     08:00 local = 13:00 UTC = 16:30 Tehran
"""

import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, Tuple, Optional

TZ_LONDON = ZoneInfo("Europe/London")
TZ_NEW_YORK = ZoneInfo("America/New_York")
TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = datetime.timezone.utc


def get_session_times_for_date(d: datetime.date) -> Dict[str, Any]:
    """
    Computes exact session open times in UTC and Tehran local time for any historical or future date,
    automatically factoring in seasonal DST shifts in the UK and USA.
    """
    # 1. London Open at 08:00 local UK time
    lon_local = datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_LONDON)
    lon_utc = lon_local.astimezone(TZ_UTC)
    lon_tehran = lon_local.astimezone(TZ_TEHRAN)

    # 2. New York Open (Forex Killzone) at 08:00 local NY time
    ny_local = datetime.datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_NEW_YORK)
    ny_utc = ny_local.astimezone(TZ_UTC)
    ny_tehran = ny_local.astimezone(TZ_TEHRAN)

    # 3. NY Equity Cash Open at 09:30 local NY time (NYSE Open)
    nyse_local = datetime.datetime(d.year, d.month, d.day, 9, 30, tzinfo=TZ_NEW_YORK)
    nyse_utc = nyse_local.astimezone(TZ_UTC)
    nyse_tehran = nyse_local.astimezone(TZ_TEHRAN)

    return {
        "date": d,
        "is_uk_dst": bool(lon_local.dst()),
        "is_us_dst": bool(ny_local.dst()),
        "london": {
            "local_str": lon_local.strftime("%H:%M %Z"),
            "utc_time": lon_utc,
            "utc_str": lon_utc.strftime("%H:%M UTC"),
            "tehran_time": lon_tehran,
            "tehran_str": lon_tehran.strftime("%H:%M Tehran"),
            "hour_tehran": lon_tehran.hour,
            "minute_tehran": lon_tehran.minute
        },
        "new_york": {
            "local_str": ny_local.strftime("%H:%M %Z"),
            "utc_time": ny_utc,
            "utc_str": ny_utc.strftime("%H:%M UTC"),
            "tehran_time": ny_tehran,
            "tehran_str": ny_tehran.strftime("%H:%M Tehran"),
            "hour_tehran": ny_tehran.hour,
            "minute_tehran": ny_tehran.minute
        },
        "nyse_open": {
            "local_str": nyse_local.strftime("%H:%M %Z"),
            "utc_time": nyse_utc,
            "utc_str": nyse_utc.strftime("%H:%M UTC"),
            "tehran_time": nyse_tehran,
            "tehran_str": nyse_tehran.strftime("%H:%M Tehran"),
            "hour_tehran": nyse_tehran.hour,
            "minute_tehran": nyse_tehran.minute
        }
    }


def get_tehran_session_hours(d: datetime.date) -> Dict[str, int]:
    """Returns the exact integer hours for London and NY in Tehran time for any given date."""
    times = get_session_times_for_date(d)
    return {
        "london_hour": times["london"]["hour_tehran"],
        "ny_hour": times["new_york"]["hour_tehran"]
    }


def get_active_session_status(dt: Optional[datetime.datetime] = None) -> Tuple[bool, str, str]:
    """
    Determines whether the market is currently inside active institutional Killzones,
    dynamically resolving seasonal DST shifts across London, New York, and Tehran.

    Returns:
        (is_active, display_label, session_key)
        e.g., (True, "London Open (11:30 Tehran)", "London_Open")
              (True, "NY Silver Bullet (18:30 Tehran)", "NY_Silver_Bullet")
              (False, "Outside Killzones", "Outside_Killzones")
    """
    if dt is None:
        dt = datetime.datetime.now(TZ_UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_TEHRAN).astimezone(TZ_UTC)
    else:
        dt = dt.astimezone(TZ_UTC)

    d = dt.date()
    # Check weekend (Saturday = 5, Sunday = 6)
    if dt.weekday() in (5, 6):
        return False, "Weekend (Market Closed)", "Outside_Killzones"

    times = get_session_times_for_date(d)
    lon_open = times["london"]["utc_time"]
    lon_post = lon_open + datetime.timedelta(minutes=30)
    lon_end = lon_open + datetime.timedelta(hours=4)

    ny_open = times["new_york"]["utc_time"]
    ny_post = ny_open + datetime.timedelta(minutes=30)
    ny_sb_start = ny_open + datetime.timedelta(hours=2)   # 10:00 local NY time
    ny_sb_end = ny_sb_start + datetime.timedelta(hours=1) # 11:00 local NY time
    ny_end = ny_open + datetime.timedelta(hours=5)

    if lon_open <= dt < lon_post:
        return True, f"London Open ({times['london']['tehran_str']})", "London_Open"
    elif lon_post <= dt < lon_end:
        return True, "London Killzone", "London_Post_Open"
    elif ny_sb_start <= dt <= ny_sb_end:
        sb_tehran = (ny_sb_start.astimezone(TZ_TEHRAN)).strftime("%H:%M Tehran")
        return True, f"NY Silver Bullet ({sb_tehran})", "NY_Silver_Bullet"
    elif ny_open <= dt < ny_post:
        return True, f"NY Open ({times['new_york']['tehran_str']})", "NY_Open"
    elif ny_post <= dt <= ny_end:
        return True, "New York Regular Session", "NY_Post_Open"

    return False, "Outside Killzones", "Outside_Killzones"

