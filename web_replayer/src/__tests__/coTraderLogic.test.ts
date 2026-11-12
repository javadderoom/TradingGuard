import { describe, it, expect } from 'vitest';
import {
  formatClockTick,
  convertServerEpochToZones,
  computeTradeRR,
  getSymbolPipValue,
  calculateTradeRiskUSD,
  checkRiskLimitUSD,
  maskBlindReplayTrade,
  computeReplayScorecard,
} from '../utils/coTraderLogic';
import type { ReplayTrade } from '../types/replay';

describe('coTraderLogic - Dynamic Seasonal Session Clock', () => {
  // Winter: Jan 15, 2026, 14:00:00 server time
  // Date.UTC(2026, 0, 15, 14, 0, 0) / 1000 = 1768485600
  const winterServerEpoch = 1768485600;

  // Summer: Jun 15, 2026, 15:00:00 server time
  // Date.UTC(2026, 5, 15, 15, 0, 0) / 1000 = 1781535600
  const summerServerEpoch = 1781535600;

  it('converts winter Athens epoch (UTC+2) faithfully to UTC and Tehran (UTC+3:30)', () => {
    const zones = convertServerEpochToZones(winterServerEpoch);
    expect(zones.srv_str).toBe('14:00');
    expect(zones.utc_str).toBe('12:00');
    expect(zones.tehran_str).toBe('15:30');
    expect(zones.offset_sec).toBe(7200);
    expect(zones.date_str).toBe('2026-01-15');
  });

  it('converts summer Athens epoch (UTC+3) faithfully to UTC and Tehran (UTC+3:30)', () => {
    const zones = convertServerEpochToZones(summerServerEpoch);
    expect(zones.srv_str).toBe('15:00');
    expect(zones.utc_str).toBe('12:00');
    expect(zones.tehran_str).toBe('15:30');
    expect(zones.offset_sec).toBe(10800);
    expect(zones.date_str).toBe('2026-06-15');
  });

  it('formatClockTick formats strings across tehran, utc, and server modes', () => {
    // Winter
    expect(formatClockTick(winterServerEpoch, 'server')).toBe('14:00');
    expect(formatClockTick(winterServerEpoch, 'utc')).toBe('12:00');
    expect(formatClockTick(winterServerEpoch, 'tehran')).toBe('15:30');

    // Summer
    expect(formatClockTick(summerServerEpoch, 'server')).toBe('15:00');
    expect(formatClockTick(summerServerEpoch, 'utc')).toBe('12:00');
    expect(formatClockTick(summerServerEpoch, 'tehran')).toBe('15:30');
  });
});

describe('coTraderLogic - Risk:Reward & Risk Limit Calculations', () => {
  it('computes Long and Short Trade R:R without clipping', () => {
    // Long trade: Entry 2680.0, SL 2670.0 (risk 10), TP 2710.0 (reward 30) -> RR 3.0
    expect(computeTradeRR(2680.0, 2670.0, 2710.0, 'LONG')).toBe(3.0);

    // Short trade: Entry 2680.0, SL 2690.0 (risk 10), TP 2650.0 (reward 30) -> RR 3.0
    expect(computeTradeRR(2680.0, 2690.0, 2650.0, 'SHORT')).toBe(3.0);

    // Uncapped swing trade (e.g. 5.5R)
    expect(computeTradeRR(20000.0, 19900.0, 20550.0, 'LONG')).toBe(5.5);

    // Inferred direction when dir omitted
    expect(computeTradeRR(2680.0, 2670.0, 2710.0)).toBe(3.0);
    expect(computeTradeRR(2680.0, 2690.0, 2650.0)).toBe(3.0);

    // Zero risk edge case
    expect(computeTradeRR(2680.0, 2680.0, 2710.0)).toBe(0.0);
  });

  it('maps symbol pip_val matching evaluator.py:306-323', () => {
    expect(getSymbolPipValue('XAUUSD_o')).toBe(1.0);
    expect(getSymbolPipValue('XAGUSD_o')).toBe(50.0);
    expect(getSymbolPipValue('GBPUSD_o')).toBe(1000.0);
    expect(getSymbolPipValue('EURUSD_o')).toBe(1000.0);
    expect(getSymbolPipValue('NQ')).toBe(0.10);
    expect(getSymbolPipValue('SPX')).toBe(0.10);
    expect(getSymbolPipValue('YM')).toBe(0.10);
    expect(getSymbolPipValue('BTCUSD')).toBe(0.01);
  });

  it('calculates trade risk in USD directly and scales with lot size', () => {
    expect(calculateTradeRiskUSD('XAUUSD_o', 2680.0, 2670.0, 0.01)).toBe(10.0);
    expect(calculateTradeRiskUSD('XAUUSD_o', 2680.0, 2670.0, 0.02)).toBe(20.0);
  });

  it('evaluates $20 risk compliance limits correctly per instrument', () => {
    // Gold: 25 points risk at 0.01 lot = $25.00 -> EXCEEDS
    const goldExceed = checkRiskLimitUSD('XAUUSD_o', 2680.0, 2655.0, 0.01, 20.0);
    expect(goldExceed.riskUsd).toBe(25.0);
    expect(goldExceed.exceedsRiskCap).toBe(true);

    // Gold: 15 points risk at 0.01 lot = $15.00 -> PASS
    const goldPass = checkRiskLimitUSD('XAUUSD_o', 2680.0, 2665.0, 0.01, 20.0);
    expect(goldPass.riskUsd).toBe(15.0);
    expect(goldPass.exceedsRiskCap).toBe(false);

    // Cable (GBPUSD): 20 pips (0.00200) = $2.00 -> PASS
    const gbpPass = checkRiskLimitUSD('GBPUSD_o', 1.30000, 1.29800, 0.01, 20.0);
    expect(gbpPass.riskUsd).toBe(2.0);
    expect(gbpPass.exceedsRiskCap).toBe(false);

    // NQ: 250 points = $25.00 -> EXCEEDS
    const nqExceed = checkRiskLimitUSD('NQ', 20000.0, 19750.0, 0.01, 20.0);
    expect(nqExceed.riskUsd).toBe(25.0);
    expect(nqExceed.exceedsRiskCap).toBe(true);

    // BTCUSD: 4000 points = $40.00 -> EXCEEDS
    const btcExceed = checkRiskLimitUSD('BTCUSD', 90000.0, 86000.0, 0.01, 20.0);
    expect(btcExceed.riskUsd).toBe(40.0);
    expect(btcExceed.exceedsRiskCap).toBe(true);
  });
});

describe('coTraderLogic - Anti-Spoiler Blind Replay Filter', () => {
  const sampleTrade: ReplayTrade = {
    trade_id: 'BOT-XAUUSD_o-001',
    symbol: 'XAUUSD_o',
    origin: 'BOT',
    direction: 'LONG',
    decision_time: 1000,
    fill_time: 1050,
    exit_time: 1500,
    entry: 2680.0,
    sl: 2670.0,
    tp: 2710.0,
    status: 'WIN',
    realized_pnl_usd: 30.0,
    rr_realized: 3.0,
    risk_usd_001: 10.0,
    exceeds_risk_cap: false,
    notes: 'TP hit at 1500',
  };

  it('leaves trade unmasked when replayTo is null or >= exit_time', () => {
    const unmaskedNull = maskBlindReplayTrade(sampleTrade, null);
    expect(unmaskedNull.status).toBe('WIN');
    expect(unmaskedNull.exit_time).toBe(1500);
    expect(unmaskedNull.realized_pnl_usd).toBe(30.0);
    expect(unmaskedNull.rr_realized).toBe(3.0);

    const unmaskedAfter = maskBlindReplayTrade(sampleTrade, 1600);
    expect(unmaskedAfter.status).toBe('WIN');
    expect(unmaskedAfter.exit_time).toBe(1500);
    expect(unmaskedAfter.realized_pnl_usd).toBe(30.0);
  });

  it('masks outcome, PnL, RR, and exit_time when replayTo < exit_time', () => {
    // When replayTo is 1200 (between fill_time 1050 and exit_time 1500)
    const maskedActive = maskBlindReplayTrade(sampleTrade, 1200);
    expect(maskedActive.status).toBe('OPEN');
    expect(maskedActive.exit_time).toBeNull();
    expect(maskedActive.realized_pnl_usd).toBeNull();
    expect(maskedActive.rr_realized).toBeNull();

    // When replayTo is 1020 (before fill_time 1050)
    const maskedPending = maskBlindReplayTrade(sampleTrade, 1020);
    expect(maskedPending.status).toBe('PENDING');
    expect(maskedPending.fill_time).toBeNull();
    expect(maskedPending.exit_time).toBeNull();
  });

  it('computes replay scorecard filtering out uncompleted future trades', () => {
    const trade2: ReplayTrade = {
      trade_id: 'HUMAN-XAUUSD_o-002',
      symbol: 'XAUUSD_o',
      origin: 'HUMAN_PROPOSED',
      direction: 'SHORT',
      decision_time: 800,
      fill_time: 820,
      exit_time: 900,
      entry: 2685.0,
      sl: 2690.0,
      tp: 2670.0,
      status: 'WIN',
      realized_pnl_usd: 15.0,
      rr_realized: 3.0,
      risk_usd_001: 5.0,
      exceeds_risk_cap: false,
    };

    const trades = [sampleTrade, trade2];

    // At replayTo = 950: trade2 is WIN, sampleTrade has not completed (exit 1500)
    const cardAt950 = computeReplayScorecard(trades, 950);
    expect(cardAt950.total_trades).toBe(1);
    expect(cardAt950.wins).toBe(1);
    expect(cardAt950.losses).toBe(0);
    expect(cardAt950.net_pnl_usd).toBe(15.0);
    expect(cardAt950.net_rr).toBe(3.0);

    // At replayTo = 2000: both completed
    const cardAt2000 = computeReplayScorecard(trades, 2000);
    expect(cardAt2000.total_trades).toBe(2);
    expect(cardAt2000.wins).toBe(2);
    expect(cardAt2000.net_pnl_usd).toBe(45.0);
  });
});
