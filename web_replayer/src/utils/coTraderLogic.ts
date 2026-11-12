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
  Candle,
  ClockMode,
  ReplayTrade,
  Scorecard,
  SweepFlag,
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
 * Identifies bars that pierce Asian High/Low levels and wick back.
 */
export function extractLiquiditySweeps(
  candles: Candle[],
  asianRanges: Record<string, AsianRangeDay> | AsianRangeDay[],
  replayTo: number | null
): SweepFlag[] {
  const arList: AsianRangeDay[] = Array.isArray(asianRanges)
    ? asianRanges
    : Object.values(asianRanges);

  if (arList.length === 0 || candles.length === 0) return [];

  const visibleCandles =
    replayTo !== null ? candles.filter((c) => c.time <= replayTo) : candles;

  const sweeps: SweepFlag[] = [];

  for (const ar of arList) {
    // Check bars occurring after Asian session end
    const sessionCandles = visibleCandles.filter(
      (c) => c.time > ar.end_time && c.time < ar.end_time + 86400
    );

    for (const c of sessionCandles) {
      // High Sweep: candle high > asian high, and closes back below or wicks
      if (c.high > ar.high && c.close <= ar.high) {
        sweeps.push({
          time: c.time,
          price: c.high,
          type: 'HIGH_SWEEP',
          label: `Asian High Sweep (${ar.high})`,
          level: ar.high,
          session: 'London/NY',
        });
      }

      // Low Sweep: candle low < asian low, and closes back above or wicks
      if (c.low < ar.low && c.close >= ar.low) {
        sweeps.push({
          time: c.time,
          price: c.low,
          type: 'LOW_SWEEP',
          label: `Asian Low Sweep (${ar.low})`,
          level: ar.low,
          session: 'London/NY',
        });
      }
    }
  }

  // Sort chronologically
  return sweeps.sort((a, b) => a.time - b.time);
}
