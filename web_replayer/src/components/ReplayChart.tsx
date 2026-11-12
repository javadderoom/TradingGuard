/**
 * TradingGuard HITL Visual Co-Backtester - Interactive Replay Chart Component
 * Built on lightweight-charts v5 with native TradingView independent X/Y axis scaling,
 * custom session killzones, forensic boxes, sweep flags, trade markers, and draggable R:R position handles.
 */

import React, { useEffect, useRef } from 'react';
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';

import type {
  AsianRangeDay,
  BreakerBox,
  Candle,
  ClockMode,
  DraftTrade,
  FvgBox,
  Killzone,
  ReplayTrade,
  SelectedSmcElement,
  SweepFlag,
} from '../types/replay';
import {
  ForensicBoxPrimitive,
  KillzonePrimitive,
  PositionBoxPrimitive,
} from '../chart/primitives';
import {
  buildClusteredTradeMarkers,
  formatClockTick,
  getClusterWindowSeconds,
} from '../utils/coTraderLogic';

export interface ReplayChartProps {
  candles: Candle[];
  symbol?: string;
  digits?: number;
  clockMode?: ClockMode;
  killzones?: Killzone[];
  asianRanges?: Record<string, AsianRangeDay> | AsianRangeDay[];
  fvgs?: FvgBox[];
  breakers?: BreakerBox[];
  sweeps?: SweepFlag[];
  trades?: ReplayTrade[];
  selectedTrade?: ReplayTrade | null;
  selectedElement?: SelectedSmcElement | null;
  draftTrade?: DraftTrade | null;
  onDraftTradeChange?: (draft: DraftTrade) => void;
  onDraftTradeChangeComplete?: (draft: DraftTrade) => void;
  replayTo?: number | null;
  className?: string;
  showKillzones?: boolean;
  showAsianRange?: boolean;
  showFvgs?: boolean;
  showBreakers?: boolean;
  showSweeps?: boolean;
  showTrades?: boolean;
  onSelectTime?: (time: number | null, price?: number | null) => void;
}

export const ReplayChart: React.FC<ReplayChartProps> = ({
  candles,
  symbol = 'XAUUSD_o',
  digits = 2,
  clockMode = 'tehran',
  killzones = [],
  asianRanges = [],
  fvgs = [],
  breakers = [],
  sweeps = [],
  trades = [],
  selectedTrade = null,
  selectedElement = null,
  draftTrade = null,
  onDraftTradeChange,
  onDraftTradeChangeComplete,
  replayTo = null,
  className = '',
  showKillzones = true,
  showAsianRange = true,
  showFvgs = true,
  showBreakers = true,
  showSweeps = true,
  showTrades = true,
  onSelectTime,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick', Time> | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Primitives
  const killzonePrimitiveRef = useRef<KillzonePrimitive | null>(null);
  const forensicPrimitiveRef = useRef<ForensicBoxPrimitive | null>(null);
  const positionBoxPrimitiveRef = useRef<PositionBoxPrimitive | null>(null);

  // Dragging State
  const isDraggingRef = useRef<boolean>(false);
  const dragHandleRef = useRef<'entry' | 'sl' | 'tp' | null>(null);
  const draftTradeRef = useRef<DraftTrade | null>(null);
  const onSelectTimeRef = useRef<((time: number | null, price?: number | null) => void) | undefined>(onSelectTime);

  // Keep draftTradeRef & onSelectTimeRef in sync without updating during render
  useEffect(() => {
    draftTradeRef.current = draftTrade;
  }, [draftTrade]);

  useEffect(() => {
    onSelectTimeRef.current = onSelectTime;
  }, [onSelectTime]);

  // Keep options in sync on mount
  const initialClockModeRef = useRef<ClockMode>(clockMode);
  const initialDigitsRef = useRef<number>(digits);
  const initialKillzonesRef = useRef<Killzone[]>(killzones);

  // Initialize Chart
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth || 800,
      height: containerRef.current.clientHeight || 500,
      layout: {
        background: { type: ColorType.Solid, color: '#131722' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#1e222d' },
        horzLines: { color: '#1e222d' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: '#2b2b43',
        autoScale: true,
      },
      timeScale: {
        borderColor: '#2b2b43',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: Time) => formatClockTick(Number(time), initialClockModeRef.current, false),
      },
      localization: {
        timeFormatter: (time: Time) => formatClockTick(Number(time), initialClockModeRef.current, true),
      },
      // Native TradingView independent X/Y axis scaling and pan
      handleScale: {
        axisPressedMouseMove: { time: true, price: true },
        mouseWheel: true,
        pinch: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      priceFormat: {
        type: 'price',
        precision: initialDigitsRef.current,
        minMove: 1 / Math.pow(10, initialDigitsRef.current),
      },
    });

    // Create & Attach Custom Series Primitives
    const kzPrim = new KillzonePrimitive(initialKillzonesRef.current);
    const boxPrim = new ForensicBoxPrimitive();
    const posPrim = new PositionBoxPrimitive();

    series.attachPrimitive(kzPrim);
    series.attachPrimitive(boxPrim);
    series.attachPrimitive(posPrim);

    chartRef.current = chart;
    seriesRef.current = series;
    killzonePrimitiveRef.current = kzPrim;
    forensicPrimitiveRef.current = boxPrim;
    positionBoxPrimitiveRef.current = posPrim;

    // Click handler for bar & SMC element inspection
    const clickHandler = (param: MouseEventParams<Time>) => {
      if (param.time) {
        const clickedPrice =
          param.point && seriesRef.current
            ? seriesRef.current.coordinateToPrice(param.point.y)
            : null;
        onSelectTimeRef.current?.(
          Number(param.time),
          clickedPrice !== null && !Number.isNaN(Number(clickedPrice)) ? Number(clickedPrice) : null
        );
      }
    };
    chart.subscribeClick(clickHandler);

    // Resize Observer for responsive sizing
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect && chartRef.current) {
          const w = Math.max(100, Math.floor(entry.contentRect.width));
          const h = Math.max(100, Math.floor(entry.contentRect.height));
          chartRef.current.resize(w, h);
        }
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      chart.unsubscribeClick(clickHandler);
      resizeObserver.disconnect();
      if (seriesRef.current) {
        if (kzPrim) seriesRef.current.detachPrimitive(kzPrim);
        if (boxPrim) seriesRef.current.detachPrimitive(boxPrim);
        if (posPrim) seriesRef.current.detachPrimitive(posPrim);
      }
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      markersPluginRef.current = null;
      killzonePrimitiveRef.current = null;
      forensicPrimitiveRef.current = null;
      positionBoxPrimitiveRef.current = null;
    };
  }, []); // Mount once

  // Update Clock Mode & Time Formatter
  useEffect(() => {
    if (!chartRef.current) return;
    chartRef.current.applyOptions({
      timeScale: {
        tickMarkFormatter: (time: Time) => formatClockTick(Number(time), clockMode, false),
      },
      localization: {
        timeFormatter: (time: Time) => formatClockTick(Number(time), clockMode, true),
      },
    });
  }, [clockMode]);

  // Update Candlestick Price Format on Digits Change
  useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.applyOptions({
      priceFormat: {
        type: 'price',
        precision: digits,
        minMove: 1 / Math.pow(10, digits),
      },
    });
  }, [digits]);

  // Update Candlestick Data - ensures clearing when candles or filtered list is empty
  useEffect(() => {
    if (!seriesRef.current) return;
    if (!candles || candles.length === 0) {
      seriesRef.current.setData([]);
      return;
    }

    const formatted = candles
      .filter((c) => (replayTo !== null ? c.time <= replayTo : true))
      .map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));

    if (formatted.length === 0) {
      seriesRef.current.setData([]);
    } else {
      seriesRef.current.setData(formatted);
    }
  }, [candles, replayTo]);

  // Update Killzones with toggle support
  useEffect(() => {
    if (killzonePrimitiveRef.current) {
      killzonePrimitiveRef.current.updateKillzones(showKillzones ? killzones : []);
    }
  }, [killzones, showKillzones]);

  // Update Forensic Boxes (FVGs, Breakers, Asian Range, Sweeps) with toggle support
  useEffect(() => {
    if (forensicPrimitiveRef.current) {
      const arList: AsianRangeDay[] = Array.isArray(asianRanges)
        ? asianRanges
        : Object.values(asianRanges);
      forensicPrimitiveRef.current.updateData({
        fvgs: showFvgs ? fvgs : [],
        breakers: showBreakers ? breakers : [],
        asianRanges: showAsianRange ? arList : [],
        sweeps: showSweeps ? sweeps : [],
        candles,
        selectedTrade,
        selectedElement,
        digits,
      });
    }
  }, [fvgs, breakers, asianRanges, sweeps, candles, selectedTrade, selectedElement, digits, showFvgs, showBreakers, showAsianRange, showSweeps]);

  // Auto-pan chart if a newly selected trade lies outside the visible horizontal range
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !selectedTrade || candles.length === 0) return;
    try {
      const timeScale = chart.timeScale();
      const vis = timeScale.getVisibleRange();
      const t = selectedTrade.fill_time ?? selectedTrade.decision_time;
      if (vis) {
        const from = Number(vis.from);
        const to = Number(vis.to);
        if (t < from || t > to) {
          const halfSpan = Math.max(1800, Math.floor((to - from) / 2));
          const minBound = candles[0].time;
          const maxBound = candles[candles.length - 1].time;
          timeScale.setVisibleRange({
            from: Math.max(minBound, t - halfSpan) as UTCTimestamp,
            to: Math.min(maxBound, t + halfSpan) as UTCTimestamp,
          });
        }
      }
    } catch {
      // Ignore if chart has insufficient data for visible range
    }
  }, [selectedTrade, candles]);

  // Update Position Box Draft Trade
  useEffect(() => {
    if (positionBoxPrimitiveRef.current) {
      positionBoxPrimitiveRef.current.updateDraftTrade(draftTrade, symbol, digits);
    }
  }, [draftTrade, symbol, digits]);

  // Update Trade Markers on Candlesticks with toggle support
  useEffect(() => {
    if (!seriesRef.current) return;

    if (!showTrades) {
      if (markersPluginRef.current) {
        markersPluginRef.current.setMarkers([]);
      }
      return;
    }

    const clusterWindowSec = getClusterWindowSeconds(candles);
    const clustered = buildClusteredTradeMarkers(
      trades,
      replayTo,
      clusterWindowSec,
      selectedTrade?.trade_id ?? null
    );

    const markers: SeriesMarker<Time>[] = clustered.map((m) => ({
      time: m.time as UTCTimestamp,
      position: m.position,
      color: m.color,
      shape: m.shape,
      text: m.text,
    }));

    if (!markersPluginRef.current) {
      markersPluginRef.current = createSeriesMarkers(seriesRef.current, markers);
    } else {
      markersPluginRef.current.setMarkers(markers);
    }
  }, [trades, candles, replayTo, showTrades, selectedTrade?.trade_id]);

  // Mouse Interaction: Dragging Entry, SL, and TP handles
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleMouseMove = (e: MouseEvent) => {
      const series = seriesRef.current;
      const chart = chartRef.current;
      const draft = draftTradeRef.current;
      if (!series || !chart || !draft) {
        container.style.cursor = 'default';
        positionBoxPrimitiveRef.current?.setHoveredHandle(null);
        return;
      }

      const rect = container.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      if (isDraggingRef.current && dragHandleRef.current) {
        // Dragging in progress: calculate new price from coordinate
        const newPrice = series.coordinateToPrice(mouseY);
        if (newPrice !== null && !isNaN(newPrice)) {
          const rounded = Number(newPrice.toFixed(digits));
          const updated: DraftTrade = {
            ...draft,
            [dragHandleRef.current]: rounded,
          };
          onDraftTradeChange?.(updated);
        }
        return;
      }

      // Constrain hit testing: Never intercept mouse inside right price scale!
      const priceScaleWidth = Math.max(55, chart.priceScale('right')?.width() ?? 65);
      const rightBoundary = container.clientWidth - priceScaleWidth;
      if (mouseX >= rightBoundary) {
        container.style.cursor = 'default';
        positionBoxPrimitiveRef.current?.setHoveredHandle(null);
        return;
      }

      // Constrain hit testing horizontally to position box X-span: [boxLeft - 15, rightBoundary - 5]
      const timeScale = chart.timeScale();
      const xSignal = draft.signal_time
        ? timeScale.timeToCoordinate(draft.signal_time as UTCTimestamp)
        : null;
      const boxLeft = Math.max(0, xSignal !== null ? Number(xSignal) : chart.timeScale().width() * 0.4);

      const isWithinBoxX = mouseX >= Math.max(0, boxLeft - 15) && mouseX <= rightBoundary - 5;
      if (!isWithinBoxX) {
        container.style.cursor = 'default';
        positionBoxPrimitiveRef.current?.setHoveredHandle(null);
        return;
      }

      // Vertical Hover Hit Detection (within 8px of price lines)
      const entryY = series.priceToCoordinate(draft.entry);
      const slY = series.priceToCoordinate(draft.sl);
      const tpY = series.priceToCoordinate(draft.tp);

      let targetHandle: 'entry' | 'sl' | 'tp' | null = null;
      if (entryY !== null && Math.abs(mouseY - Number(entryY)) <= 8) {
        targetHandle = 'entry';
      } else if (slY !== null && Math.abs(mouseY - Number(slY)) <= 8) {
        targetHandle = 'sl';
      } else if (tpY !== null && Math.abs(mouseY - Number(tpY)) <= 8) {
        targetHandle = 'tp';
      }

      if (targetHandle) {
        container.style.cursor = 'ns-resize';
      } else {
        container.style.cursor = 'crosshair';
      }
      positionBoxPrimitiveRef.current?.setHoveredHandle(targetHandle);
    };

    const handleMouseDown = (e: MouseEvent) => {
      const series = seriesRef.current;
      const chart = chartRef.current;
      const draft = draftTradeRef.current;
      if (!series || !chart || !draft) return;

      const rect = container.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // Price scale boundary check: allow native price scale drag!
      const priceScaleWidth = Math.max(55, chart.priceScale('right')?.width() ?? 65);
      const rightBoundary = container.clientWidth - priceScaleWidth;
      if (mouseX >= rightBoundary) return;

      // Box horizontal boundary check: allow native chart pan!
      const timeScale = chart.timeScale();
      const xSignal = draft.signal_time
        ? timeScale.timeToCoordinate(draft.signal_time as UTCTimestamp)
        : null;
      const boxLeft = Math.max(0, xSignal !== null ? Number(xSignal) : chart.timeScale().width() * 0.4);

      const isWithinBoxX = mouseX >= Math.max(0, boxLeft - 15) && mouseX <= rightBoundary - 5;
      if (!isWithinBoxX) return;

      const entryY = series.priceToCoordinate(draft.entry);
      const slY = series.priceToCoordinate(draft.sl);
      const tpY = series.priceToCoordinate(draft.tp);

      let targetHandle: 'entry' | 'sl' | 'tp' | null = null;
      if (entryY !== null && Math.abs(mouseY - Number(entryY)) <= 8) {
        targetHandle = 'entry';
      } else if (slY !== null && Math.abs(mouseY - Number(slY)) <= 8) {
        targetHandle = 'sl';
      } else if (tpY !== null && Math.abs(mouseY - Number(tpY)) <= 8) {
        targetHandle = 'tp';
      }

      if (targetHandle) {
        isDraggingRef.current = true;
        dragHandleRef.current = targetHandle;
        positionBoxPrimitiveRef.current?.setHoveredHandle(targetHandle, true);

        // Smoothly freeze chart pan & scale while dragging handles
        chart.applyOptions({
          handleScroll: false,
          handleScale: false,
        });

        e.preventDefault();
        e.stopPropagation();
      }
    };

    const handleMouseUp = () => {
      if (isDraggingRef.current) {
        isDraggingRef.current = false;
        dragHandleRef.current = null;
        positionBoxPrimitiveRef.current?.setHoveredHandle(null, false);

        // Re-enable chart pan & scale
        chartRef.current?.applyOptions({
          handleScroll: true,
          handleScale: {
            axisPressedMouseMove: { time: true, price: true },
            mouseWheel: true,
            pinch: true,
          },
        });

        if (draftTradeRef.current) {
          onDraftTradeChangeComplete?.(draftTradeRef.current);
        }
      }
    };

    container.addEventListener('mousemove', handleMouseMove);
    container.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      container.removeEventListener('mousemove', handleMouseMove);
      container.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [digits, onDraftTradeChange, onDraftTradeChangeComplete]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '300px',
        overflow: 'hidden',
        userSelect: 'none',
        touchAction: 'none',
      }}
    />
  );
};

export default ReplayChart;
