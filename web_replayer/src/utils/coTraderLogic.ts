/**
 * TradingGuard HITL Visual Co-Backtester - Core Logic & Coordinate Helpers
 * Implements:
 * - Dynamic Seasonal Session Clock (EET/EEST Athens -> UTC -> Tehran UTC+3:30)
 * - Pure R:R calculation without arbitrary clipping
 * - $20 system risk limit check matching evaluator.py:306-323
 * - Zero-lookahead blind replay trade masking and dynamic scorecard calculation
 */

import type {
  AsianRangeDay,
  BotDiagnostic,
  BreakerBox,
  Candle,
  CatalogSymbol,
  ClockMode,
  EngineClockMode,
  FvgBox,
  ReplayTrade,
  Scorecard,
  SelectedSmcElement,
  SmcElementKind,
  SweepFlag,
  Timeframe,
  TradeDirection,
} from '../types/replay';

export interface ServerZoneTimes {
  srv_str: string;
  utc_str: string;
  tehran_str: string;
  srv_epoch: number;
  utc_epoch: number;
  tehran_epoch: number;
  offset_sec: number;
  date_str: string;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

/**
 * Returns Athens (EET/EEST) UTC offset in seconds for a given server epoch.
 * Europe/Athens DST: starts last Sunday in March at 04:00 local time (10800s, UTC+3)
 * Ends last Sunday in October at 04:00 local time (7200s, UTC+2).
 */
export function getAthensBrokerOffset(srvEpoch: number): number {
  const d = new Date(srvEpoch * 1000);
  const y = d.getUTCFullYear();

  // Last Sunday in March
  const lastSunMarch = 31 - new Date(Date.UTC(y, 2, 31)).getUTCDay();
  const dstStart = Date.UTC(y, 2, lastSunMarch, 4, 0, 0) / 1000;

  // Last Sunday in October
  const lastSunOct = 31 - new Date(Date.UTC(y, 9, 31)).getUTCDay();
  const dstEnd = Date.UTC(y, 9, lastSunOct, 4, 0, 0) / 1000;

  return srvEpoch >= dstStart && srvEpoch < dstEnd ? 10800 : 7200;
}

/**
 * Converts MT5 server wall-clock epoch into server, UTC, and Tehran times faithfully.
 */
export function convertServerEpochToZones(srvEpoch: number): ServerZoneTimes {
  const offsetSec = getAthensBrokerOffset(srvEpoch);
  const utcEpoch = srvEpoch - offsetSec;
  // Tehran abolished DST permanently: fixed UTC+3:30 (12600s) year-round
  const tehranEpoch = utcEpoch + 12600;

  const srvDate = new Date(srvEpoch * 1000);
  const utcDate = new Date(utcEpoch * 1000);
  const tehDate = new Date(tehranEpoch * 1000);

  const srv_str = `${pad2(srvDate.getUTCHours())}:${pad2(srvDate.getUTCMinutes())}`;
  const utc_str = `${pad2(utcDate.getUTCHours())}:${pad2(utcDate.getUTCMinutes())}`;
  const tehran_str = `${pad2(tehDate.getUTCHours())}:${pad2(tehDate.getUTCMinutes())}`;
  const date_str = `${srvDate.getUTCFullYear()}-${pad2(srvDate.getUTCMonth() + 1)}-${pad2(srvDate.getUTCDate())}`;

  return {
    srv_str,
    utc_str,
    tehran_str,
    srv_epoch: srvEpoch,
    utc_epoch: utcEpoch,
    tehran_epoch: tehranEpoch,
    offset_sec: offsetSec,
    date_str,
  };
}

/**
 * Formats server epoch tick for lightweight-charts crosshair & axis labels.
 */
export function formatClockTick(
  srvEpoch: number,
  clockMode: ClockMode,
  includeDate: boolean = false
): string {
  const zones = convertServerEpochToZones(srvEpoch);
  let timeStr = zones.srv_str;
  if (clockMode === 'utc') {
    timeStr = zones.utc_str;
  } else if (clockMode === 'tehran') {
    timeStr = zones.tehran_str;
  }

  if (includeDate) {
    return `${zones.date_str} ${timeStr}`;
  }
  return timeStr;
}

/**
 * Computes uncapped true R:R from Entry, SL, and TP.
 * For Long: (tp - entry) / (entry - sl)
 * For Short: (entry - tp) / (sl - entry)
 */
export function computeTradeRR(
  entry: number,
  sl: number,
  tp: number,
  dir?: TradeDirection
): number {
  const isBuy = dir ? dir === 'LONG' : tp > entry;
  const risk = Math.abs(entry - sl);
  if (risk === 0) return 0.0;

  const reward = isBuy ? tp - entry : entry - tp;
  return Number((reward / risk).toFixed(2));
}

/**
 * Maps symbol to dollar value per point per 0.01 reference lot.
 * Exactly mirrors hitl/backtest/evaluator.py:306-323.
 */
export function getSymbolPipValue(symbol: string): number {
  const sym = symbol.toUpperCase();
  if (sym.includes('XAU')) return 1.0;
  if (sym.includes('XAG')) return 50.0;
  if (sym.includes('EUR') || sym.includes('GBP')) return 1000.0;
  if (sym.includes('BTC')) return 0.01;
  if (['NQ', 'NAS', 'US100', 'SPX', 'US500', 'YM', 'US30', 'DJ'].some((k) => sym.includes(k))) {
    return 0.10;
  }
  return 1.0;
}

/**
 * Calculates raw risk in USD for a trade setup at reference lot (0.01).
 */
export function calculateTradeRiskUSD(
  symbol: string,
  entry: number,
  sl: number,
  lot: number = 0.01
): number {
  const pipVal = getSymbolPipValue(symbol);
  const riskPts = Math.abs(entry - sl);
  return Number(((riskPts * pipVal * (lot / 0.01))).toFixed(2));
}

/**
 * Checks whether trade setup complies with system-wide $20 risk limit.
 */
export function checkRiskLimitUSD(
  symbol: string,
  entry: number,
  sl: number,
  lot: number = 0.01,
  maxRiskUsd: number = 20.0
): { riskUsd: number; exceedsRiskCap: boolean; pipVal: number; riskPts: number } {
  const pipVal = getSymbolPipValue(symbol);
  const riskPts = Math.abs(entry - sl);
  const riskUsd = Number(((riskPts * pipVal * (lot / 0.01))).toFixed(2));
  return {
    riskUsd,
    exceedsRiskCap: riskUsd > maxRiskUsd,
    pipVal,
    riskPts: Number(riskPts.toFixed(5)),
  };
}

/**
 * Anti-spoiler blind replay trade filter.
 * Hides exit_time, realized outcome, and PnL when replayTo is prior to trade exit.
 */
export function maskBlindReplayTrade(
  trade: ReplayTrade,
  replayTo: number | null
): ReplayTrade {
  if (replayTo === null) {
    return { ...trade };
  }

  // Not filled yet
  if (trade.fill_time && trade.fill_time > replayTo) {
    return {
      ...trade,
      status: 'PENDING',
      fill_time: null,
      exit_time: null,
      realized_pnl_usd: null,
      rr_realized: null,
      notes: undefined,
    };
  }

  // Filled but not exited yet
  if (trade.exit_time && trade.exit_time > replayTo) {
    return {
      ...trade,
      status: 'OPEN',
      exit_time: null,
      realized_pnl_usd: null,
      rr_realized: null,
      notes: undefined,
    };
  }

  return { ...trade };
}

/**
 * Computes Scorecard metrics filtering out trades that have not completed by replayTo.
 */
export function computeReplayScorecard(
  trades: ReplayTrade[],
  replayTo: number | null
): Scorecard {
  const closedTrades = trades.filter((t) => {
    if (replayTo !== null) {
      if (t.decision_time > replayTo) return false;
      if (!t.exit_time || t.exit_time > replayTo) return false;
    }
    return t.status === 'WIN' || t.status === 'LOSS' || t.status === 'BREAKEVEN';
  });

  const total = closedTrades.length;
  if (total === 0) {
    return {
      total_trades: 0,
      wins: 0,
      losses: 0,
      breakevens: 0,
      win_rate_pct: 0.0,
      net_pnl_usd: 0.0,
      net_rr: 0.0,
      profit_factor: 0.0,
      max_drawdown_usd: 0.0,
    };
  }

  const wins = closedTrades.filter((t) => t.status === 'WIN');
  const losses = closedTrades.filter((t) => t.status === 'LOSS');
  const breakevens = closedTrades.filter((t) => t.status === 'BREAKEVEN');

  const grossWin = wins.reduce((acc, t) => acc + (t.realized_pnl_usd ?? 0), 0);
  const grossLoss = Math.abs(losses.reduce((acc, t) => acc + (t.realized_pnl_usd ?? 0), 0));
  const netPnl = Number(closedTrades.reduce((acc, t) => acc + (t.realized_pnl_usd ?? 0), 0).toFixed(2));
  const netRr = Number(closedTrades.reduce((acc, t) => acc + (t.rr_realized ?? 0), 0).toFixed(2));

  const pf = grossLoss > 0 ? Number((grossWin / grossLoss).toFixed(2)) : grossWin > 0 ? 99.0 : 0.0;
  const wr = Number(((wins.length / total) * 100).toFixed(1));

  let running = 0.0;
  let peak = 0.0;
  let maxDd = 0.0;
  // Evaluate cash balance drawdown strictly by realization (exit_time) order
  const sorted = [...closedTrades].sort((a, b) => {
    const exitA = a.exit_time ?? a.decision_time;
    const exitB = b.exit_time ?? b.decision_time;
    return exitA - exitB;
  });
  for (const t of sorted) {
    running += t.realized_pnl_usd ?? 0;
    if (running > peak) peak = running;
    const dd = peak - running;
    if (dd > maxDd) maxDd = dd;
  }

  return {
    total_trades: total,
    wins: wins.length,
    losses: losses.length,
    breakevens: breakevens.length,
    win_rate_pct: wr,
    net_pnl_usd: netPnl,
    net_rr: netRr,
    profit_factor: pf,
    max_drawdown_usd: Number(maxDd.toFixed(2)),
  };
}

/**
 * Causal Liquidity Sweep Extraction (Zero-Lookahead)
 * Detects genuine Liquidity Sweeps (SFP / Turtle Soup):
 * 1. First unbroken Asian High/Low raid where price pushes out from inside and closes back inside.
 * 2. Confirmed causal Swing High/Low (3L/3R) liquidity grabs with >= 35% rejection wick & inside close.
 * Never re-fires on already-broken levels or choppy bounces below broken support / above broken resistance.
 */
export function extractLiquiditySweeps(
  candles: Candle[],
  asianRanges: Record<string, AsianRangeDay> | AsianRangeDay[],
  replayTo: number | null
): SweepFlag[] {
  const visibleCandles =
    replayTo !== null ? candles.filter((c) => c.time <= replayTo) : candles;
  if (visibleCandles.length === 0) return [];

  const arList: AsianRangeDay[] = (
    Array.isArray(asianRanges) ? asianRanges : Object.values(asianRanges)
  )
    .slice()
    .sort((a, b) => a.start_time - b.start_time);

  const sweeps: SweepFlag[] = [];
  const emittedKeys = new Set<string>();

  // Track 1: First unbroken raid of Asian High / Asian Low per session day
  for (let aIdx = 0; aIdx < arList.length; aIdx++) {
    const ar = arList[aIdx];
    const nextStart = aIdx + 1 < arList.length ? arList[aIdx + 1].start_time : ar.end_time + 57600;
    const cutoffEnd = Math.min(nextStart, ar.end_time + 57600);
    const sessionCandles = visibleCandles.filter(
      (c) => c.time > ar.end_time && c.time < cutoffEnd
    );

    let highExhausted = false;
    let lowExhausted = false;

    for (const c of sessionCandles) {
      if (!highExhausted) {
        if (c.open <= ar.high && c.high > ar.high && c.close < ar.high) {
          sweeps.push({
            time: c.time,
            price: c.high,
            type: 'HIGH_SWEEP',
            label: `Asian BSL Sweep (${ar.high})`,
            level: ar.high,
            origin_time: ar.end_time,
            session: 'Asian',
          });
          emittedKeys.add(`HIGH:${c.time}`);
          highExhausted = true;
        } else if (c.close > ar.high) {
          highExhausted = true;
        }
      }

      if (!lowExhausted) {
        if (c.open >= ar.low && c.low < ar.low && c.close > ar.low) {
          sweeps.push({
            time: c.time,
            price: c.low,
            type: 'LOW_SWEEP',
            label: `Asian SSL Sweep (${ar.low})`,
            level: ar.low,
            origin_time: ar.end_time,
            session: 'Asian',
          });
          emittedKeys.add(`LOW:${c.time}`);
          lowExhausted = true;
        } else if (c.close < ar.low) {
          lowExhausted = true;
        }
      }

      if (highExhausted && lowExhausted) break;
    }
  }

  // Track 2 & 3: Causal 3L/3R major swing pivots (>=35% wick) + 1L/1R minor swing pivots (>=50% wick, e.g. 14:30 TEH raid)
  const pivotSpan = 3;
  const activeSwingHighs: Array<{ time: number; price: number }> = [];
  const activeSwingLows: Array<{ time: number; price: number }> = [];
  const activeMinorHighs: Array<{ time: number; price: number }> = [];
  const activeMinorLows: Array<{ time: number; price: number }> = [];

  const consumeSweptHigh = (list: Array<{ time: number; price: number }>, bar: Candle) => {
    let best: { time: number; price: number } | null = null;
    for (let s = list.length - 1; s >= 0; s--) {
      const sh = list[s];
      if (bar.high > sh.price && bar.open <= sh.price && bar.close < sh.price) {
        if (!best || sh.price > best.price) best = sh;
        list.splice(s, 1);
      } else if (bar.high > sh.price) {
        list.splice(s, 1);
      }
    }
    return best;
  };

  const consumeSweptLow = (list: Array<{ time: number; price: number }>, bar: Candle) => {
    let best: { time: number; price: number } | null = null;
    for (let s = list.length - 1; s >= 0; s--) {
      const sl = list[s];
      if (bar.low < sl.price && bar.open >= sl.price && bar.close > sl.price) {
        if (!best || sl.price < best.price) best = sl;
        list.splice(s, 1);
      } else if (bar.low < sl.price) {
        list.splice(s, 1);
      }
    }
    return best;
  };

  for (let i = 2; i < visibleCandles.length; i++) {
    // Causal 1L/1R minor pivot confirmed at i-2 once bar i-1 closed
    const mIdx = i - 2;
    if (mIdx >= 1) {
      const mBar = visibleCandles[mIdx];
      if (mBar.high > visibleCandles[mIdx - 1].high && mBar.high >= visibleCandles[mIdx + 1].high) {
        activeMinorHighs.push({ time: mBar.time, price: mBar.high });
      }
      if (mBar.low < visibleCandles[mIdx - 1].low && mBar.low <= visibleCandles[mIdx + 1].low) {
        activeMinorLows.push({ time: mBar.time, price: mBar.low });
      }
    }

    // Causal 3L/3R major pivot confirmed pivotSpan bars ago
    if (i >= pivotSpan * 2) {
      const pIdx = i - pivotSpan;
      const pBar = visibleCandles[pIdx];
      let isPivotHigh = true;
      let isPivotLow = true;
      let strictHigh = false;
      let strictLow = false;
      for (let k = pIdx - pivotSpan; k <= pIdx + pivotSpan; k++) {
        if (k === pIdx) continue;
        if (visibleCandles[k].high > pBar.high) isPivotHigh = false;
        if (visibleCandles[k].high < pBar.high) strictHigh = true;
        if (visibleCandles[k].low < pBar.low) isPivotLow = false;
        if (visibleCandles[k].low > pBar.low) strictLow = true;
      }
      if (isPivotHigh && strictHigh) {
        activeSwingHighs.push({ time: pBar.time, price: pBar.high });
      }
      if (isPivotLow && strictLow) {
        activeSwingLows.push({ time: pBar.time, price: pBar.low });
      }
    }

    const c = visibleCandles[i];
    const barRange = c.high - c.low;
    if (barRange <= 0) continue;

    const upperWick = c.high - Math.max(c.open, c.close);
    const lowerWick = Math.min(c.open, c.close) - c.low;

    const sweptMajorHigh = consumeSweptHigh(activeSwingHighs, c);
    const sweptMinorHigh = consumeSweptHigh(activeMinorHighs, c);

    if (
      sweptMajorHigh &&
      upperWick >= 0.35 * barRange &&
      !emittedKeys.has(`HIGH:${c.time}`)
    ) {
      sweeps.push({
        time: c.time,
        price: c.high,
        type: 'HIGH_SWEEP',
        label: `BSL Sweep (${sweptMajorHigh.price})`,
        level: sweptMajorHigh.price,
        origin_time: sweptMajorHigh.time,
        session: 'Swing',
      });
      emittedKeys.add(`HIGH:${c.time}`);
    } else if (
      sweptMinorHigh &&
      upperWick >= 0.50 * barRange &&
      !emittedKeys.has(`HIGH:${c.time}`)
    ) {
      sweeps.push({
        time: c.time,
        price: c.high,
        type: 'HIGH_SWEEP',
        label: `Minor BSL Sweep (${sweptMinorHigh.price})`,
        level: sweptMinorHigh.price,
        origin_time: sweptMinorHigh.time,
        session: 'MinorSwing',
      });
      emittedKeys.add(`HIGH:${c.time}`);
    }

    const sweptMajorLow = consumeSweptLow(activeSwingLows, c);
    const sweptMinorLow = consumeSweptLow(activeMinorLows, c);

    if (
      sweptMajorLow &&
      lowerWick >= 0.35 * barRange &&
      !emittedKeys.has(`LOW:${c.time}`)
    ) {
      sweeps.push({
        time: c.time,
        price: c.low,
        type: 'LOW_SWEEP',
        label: `SSL Sweep (${sweptMajorLow.price})`,
        level: sweptMajorLow.price,
        origin_time: sweptMajorLow.time,
        session: 'Swing',
      });
      emittedKeys.add(`LOW:${c.time}`);
    } else if (
      sweptMinorLow &&
      lowerWick >= 0.50 * barRange &&
      !emittedKeys.has(`LOW:${c.time}`)
    ) {
      sweeps.push({
        time: c.time,
        price: c.low,
        type: 'LOW_SWEEP',
        label: `Minor SSL Sweep (${sweptMinorLow.price})`,
        level: sweptMinorLow.price,
        origin_time: sweptMinorLow.time,
        session: 'MinorSwing',
      });
      emittedKeys.add(`LOW:${c.time}`);
    }
  }

  return sweeps.sort((a, b) => a.time - b.time);
}

export function shiftIsoDateDays(dateStr: string, deltaDays: number): string {
  const parts = dateStr.split('-').map((p) => parseInt(p, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return dateStr;
  const dt = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + deltaDays));
  return dt.toISOString().slice(0, 10);
}

export function getLatestRangeForSymbol(
  symInfo: CatalogSymbol | undefined,
  windowDays: number = 3
): { start: string; end: string } | null {
  if (!symInfo?.max_date) return null;
  const end = symInfo.max_date;
  const shiftedStart = shiftIsoDateDays(end, -(Math.max(1, windowDays) - 1));
  const start =
    symInfo.min_date && shiftedStart < symInfo.min_date ? symInfo.min_date : shiftedStart;
  return { start, end };
}

export function resolveDateRangeForSymbol(
  symInfo: CatalogSymbol | undefined,
  currentStart: string,
  currentEnd: string,
  windowDays: number = 3
): { start: string; end: string; adjusted: boolean } {
  if (!symInfo?.max_date) {
    return { start: currentStart, end: currentEnd, adjusted: false };
  }
  const minDate = symInfo.min_date ?? symInfo.max_date;
  const maxDate = symInfo.max_date;
  const hasOverlap = !(currentEnd < minDate || currentStart > maxDate);
  if (hasOverlap) {
    return { start: currentStart, end: currentEnd, adjusted: false };
  }
  const latest = getLatestRangeForSymbol(symInfo, windowDays);
  return latest
    ? { start: latest.start, end: latest.end, adjusted: true }
    : { start: currentStart, end: currentEnd, adjusted: false };
}

export interface WorkbenchPrefs {
  showKillzones: boolean;
  showAsianRange: boolean;
  showBoxes: boolean;
  showSweeps: boolean;
  showTrades: boolean;
  clockMode: ClockMode;
  engineClockMode: EngineClockMode;
  timeframe: Timeframe;
  isDrawerOpen: boolean;
}

export const WORKBENCH_PREFS_KEY = 'tradingguard_replayer_prefs_v1';

export const DEFAULT_WORKBENCH_PREFS: WorkbenchPrefs = {
  showKillzones: true,
  showAsianRange: true,
  showBoxes: true,
  showSweeps: true,
  showTrades: true,
  clockMode: 'tehran',
  engineClockMode: 'true_tehran',
  timeframe: '5M',
  isDrawerOpen: true,
};

export function loadWorkbenchPrefs(): WorkbenchPrefs {
  try {
    const raw =
      typeof globalThis !== 'undefined' && 'localStorage' in globalThis
        ? globalThis.localStorage.getItem(WORKBENCH_PREFS_KEY)
        : null;
    if (!raw) return { ...DEFAULT_WORKBENCH_PREFS };
    const parsed = JSON.parse(raw) as Partial<WorkbenchPrefs>;
    return {
      showKillzones: typeof parsed.showKillzones === 'boolean' ? parsed.showKillzones : DEFAULT_WORKBENCH_PREFS.showKillzones,
      showAsianRange: typeof parsed.showAsianRange === 'boolean' ? parsed.showAsianRange : DEFAULT_WORKBENCH_PREFS.showAsianRange,
      showBoxes: typeof parsed.showBoxes === 'boolean' ? parsed.showBoxes : DEFAULT_WORKBENCH_PREFS.showBoxes,
      showSweeps: typeof parsed.showSweeps === 'boolean' ? parsed.showSweeps : DEFAULT_WORKBENCH_PREFS.showSweeps,
      showTrades: typeof parsed.showTrades === 'boolean' ? parsed.showTrades : DEFAULT_WORKBENCH_PREFS.showTrades,
      clockMode:
        parsed.clockMode === 'tehran' || parsed.clockMode === 'utc' || parsed.clockMode === 'server'
          ? parsed.clockMode
          : DEFAULT_WORKBENCH_PREFS.clockMode,
      engineClockMode:
        parsed.engineClockMode === 'true_tehran' || parsed.engineClockMode === 'live_legacy'
          ? parsed.engineClockMode
          : DEFAULT_WORKBENCH_PREFS.engineClockMode,
      timeframe:
        parsed.timeframe === '1M' ||
        parsed.timeframe === '5M' ||
        parsed.timeframe === '15M' ||
        parsed.timeframe === '1H' ||
        parsed.timeframe === '4H' ||
        parsed.timeframe === '1D'
          ? parsed.timeframe
          : DEFAULT_WORKBENCH_PREFS.timeframe,
      isDrawerOpen: typeof parsed.isDrawerOpen === 'boolean' ? parsed.isDrawerOpen : DEFAULT_WORKBENCH_PREFS.isDrawerOpen,
    };
  } catch {
    return { ...DEFAULT_WORKBENCH_PREFS };
  }
}

export function saveWorkbenchPrefs(prefs: WorkbenchPrefs): void {
  try {
    if (typeof globalThis !== 'undefined' && 'localStorage' in globalThis) {
      globalThis.localStorage.setItem(WORKBENCH_PREFS_KEY, JSON.stringify(prefs));
    }
  } catch {
    // Ignore storage quota / disabled storage errors
  }
}

export function dedupeFvgBoxes(boxes: FvgBox[]): FvgBox[] {
  const byKey = new Map<string, FvgBox>();
  for (const box of boxes) {
    const key = `${box.dir}:${box.top}:${box.bottom}:${box.t_start}`;
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, { ...box });
    } else if (box.t_end > existing.t_end) {
      existing.t_end = box.t_end;
    }
  }
  return Array.from(byKey.values());
}

export function dedupeBreakerBoxes(boxes: BreakerBox[]): BreakerBox[] {
  const byKey = new Map<string, BreakerBox>();
  for (const box of boxes) {
    const key = `${box.type}:${box.top}:${box.bottom}:${box.t_start}`;
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, { ...box });
    } else if (box.t_end > existing.t_end) {
      existing.t_end = box.t_end;
    }
  }
  return Array.from(byKey.values());
}

export interface ClusteredMarkerDescriptor {
  time: number;
  position: 'aboveBar' | 'belowBar';
  color: string;
  shape: 'arrowUp' | 'arrowDown' | 'circle';
  text: string;
  tradeIds: string[];
  isCluster: boolean;
}

export function getClusterWindowSeconds(candles: Candle[]): number {
  if (candles.length < 2) return 1800; // default 30m
  const deltas: number[] = [];
  const limit = Math.min(candles.length - 1, 20);
  for (let i = 0; i < limit; i++) {
    const d = candles[i + 1].time - candles[i].time;
    if (d > 0) deltas.push(d);
  }
  if (deltas.length === 0) return 1800;
  deltas.sort((a, b) => a - b);
  const barSec = deltas[Math.floor(deltas.length / 2)];
  return Math.max(barSec * 6, 1800);
}

export function findMatchingTradesNearTime(
  trades: ReplayTrade[],
  clickedTime: number,
  toleranceSeconds: number,
  replayTo: number | null
): ReplayTrade[] {
  const matches: Array<{ trade: ReplayTrade; dist: number }> = [];
  for (const t of trades) {
    if (replayTo !== null && t.decision_time > replayTo) continue;
    const masked = maskBlindReplayTrade(t, replayTo);
    const times: number[] = [masked.decision_time];
    if (masked.fill_time != null) times.push(masked.fill_time);
    if (masked.exit_time != null && masked.status !== 'OPEN' && masked.status !== 'PENDING') {
      times.push(masked.exit_time);
    }
    const minDist = Math.min(...times.map((x) => Math.abs(x - clickedTime)));
    if (minDist <= toleranceSeconds) {
      matches.push({ trade: masked, dist: minDist });
    }
  }
  matches.sort((a, b) => a.dist - b.dist || a.trade.decision_time - b.trade.decision_time);
  return matches.map((m) => m.trade);
}

export function buildClusteredTradeMarkers(
  trades: ReplayTrade[],
  replayTo: number | null,
  clusterWindowSeconds: number,
  selectedTradeId: string | null = null
): ClusteredMarkerDescriptor[] {
  const windowSec = Math.max(60, clusterWindowSeconds);
  const visible = trades
    .filter((t) => (replayTo !== null ? t.decision_time <= replayTo : true))
    .map((t) => ({
      raw: t,
      masked: maskBlindReplayTrade(t, replayTo),
    }))
    .filter(
      ({ raw }) => raw.fill_time != null && (replayTo === null || raw.fill_time <= replayTo)
    )
    .sort((a, b) => Number(a.raw.fill_time) - Number(b.raw.fill_time));

  const markers: ClusteredMarkerDescriptor[] = [];

  for (const dir of ['LONG', 'SHORT'] as const) {
    const dirTrades = visible.filter((item) => item.masked.direction === dir);
    let idx = 0;
    while (idx < dirTrades.length) {
      const anchorTime = Number(dirTrades[idx].raw.fill_time);
      const group = [dirTrades[idx]];
      let j = idx + 1;
      while (j < dirTrades.length && Number(dirTrades[j].raw.fill_time) - anchorTime <= windowSec) {
        group.push(dirTrades[j]);
        j++;
      }

      const tradeIds = group.map((g) => g.masked.trade_id);
      const hasSelected = selectedTradeId !== null && tradeIds.includes(selectedTradeId);

      let wins = 0;
      let losses = 0;
      let bes = 0;
      let opens = 0;
      for (const { masked } of group) {
        if (masked.status === 'WIN') wins++;
        else if (masked.status === 'LOSS') losses++;
        else if (masked.status === 'BREAKEVEN') bes++;
        else opens++;
      }

      const first = group[0].masked;
      const prefix = first.origin === 'BOT' ? '🤖' : '👤';
      const dirChar = dir === 'LONG' ? 'L' : 'S';

      let text: string;
      if (group.length === 1) {
        const statusTag =
          opens > 0
            ? 'Open'
            : wins > 0 && first.rr_realized != null
            ? `+${first.rr_realized.toFixed(1)}R`
            : losses > 0
            ? '-1R'
            : bes > 0
            ? 'BE'
            : '';
        text = `${hasSelected ? '★ ' : ''}${prefix} ${dirChar}${statusTag ? ` ${statusTag}` : ''}`;
      } else {
        const parts: string[] = [];
        if (wins > 0) parts.push(`${wins}W`);
        if (losses > 0) parts.push(`${losses}L`);
        if (bes > 0) parts.push(`${bes}BE`);
        if (opens > 0) parts.push(`${opens}O`);
        text = `${hasSelected ? '★ ' : ''}${prefix} ${group.length}×${dirChar} (${parts.join('/')})`;
      }

      const color = hasSelected
        ? '#f0b90b'
        : opens > 0 && wins === 0 && losses === 0 && bes === 0
        ? '#9c9c9c'
        : wins > losses
        ? '#089981'
        : losses > wins
        ? '#cf5c60'
        : '#d4a84f';

      markers.push({
        time: anchorTime,
        position: dir === 'LONG' ? 'belowBar' : 'aboveBar',
        color,
        shape: dir === 'LONG' ? 'arrowUp' : 'arrowDown',
        text,
        tradeIds,
        isCluster: group.length > 1,
      });

      // Only emit standalone exit marker if selected OR unclustered single trade
      if (group.length === 1 && opens === 0 && first.exit_time && (replayTo === null || first.exit_time <= replayTo)) {
        const isWin = first.status === 'WIN';
        const isLoss = first.status === 'LOSS';
        const pnlStr =
          first.realized_pnl_usd !== null && first.realized_pnl_usd !== undefined
            ? `${first.realized_pnl_usd >= 0 ? '+' : ''}$${first.realized_pnl_usd.toFixed(1)}`
            : first.status;
        markers.push({
          time: Number(first.exit_time),
          position: isWin ? 'aboveBar' : 'belowBar',
          color: hasSelected ? '#f0b90b' : isWin ? '#089981' : isLoss ? '#cf5c60' : '#d4a84f',
          shape: 'circle',
          text: pnlStr,
          tradeIds,
          isCluster: false,
        });
      } else if (hasSelected) {
        const sel = group.find((g) => g.masked.trade_id === selectedTradeId)?.masked;
        if (
          sel &&
          sel.status !== 'OPEN' &&
          sel.status !== 'PENDING' &&
          sel.exit_time &&
          (replayTo === null || sel.exit_time <= replayTo)
        ) {
          const pnlStr =
            sel.realized_pnl_usd !== null && sel.realized_pnl_usd !== undefined
              ? `${sel.realized_pnl_usd >= 0 ? '+' : ''}$${sel.realized_pnl_usd.toFixed(1)}`
              : sel.status;
          markers.push({
            time: Number(sel.exit_time),
            position: sel.status === 'WIN' ? 'aboveBar' : 'belowBar',
            color: '#f0b90b',
            shape: 'circle',
            text: `★ ${pnlStr}`,
            tradeIds: [sel.trade_id],
            isCluster: false,
          });
        }
      }

      idx = j;
    }
  }

  return markers.sort((a, b) => a.time - b.time);
}

export function findMatchingSmcElementsAtPoint(
  clickedTime: number,
  clickedPrice: number | null,
  overlays: {
    fvgs: FvgBox[];
    breakers: BreakerBox[];
    sweeps: SweepFlag[];
    asianRanges: AsianRangeDay[];
    showBoxes?: boolean;
    showSweeps?: boolean;
    showAsianRange?: boolean;
  },
  timeToleranceSec: number,
  priceTolerance: number,
  replayTo: number | null
): SelectedSmcElement[] {
  const hits: SelectedSmcElement[] = [];
  const tTol = Math.max(60, timeToleranceSec);
  const pTol = Math.max(0, priceTolerance);
  const priceHitsBand = (top: number, bottom: number, extra: number): boolean => {
    if (clickedPrice === null) return true;
    const hi = Math.max(top, bottom) + extra;
    const lo = Math.min(top, bottom) - extra;
    return clickedPrice >= lo && clickedPrice <= hi;
  };

  if (overlays.showBoxes !== false) {
    for (const brk of overlays.breakers) {
      if (replayTo !== null && brk.t_start > replayTo) continue;
      if (clickedTime >= brk.t_start - tTol && clickedTime <= brk.t_end + tTol) {
        if (priceHitsBand(brk.top, brk.bottom, pTol * 0.45)) {
          hits.push({
            id: `BRK:${brk.type}:${brk.t_start}:${brk.top}:${brk.bottom}`,
            kind: 'BREAKER',
            label: brk.type,
            time: brk.t_start,
            endTime: brk.t_end,
            top: brk.top,
            bottom: brk.bottom,
            direction: brk.type.toUpperCase().includes('BULLISH') ? 'BULLISH' : 'BEARISH',
            breaker: brk,
          });
        }
      }
    }

    for (const fvg of overlays.fvgs) {
      if (replayTo !== null && fvg.t_start > replayTo) continue;
      if (clickedTime >= fvg.t_start - tTol && clickedTime <= fvg.t_end + tTol) {
        if (priceHitsBand(fvg.top, fvg.bottom, pTol * 0.45)) {
          hits.push({
            id: `FVG:${fvg.dir}:${fvg.t_start}:${fvg.top}:${fvg.bottom}`,
            kind: 'FVG',
            label: `${fvg.dir} FVG`,
            time: fvg.t_start,
            endTime: fvg.t_end,
            top: fvg.top,
            bottom: fvg.bottom,
            direction: fvg.dir,
            fvg,
          });
        }
      }
    }
  }

  if (overlays.showSweeps !== false) {
    for (const sw of overlays.sweeps) {
      if (replayTo !== null && sw.time > replayTo) continue;
      const lineStart = Math.min(sw.origin_time ?? sw.time, sw.time);
      if (clickedTime >= lineStart - tTol && clickedTime <= sw.time + tTol) {
        const hitWick =
          clickedPrice === null ||
          (sw.level !== undefined && Math.abs(clickedPrice - sw.level) <= pTol * 0.85) ||
          (Math.abs(clickedTime - sw.time) <= tTol && Math.abs(clickedPrice - sw.price) <= pTol);
        if (hitWick) {
          hits.push({
            id: `SWEEP:${sw.type}:${sw.time}:${sw.price}`,
            kind: 'SWEEP',
            label: sw.label,
            time: sw.time,
            price: sw.price,
            top: sw.level ?? sw.price,
            direction: sw.type === 'HIGH_SWEEP' ? 'BEARISH_RAID' : 'BULLISH_RAID',
            sweep: sw,
          });
        }
      }
    }
  }

  if (overlays.showAsianRange !== false) {
    for (const ar of overlays.asianRanges) {
      if (replayTo !== null && ar.start_time > replayTo) continue;
      if (clickedTime >= ar.start_time - tTol && clickedTime <= ar.end_time + tTol) {
        const nearHigh = clickedPrice !== null && Math.abs(clickedPrice - ar.high) <= pTol * 0.85;
        const nearLow = clickedPrice !== null && Math.abs(clickedPrice - ar.low) <= pTol * 0.85;
        if (nearHigh || nearLow) {
          hits.push({
            id: `AR:${ar.date}:${ar.start_time}`,
            kind: 'ASIAN_RANGE',
            label: `Asian Range (${ar.date})`,
            time: ar.start_time,
            endTime: ar.end_time,
            top: ar.high,
            bottom: ar.low,
            asianRange: ar,
          });
        }
      }
    }
  }

  return hits;
}

export interface ChartClickContext {
  pricePerPx?: number | null;
  barSpacingPx?: number | null;
  onBarColumn?: boolean;
}

export type ChartClickTarget =
  | { kind: 'SMC'; hits: SelectedSmcElement[]; inspectTime: number }
  | { kind: 'TRADE'; hits: ReplayTrade[]; inspectTime: number }
  | { kind: 'CANDLE'; time: number }
  | { kind: 'EMPTY' };

function getBarIntervalSeconds(candles: Candle[]): number {
  if (candles.length < 2) return 300;
  const deltas: number[] = [];
  const limit = Math.min(candles.length - 1, 20);
  for (let i = 0; i < limit; i++) {
    const d = candles[i + 1].time - candles[i].time;
    if (d > 0) deltas.push(d);
  }
  if (deltas.length === 0) return 300;
  deltas.sort((a, b) => a - b);
  return deltas[Math.floor(deltas.length / 2)];
}

function findClosestVisibleCandle(candles: Candle[], targetTime: number, replayTo: number | null): Candle | null {
  let best: Candle | null = null;
  let bestDist = Infinity;
  for (const c of candles) {
    if (replayTo !== null && c.time > replayTo) continue;
    const d = Math.abs(c.time - targetTime);
    if (d < bestDist) {
      bestDist = d;
      best = c;
    }
  }
  return best;
}

/**
 * Resolves a pointer click at (clickedTime, clickedPrice) against drawn chart geometry only.
 * Empty background space returns { kind: 'EMPTY' } so it never snaps to the time-aligned candle.
 */
export function resolveChartClickTarget(params: {
  clickedTime: number | null;
  clickedPrice: number | null;
  candles: Candle[];
  overlays: {
    fvgs: FvgBox[];
    breakers: BreakerBox[];
    sweeps: SweepFlag[];
    asianRanges: AsianRangeDay[];
    showBoxes?: boolean;
    showSweeps?: boolean;
    showAsianRange?: boolean;
  };
  trades: ReplayTrade[];
  showTrades?: boolean;
  selectedTradeId?: string | null;
  clusterWindowSec: number;
  replayTo: number | null;
  digits: number;
  context?: ChartClickContext;
}): ChartClickTarget {
  const {
    clickedTime,
    clickedPrice,
    candles,
    overlays,
    trades,
    showTrades = true,
    selectedTradeId = null,
    clusterWindowSec,
    replayTo,
    digits,
    context,
  } = params;

  if (clickedTime === null || clickedPrice === null || !Number.isFinite(clickedPrice)) {
    return { kind: 'EMPTY' };
  }

  const barSec = getBarIntervalSeconds(candles);
  const halfBarSec = Math.max(30, Math.round(barSec * 0.55));
  const minPriceStep = digits >= 4 ? 0.0001 : 0.1;

  // Fallback price-per-pixel estimate when invoked without live canvas metrics
  let pxY = context?.pricePerPx ?? null;
  if (pxY === null || !Number.isFinite(pxY) || pxY <= 0) {
    let minLow = Infinity;
    let maxHigh = -Infinity;
    for (const c of candles) {
      if (replayTo !== null && c.time > replayTo) continue;
      if (c.low < minLow) minLow = c.low;
      if (c.high > maxHigh) maxHigh = c.high;
    }
    const span = Number.isFinite(maxHigh - minLow) && maxHigh > minLow ? maxHigh - minLow : 10;
    pxY = Math.max(span / 500, minPriceStep * 0.25);
  }

  const linePriceTol = Math.max(9 * pxY, minPriceStep);
  const candlePricePad = Math.max(6 * pxY, minPriceStep * 0.5);
  const markerReachY = Math.max(46 * pxY, linePriceTol * 2);

  const pxPerSec =
    context?.barSpacingPx && context.barSpacingPx > 0 ? context.barSpacingPx / barSec : 8 / barSec;
  const secPerPx = 1 / Math.max(pxPerSec, 1e-6);
  const smcTimePadSec = Math.max(halfBarSec, Math.round(6 * secPerPx));
  const markerTimeTolSec = Math.max(barSec * 1.5, Math.round(36 * secPerPx));

  const targetCandle = findClosestVisibleCandle(candles, clickedTime, replayTo);
  const candleAligned =
    targetCandle !== null &&
    Math.abs(targetCandle.time - clickedTime) <= halfBarSec &&
    context?.onBarColumn !== false;

  // 1. Direct hit on rendered SMC elements (Breaker, FVG, Sweep line, Asian High/Low line)
  const smcHits = findMatchingSmcElementsAtPoint(
    clickedTime,
    clickedPrice,
    overlays,
    smcTimePadSec,
    linePriceTol,
    replayTo
  );
  if (smcHits.length > 0) {
    return {
      kind: 'SMC',
      hits: smcHits,
      inspectTime: candleAligned && targetCandle ? targetCandle.time : smcHits[0].time,
    };
  }

  // 2. Direct hit on rendered Trade Markers (clustered aboveBar / belowBar pills)
  if (showTrades && trades.length > 0 && context?.onBarColumn !== false) {
    const markers = buildClusteredTradeMarkers(trades, replayTo, clusterWindowSec, selectedTradeId);
    const tradeById = new Map<string, ReplayTrade>();
    for (const t of trades) {
      if (replayTo !== null && t.decision_time > replayTo) continue;
      tradeById.set(t.trade_id, maskBlindReplayTrade(t, replayTo));
    }

    const markerEdgePad = Math.max(2 * pxY, minPriceStep * 0.25);
    let bestMarker: { marker: ClusteredMarkerDescriptor; distSec: number } | null = null;
    for (const m of markers) {
      const distSec = Math.abs(clickedTime - m.time);
      if (distSec > markerTimeTolSec) continue;

      const anchorBar = findClosestVisibleCandle(candles, m.time, replayTo);
      if (!anchorBar) continue;

      const inVerticalBand =
        m.position === 'aboveBar'
          ? clickedPrice >= anchorBar.high - markerEdgePad && clickedPrice <= anchorBar.high + markerReachY
          : clickedPrice <= anchorBar.low + markerEdgePad && clickedPrice >= anchorBar.low - markerReachY;

      if (inVerticalBand && (!bestMarker || distSec < bestMarker.distSec)) {
        bestMarker = { marker: m, distSec };
      }
    }

    if (bestMarker) {
      const hitTrades = bestMarker.marker.tradeIds
        .map((id) => tradeById.get(id))
        .filter((t): t is ReplayTrade => t !== undefined);
      if (hitTrades.length > 0) {
        return {
          kind: 'TRADE',
          hits: hitTrades,
          inspectTime: bestMarker.marker.time,
        };
      }
    }
  }

  // 3. Direct hit on Candlestick body / wick ([low, high] +/- small click pad)
  if (
    candleAligned &&
    targetCandle &&
    clickedPrice >= targetCandle.low - candlePricePad &&
    clickedPrice <= targetCandle.high + candlePricePad
  ) {
    return {
      kind: 'CANDLE',
      time: targetCandle.time,
    };
  }

  // 4. Empty space: do not snap to any candle
  return { kind: 'EMPTY' };
}

export function getQuickQuestionsForSmcElement(kind: SmcElementKind | 'TRADE' | 'BAR'): string[] {
  if (kind === 'BREAKER') {
    return [
      "Why didn't the bot take a setup at this Breaker?",
      'Is this Breaker block valid per ICT MSS rules?',
      'Zone calibration issue: false or mistimed Breaker',
    ];
  }
  if (kind === 'FVG') {
    return [
      "Why didn't the bot enter on this FVG retracement?",
      'Is this FVG fresh/valid or already mitigated?',
      'Zone calibration issue: noise / false FVG',
    ];
  }
  if (kind === 'SWEEP') {
    return [
      'Why did no MSS entry trigger after this Sweep?',
      'Is this Sweep genuine liquidity or noise?',
      'Analyze direction & SL placement relative to this Sweep',
    ];
  }
  if (kind === 'ASIAN_RANGE') {
    return [
      'Audit Asian Range breakout vs Judas sweep logic here',
      'Check Tehran / session clock alignment for this Asian session',
      'Why was this session extreme filtered or skipped?',
    ];
  }
  if (kind === 'TRADE') {
    return [
      'Review this trade entry, SL, and TP placement',
      'Why did the bot fire here instead of waiting for confirmation?',
      'How can we improve target/BE management on this setup?',
    ];
  }
  return [
    'Why did the bot veto / skip this candle?',
    'Evaluate missed setup opportunity at this bar',
    'Explain current market structure & active session state',
  ];
}

export function buildSmcElementContextMarkdown(params: {
  symbol: string;
  timeframe: Timeframe;
  clockMode: ClockMode;
  digits: number;
  element: SelectedSmcElement;
  candles: Candle[];
  diagnostic?: BotDiagnostic | null;
  question: string;
}): string {
  const { symbol, timeframe, clockMode, digits, element, candles, diagnostic, question } = params;
  const zones = convertServerEpochToZones(element.time);

  const lines: string[] = [
    `### Agentify Chart Inquiry — ${symbol} (${timeframe})`,
    `- **Question:** ${question}`,
    `- **Selected Element:** \`${element.kind}\` — ${element.label}`,
    `- **Timestamp:** \`${zones.tehran_str} Tehran\` | \`${zones.srv_str} MT5 Server\` (\`epoch=${element.time}\`)`,
  ];

  if (element.top !== undefined && element.bottom !== undefined) {
    lines.push(
      `- **Zone Bounds:** \`${element.bottom.toFixed(digits)} – ${element.top.toFixed(digits)}\`${element.endTime ? ` (to \`${formatClockTick(element.endTime, clockMode, true)}\`)` : ''}`
    );
  } else if (element.price !== undefined) {
    lines.push(
      `- **Price Level:** \`${element.price.toFixed(digits)}\`${element.top !== undefined ? ` (Swept Level: \`${element.top.toFixed(digits)}\`)` : ''}`
    );
  }

  if (diagnostic) {
    lines.push(
      `- **Screener State @ Bar:** Verdict=\`${diagnostic.has_setup ? 'SETUP' : 'NO_SETUP'}\` | Archetype=\`${diagnostic.archetype_id ?? 'NONE'}\` | Phase=\`${diagnostic.phase}\` | SessionHour=\`${diagnostic.session_hour}\``
    );
    lines.push(`- **Screener Reason / Veto:** ${diagnostic.reason || 'None'}`);
    if (diagnostic.asian_high !== undefined && diagnostic.asian_low !== undefined) {
      lines.push(
        `- **Asian Bounds @ Bar:** High \`${diagnostic.asian_high.toFixed(digits)}\` / Low \`${diagnostic.asian_low.toFixed(digits)}\``
      );
    }
  }

  // Extract 5 surrounding OHLC bars around element.time
  if (candles.length > 0) {
    let closestIdx = 0;
    let bestDiff = Infinity;
    for (let i = 0; i < candles.length; i++) {
      const diff = Math.abs(candles[i].time - element.time);
      if (diff < bestDiff) {
        bestDiff = diff;
        closestIdx = i;
      }
    }
    const startIdx = Math.max(0, closestIdx - 2);
    const endIdx = Math.min(candles.length - 1, closestIdx + 2);
    lines.push('', '**Surrounding Candles:**');
    for (let i = startIdx; i <= endIdx; i++) {
      const b = candles[i];
      const mark = i === closestIdx ? ' ◀' : '';
      lines.push(
        `- \`${formatClockTick(b.time, clockMode, true)}\`: O=${b.open.toFixed(digits)} H=${b.high.toFixed(digits)} L=${b.low.toFixed(digits)} C=${b.close.toFixed(digits)}${mark}`
      );
    }
  }

  return lines.join('\n');
}
