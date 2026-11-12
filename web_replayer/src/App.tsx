/**
 * TradingGuard HITL Visual Co-Backtester - Main Workbench Application (App.tsx)
 * Features:
 * - Asset Switcher (XAUUSD_o, GBPUSD_o, NQ, SPX, YM, BTCUSD) + [Sync MT5]
 * - Date Range inputs & Jump-to-Date presets (Nov 10, Nov 11, Nov 12, Full)
 * - 6 Timeframe switcher (1M | 5M | 15M | 1H | 4H | 1D)
 * - Multi-clock display toggle (Tehran UTC+3:30 | UTC | MT5 Server)
 * - Screener clock mode toggle (true_tehran | live_legacy)
 * - Overlay visibility toggles (Killzones, Asian Bounds, FVG/Breaker boxes, Sweeps, Trades)
 * - Anti-spoiler Blind Replay transport (Play/Pause, Step -1/+1, Speed 1x-20x, Timeline Scrubber)
 * - Interactive Co-Trading: + Long / + Short, draggable Entry/SL/TP handles, live R:R, $20 risk compliance badge,
 *   [Simulate Trade] with canonical M1 evaluator, and [Save to Ledger] persisting to shared ledger.
 * - Right Workbench Drawer: Bot Brain Inspector, Co-Trade Scorecard & Ledger, and Agentify Feedback Bridge.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Award,
  Bot,
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
  EyeOff,
  Layers,
  Pause,
  Play,
  RefreshCw,
  Save,
  SkipBack,
  SkipForward,
  Sparkles,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react';

import { replayApi } from './api/client';
import { AgentifyFeedbackPanel } from './components/AgentifyFeedbackPanel';
import { BotBrainPanel } from './components/BotBrainPanel';
import { ReplayChart } from './components/ReplayChart';
import { ScorecardPanel } from './components/ScorecardPanel';
import type {
  AsianRangeDay,
  BreakerBox,
  Candle,
  CatalogResponse,
  CatalogSymbol,
  ClockMode,
  DraftTrade,
  EngineClockMode,
  FvgBox,
  Killzone,
  ReplayTrade,
  SimulateTradeResponse,
  SweepFlag,
  Timeframe,
  TradeDirection,
} from './types/replay';
import {
  checkRiskLimitUSD,
  computeTradeRR,
  dedupeBreakerBoxes,
  dedupeFvgBoxes,
  extractLiquiditySweeps,
  formatClockTick,
  getLatestRangeForSymbol,
  loadWorkbenchPrefs,
  maskBlindReplayTrade,
  resolveDateRangeForSymbol,
  saveWorkbenchPrefs,
} from './utils/coTraderLogic';

const DEFAULT_TIMEFRAMES: Timeframe[] = ['1M', '5M', '15M', '1H', '4H', '1D'];
const SPEED_OPTIONS = [1, 2, 5, 10, 20];

export function App() {
  // Catalog & Symbol Selection
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('XAUUSD_o');
  const [isSyncingMt5, setIsSyncingMt5] = useState<boolean>(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [isLoadingCandles, setIsLoadingCandles] = useState<boolean>(false);

  const [initialPrefs] = useState(() => loadWorkbenchPrefs());

  // Timeframe & Clocks
  const [timeframe, setTimeframe] = useState<Timeframe>(initialPrefs.timeframe);
  const [clockMode, setClockMode] = useState<ClockMode>(initialPrefs.clockMode);
  const [engineClockMode, setEngineClockMode] = useState<EngineClockMode>(initialPrefs.engineClockMode);

  // Date Range (Defaults to Nov 10 - Nov 12, 2026 where verified test data exists)
  const [startDateStr, setStartDateStr] = useState<string>('2026-11-10');
  const [endDateStr, setEndDateStr] = useState<string>('2026-11-12');

  // Visibility Toggles
  const [showKillzones, setShowKillzones] = useState<boolean>(initialPrefs.showKillzones);
  const [showAsianRange, setShowAsianRange] = useState<boolean>(initialPrefs.showAsianRange);
  const [showBoxes, setShowBoxes] = useState<boolean>(initialPrefs.showBoxes);
  const [showSweeps, setShowSweeps] = useState<boolean>(initialPrefs.showSweeps);
  const [showTrades, setShowTrades] = useState<boolean>(initialPrefs.showTrades);

  // Replay Transport & Blind Replay State
  const [blindReplay, setBlindReplay] = useState<boolean>(false);
  const [replayCursor, setReplayCursor] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(2);

  // Inspected Bar & Workbench Tabs
  const [inspectedTime, setInspectedTime] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<'bot' | 'scorecard' | 'agentify'>('bot');
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(initialPrefs.isDrawerOpen);

  useEffect(() => {
    saveWorkbenchPrefs({
      showKillzones,
      showAsianRange,
      showBoxes,
      showSweeps,
      showTrades,
      clockMode,
      engineClockMode,
      timeframe,
      isDrawerOpen,
    });
  }, [
    showKillzones,
    showAsianRange,
    showBoxes,
    showSweeps,
    showTrades,
    clockMode,
    engineClockMode,
    timeframe,
    isDrawerOpen,
  ]);

  // Co-Trading & Position Box State
  const [draftTrade, setDraftTrade] = useState<DraftTrade | null>(null);
  const [simResult, setSimResult] = useState<SimulateTradeResponse | null>(null);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [isSavingTrade, setIsSavingTrade] = useState<boolean>(false);

  // Data Collections
  const [candles, setCandles] = useState<Candle[]>([]);
  const [killzones, setKillzones] = useState<Killzone[]>([]);
  const [asianRanges, setAsianRanges] = useState<Record<string, AsianRangeDay>>({});
  const [fvgs, setFvgs] = useState<FvgBox[]>([]);
  const [breakers, setBreakers] = useState<BreakerBox[]>([]);
  const [botTrades, setBotTrades] = useState<ReplayTrade[]>([]);
  const [coTrades, setCoTrades] = useState<ReplayTrade[]>([]);
  const [diagnostics, setDiagnostics] = useState<any[]>([]);
  const [botEvents, setBotEvents] = useState<any[]>([]);

  // Agentify Feedback Prefill Context
  const [feedbackPrefill, setFeedbackPrefill] = useState<{
    title?: string;
    category?: 'MISSED_SETUP' | 'BOT_TRADE_EDIT' | 'VETO_DISAGREEMENT' | 'NOTE';
    rationale?: string;
    archetype_id?: string;
    timestamp?: number;
  } | null>(null);

  // Active Symbol metadata
  const activeSymbolObj: CatalogSymbol | undefined = useMemo(() => {
    return catalog?.symbols.find((s) => s.symbol === selectedSymbol);
  }, [catalog, selectedSymbol]);

  const digits = activeSymbolObj?.digits ?? (selectedSymbol.includes('GBP') ? 5 : 2);

  // Convert Date strings to Server epochs (EET / UTC timestamps)
  const { startEpoch, endEpoch } = useMemo(() => {
    const parseDateToEpoch = (dStr: string, isEnd: boolean) => {
      const parts = dStr.split('-');
      if (parts.length === 3) {
        const y = parseInt(parts[0], 10);
        const m = parseInt(parts[1], 10) - 1;
        const d = parseInt(parts[2], 10);
        if (isEnd) {
          return Math.floor(Date.UTC(y, m, d, 23, 59, 59) / 1000);
        }
        return Math.floor(Date.UTC(y, m, d, 0, 0, 0) / 1000);
      }
      return 0;
    };
    return {
      startEpoch: parseDateToEpoch(startDateStr, false),
      endEpoch: parseDateToEpoch(endDateStr, true),
    };
  }, [startDateStr, endDateStr]);

  // Load Catalog on Mount
  useEffect(() => {
    replayApi.getCatalog().then((res) => {
      setCatalog(res);
    }).catch(() => {});
  }, []);

  // Switch Symbol & auto-adjust date range when active window is outside symbol cache
  const handleSelectSymbol = (nextSymbol: string) => {
    setSelectedSymbol(nextSymbol);
    setInspectedTime(null);
    setReplayCursor(null);
    setIsPlaying(false);
    setDraftTrade(null);
    setSimResult(null);
    setSyncNotice(null);

    const targetSym = catalog?.symbols.find((s) => s.symbol === nextSymbol);
    const resolved = resolveDateRangeForSymbol(targetSym, startDateStr, endDateStr, 3);
    if (resolved.adjusted) {
      setStartDateStr(resolved.start);
      setEndDateStr(resolved.end);
    }
  };

  // Fetch Candles
  const loadCandles = useCallback(async (isCancelled?: () => boolean) => {
    if (!startEpoch || !endEpoch) return;
    setIsLoadingCandles(true);
    try {
      const res = await replayApi.getCandles({
        symbol: selectedSymbol,
        tf: timeframe,
        start: startEpoch,
        end: endEpoch,
      });
      if (isCancelled?.()) return;
      setCandles(res || []);
      setReplayCursor((prev) => (prev === null && res && res.length > 0 ? res[Math.min(res.length - 1, 15)].time : prev));
    } catch {
      if (!isCancelled?.()) {
        setCandles([]);
      }
    } finally {
      if (!isCancelled?.()) {
        setIsLoadingCandles(false);
      }
    }
  }, [selectedSymbol, timeframe, startEpoch, endEpoch]);

  // Fetch Bot Scan & SMC Diagnostics
  const loadBotScan = useCallback(async (isCancelled?: () => boolean) => {
    if (!startEpoch || !endEpoch) return;
    try {
      const res = await replayApi.getBotScan({
        symbol: selectedSymbol,
        start: startEpoch,
        end: endEpoch,
        clock_mode: engineClockMode,
      });
      if (isCancelled?.()) return;
      setKillzones(res.killzones || []);
      setAsianRanges(res.asian_ranges_by_day || {});
      setDiagnostics(res.diagnostics || []);
      setBotEvents(res.events || []);
      setBotTrades(res.bot_trades || []);

      const fvgList: FvgBox[] = [];
      const brkList: BreakerBox[] = [];
      for (const d of res.diagnostics || []) {
        if (d.fvg_box) fvgList.push(d.fvg_box);
        if (d.breaker_box) brkList.push(d.breaker_box);
      }
      setFvgs(dedupeFvgBoxes(fvgList));
      setBreakers(dedupeBreakerBoxes(brkList));
    } catch {
      if (isCancelled?.()) return;
      setKillzones([]);
      setAsianRanges({});
      setDiagnostics([]);
      setBotEvents([]);
      setBotTrades([]);
      setFvgs([]);
      setBreakers([]);
    }
  }, [selectedSymbol, startEpoch, endEpoch, engineClockMode]);

  // Fetch Shared Co-Trades Ledger
  const loadCoTrades = useCallback(async (isCancelled?: () => boolean) => {
    try {
      const res = await replayApi.getCoTrades(selectedSymbol);
      if (isCancelled?.()) return;
      setCoTrades(res.trades || []);
    } catch {
      if (!isCancelled?.()) {
        setCoTrades([]);
      }
    }
  }, [selectedSymbol]);

  // Load data when symbol, range, or clock mode changes (reusing loadCandles, loadBotScan, loadCoTrades)
  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) void loadCandles(() => !active);
    });
    return () => {
      active = false;
    };
  }, [loadCandles]);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) void loadBotScan(() => !active);
    });
    return () => {
      active = false;
    };
  }, [loadBotScan]);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) void loadCoTrades(() => !active);
    });
    return () => {
      active = false;
    };
  }, [loadCoTrades]);

  // Extract Causal Liquidity Sweeps
  const sweeps: SweepFlag[] = useMemo(() => {
    return extractLiquiditySweeps(candles, asianRanges, blindReplay ? replayCursor : null);
  }, [candles, asianRanges, blindReplay, replayCursor]);

  // Merge Bot Trades + Co-Trades for full chart & scorecard view
  const allTrades: ReplayTrade[] = useMemo(() => {
    const map = new Map<string, ReplayTrade>();
    for (const t of botTrades) {
      map.set(t.trade_id, t);
    }
    for (const t of coTrades) {
      map.set(t.trade_id, t);
    }
    return Array.from(map.values()).sort((a, b) => a.decision_time - b.decision_time);
  }, [botTrades, coTrades]);

  // Masked trades passed to ReplayChart (strict anti-spoiler)
  const chartTrades: ReplayTrade[] = useMemo(() => {
    if (!blindReplay || replayCursor === null) {
      return allTrades;
    }
    return allTrades.map((t) => maskBlindReplayTrade(t, replayCursor));
  }, [allTrades, blindReplay, replayCursor]);

  // Active Bar for Bot Brain Inspector
  const activeInspectionTime = useMemo(() => {
    if (inspectedTime !== null) return inspectedTime;
    if (blindReplay && replayCursor !== null) return replayCursor;
    if (candles.length > 0) return candles[candles.length - 1].time;
    return null;
  }, [inspectedTime, blindReplay, replayCursor, candles]);

  // Keep candles ref updated so playback interval does not thrash or reset when candles change
  const candlesRef = useRef(candles);
  useEffect(() => {
    candlesRef.current = candles;
  }, [candles]);

  // Replay Transport Stepping Loop (stable interval using candlesRef without thrashing on ticks)
  useEffect(() => {
    if (!isPlaying || !blindReplay) return;

    const intervalMs = Math.max(50, Math.floor(1000 / playbackSpeed));
    const timer = setInterval(() => {
      const currentCandles = candlesRef.current;
      if (currentCandles.length === 0) return;

      setReplayCursor((prev) => {
        if (prev === null) return currentCandles[0].time;
        let curIdx = currentCandles.findIndex((c) => c.time >= prev);
        if (curIdx === -1) curIdx = 0;
        const nextIdx = curIdx + 1;
        if (nextIdx >= currentCandles.length) {
          setIsPlaying(false);
          return prev;
        }
        const nextTime = currentCandles[nextIdx].time;
        setInspectedTime(nextTime);
        return nextTime;
      });
    }, intervalMs);

    return () => clearInterval(timer);
  }, [isPlaying, blindReplay, playbackSpeed]);

  // Step -1 / +1 helpers
  const handleStepReplay = (delta: number) => {
    const currentCandles = candlesRef.current;
    if (currentCandles.length === 0) return;
    setReplayCursor((prev) => {
      const cur = prev ?? currentCandles[0].time;
      let curIdx = currentCandles.findIndex((c) => c.time >= cur);
      if (curIdx === -1) curIdx = delta > 0 ? 0 : currentCandles.length - 1;
      const targetIdx = Math.max(0, Math.min(currentCandles.length - 1, curIdx + delta));
      const targetTime = currentCandles[targetIdx].time;
      setInspectedTime(targetTime);
      return targetTime;
    });
  };

  // MT5 Sync Handler
  const handleSyncMt5 = async () => {
    setIsSyncingMt5(true);
    setSyncNotice(null);
    try {
      const syncRes = await replayApi.syncMt5(selectedSymbol, 5);
      const freshCatalog = await replayApi.getCatalog().catch(() => null);
      if (freshCatalog) {
        setCatalog(freshCatalog);
        const syncedSym = freshCatalog.symbols.find((s) => s.symbol === selectedSymbol);
        const latest = getLatestRangeForSymbol(syncedSym, 3);
        if (syncRes.success && latest && latest.end > endDateStr) {
          setStartDateStr(latest.start);
          setEndDateStr(latest.end);
        }
      }
      if (syncRes.success === false && typeof syncRes.message === 'string') {
        setSyncNotice(syncRes.message);
      }
      await Promise.all([loadCandles(), loadBotScan(), loadCoTrades()]);
    } catch (err) {
      setSyncNotice(err instanceof Error ? err.message : 'MT5 sync failed');
    } finally {
      setIsSyncingMt5(false);
    }
  };

  // Co-Trading: Initiate Draft Setup
  const handleCreateDraft = (dir: TradeDirection) => {
    const anchorCandle =
      candles.find((c) => (blindReplay && replayCursor !== null ? c.time === replayCursor : false)) ||
      candles[candles.length - 1];

    const currentPrice = anchorCandle ? anchorCandle.close : 2680.0;
    const defaultPts = selectedSymbol.includes('GBP')
      ? 0.003
      : selectedSymbol.includes('XAU')
      ? 5.0
      : selectedSymbol.includes('BTC')
      ? 250.0
      : 25.0;

    const isLong = dir === 'LONG';
    const entry = Number(currentPrice.toFixed(digits));
    const sl = Number((isLong ? entry - defaultPts : entry + defaultPts).toFixed(digits));
    const tp = Number((isLong ? entry + defaultPts * 2 : entry - defaultPts * 2).toFixed(digits));

    setDraftTrade({
      direction: dir,
      entry,
      sl,
      tp,
      symbol: selectedSymbol,
      signal_time: anchorCandle ? anchorCandle.time : Math.floor(Date.now() / 1000),
    });
    setSimResult(null);
  };

  // Co-Trading: Clone existing trade
  const handleCloneTrade = (trade: ReplayTrade) => {
    setDraftTrade({
      direction: trade.direction,
      entry: trade.entry,
      sl: trade.sl,
      tp: trade.tp,
      symbol: trade.symbol,
      signal_time: trade.decision_time,
      parent_bot_ref: trade.origin === 'BOT' ? trade.trade_id : trade.parent_bot_ref,
    });
    setSimResult(null);
  };

  // Co-Trading: Simulate Draft Setup
  const handleSimulateDraft = async () => {
    if (!draftTrade) return;
    setIsSimulating(true);
    try {
      const res = await replayApi.simulateTrade({
        symbol: selectedSymbol,
        direction: draftTrade.direction,
        signal_time: draftTrade.signal_time ?? 0,
        entry: draftTrade.entry,
        sl: draftTrade.sl,
        tp: draftTrade.tp,
        horizon_end: endEpoch,
      });
      setSimResult(res);
    } catch {
      // Error
    } finally {
      setIsSimulating(false);
    }
  };

  // Co-Trading: Save to Shared Ledger
  const handleSaveDraftToLedger = async () => {
    if (!draftTrade) return;
    setIsSavingTrade(true);
    try {
      const isEdited = Boolean(draftTrade.parent_bot_ref);
      const riskCheck = checkRiskLimitUSD(selectedSymbol, draftTrade.entry, draftTrade.sl, 0.01, 20.0);

      await replayApi.createCoTrade({
        symbol: selectedSymbol,
        direction: draftTrade.direction,
        decision_time: draftTrade.signal_time ?? Math.floor(Date.now() / 1000),
        entry: draftTrade.entry,
        sl: draftTrade.sl,
        tp: draftTrade.tp,
        origin: isEdited ? 'HUMAN_EDITED_BOT' : 'HUMAN_PROPOSED',
        parent_bot_ref: draftTrade.parent_bot_ref ?? null,
        status: simResult?.status ?? 'PENDING',
        realized_pnl_usd: simResult?.realized_pnl_usd ?? null,
        rr_realized: simResult?.rr_realized ?? null,
        fill_time: simResult?.fill_time ?? null,
        exit_time: simResult?.exit_time ?? null,
        risk_usd_001: riskCheck.riskUsd,
        exceeds_risk_cap: riskCheck.exceedsRiskCap,
        notes: isEdited ? `Cloned from ${draftTrade.parent_bot_ref}` : 'Proposed in Replay',
      });

      await loadCoTrades();
      setDraftTrade(null);
      setSimResult(null);
    } catch {
      // Error
    } finally {
      setIsSavingTrade(false);
    }
  };

  // Delete trade from ledger
  const handleDeleteTrade = async (tradeId: string) => {
    try {
      await replayApi.deleteCoTrade(tradeId);
      await loadCoTrades();
    } catch {
      // Error
    }
  };

  // Trigger feedback prefill from Bot Brain or Scorecard
  const handleTriggerFeedback = (ctx: {
    title: string;
    category: 'MISSED_SETUP' | 'BOT_TRADE_EDIT' | 'VETO_DISAGREEMENT' | 'NOTE';
    rationale: string;
    archetype_id?: string;
    timestamp?: number;
  }) => {
    setFeedbackPrefill(ctx);
    setActiveTab('agentify');
    setIsDrawerOpen(true);
  };

  // Live Draft Risk & R:R Checks
  const draftRiskCheck = useMemo(() => {
    if (!draftTrade) return null;
    return checkRiskLimitUSD(selectedSymbol, draftTrade.entry, draftTrade.sl, 0.01, 20.0);
  }, [draftTrade, selectedSymbol]);

  const draftRR = useMemo(() => {
    if (!draftTrade) return 0;
    return computeTradeRR(draftTrade.entry, draftTrade.sl, draftTrade.tp, draftTrade.direction);
  }, [draftTrade]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh', backgroundColor: '#131722', color: '#d1d4dc', overflow: 'hidden' }}>
      {/* Top Header - Level 1 */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 14px',
          borderBottom: '1px solid #2a2e39',
          backgroundColor: '#1e222d',
          minHeight: '44px',
          gap: '12px',
        }}
      >
        {/* Brand & Asset Switcher */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontWeight: 800, fontSize: '14px', letterSpacing: '0.5px', color: '#f0b90b' }}>
              TradingGuard
            </span>
            <span style={{ color: '#565a65', fontSize: '12px' }}>|</span>
            <span style={{ fontWeight: 600, fontSize: '13px', color: '#ffffff' }}>
              Visual Co-Backtester
            </span>
          </div>

          {/* Symbol Select */}
          <select
            value={selectedSymbol}
            onChange={(e) => handleSelectSymbol(e.target.value)}
            style={{
              backgroundColor: '#131722',
              border: '1px solid #2a2e39',
              borderRadius: '4px',
              color: '#ffffff',
              fontSize: '12px',
              fontWeight: 700,
              padding: '4px 8px',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            {catalog?.symbols ? (
              catalog.symbols.map((s) => (
                <option key={s.symbol} value={s.symbol}>
                  {s.display_name} ({s.symbol})
                </option>
              ))
            ) : (
              <option value="XAUUSD_o">Gold (XAUUSD_o)</option>
            )}
          </select>

          {/* Engine Status Badge */}
          {activeSymbolObj?.engine_mode === 'MANUAL_ONLY' || selectedSymbol === 'BTCUSD' ? (
            <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', backgroundColor: 'rgba(171, 71, 188, 0.2)', color: '#ce93d8', fontWeight: 600 }}>
              Manual Only (SMC decommissioned)
            </span>
          ) : activeSymbolObj?.uncalibrated ? (
            <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', backgroundColor: 'rgba(255, 179, 0, 0.2)', color: '#ffd54f', fontWeight: 600 }}>
              Uncalibrated Index
            </span>
          ) : (
            <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', backgroundColor: 'rgba(38, 166, 154, 0.2)', color: '#26a69a', fontWeight: 600 }}>
              SMC Active
            </span>
          )}

          {/* MT5 Sync Button */}
          <button
            onClick={handleSyncMt5}
            disabled={isSyncingMt5}
            title="Fetch recent candles from live MT5 terminal"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              backgroundColor: '#131722',
              border: '1px solid #2a2e39',
              borderRadius: '4px',
              color: '#90caf9',
              fontSize: '11px',
              fontWeight: 600,
              padding: '3px 8px',
              cursor: isSyncingMt5 ? 'not-allowed' : 'pointer',
              opacity: isSyncingMt5 ? 0.6 : 1,
            }}
          >
            <RefreshCw size={12} className={isSyncingMt5 ? 'animate-spin' : ''} />
            {isSyncingMt5 ? 'Syncing...' : 'Sync MT5'}
          </button>
        </div>

        {/* Date Range Inputs & Jump Presets */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#131722', padding: '2px 6px', borderRadius: '4px', border: '1px solid #2a2e39' }}>
            <Calendar size={13} style={{ color: '#787b86' }} />
            <input
              type="date"
              value={startDateStr}
              onChange={(e) => setStartDateStr(e.target.value)}
              style={{ backgroundColor: 'transparent', border: 'none', color: '#d1d4dc', fontSize: '11px', outline: 'none' }}
            />
            <span style={{ color: '#787b86', fontSize: '11px' }}>→</span>
            <input
              type="date"
              value={endDateStr}
              onChange={(e) => setEndDateStr(e.target.value)}
              style={{ backgroundColor: 'transparent', border: 'none', color: '#d1d4dc', fontSize: '11px', outline: 'none' }}
            />
          </div>

          {/* Quick Date Presets (Dynamic per symbol's cached max_date) */}
          <div style={{ display: 'flex', gap: '3px' }}>
            {([
              ['Last Day', 1],
              ['Latest 3D', 3],
              ['Latest 7D', 7],
            ] as const).map(([lbl, days]) => {
              const range = getLatestRangeForSymbol(activeSymbolObj, days);
              const s = range ? range.start : (days === 1 ? '2026-11-12' : days === 3 ? '2026-11-10' : '2026-11-06');
              const e = range ? range.end : '2026-11-12';
              const isActive = startDateStr === s && endDateStr === e;
              return (
                <button
                  key={lbl}
                  onClick={() => {
                    setStartDateStr(s);
                    setEndDateStr(e);
                  }}
                  title={range ? `${s} → ${e}` : undefined}
                  style={{
                    padding: '2px 6px',
                    fontSize: '10px',
                    fontWeight: isActive ? 700 : 500,
                    backgroundColor: isActive ? '#2962ff' : '#131722',
                    color: isActive ? '#ffffff' : '#b2b5be',
                    border: '1px solid #2a2e39',
                    borderRadius: '3px',
                    cursor: 'pointer',
                  }}
                >
                  {lbl}
                </button>
              );
            })}
          </div>

          {/* Timeframe Switcher (6 Buttons) */}
          <div style={{ display: 'flex', backgroundColor: '#131722', padding: '2px', borderRadius: '4px', border: '1px solid #2a2e39' }}>
            {DEFAULT_TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                style={{
                  padding: '3px 7px',
                  fontSize: '11px',
                  fontWeight: timeframe === tf ? 700 : 500,
                  backgroundColor: timeframe === tf ? '#2962ff' : 'transparent',
                  color: timeframe === tf ? '#ffffff' : '#787b86',
                  border: 'none',
                  borderRadius: '3px',
                  cursor: 'pointer',
                }}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Top Header - Level 2: Transport & Overlays & Position Tools */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 14px',
          borderBottom: '1px solid #2a2e39',
          backgroundColor: '#181b24',
          minHeight: '38px',
          fontSize: '11px',
          gap: '10px',
        }}
      >
        {/* Clocks & Screener Engine Mode */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Display Clock */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#131722', padding: '2px 4px', borderRadius: '4px', border: '1px solid #2a2e39' }}>
            <Clock size={12} style={{ color: '#787b86', marginLeft: '2px' }} />
            {(['tehran', 'utc', 'server'] as ClockMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setClockMode(mode)}
                style={{
                  padding: '2px 6px',
                  fontSize: '10px',
                  fontWeight: clockMode === mode ? 600 : 400,
                  backgroundColor: clockMode === mode ? '#2962ff' : 'transparent',
                  color: clockMode === mode ? '#ffffff' : '#787b86',
                  border: 'none',
                  borderRadius: '3px',
                  cursor: 'pointer',
                  textTransform: 'uppercase',
                }}
              >
                {mode === 'tehran' ? 'Tehran (+3:30)' : mode}
              </button>
            ))}
          </div>

          {/* Screener Engine Clock Mode Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#131722', padding: '2px 4px', borderRadius: '4px', border: '1px solid #2a2e39' }}>
            <span style={{ fontSize: '10px', color: '#787b86', fontWeight: 600 }}>Screener:</span>
            {(['true_tehran', 'live_legacy'] as EngineClockMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setEngineClockMode(mode)}
                title={mode === 'true_tehran' ? 'Dynamic historical DST offset' : 'Reproduce live 16:40 NY PM veto bug'}
                style={{
                  padding: '2px 5px',
                  fontSize: '10px',
                  fontWeight: engineClockMode === mode ? 600 : 400,
                  backgroundColor: engineClockMode === mode ? (mode === 'true_tehran' ? '#26a69a' : '#ef5350') : 'transparent',
                  color: engineClockMode === mode ? '#ffffff' : '#787b86',
                  border: 'none',
                  borderRadius: '3px',
                  cursor: 'pointer',
                }}
              >
                {mode}
              </button>
            ))}
          </div>

          {/* Overlay Visibility Toggles */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '3px', backgroundColor: '#131722', padding: '2px 4px', borderRadius: '4px', border: '1px solid #2a2e39' }}>
            <Layers size={12} style={{ color: '#787b86', marginLeft: '2px' }} />
            <button
              onClick={() => setShowKillzones(!showKillzones)}
              title="Toggle Killzones"
              style={{
                padding: '2px 5px',
                fontSize: '10px',
                fontWeight: showKillzones ? 600 : 400,
                backgroundColor: showKillzones ? 'rgba(41, 98, 255, 0.2)' : 'transparent',
                color: showKillzones ? '#90caf9' : '#565a65',
                border: 'none',
                borderRadius: '3px',
                cursor: 'pointer',
              }}
            >
              KZ
            </button>
            <button
              onClick={() => setShowAsianRange(!showAsianRange)}
              title="Toggle Asian Range Bounds"
              style={{
                padding: '2px 5px',
                fontSize: '10px',
                fontWeight: showAsianRange ? 600 : 400,
                backgroundColor: showAsianRange ? 'rgba(255, 179, 0, 0.2)' : 'transparent',
                color: showAsianRange ? '#ffd54f' : '#565a65',
                border: 'none',
                borderRadius: '3px',
                cursor: 'pointer',
              }}
            >
              AR
            </button>
            <button
              onClick={() => setShowBoxes(!showBoxes)}
              title="Toggle FVG & Breaker Boxes"
              style={{
                padding: '2px 5px',
                fontSize: '10px',
                fontWeight: showBoxes ? 600 : 400,
                backgroundColor: showBoxes ? 'rgba(38, 166, 154, 0.2)' : 'transparent',
                color: showBoxes ? '#80cbc4' : '#565a65',
                border: 'none',
                borderRadius: '3px',
                cursor: 'pointer',
              }}
            >
              BOX
            </button>
            <button
              onClick={() => setShowSweeps(!showSweeps)}
              title="Toggle Sweep Flags"
              style={{
                padding: '2px 5px',
                fontSize: '10px',
                fontWeight: showSweeps ? 600 : 400,
                backgroundColor: showSweeps ? 'rgba(0, 230, 118, 0.2)' : 'transparent',
                color: showSweeps ? '#69f0ae' : '#565a65',
                border: 'none',
                borderRadius: '3px',
                cursor: 'pointer',
              }}
            >
              SWEEP
            </button>
            <button
              onClick={() => setShowTrades(!showTrades)}
              title="Toggle Trade Markers"
              style={{
                padding: '2px 5px',
                fontSize: '10px',
                fontWeight: showTrades ? 600 : 400,
                backgroundColor: showTrades ? 'rgba(239, 83, 80, 0.2)' : 'transparent',
                color: showTrades ? '#ff8a80' : '#565a65',
                border: 'none',
                borderRadius: '3px',
                cursor: 'pointer',
              }}
            >
              TRADES
            </button>
          </div>
        </div>

        {/* Blind Replay Transport Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {/* Blind Replay Toggle Button */}
          <button
            onClick={() => {
              const next = !blindReplay;
              setBlindReplay(next);
              if (next && replayCursor === null && candles.length > 0) {
                setReplayCursor(candles[Math.min(candles.length - 1, 15)].time);
              }
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '3px 8px',
              borderRadius: '4px',
              fontSize: '10px',
              fontWeight: 700,
              backgroundColor: blindReplay ? 'rgba(255, 179, 0, 0.2)' : '#131722',
              color: blindReplay ? '#ffd54f' : '#787b86',
              border: `1px solid ${blindReplay ? '#ffd54f' : '#2a2e39'}`,
              cursor: 'pointer',
            }}
          >
            {blindReplay ? <EyeOff size={12} /> : <Eye size={12} />}
            Blind Replay: {blindReplay ? 'ON' : 'OFF'}
          </button>

          {/* Transport Controls (when Blind Replay active) */}
          {blindReplay && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#131722', padding: '2px 6px', borderRadius: '4px', border: '1px solid #2a2e39' }}>
              {/* Step Back */}
              <button
                onClick={() => handleStepReplay(-1)}
                title="Step -1 Bar"
                style={{ background: 'transparent', border: 'none', color: '#d1d4dc', cursor: 'pointer', padding: '2px' }}
              >
                <SkipBack size={13} />
              </button>

              {/* Play / Pause */}
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                title={isPlaying ? 'Pause' : 'Play Replay'}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: isPlaying ? '#ef5350' : '#2962ff',
                  border: 'none',
                  borderRadius: '3px',
                  color: '#ffffff',
                  cursor: 'pointer',
                  padding: '3px 6px',
                }}
              >
                {isPlaying ? <Pause size={12} /> : <Play size={12} />}
              </button>

              {/* Step Forward */}
              <button
                onClick={() => handleStepReplay(1)}
                title="Step +1 Bar"
                style={{ background: 'transparent', border: 'none', color: '#d1d4dc', cursor: 'pointer', padding: '2px' }}
              >
                <SkipForward size={13} />
              </button>

              {/* Speed Selector */}
              <select
                value={playbackSpeed}
                onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
                style={{
                  backgroundColor: '#1e222d',
                  border: '1px solid #2a2e39',
                  borderRadius: '3px',
                  color: '#ffd54f',
                  fontSize: '10px',
                  fontWeight: 600,
                  padding: '1px 3px',
                  outline: 'none',
                }}
              >
                {SPEED_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}x
                  </option>
                ))}
              </select>

              {/* Timeline Scrubber */}
              {candles.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginLeft: '4px' }}>
                  <input
                    type="range"
                    min={candles[0].time}
                    max={candles[candles.length - 1].time}
                    value={replayCursor ?? candles[candles.length - 1].time}
                    onChange={(e) => {
                      const t = Number(e.target.value);
                      setReplayCursor(t);
                      setInspectedTime(t);
                    }}
                    style={{ width: '90px', cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: '10px', color: '#ffd54f', minWidth: '45px' }}>
                    {replayCursor ? formatClockTick(replayCursor, clockMode, false) : ''}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Interactive Co-Trading Setup Buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <button
              onClick={() => handleCreateDraft('LONG')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
                padding: '3px 8px',
                fontSize: '11px',
                fontWeight: 700,
                backgroundColor: 'rgba(38, 166, 154, 0.2)',
                color: '#26a69a',
                border: '1px solid rgba(38, 166, 154, 0.4)',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              <TrendingUp size={12} />
              + Long Setup
            </button>
            <button
              onClick={() => handleCreateDraft('SHORT')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
                padding: '3px 8px',
                fontSize: '11px',
                fontWeight: 700,
                backgroundColor: 'rgba(239, 83, 80, 0.2)',
                color: '#ef5350',
                border: '1px solid rgba(239, 83, 80, 0.4)',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              <TrendingDown size={12} />
              + Short Setup
            </button>
          </div>
        </div>
      </div>

      {/* Active Draft Trade Control Banner */}
      {draftTrade && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 14px',
            backgroundColor: '#1e222d',
            borderBottom: '1px solid #2962ff',
            fontSize: '11px',
            gap: '12px',
          }}
        >
          {/* Position Parameters */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span
              style={{
                fontWeight: 800,
                padding: '2px 6px',
                borderRadius: '3px',
                backgroundColor: draftTrade.direction === 'LONG' ? 'rgba(38, 166, 154, 0.2)' : 'rgba(239, 83, 80, 0.2)',
                color: draftTrade.direction === 'LONG' ? '#26a69a' : '#ef5350',
              }}
            >
              {draftTrade.direction} POSITION BOX
            </span>

            {draftTrade.parent_bot_ref && (
              <span style={{ fontSize: '10px', color: '#ffd54f', backgroundColor: 'rgba(255, 179, 0, 0.1)', padding: '1px 5px', borderRadius: '3px' }}>
                Cloned from {draftTrade.parent_bot_ref}
              </span>
            )}

            <span>Entry: <b style={{ color: '#ffffff' }}>{draftTrade.entry.toFixed(digits)}</b></span>
            <span>SL: <b style={{ color: '#ef5350' }}>{draftTrade.sl.toFixed(digits)}</b></span>
            <span>TP: <b style={{ color: '#26a69a' }}>{draftTrade.tp.toFixed(digits)}</b></span>
            <span>R:R: <b style={{ color: '#ffd54f' }}>{draftRR.toFixed(2)}R</b></span>

            {/* Risk & Compliance Warning Badge */}
            {draftRiskCheck && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>Risk: <b>${draftRiskCheck.riskUsd.toFixed(2)}</b></span>
                {draftRiskCheck.exceedsRiskCap && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '3px', backgroundColor: 'rgba(255, 179, 0, 0.2)', color: '#ffd54f', padding: '2px 6px', borderRadius: '3px', fontWeight: 600 }}>
                    <AlertTriangle size={11} />
                    ⚠️ Exceeds $20.00 risk cap at 0.01 lot
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Action Buttons: Simulate, Save to Ledger, Cancel */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {/* Simulation Result Preview */}
            {simResult && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '3px', backgroundColor: simResult.status === 'WIN' ? 'rgba(38, 166, 154, 0.2)' : 'rgba(239, 83, 80, 0.2)', color: simResult.status === 'WIN' ? '#26a69a' : '#ef5350', fontWeight: 700 }}>
                {simResult.status === 'WIN' ? <CheckCircle2 size={12} /> : null}
                <span>{simResult.status} ({simResult.rr_realized?.toFixed(2)}R, ${simResult.realized_pnl_usd.toFixed(2)})</span>
              </div>
            )}

            {/* Simulate Button */}
            <button
              onClick={handleSimulateDraft}
              disabled={isSimulating}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                backgroundColor: '#2962ff',
                color: '#ffffff',
                border: 'none',
                borderRadius: '3px',
                padding: '4px 10px',
                fontWeight: 600,
                cursor: isSimulating ? 'not-allowed' : 'pointer',
                opacity: isSimulating ? 0.7 : 1,
              }}
            >
              <Play size={11} />
              {isSimulating ? 'Simulating...' : 'Run Simulation'}
            </button>

            {/* Save to Ledger Button */}
            <button
              onClick={handleSaveDraftToLedger}
              disabled={isSavingTrade}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                backgroundColor: '#00e676',
                color: '#121418',
                border: 'none',
                borderRadius: '3px',
                padding: '4px 10px',
                fontWeight: 700,
                cursor: isSavingTrade ? 'not-allowed' : 'pointer',
                opacity: isSavingTrade ? 0.7 : 1,
              }}
            >
              <Save size={11} />
              {isSavingTrade ? 'Saving...' : 'Save to Ledger'}
            </button>

            {/* Cancel Button */}
            <button
              onClick={() => {
                setDraftTrade(null);
                setSimResult(null);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                background: 'transparent',
                border: '1px solid #565a65',
                color: '#b2b5be',
                borderRadius: '3px',
                padding: '3px 6px',
                cursor: 'pointer',
              }}
            >
              <X size={12} />
            </button>
          </div>
        </div>
      )}

      {/* Main Body: Chart on Left, Workbench on Right */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0, width: '100%', position: 'relative', overflow: 'hidden' }}>
        {/* Main Chart Canvas */}
        <main style={{ flex: 1, minWidth: 0, height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>
          <ReplayChart
            candles={candles}
            symbol={selectedSymbol}
            digits={digits}
            clockMode={clockMode}
            killzones={killzones}
            asianRanges={asianRanges}
            fvgs={fvgs}
            breakers={breakers}
            sweeps={sweeps}
            trades={chartTrades}
            draftTrade={draftTrade}
            onDraftTradeChange={setDraftTrade}
            replayTo={blindReplay ? replayCursor : null}
            showKillzones={showKillzones}
            showAsianRange={showAsianRange}
            showFvgs={showBoxes}
            showBreakers={showBoxes}
            showSweeps={showSweeps}
            showTrades={showTrades}
            onSelectTime={(t) => {
              setInspectedTime(t);
              if (!isDrawerOpen) setIsDrawerOpen(true);
            }}
          />

          {syncNotice && (
            <div
              style={{
                position: 'absolute',
                top: '10px',
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 20,
                backgroundColor: '#1e222d',
                border: '1px solid #f0b90b',
                color: '#ffd54f',
                padding: '5px 12px',
                borderRadius: '6px',
                fontSize: '11px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span>{syncNotice}</span>
              <button
                onClick={() => setSyncNotice(null)}
                style={{ background: 'none', border: 'none', color: '#787b86', cursor: 'pointer', padding: 0 }}
              >
                <X size={12} />
              </button>
            </div>
          )}

          {!isLoadingCandles && candles.length === 0 && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                pointerEvents: 'none',
                zIndex: 15,
              }}
            >
              <div
                style={{
                  pointerEvents: 'auto',
                  backgroundColor: 'rgba(30, 34, 45, 0.94)',
                  border: '1px solid #2a2e39',
                  borderRadius: '8px',
                  padding: '16px 20px',
                  maxWidth: '420px',
                  textAlign: 'center',
                  color: '#d1d4dc',
                  fontSize: '12px',
                }}
              >
                <div style={{ fontWeight: 700, color: '#ffffff', marginBottom: '6px' }}>
                  No cached {selectedSymbol} candles in {startDateStr} → {endDateStr}
                </div>
                {activeSymbolObj?.min_date && activeSymbolObj?.max_date && (
                  <div style={{ color: '#90caf9', marginBottom: '12px', fontSize: '11px' }}>
                    Local Parquet cache covers <b>{activeSymbolObj.min_date}</b> to <b>{activeSymbolObj.max_date}</b>.
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'center', gap: '8px' }}>
                  {activeSymbolObj?.max_date && (
                    <button
                      onClick={() => {
                        const latest = getLatestRangeForSymbol(activeSymbolObj, 3);
                        if (latest) {
                          setStartDateStr(latest.start);
                          setEndDateStr(latest.end);
                        }
                      }}
                      style={{
                        backgroundColor: '#2962ff',
                        border: 'none',
                        borderRadius: '4px',
                        color: '#ffffff',
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '5px 10px',
                        cursor: 'pointer',
                      }}
                    >
                      Load Latest Cached ({activeSymbolObj.max_date})
                    </button>
                  )}
                  <button
                    onClick={handleSyncMt5}
                    disabled={isSyncingMt5}
                    style={{
                      backgroundColor: '#131722',
                      border: '1px solid #2a2e39',
                      borderRadius: '4px',
                      color: '#90caf9',
                      fontSize: '11px',
                      fontWeight: 600,
                      padding: '5px 10px',
                      cursor: isSyncingMt5 ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {isSyncingMt5 ? 'Syncing MT5...' : 'Sync MT5'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>

        {/* Right Workbench Drawer */}
        <aside
          style={{
            width: isDrawerOpen ? '380px' : '36px',
            height: '100%',
            backgroundColor: '#181b24',
            borderLeft: '1px solid #2a2e39',
            display: 'flex',
            flexDirection: 'column',
            transition: 'width 0.2s ease',
            position: 'relative',
            zIndex: 10,
          }}
        >
          {/* Drawer Toggle Button */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: isDrawerOpen ? 'space-between' : 'center',
              padding: '6px 8px',
              backgroundColor: '#1e222d',
              borderBottom: '1px solid #2a2e39',
              minHeight: '34px',
            }}
          >
            {isDrawerOpen ? (
              <div style={{ display: 'flex', gap: '4px' }}>
                <button
                  onClick={() => setActiveTab('bot')}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '4px 8px',
                    fontSize: '11px',
                    fontWeight: activeTab === 'bot' ? 700 : 500,
                    backgroundColor: activeTab === 'bot' ? '#2962ff' : 'transparent',
                    color: activeTab === 'bot' ? '#ffffff' : '#787b86',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  <Bot size={12} />
                  Bot Brain
                </button>
                <button
                  onClick={() => setActiveTab('scorecard')}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '4px 8px',
                    fontSize: '11px',
                    fontWeight: activeTab === 'scorecard' ? 700 : 500,
                    backgroundColor: activeTab === 'scorecard' ? '#2962ff' : 'transparent',
                    color: activeTab === 'scorecard' ? '#ffffff' : '#787b86',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  <Award size={12} />
                  Scorecard
                </button>
                <button
                  onClick={() => setActiveTab('agentify')}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '4px 8px',
                    fontSize: '11px',
                    fontWeight: activeTab === 'agentify' ? 700 : 500,
                    backgroundColor: activeTab === 'agentify' ? '#00e676' : 'transparent',
                    color: activeTab === 'agentify' ? '#121418' : '#787b86',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  <Sparkles size={12} />
                  Agentify
                </button>
              </div>
            ) : null}

            <button
              onClick={() => setIsDrawerOpen(!isDrawerOpen)}
              title={isDrawerOpen ? 'Collapse Drawer' : 'Expand Drawer'}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#787b86',
                cursor: 'pointer',
                padding: '4px',
              }}
            >
              {isDrawerOpen ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            </button>
          </div>

          {/* Drawer Content */}
          {isDrawerOpen && (
            <div style={{ flex: 1, height: 'calc(100% - 34px)', overflow: 'hidden' }}>
              {activeTab === 'bot' && (
                <BotBrainPanel
                  symbol={selectedSymbol}
                  currentTime={activeInspectionTime}
                  diagnostics={diagnostics}
                  events={botEvents}
                  clockMode={clockMode}
                  engineClockMode={engineClockMode}
                  onSelectEventTime={(t) => {
                    setInspectedTime(t);
                    setReplayCursor(t);
                  }}
                  onTriggerFeedback={handleTriggerFeedback}
                />
              )}

              {activeTab === 'scorecard' && (
                <ScorecardPanel
                  trades={allTrades}
                  replayTo={blindReplay ? replayCursor : null}
                  clockMode={clockMode}
                  digits={digits}
                  onCloneTrade={handleCloneTrade}
                  onDeleteTrade={handleDeleteTrade}
                  onSelectTrade={(t) => {
                    setInspectedTime(t.decision_time);
                    setReplayCursor(t.decision_time);
                  }}
                  onTriggerFeedback={(t) => {
                    handleTriggerFeedback({
                      title: `Trade Feedback: ${t.trade_id} (${t.origin}) on ${t.symbol}`,
                      category: t.origin === 'BOT' ? 'BOT_TRADE_EDIT' : 'MISSED_SETUP',
                      rationale: `Trade ${t.trade_id} (${t.direction} @ ${t.entry}):
Realized: ${t.status} (${t.rr_realized}R / $${t.realized_pnl_usd})
Entry: ${t.entry}, SL: ${t.sl}, TP: ${t.tp}`,
                      archetype_id: t.archetype_id,
                      timestamp: t.decision_time,
                    });
                  }}
                />
              )}

              {activeTab === 'agentify' && (
                <AgentifyFeedbackPanel
                  symbol={selectedSymbol}
                  currentTime={activeInspectionTime}
                  clockMode={clockMode}
                  prefillContext={feedbackPrefill}
                />
              )}
            </div>
          )}
        </aside>
      </div>

      {/* Footer Status Bar */}
      <footer
        style={{
          display: 'flex',
          flexShrink: 0,
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 14px',
          borderTop: '1px solid #2a2e39',
          backgroundColor: '#181b24',
          height: '24px',
          fontSize: '11px',
          color: '#787b86',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span>Account: <b style={{ color: '#ffffff' }}>$2,000.00</b> (PROP_FIRM)</span>
          <span>Max Bot Risk: <b style={{ color: '#26a69a' }}>$20.00</b> (1.0%)</span>
          <span>Candles Loaded: <b style={{ color: '#d1d4dc' }}>{candles.length}</b> ({timeframe})</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span>
            Active Bar: <b style={{ color: '#ffd54f' }}>{activeInspectionTime ? formatClockTick(activeInspectionTime, clockMode, true) : 'N/A'}</b>
          </span>
          <span style={{ color: '#26a69a', display: 'flex', alignItems: 'center', gap: '4px' }}>
            ● Server Connected (127.0.0.1:8765)
          </span>
        </div>
      </footer>
    </div>
  );
}

export default App;
