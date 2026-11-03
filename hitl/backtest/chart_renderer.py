"""
TradingGuard HITL - High-Fidelity PIL Candlestick Chart Renderer
Renders institutional dark-mode multi-timeframe charts (TradingView styling)
directly from MT5 OHLC rates with zero external plotting dependencies.
"""

import sys
import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# TradingView Color Palette
BG_COLOR = (19, 23, 34)           # #131722 Dark background
PANEL_BG = (24, 29, 42)          # Header panel
GRID_COLOR = (32, 38, 54)        # Grid lines
TEXT_MUTED = (140, 150, 175)     # Secondary text / axis
TEXT_LIGHT = (235, 240, 250)     # Primary text
GREEN_CANDLE = (8, 153, 129)     # #089981 Bullish candle & wick
RED_CANDLE = (242, 54, 69)       # #f23645 Bearish candle & wick
PRICE_AXIS_BG = (20, 24, 35)     # Right sidebar


# Timeframe color accents
TIMEFRAME_META: Dict[str, Dict[str, Any]] = {
    "1D": {"tag": "1D", "accent": (41, 98, 255)},    # Vibrant Blue
    "1H": {"tag": "1H", "accent": (255, 109, 0)},   # Vivid Orange
    "15M": {"tag": "15M", "accent": (171, 71, 188)},# Vivid Purple
    "5M": {"tag": "5M", "accent": (0, 230, 118)},   # Neon Emerald
}


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Safely loads Windows/system TrueType fonts with graceful fallback."""
    candidates = (
        ["arialbd.ttf", "segoeuib.ttf", "calibrib.ttf", "tahomabd.ttf"]
        if bold
        else ["arial.ttf", "segoeui.ttf", "calibri.ttf", "tahoma.ttf"]
    )
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_horizontal_dashed_line(
    draw: ImageDraw.ImageDraw,
    x0: int,
    x1: int,
    y: int,
    color: tuple,
    dash_len: int = 7,
    space_len: int = 5,
    width: int = 1
):
    """Draws a clean horizontal dashed reference line across the chart."""
    curr_x = x0
    while curr_x < x1:
        end_x = min(curr_x + dash_len, x1)
        draw.line([(curr_x, y), (end_x, y)], fill=color, width=width)
        curr_x += dash_len + space_len


def get_broker_utc_offset_seconds() -> int:
    """Computes broker server timezone offset relative to true UTC in seconds."""
    try:
        import MetaTrader5 as mt5
        for sym in ["XAUUSD_o", "GBPUSD_o", "EURUSD_o", "XAUUSD", "GBPUSD"]:
            t = mt5.symbol_info_tick(sym)
            if t and t.time > 0:
                utc_now = datetime.datetime.now(datetime.timezone.utc).timestamp()
                return int(round((t.time - utc_now) / 3600.0) * 3600)
    except Exception:
        pass
    return 7200  # Default to EET (UTC+2)


def extract_chart_landmarks(
    symbol: str,
    rates_1d: Optional[List[Dict[str, Any]]] = None,
    rates_5m_full: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Extracts key institutional benchmark levels (PDH, PDL, Asian High/Low, London High/Low)
    for horizontal projection onto lower timeframe execution charts (5M and 15M).
    Uses strict UTC time conversion respecting broker server timezone offsets.
    """
    levels = []
    is_fx = "XAU" not in symbol.upper()
    fmt = ".5f" if is_fx else ".2f"

    # Prior Day High / Low
    if rates_1d and len(rates_1d) >= 2:
        prev_day = rates_1d[-2]
        pdh = prev_day.get("high")
        pdl = prev_day.get("low")
        if pdh:
            levels.append({
                "price": pdh,
                "label": f"PDH · {pdh:{fmt}}",
                "color": (242, 84, 91)   # Coral Red
            })
        if pdl:
            levels.append({
                "price": pdl,
                "label": f"PDL · {pdl:{fmt}}",
                "color": (41, 182, 246)  # Cyan Teal
            })

    # Session Benchmarks (Asian and London)
    if rates_5m_full:
        try:
            offset_sec = get_broker_utc_offset_seconds()

            # Map each bar's timestamp to true UTC datetime
            for b in rates_5m_full:
                b["_utc_dt"] = datetime.datetime.fromtimestamp(b["time"] - offset_sec, datetime.timezone.utc)

            last_dt = rates_5m_full[-1]["_utc_dt"]
            today_bars = [
                b for b in rates_5m_full
                if b["_utc_dt"].date() == last_dt.date()
            ]

            # True Asian Range (00:00 to 07:00 UTC / 03:30 to 10:30 Tehran)
            asian_bars = [
                b for b in today_bars
                if 0 <= b["_utc_dt"].hour < 7
            ]
            if asian_bars:
                a_h = max(b["high"] for b in asian_bars)
                a_l = min(b["low"] for b in asian_bars)
                levels.append({
                    "price": a_h,
                    "label": f"Asian High · {a_h:{fmt}}",
                    "color": (240, 185, 11)  # Amber Gold
                })
                levels.append({
                    "price": a_l,
                    "label": f"Asian Low · {a_l:{fmt}}",
                    "color": (240, 185, 11)  # Amber Gold
                })

            # True London Session (07:00 to 12:00 UTC / 10:30 to 15:30 Tehran)
            london_bars = [
                b for b in today_bars
                if 7 <= b["_utc_dt"].hour < 12
            ]
            if london_bars:
                l_h = max(b["high"] for b in london_bars)
                l_l = min(b["low"] for b in london_bars)
                levels.append({
                    "price": l_h,
                    "label": f"London High · {l_h:{fmt}}",
                    "color": (92, 140, 250)  # Royal Blue
                })
                levels.append({
                    "price": l_l,
                    "label": f"London Low · {l_l:{fmt}}",
                    "color": (92, 140, 250)  # Royal Blue
                })
        except Exception as e:
            print(f"[ChartRenderer] Error extracting session landmarks: {e}")

    return levels


def render_candlestick_chart(
    rates: List[Dict[str, Any]],
    symbol: str,
    timeframe_str: str,
    output_path: Path,
    width: int = 1280,
    height: int = 720,
    horizontal_levels: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """
    Renders an institutional candlestick chart with exact wicks, bodies, grid lines,
    price scale, and prominent timeframe displayed in the center of the chart.
    """
    if not rates or len(rates) < 5:
        print(f"[ChartRenderer] Insufficient rate data ({len(rates) if rates else 0} bars).")
        return False

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_tag = _get_font(18, bold=True)
    font_sym = _get_font(20, bold=True)
    font_ohlc = _get_font(14, bold=True)
    font_axis = _get_font(12, bold=False)
    font_watermark = _get_font(160, bold=True)

    # Margins and layout
    pad_top = 65
    pad_bottom = 42
    pad_left = 22
    pad_right = 95  # Price axis
    
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom

    # Find global High and Low
    highs = [r['high'] for r in rates]
    lows = [r['low'] for r in rates]
    min_price = min(lows)
    max_price = max(highs)

    price_range = max_price - min_price
    if price_range <= 0:
        price_range = 1.0

    # Add 5% breathing room top and bottom
    min_price -= price_range * 0.05
    max_price += price_range * 0.05
    price_range = max_price - min_price

    def to_y(p: float) -> int:
        return int(pad_top + chart_h - ((p - min_price) / price_range * chart_h))

    # Subtle Single Timeframe Watermark in the Center of the Chart (Rendered Once)
    wm_text = timeframe_str.upper()
    try:
        wm_bbox = draw.textbbox((0, 0), wm_text, font=font_watermark)
        wm_w = wm_bbox[2] - wm_bbox[0]
        wm_h = wm_bbox[3] - wm_bbox[1]
        wm_x = pad_left + (chart_w - wm_w) // 2
        wm_y = pad_top + (chart_h - wm_h) // 2
        draw.text((wm_x, wm_y), wm_text, fill=(30, 37, 52), font=font_watermark)
    except Exception:
        pass

    # Horizontal Price Grid Lines
    grid_steps = 6
    for i in range(grid_steps + 1):
        p_val = min_price + (i * (price_range / grid_steps))
        y_pos = to_y(p_val)
        draw.line([(pad_left, y_pos), (pad_left + chart_w, y_pos)], fill=GRID_COLOR, width=1)
        # Price label on right axis
        p_str = f"{p_val:.2f}" if "XAU" in symbol.upper() else f"{p_val:.5f}"
        draw.text((pad_left + chart_w + 8, y_pos - 7), p_str, fill=TEXT_MUTED, font=font_axis)

    # Vertical Price Axis Border
    draw.line([(pad_left + chart_w, pad_top), (pad_left + chart_w, pad_top + chart_h)], fill=GRID_COLOR, width=1)

    # Projected Benchmark Landmark Lines (PDH, PDL, Session Extremes)
    if horizontal_levels:
        font_lvl = _get_font(11, bold=True)
        for lvl in horizontal_levels:
            p = lvl.get("price")
            if p is None or not (min_price <= p <= max_price):
                continue
            y_lvl = to_y(p)
            col = lvl.get("color", (120, 140, 180))
            # Draw dashed line across chart
            draw_horizontal_dashed_line(
                draw, pad_left, pad_left + chart_w, y_lvl, col, dash_len=7, space_len=5, width=1
            )
            # Pinned pill label on the left
            lbl = lvl.get("label", "")
            if lbl:
                lbl_bbox = draw.textbbox((0, 0), lbl, font=font_lvl)
                lw = lbl_bbox[2] - lbl_bbox[0]
                draw.rounded_rectangle(
                    [pad_left + 10, y_lvl - 16, pad_left + 18 + lw, y_lvl - 2],
                    radius=4,
                    fill=(15, 18, 26),
                    outline=col,
                    width=1
                )
                draw.text((pad_left + 14, y_lvl - 15), lbl, fill=col, font=font_lvl)

            # Highlighted price marker on right axis
            p_fmt = f"{p:.2f}" if "XAU" in symbol.upper() else f"{p:.5f}"
            draw.rectangle([pad_left + chart_w + 2, y_lvl - 8, width - 4, y_lvl + 8], fill=(22, 28, 40), outline=col, width=1)
            draw.text((pad_left + chart_w + 6, y_lvl - 6), p_fmt, fill=col, font=font_axis)

    # Draw Candlesticks
    num_bars = len(rates)
    slot_w = chart_w / num_bars
    candle_w = max(2, int(slot_w * 0.7))

    for idx, bar in enumerate(rates):
        x_center = int(pad_left + (idx + 0.5) * slot_w)
        y_open = to_y(bar['open'])
        y_close = to_y(bar['close'])
        y_high = to_y(bar['high'])
        y_low = to_y(bar['low'])

        is_bull = bar['close'] >= bar['open']
        color = GREEN_CANDLE if is_bull else RED_CANDLE

        # Wick
        draw.line([(x_center, y_high), (x_center, y_low)], fill=color, width=1)

        # Body
        top_y = min(y_open, y_close)
        bot_y = max(y_open, y_close)
        if bot_y == top_y:
            bot_y += 1  # Doji minimum 1px height

        x_left = x_center - (candle_w // 2)
        x_right = x_left + candle_w
        draw.rectangle([x_left, top_y, x_right, bot_y], fill=color, outline=color)

        # Date / Time label on bottom axis every ~10 bars
        if idx % max(1, (num_bars // 6)) == 0 or idx == num_bars - 1:
            dt = datetime.datetime.fromtimestamp(bar['time'])
            if timeframe_str == "1D":
                t_str = dt.strftime("%b %d")
            elif timeframe_str in ["1H", "15M"]:
                t_str = dt.strftime("%m/%d %H:%M")
            else:
                t_str = dt.strftime("%H:%M")
            draw.text((x_center - 18, pad_top + chart_h + 8), t_str, fill=TEXT_MUTED, font=font_axis)

    # Current Price Marker on Right Axis
    latest = rates[-1]
    curr_y = to_y(latest['close'])
    curr_p_str = f"{latest['close']:.2f}" if "XAU" in symbol.upper() else f"{latest['close']:.5f}"
    is_latest_bull = latest['close'] >= latest['open']
    change_color = GREEN_CANDLE if is_latest_bull else RED_CANDLE
    draw.rectangle([pad_left + chart_w + 2, curr_y - 10, width - 4, curr_y + 10], fill=change_color)
    draw.text((pad_left + chart_w + 8, curr_y - 7), curr_p_str, fill=(255, 255, 255), font=font_axis)

    # Top Header Banner
    draw.rectangle([0, 0, width, pad_top - 5], fill=PANEL_BG)
    draw.line([(0, pad_top - 5), (width, pad_top - 5)], fill=(36, 43, 60), width=1)

    # Timeframe Badge (Clean, compact tag)
    meta = TIMEFRAME_META.get(timeframe_str.upper(), {"accent": (41, 98, 255)})
    accent = meta["accent"]
    tag_txt = timeframe_str.upper()

    x_pill = 18
    y_pill = 14
    tag_bbox = draw.textbbox((0, 0), tag_txt, font=font_tag)
    tag_w = tag_bbox[2] - tag_bbox[0]
    pill_w = tag_w + 22
    pill_h = 32

    draw.rounded_rectangle([x_pill, y_pill, x_pill + pill_w, y_pill + pill_h], radius=6, fill=accent)
    draw.text((x_pill + 11, y_pill + 6), tag_txt, fill=(255, 255, 255), font=font_tag)

    # Symbol text right next to badge
    x_sym = x_pill + pill_w + 14
    draw.text((x_sym, 18), f"•  {symbol}", fill=TEXT_LIGHT, font=font_sym)

    # Right side: OHLC info in crisp font
    p_format = ".2f" if "XAU" in symbol.upper() else ".5f"
    ohlc_text = (
        f"O: {latest['open']:{p_format}}  "
        f"H: {latest['high']:{p_format}}  "
        f"L: {latest['low']:{p_format}}  "
        f"C: {latest['close']:{p_format}}"
    )
    ohlc_bbox = draw.textbbox((0, 0), ohlc_text, font=font_ohlc)
    ohlc_w = ohlc_bbox[2] - ohlc_bbox[0]
    draw.text((width - ohlc_w - 25, 18), ohlc_text, fill=change_color, font=font_ohlc)

    # Save to disk
    img.save(output_path, "PNG", optimize=True)
    return True


def create_mtf_grid_image(
    p_1d: Path,
    p_1h: Path,
    p_15m: Path,
    p_5m: Path,
    output_path: Path,
    target_width: int = 1600,
    target_height: int = 900
) -> bool:
    """
    Combines 4 MTF candlestick chart images into a clean 2x2 grid image (1D, 1H, 15M, 5M).
    Each quadrant displays its timeframe clearly and boldly in the center.
    """
    try:
        paths = [Path(p_1d), Path(p_1h), Path(p_15m), Path(p_5m)]
        if not all(p.exists() for p in paths):
            return False

        w_half = target_width // 2
        h_half = target_height // 2

        im_1d = Image.open(p_1d).resize((w_half, h_half), Image.Resampling.LANCZOS)
        im_1h = Image.open(p_1h).resize((w_half, h_half), Image.Resampling.LANCZOS)
        im_15m = Image.open(p_15m).resize((w_half, h_half), Image.Resampling.LANCZOS)
        im_5m = Image.open(p_5m).resize((w_half, h_half), Image.Resampling.LANCZOS)

        grid = Image.new("RGB", (target_width, target_height), BG_COLOR)
        grid.paste(im_1d, (0, 0))
        grid.paste(im_1h, (w_half, 0))
        grid.paste(im_15m, (0, h_half))
        grid.paste(im_5m, (w_half, h_half))

        draw = ImageDraw.Draw(grid)

        # Crisp crosshair dividers cleanly framing the 4 quadrants
        BORDER_COLOR = (45, 52, 70)
        draw.line([(w_half, 0), (w_half, target_height)], fill=BORDER_COLOR, width=3)
        draw.line([(0, h_half), (target_width, h_half)], fill=BORDER_COLOR, width=3)
        draw.rectangle([(0, 0), (target_width - 1, target_height - 1)], outline=BORDER_COLOR, width=2)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        grid.save(output_path, "PNG", optimize=True)
        return True
    except Exception as e:
        print(f"[ChartRenderer] Error creating MTF grid image: {e}")
        return False


def overlay_timeframe_badge(
    image_path: Path | str,
    timeframe_str: str,
    output_path: Path | str | None = None
) -> bool:
    """
    Overlays a prominent timeframe centered on the image and a clean corner badge.
    """
    try:
        p_in = Path(image_path)
        if not p_in.exists():
            return False

        p_out = Path(output_path) if output_path else p_in
        img = Image.open(p_in).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        tf_tag = timeframe_str.upper()
        meta = TIMEFRAME_META.get(tf_tag, {"accent": (41, 98, 255)})
        accent = meta["accent"]

        # Subtle timeframe centered in the middle of the image
        font_wm = _get_font(140, bold=True)
        wm_bbox = draw.textbbox((0, 0), tf_tag, font=font_wm)
        wm_w = wm_bbox[2] - wm_bbox[0]
        wm_h = wm_bbox[3] - wm_bbox[1]
        draw.text(((w - wm_w) // 2, (h - wm_h) // 2), tf_tag, fill=(30, 37, 52), font=font_wm)

        # Compact corner badge
        font_tag = _get_font(22, bold=True)
        tag_bbox = draw.textbbox((0, 0), tf_tag, font=font_tag)
        tag_w = tag_bbox[2] - tag_bbox[0]
        pill_w = tag_w + 26
        pill_h = 38
        draw.rounded_rectangle([20, 18, 20 + pill_w, 18 + pill_h], radius=6, fill=accent)
        draw.text((33 - tag_w // 2, 25), tf_tag, fill=(255, 255, 255), font=font_tag)

        p_out.parent.mkdir(parents=True, exist_ok=True)
        img.save(p_out, "PNG", optimize=True)
        return True
    except Exception as e:
        print(f"[ChartRenderer] Failed to overlay timeframe badge: {e}")
        return False


if __name__ == "__main__":
    import MetaTrader5 as mt5
    from hitl.mt5_engine import MT5Engine

    engine = MT5Engine()
    if not engine.ensure_connected():
        print("MT5 initialization failed")
        sys.exit(1)

    sym = engine.resolve_symbol("XAUUSD")
    bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 60)

    if bars is not None and len(bars) > 0:
        bar_list = [
            {
                'time': int(b[0]),
                'open': float(b[1]),
                'high': float(b[2]),
                'low': float(b[3]),
                'close': float(b[4]),
                'tick_volume': int(b[5])
            }
            for b in bars
        ]
        out_f = BASE_DIR / "analysis_assets" / "backtest_sample_H1.png"
        render_candlestick_chart(bar_list, "XAUUSD", "1H", out_f)
        print(f"Sample chart saved successfully to: {out_f}")
    else:
        print("Could not fetch test bars.")
