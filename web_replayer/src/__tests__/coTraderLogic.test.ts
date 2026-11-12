import { describe, it, expect, vi, afterEach } from 'vitest';
import { replayApi } from '../api/client';
import {
  formatClockTick,
  convertServerEpochToZones,
  computeTradeRR,
  getSymbolPipValue,
  calculateTradeRiskUSD,
  checkRiskLimitUSD,
  maskBlindReplayTrade,
  computeReplayScorecard,
  extractLiquiditySweeps,
} from '../utils/coTraderLogic';
import type { Candle, ReplayTrade, AsianRangeDay } from '../types/replay';

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

  it('evaluates max drawdown strictly by cash exit_time sequence rather than entry order', () => {
    // Trade A: entered at 1000, but held until 5000, WIN +$100
    const tradeA: ReplayTrade = {
      trade_id: 'TR-A',
      symbol: 'XAUUSD_o',
      origin: 'BOT',
      direction: 'LONG',
      decision_time: 1000,
      fill_time: 1050,
      exit_time: 5000,
      entry: 2680.0,
      sl: 2670.0,
      tp: 2710.0,
      status: 'WIN',
      realized_pnl_usd: 100.0,
      rr_realized: 3.0,
    };

    // Trade B: entered later at 2000, exited earlier at 2500, LOSS -$40
    const tradeB: ReplayTrade = {
      trade_id: 'TR-B',
      symbol: 'XAUUSD_o',
      origin: 'HUMAN_PROPOSED',
      direction: 'SHORT',
      decision_time: 2000,
      fill_time: 2020,
      exit_time: 2500,
      entry: 2685.0,
      sl: 2695.0,
      tp: 2665.0,
      status: 'LOSS',
      realized_pnl_usd: -40.0,
      rr_realized: -1.0,
    };

    // If sorted by exit_time:
    // 1. Trade B exits at 2500: PnL -40. Peak = 0. Drawdown = 40.
    // 2. Trade A exits at 5000: PnL +100. Net running = +60. Peak = 60. Drawdown = 0.
    // Max Drawdown must be 40.00!
    // If sorted incorrectly by decision_time: Trade A (+100) first -> running = 100, peak = 100.
    // Then Trade B (-40) -> running = 60, DD = 40.
    // Now consider when Trade C entered at 3000, exited at 3500 with -$25 loss:
    const tradeC: ReplayTrade = {
      trade_id: 'TR-C',
      symbol: 'XAUUSD_o',
      origin: 'BOT',
      direction: 'LONG',
      decision_time: 3000,
      fill_time: 3050,
      exit_time: 3500,
      entry: 2680.0,
      sl: 2670.0,
      tp: 2700.0,
      status: 'LOSS',
      realized_pnl_usd: -25.0,
      rr_realized: -1.0,
    };

    // Exit sequence:
    // t=2500: B exits (-$40) -> running = -40, peak = 0, DD = $40
    // t=3500: C exits (-$25) -> running = -65, peak = 0, DD = $65
    // t=5000: A exits (+$100) -> running = +35, peak = 35, DD = 0
    // True Max Drawdown in cash realization is $65.00!
    // (If sorted by decision_time: A(+100)->100, then B(-40)->60 (DD 40), then C(-25)->35 (DD 65))
    const scorecard = computeReplayScorecard([tradeA, tradeB, tradeC], null);
    expect(scorecard.max_drawdown_usd).toBe(65.0);
    expect(scorecard.net_pnl_usd).toBe(35.0);
    expect(scorecard.total_trades).toBe(3);
    expect(scorecard.wins).toBe(1);
    expect(scorecard.losses).toBe(2);
  });
});

describe('coTraderLogic - Causal Liquidity Sweep Extraction', () => {
  const asianRanges: Record<string, AsianRangeDay> = {
    '2026-01-15': {
      date: '2026-01-15',
      high: 2680.0,
      low: 2660.0,
      start_time: 1768442400, // 02:00
      end_time: 1768467600,   // 09:00
      bars_count: 84,
    },
  };

  const candles: Candle[] = [
    // Bar 1: inside Asian session
    { time: 1768450000, open: 2665.0, high: 2675.0, low: 2662.0, close: 2670.0 },
    // Bar 2: Post-Asian London candle sweeps Asian High (high 2683 > 2680, close 2678 < 2680)
    { time: 1768470000, open: 2675.0, high: 2683.0, low: 2674.0, close: 2678.0 },
    // Bar 3: Normal candle
    { time: 1768470300, open: 2678.0, high: 2679.0, low: 2671.0, close: 2673.0 },
    // Bar 4: Candle sweeps Asian Low (low 2657 < 2660, close 2663 > 2660)
    { time: 1768470600, open: 2672.0, high: 2673.0, low: 2657.0, close: 2663.0 },
    // Bar 5: Later candle outside active replay window
    { time: 1768475000, open: 2663.0, high: 2685.0, low: 2662.0, close: 2675.0 },
  ];

  it('detects Asian High and Low liquidity sweeps cleanly', () => {
    const sweeps = extractLiquiditySweeps(candles, asianRanges, null);
    expect(sweeps.length).toBe(3); // bar 2 (high), bar 4 (low), bar 5 (high)

    const highSweep = sweeps.find((s) => s.time === 1768470000);
    expect(highSweep).toBeDefined();
    expect(highSweep?.type).toBe('HIGH_SWEEP');
    expect(highSweep?.level).toBe(2680.0);
    expect(highSweep?.price).toBe(2683.0);

    const lowSweep = sweeps.find((s) => s.time === 1768470600);
    expect(lowSweep).toBeDefined();
    expect(lowSweep?.type).toBe('LOW_SWEEP');
    expect(lowSweep?.level).toBe(2660.0);
    expect(lowSweep?.price).toBe(2657.0);
  });

  it('strictly respects replayTo anti-spoiler cursor', () => {
    // When replayTo is 1768471000 (after bar 4, before bar 5)
    const sweepsReplay = extractLiquiditySweeps(candles, asianRanges, 1768471000);
    expect(sweepsReplay.length).toBe(2);
    expect(sweepsReplay.some((s) => s.time === 1768475000)).toBe(false);
  });
});

describe('replayApi - Payload Normalization', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('unwraps /api/candles object responses { bars, truncated, forming_bar } into Candle[]', async () => {
    const mockBars: Candle[] = [
      { time: 1794272400, open: 4136.36, high: 4138.35, low: 4133.82, close: 4135.46 },
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ bars: mockBars, truncated: false, forming_bar: false }),
      }),
    );

    const result = await replayApi.getCandles({
      symbol: 'XAUUSD_o',
      tf: '5M',
      start: 1794268800,
      end: 1794527999,
    });

    expect(Array.isArray(result)).toBe(true);
    expect(result).toEqual(mockBars);
  });
});
