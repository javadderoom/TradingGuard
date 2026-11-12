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
  BreakerBox,
  Candle,
  CatalogSymbol,
  ClockMode,
  EngineClockMode,
  FvgBox,
  ReplayTrade,
  Scorecard,
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

  // Track 2: Causal 3-left / 3-right Swing High & Swing Low liquidity grabs
  const pivotSpan = 3;
  const activeSwingHighs: Array<{ time: number; price: number }> = [];
  const activeSwingLows: Array<{ time: number; price: number }> = [];

  for (let i = pivotSpan * 2; i < visibleCandles.length; i++) {
    // Confirm pivot formed pivotSpan bars ago (zero future lookahead)
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

    const c = visibleCandles[i];
    const barRange = c.high - c.low;
    if (barRange <= 0) continue;

    const upperWick = c.high - Math.max(c.open, c.close);
    const lowerWick = Math.min(c.open, c.close) - c.low;

    // Check swept Swing Highs (comes from below/equal, pierces high, closes below with >=35% wick)
    let sweptHighPivot: { time: number; price: number } | null = null;
    for (let s = activeSwingHighs.length - 1; s >= 0; s--) {
      const sh = activeSwingHighs[s];
      if (c.high > sh.price && c.open <= sh.price && c.close < sh.price) {
        if (!sweptHighPivot || sh.price > sweptHighPivot.price) {
          sweptHighPivot = sh;
        }
        activeSwingHighs.splice(s, 1);
      } else if (c.high > sh.price) {
        // Broken through without immediate rejection: consume resting liquidity
        activeSwingHighs.splice(s, 1);
      }
    }
    if (
      sweptHighPivot &&
      upperWick >= 0.35 * barRange &&
      !emittedKeys.has(`HIGH:${c.time}`)
    ) {
      sweeps.push({
        time: c.time,
        price: c.high,
        type: 'HIGH_SWEEP',
        label: `BSL Sweep (${sweptHighPivot.price})`,
        level: sweptHighPivot.price,
        origin_time: sweptHighPivot.time,
        session: 'Swing',
      });
      emittedKeys.add(`HIGH:${c.time}`);
    }

    // Check swept Swing Lows (comes from above/equal, pierces low, closes above with >=35% wick)
    let sweptLowPivot: { time: number; price: number } | null = null;
    for (let s = activeSwingLows.length - 1; s >= 0; s--) {
      const sl = activeSwingLows[s];
      if (c.low < sl.price && c.open >= sl.price && c.close > sl.price) {
        if (!sweptLowPivot || sl.price < sweptLowPivot.price) {
          sweptLowPivot = sl;
        }
        activeSwingLows.splice(s, 1);
      } else if (c.low < sl.price) {
        // Broken through without immediate rejection: consume resting liquidity
        activeSwingLows.splice(s, 1);
      }
    }
    if (
      sweptLowPivot &&
      lowerWick >= 0.35 * barRange &&
      !emittedKeys.has(`LOW:${c.time}`)
    ) {
      sweeps.push({
        time: c.time,
        price: c.low,
        type: 'LOW_SWEEP',
        label: `SSL Sweep (${sweptLowPivot.price})`,
        level: sweptLowPivot.price,
        origin_time: sweptLowPivot.time,
        session: 'Swing',
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
        ? '#2962ff'
        : wins > losses
        ? '#26a69a'
        : losses > wins
        ? '#ef5350'
        : '#ffb300';

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
          color: hasSelected ? '#f0b90b' : isWin ? '#26a69a' : isLoss ? '#ef5350' : '#ffb300',
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
