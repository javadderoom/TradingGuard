"""
TradingGuard HITL - TradingView Screen Capture Engine
Supports:
- Multi-Timeframe automated cycling (1H, 15M, 5M)
- Multi-Symbol tab switching (Tab 1: Gold, Tab 2: EURUSD)
- Clean GDI background rendering without address bar or tabs
"""

import os
import sys
import time
import ctypes
from ctypes import wintypes
from typing import List, Dict, Optional
from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def attach_to_default_desktop():
    """Attaches the current thread to the interactive Windows Default desktop."""
    h_desk = user32.OpenDesktopW('Default', 0, False, 0x01FF)
    if h_desk:
        user32.SetThreadDesktop(h_desk)
    return h_desk


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD)
    ]


def find_tradingview_window() -> Optional[int]:
    """Finds the main Chrome window hosting TradingView tabs."""
    attach_to_default_desktop()
    target_hwnd = None

    def enum_cb(hwnd, lparam):
        nonlocal target_hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        cls_buff = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buff, 256)
        if cls_buff.value == 'Chrome_WidgetWin_1':
            title_buff = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title_buff, 512)
            title = title_buff.value
            # Match Chrome with Google Chrome in title or large window
            if 'Google Chrome' in title or 'TradingView' in title:
                rect = wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 600 and h > 500:
                        target_hwnd = hwnd
                        return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return target_hwnd


def focus_window(hwnd: int):
    """Bypasses Windows ASFW lock and activates the window maximized."""
    user32.keybd_event(0x12, 0, 0, 0) # ALT down
    user32.ShowWindow(hwnd, 3)        # SW_MAXIMIZE (keeps browser full screen)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 2, 0) # ALT up
    time.sleep(0.2)


def switch_tab(hwnd: int, tab_index: int):
    """Switches to Chrome tab index (1-based: Ctrl+1, Ctrl+2, etc.)."""
    focus_window(hwnd)
    user32.keybd_event(0x11, 0, 0, 0) # CTRL down
    user32.keybd_event(0x30 + tab_index, 0, 0, 0) # Number key
    time.sleep(0.04)
    user32.keybd_event(0x30 + tab_index, 0, 2, 0)
    user32.keybd_event(0x11, 0, 2, 0) # CTRL up
    time.sleep(0.6)


TOOLBAR_TF_OFFSETS = {
    '1D': 570,
    'D': 570,
    '4H': 545,
    '1H': 465,
    '60': 465,
    '15M': 357,
    '15': 357,
    '5M': 322,
    '5': 322,
    '3M': 290,
    '1M': 260
}


def set_timeframe(hwnd: int, tf_str: str):
    """Switches TradingView timeframe by clicking pinned toolbar buttons or fallback to typing."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))

    key = tf_str.upper()
    if key in TOOLBAR_TF_OFFSETS:
        x_off = TOOLBAR_TF_OFFSETS[key]
        dx = rect.left + x_off
        dy = rect.top + 147
        user32.SetCursorPos(dx, dy)
        time.sleep(0.04)
        user32.mouse_event(0x0002, 0, 0, 0, 0) # LEFTDOWN
        time.sleep(0.04)
        user32.mouse_event(0x0004, 0, 0, 0, 0) # LEFTUP
        time.sleep(1.2) # Wait for candles to fetch & render
        return

    w = rect.right - rect.left
    h = rect.bottom - rect.top
    cx = rect.left + (w // 2)
    cy = rect.top + (h // 2)

    # Click chart canvas to focus TradingView shortcuts
    user32.SetCursorPos(cx, cy)
    time.sleep(0.05)
    user32.mouse_event(0x0002, 0, 0, 0, 0) # LEFTDOWN
    time.sleep(0.04)
    user32.mouse_event(0x0004, 0, 0, 0, 0) # LEFTUP
    time.sleep(0.1)

    # Send timeframe keys (e.g. '6', '0' for 1h; '1', '5' for 15m; '5' for 5m)
    for ch in tf_str:
        vk = ord(ch.upper())
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.03)

    time.sleep(0.1)
    user32.keybd_event(0x0D, 0, 0, 0) # ENTER
    time.sleep(0.04)
    user32.keybd_event(0x0D, 0, 2, 0)
    time.sleep(1.4) # Wait for candles to fetch & render


def capture_tradingview(output_path: str = 'analysis_assets/tv_latest.png', crop_chrome_ui: bool = True) -> Optional[str]:
    """Captures background screenshot of TradingView Chrome window."""
    attach_to_default_desktop()
    hwnd = find_tradingview_window()
    if not hwnd:
        print("[Capture] Error: TradingView Chrome window not found.")
        return None

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None

    w = rect.right - rect.left
    h = rect.bottom - rect.top

    if w <= 0 or h <= 0:
        return None

    hwnd_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    save_bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    gdi32.SelectObject(mem_dc, save_bmp)

    user32.PrintWindow(hwnd, mem_dc, 2)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem_dc, save_bmp, 0, h, buf, ctypes.byref(bmi), 0)

    gdi32.DeleteObject(save_bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)

    img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB')

    if crop_chrome_ui and h > 120:
        # Crop out top browser tabs and address bar (~82px in 1080p)
        top_crop = 82
        img = img.crop((0, top_crop, w, h))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, quality=95)
    return output_path


def capture_multi_timeframe(symbol: str = "XAUUSD") -> List[Dict[str, str]]:
    """
    Cycles through 1H, 15M, and 5M timeframes for the specified symbol.
    Tab 1 is dedicated to Gold (XAUUSD).
    Tab 2 is dedicated to Euro (EURUSD).
    Returns list of dicts: [{'path': str, 'caption': str}, ...]
    """
    attach_to_default_desktop()
    hwnd = find_tradingview_window()
    if not hwnd:
        return []

    is_gbp = "GBP" in symbol.upper()
    is_euro = "EUR" in symbol.upper()
    if is_gbp:
        tab_idx = 3
        sym_label = "GBPUSD"
        sym_icon = "💷"
    elif is_euro:
        tab_idx = 2
        sym_label = "EURUSD"
        sym_icon = "💶"
    else:
        tab_idx = 1
        sym_label = "XAUUSD"
        sym_icon = "🥇"

    # Switch to target tab
    switch_tab(hwnd, tab_idx)

    timeframes = [
        ("1D", "1D", "Daily Macro Order Flow & Key Liquidity Bias"),
        ("60", "1H", "Major Structure & Intraday Trend Direction"),
        ("15", "15M", "Market Structure Shifts & Liquidity POIs"),
        ("5", "5M", "Execution Entry & FVG Displacement Timing")
    ]

    out_dir = "analysis_assets/mtf"
    os.makedirs(out_dir, exist_ok=True)
    results = []

    for tf_code, tf_label, desc in timeframes:
        set_timeframe(hwnd, tf_code)
        file_path = os.path.abspath(f"{out_dir}/{sym_label}_{tf_label}.png")
        captured = capture_tradingview(file_path, crop_chrome_ui=True)
        if captured and os.path.exists(captured):
            # Stamp prominent institutional timeframe badge onto the captured chart
            try:
                from hitl.backtest.chart_renderer import overlay_timeframe_badge
                overlay_timeframe_badge(captured, tf_label)
            except Exception as e:
                print(f"[Capture] Badge overlay error: {e}")

            results.append({
                "path": captured,
                "caption": f"{sym_icon} *{sym_label} · {tf_label}*\n📌 _{desc}_"
            })

    # Automatically generate merged 2x2 MTF grid image
    try:
        from hitl.backtest.chart_renderer import create_mtf_grid_image
        p_1d = os.path.abspath(f"{out_dir}/{sym_label}_1D.png")
        p_1h = os.path.abspath(f"{out_dir}/{sym_label}_1H.png")
        p_15m = os.path.abspath(f"{out_dir}/{sym_label}_15M.png")
        p_5m = os.path.abspath(f"{out_dir}/{sym_label}_5M.png")
        p_grid = os.path.abspath(f"{out_dir}/{sym_label}_MTF_GRID.png")
        create_mtf_grid_image(p_1d, p_1h, p_15m, p_5m, p_grid)
    except Exception as e:
        print(f"[Capture] MTF grid generation error: {e}")

    return results
