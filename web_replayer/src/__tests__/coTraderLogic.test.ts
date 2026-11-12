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
  getLatestRangeForSymbol,
  resolveDateRangeForSymbol,
  DEFAULT_WORKBENCH_PREFS,
  loadWorkbenchPrefs,
  saveWorkbenchPrefs,
  dedupeFvgBoxes,
  dedupeBreakerBoxes,
  buildClusteredTradeMarkers,
  findMatchingTradesNearTime,
  getClusterWindowSeconds,
  findMatchingSmcElementsAtPoint,
  getQuickQuestionsForSmcElement,
  buildSmcElementContextMarkdown,
} from '../utils/coTraderLogic';
import type { BreakerBox, Candle, CatalogSymbol, FvgBox, ReplayTrade, AsianRangeDay } from '../types/replay';

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
    // Bar 2: First unbroken raid above Asian High (open 2675 <= 2680, high 2683 > 2680, close 2678 < 2680)
    { time: 1768470000, open: 2675.0, high: 2683.0, low: 2674.0, close: 2678.0 },
    // Bar 3: Normal candle
    { time: 1768470300, open: 2678.0, high: 2679.0, low: 2671.0, close: 2673.0 },
    // Bar 4: First unbroken raid below Asian Low (open 2672 >= 2660, low 2657 < 2660, close 2663 > 2660)
    { time: 1768470600, open: 2672.0, high: 2673.0, low: 2657.0, close: 2663.0 },
    // Bar 5: Duplicate push over already-swept Asian High (must NOT re-fire bogus sweep)
    { time: 1768475000, open: 2663.0, high: 2685.0, low: 2662.0, close: 2675.0 },
  ];

  it('detects authentic unbroken Asian High and Low liquidity sweeps without repeating', () => {
    const sweeps = extractLiquiditySweeps(candles, asianRanges, null);
    expect(sweeps.length).toBe(2); // bar 2 (BSL), bar 4 (SSL); bar 5 ignored

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

  it('ignores choppy bounces below already-broken Asian Low (Nov 12 false sweep bug)', () => {
    const nov12Range: Record<string, AsianRangeDay> = {
      '2026-11-12': {
        date: '2026-11-12',
        high: 4000.34,
        low: 3962.51,
        start_time: 1794448800,
        end_time: 1794473700,
        bars_count: 84,
      },
    };
    const brokenBars: Candle[] = [
      // Closes cleanly BELOW Asian Low (breaks 3962.51)
      { time: 1794474600, open: 3964.11, high: 3965.0, low: 3959.16, close: 3960.82 },
      // Bounce that opens BELOW 3962.51 and closes above it -> NOT a downward sweep!
      { time: 1794474900, open: 3960.8, high: 3966.99, low: 3959.54, close: 3964.65 },
      // Another bounce opening below 3962.51 -> NOT a sweep!
      { time: 1794477000, open: 3960.53, high: 3964.63, low: 3960.16, close: 3964.56 },
    ];
    expect(extractLiquiditySweeps(brokenBars, nov12Range, null)).toEqual([]);
  });

  it('detects causal 3-bar swing pivot liquidity grabs and respects replayTo anti-spoiler cursor', () => {
    // When replayTo excludes bar 4 (1768470600), only bar 2 sweep is visible
    const sweepsReplay = extractLiquiditySweeps(candles, asianRanges, 1768470400);
    expect(sweepsReplay.length).toBe(1);
    expect(sweepsReplay[0].time).toBe(1768470000);

    // Causal Swing High at bar 3 (price 100), swept with >=35% rejection wick at bar 7
    const swingBars: Candle[] = [
      { time: 100, open: 95, high: 96, low: 94, close: 95.5 },
      { time: 200, open: 95.5, high: 97, low: 95, close: 96.5 },
      { time: 300, open: 96.5, high: 98, low: 96, close: 97.5 },
      { time: 400, open: 97.5, high: 100, low: 97, close: 98 }, // Swing High = 100
      { time: 500, open: 98, high: 99, low: 96, close: 97 },
      { time: 600, open: 97, high: 98, low: 95, close: 96 },
      { time: 700, open: 96, high: 97, low: 94, close: 96.5 }, // Pivot confirmed here
      { time: 800, open: 97, high: 102, low: 96.5, close: 97.2 }, // Sweeps 100 -> 102, closes 97.2 (wick 4.8 / 5.5 = 87%)
    ];
    const swingSweeps = extractLiquiditySweeps(swingBars, {}, null);
    expect(swingSweeps).toHaveLength(1);
    expect(swingSweeps[0].type).toBe('HIGH_SWEEP');
    expect(swingSweeps[0].level).toBe(100);
    expect(swingSweeps[0].origin_time).toBe(400);
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

describe('coTraderLogic - Symbol Cached Date Range Resolution', () => {
  const cableSym: CatalogSymbol = {
    symbol: 'GBPUSD_o',
    display_name: 'British Pound / USD',
    engine_mode: 'SMC',
    uncalibrated: false,
    spread_pts: 0.00015,
    digits: 5,
    min_date: '2026-01-02',
    max_date: '2026-11-04',
  };

  it('auto-snaps to latest cached 3-day window when active range is outside symbol cache', () => {
    const res = resolveDateRangeForSymbol(cableSym, '2026-11-10', '2026-11-12', 3);
    expect(res).toEqual({ start: '2026-11-02', end: '2026-11-04', adjusted: true });
  });

  it('preserves active range when there is valid date overlap', () => {
    const res = resolveDateRangeForSymbol(cableSym, '2026-11-01', '2026-11-05', 3);
    expect(res).toEqual({ start: '2026-11-01', end: '2026-11-05', adjusted: false });
  });

  it('clamps getLatestRangeForSymbol cleanly against min_date', () => {
    const shortSym: CatalogSymbol = { ...cableSym, min_date: '2026-11-03', max_date: '2026-11-04' };
    expect(getLatestRangeForSymbol(shortSym, 7)).toEqual({ start: '2026-11-03', end: '2026-11-04' });
  });
});

describe('coTraderLogic - Workbench Preferences & Forensic Box Deduplication', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('persists and restores overlay toggles via localStorage cleanly', () => {
    const store: Record<string, string> = {};
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
    });

    const custom = {
      ...DEFAULT_WORKBENCH_PREFS,
      showKillzones: false,
      showBoxes: false,
      showSweeps: true,
      clockMode: 'utc' as const,
    };
    saveWorkbenchPrefs(custom);
    const loaded = loadWorkbenchPrefs();
    expect(loaded).toEqual(custom);
  });

  it('deduplicates repeated per-bar FVG and Breaker zones while preserving max t_end', () => {
    const fvgs: FvgBox[] = [
      { top: 4000, bottom: 3995, t_start: 1000, t_end: 1300, dir: 'BEARISH' },
      { top: 4000, bottom: 3995, t_start: 1000, t_end: 1600, dir: 'BEARISH' },
      { top: 4000, bottom: 3995, t_start: 1000, t_end: 1900, dir: 'BEARISH' },
    ];
    const dedupedFvg = dedupeFvgBoxes(fvgs);
    expect(dedupedFvg).toHaveLength(1);
    expect(dedupedFvg[0].t_end).toBe(1900);

    const brks: BreakerBox[] = [
      { top: 3980, bottom: 3975, t_start: 2000, t_end: 2300, type: 'BEARISH_BREAKER' },
      { top: 3980, bottom: 3975, t_start: 2000, t_end: 2600, type: 'BEARISH_BREAKER' },
    ];
    const dedupedBrk = dedupeBreakerBoxes(brks);
    expect(dedupedBrk).toHaveLength(1);
    expect(dedupedBrk[0].t_end).toBe(2600);
  });

  it('clusters nearby same-direction bot trades cleanly and respects blind replay masking', () => {
    const closeTrades: ReplayTrade[] = [
      {
        trade_id: 'BOT-1',
        symbol: 'GBPUSD_o',
        origin: 'BOT',
        direction: 'SHORT',
        decision_time: 10000,
        fill_time: 10000,
        exit_time: 10900,
        entry: 1.347,
        sl: 1.348,
        tp: 1.345,
        status: 'LOSS',
        realized_pnl_usd: -10.0,
        rr_realized: -1.0,
      },
      {
        trade_id: 'BOT-2',
        symbol: 'GBPUSD_o',
        origin: 'BOT',
        direction: 'SHORT',
        decision_time: 10300,
        fill_time: 10300,
        exit_time: 11200,
        entry: 1.3468,
        sl: 1.3478,
        tp: 1.3448,
        status: 'WIN',
        realized_pnl_usd: 20.0,
        rr_realized: 2.0,
      },
      {
        trade_id: 'BOT-3',
        symbol: 'GBPUSD_o',
        origin: 'BOT',
        direction: 'SHORT',
        decision_time: 10600,
        fill_time: 10600,
        exit_time: 13000,
        entry: 1.3465,
        sl: 1.3475,
        tp: 1.3445,
        status: 'LOSS',
        realized_pnl_usd: -10.0,
        rr_realized: -1.0,
      },
    ];

    // All 3 fall inside 1800s window -> 1 clustered entry marker + 0 exit clutter
    const clustered = buildClusteredTradeMarkers(closeTrades, null, 1800, null);
    expect(clustered).toHaveLength(1);
    expect(clustered[0].isCluster).toBe(true);
    expect(clustered[0].text).toContain('3×S (1W/2L)');
    expect(clustered[0].tradeIds).toEqual(['BOT-1', 'BOT-2', 'BOT-3']);

    // Selecting BOT-2 highlights cluster gold and shows BOT-2 exit marker
    const withSel = buildClusteredTradeMarkers(closeTrades, null, 1800, 'BOT-2');
    expect(withSel).toHaveLength(2);
    expect(withSel[0].color).toBe('#f0b90b');
    expect(withSel[1].time).toBe(11200);
    expect(withSel[1].text).toContain('+$20.0');

    // Blind replay at t=11000 masks BOT-2 & BOT-3 as open (1L/2O)
    const masked = buildClusteredTradeMarkers(closeTrades, 11000, 1800, null);
    expect(masked).toHaveLength(1);
    expect(masked[0].text).toContain('3×S (1L/2O)');

    // Interactive lookup finds nearby trades cleanly
    const hits = findMatchingTradesNearTime(closeTrades, 10300, 1800, null);
    expect(hits.map((h) => h.trade_id)).toEqual(['BOT-2', 'BOT-1', 'BOT-3']);
    expect(getClusterWindowSeconds([{ time: 1000, open: 1, high: 1, low: 1, close: 1 }, { time: 1300, open: 1, high: 1, low: 1, close: 1 }])).toBe(1800);
  });

  it('hit-tests Breaker, FVG, and Sweep SMC elements by (time, price) and builds structured context', () => {
    const brk: BreakerBox = {
      top: 3982.0,
      bottom: 3977.0,
      t_start: 1794471000,
      t_end: 1794473400,
      type: 'BEARISH_BREAKER',
    };
    const fvg: FvgBox = {
      top: 3960.0,
      bottom: 3955.0,
      t_start: 1794474000,
      t_end: 1794475500,
      dir: 'BEARISH',
    };
    const hits = findMatchingSmcElementsAtPoint(
      1794472000,
      3979.5,
      { fvgs: [fvg], breakers: [brk], sweeps: [], asianRanges: [], showBoxes: true },
      600,
      3.0,
      null
    );
    expect(hits).toHaveLength(1);
    expect(hits[0].kind).toBe('BREAKER');
    expect(hits[0].label).toBe('BEARISH_BREAKER');

    const questions = getQuickQuestionsForSmcElement('BREAKER');
    expect(questions.length).toBeGreaterThanOrEqual(3);

    const md = buildSmcElementContextMarkdown({
      symbol: 'XAUUSD_o',
      timeframe: '5M',
      clockMode: 'tehran',
      digits: 2,
      element: hits[0],
      candles: [
        { time: 1794471700, open: 3983, high: 3984, low: 3978, close: 3979 },
        { time: 1794472000, open: 3979, high: 3981, low: 3976, close: 3977 },
      ],
      question: questions[0],
    });
    expect(md).toContain('BEARISH_BREAKER');
    expect(md).toContain('3977.00 – 3982.00');
    expect(md).toContain(questions[0]);
  });
});
