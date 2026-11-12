/**
 * TradingGuard HITL Visual Co-Backtester - Custom Series Primitives (lightweight-charts v5)
 * Implements:
 * 1. KillzonePrimitive: Vertical Session Killzone shading (Asian, London Open, NY Open)
 * 2. ForensicBoxPrimitive: Asian range bounds, FVG boxes, Breaker Block rectangles, and Sweep Flags
 * 3. PositionBoxPrimitive: Shaded Red/Green R:R zones with draggable Entry/SL/TP handles
 */

import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  IChartApiBase,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';
import type {
  AsianRangeDay,
  BreakerBox,
  Candle,
  DraftTrade,
  FvgBox,
  Killzone,
  ReplayTrade,
  SweepFlag,
} from '../types/replay';
import {
  checkRiskLimitUSD,
  computeTradeRR,
} from '../utils/coTraderLogic';

/**
 * Resolves a timestamp into an X pixel coordinate on the time scale.
 * If the exact timestamp does not match a bar on the active timeframe (e.g. 5M marks on 15M/1H),
 * it performs a binary search on the loaded candles to map to the enclosing visible bar.
 */
function resolveTimeX(
  timeScale: ReturnType<IChartApiBase<Time>['timeScale']>,
  timestamp: number,
  candles?: Candle[]
): number | null {
  const direct = timeScale.timeToCoordinate(timestamp as UTCTimestamp);
  if (direct !== null) return Number(direct);

  if (candles && candles.length > 0) {
    if (timestamp < candles[0].time) {
      return null;
    }
    if (timestamp > candles[candles.length - 1].time) {
      const lastX = timeScale.timeToCoordinate(candles[candles.length - 1].time as UTCTimestamp);
      return lastX !== null ? Number(lastX) + 20 : null;
    }

    let low = 0;
    let high = candles.length - 1;
    let best = 0;
    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      if (candles[mid].time <= timestamp) {
        best = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }
    const barCoord = timeScale.timeToCoordinate(candles[best].time as UTCTimestamp);
    if (barCoord !== null) return Number(barCoord);
  }

  return null;
}

/* =========================================================================
   1. KILLZONE PRIMITIVE
   ========================================================================= */

interface KillzoneParams {
  chart: IChartApiBase<Time> | null;
  killzones: Killzone[];
}

class KillzonePaneRenderer implements IPrimitivePaneRenderer {
  private _getParams: () => KillzoneParams;

  constructor(getParams: () => KillzoneParams) {
    this._getParams = getParams;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const { chart, killzones } = this._getParams();
      if (!chart || !killzones.length) return;

      const timeScale = chart.timeScale();
      const ctx = scope.context;
      const { width, height } = scope.mediaSize;

      for (const kz of killzones) {
        const x1 = timeScale.timeToCoordinate(kz.start_time as UTCTimestamp);
        const x2 = timeScale.timeToCoordinate(kz.end_time as UTCTimestamp);

        let left: number | null = x1 !== null ? Number(x1) : null;
        let right: number | null = x2 !== null ? Number(x2) : null;

        if (left === null && right === null) continue;
        if (left === null && right !== null) left = 0;
        if (left !== null && right === null) right = width;
        if (left === null || right === null) continue;

        if (right < 0 || left > width) continue;

        const renderLeft = Math.max(0, left);
        const renderRight = Math.min(width, right);
        const renderWidth = Math.max(2, renderRight - renderLeft);

        // Fill Killzone shading
        ctx.fillStyle = kz.color;
        ctx.fillRect(renderLeft, 0, renderWidth, height);

        // Top Session Badge
        if (renderLeft < width - 60) {
          ctx.save();
          ctx.fillStyle = 'rgba(255, 255, 255, 0.75)';
          ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
          ctx.fillText(kz.name, renderLeft + 6, 14);
          ctx.restore();
        }
      }
    });
  }
}

export class KillzonePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _killzones: Killzone[] = [];
  private _requestUpdate: (() => void) | null = null;
  private _paneView: IPrimitivePaneView;

  constructor(killzones: Killzone[] = []) {
    this._killzones = killzones;
    const renderer = new KillzonePaneRenderer(() => ({
      chart: this._chart,
      killzones: this._killzones,
    }));

    this._paneView = {
      zOrder: (): PrimitivePaneViewZOrder => 'bottom',
      renderer: () => renderer,
    };
  }

  updateKillzones(killzones: Killzone[]): void {
    this._killzones = killzones;
    this._requestUpdate?.();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this._chart = param.chart;
    this._requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this._chart = null;
    this._requestUpdate = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this._paneView];
  }
}

/* =========================================================================
   2. FORENSIC BOX PRIMITIVE (FVG, Breakers, Asian Range Lines, Sweep Flags)
   ========================================================================= */

interface ForensicBoxParams {
  chart: IChartApiBase<Time> | null;
  series: ISeriesApi<SeriesType, Time> | null;
  fvgs: FvgBox[];
  breakers: BreakerBox[];
  asianRanges: AsianRangeDay[];
  sweeps: SweepFlag[];
  candles: Candle[];
  selectedTrade: ReplayTrade | null;
  digits: number;
}

class ForensicBoxPaneRenderer implements IPrimitivePaneRenderer {
  private _getParams: () => ForensicBoxParams;

  constructor(getParams: () => ForensicBoxParams) {
    this._getParams = getParams;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const { chart, series, fvgs, breakers, asianRanges, sweeps, candles, selectedTrade, digits } = this._getParams();
      if (!chart || !series) return;

      const timeScale = chart.timeScale();
      const ctx = scope.context;
      const { width, height } = scope.mediaSize;

      interface LabelRect {
        x1: number;
        y1: number;
        x2: number;
        y2: number;
      }
      const occupiedLabels: LabelRect[] = [];

      const collides = (r: LabelRect): boolean =>
        occupiedLabels.some(
          (o) => r.x1 < o.x2 + 2 && r.x2 + 2 > o.x1 && r.y1 < o.y2 + 2 && r.y2 + 2 > o.y1
        );

      const drawZonePill = (
        text: string,
        x: number,
        y: number,
        textColor: string,
        borderColor: string
      ): void => {
        ctx.font = 'bold 9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        const pillW = Math.ceil(ctx.measureText(text).width) + 8;
        const pillH = 13;
        const pillX = Math.max(2, Math.min(width - pillW - 2, x));
        const pillY = Math.max(2, Math.min(height - pillH - 2, y));
        const rect: LabelRect = { x1: pillX, y1: pillY, x2: pillX + pillW, y2: pillY + pillH };
        if (collides(rect)) return;
        occupiedLabels.push(rect);

        ctx.fillStyle = 'rgba(19, 23, 34, 0.88)';
        ctx.fillRect(pillX, pillY, pillW, pillH);
        ctx.strokeStyle = borderColor;
        ctx.lineWidth = 1;
        ctx.strokeRect(pillX, pillY, pillW, pillH);
        ctx.fillStyle = textColor;
        ctx.fillText(text, pillX + 4, pillY + 9.5);
      };

      // 1. Asian Range High/Low lines
      for (const ar of asianRanges) {
        const yHigh = series.priceToCoordinate(ar.high);
        const yLow = series.priceToCoordinate(ar.low);

        const xStart = resolveTimeX(timeScale, ar.start_time, candles);
        const xEnd = resolveTimeX(timeScale, ar.end_time, candles);

        // Strict off-screen guard: skip if unmapped or out of visible viewport
        if (xStart === null && xEnd === null) continue;

        const left = xStart !== null ? xStart : 0;
        const right = xEnd !== null ? xEnd : width;

        if (right < 0 || left > width) continue;

        const renderLeft = Math.max(0, left);
        const renderRight = Math.min(width, right);
        if (renderRight <= renderLeft) continue;

        if (yHigh !== null && yHigh >= 0) {
          ctx.save();
          ctx.strokeStyle = 'rgba(240, 185, 11, 0.7)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(renderLeft, Number(yHigh));
          ctx.lineTo(renderRight, Number(yHigh));
          ctx.stroke();

          ctx.fillStyle = 'rgba(240, 185, 11, 0.9)';
          ctx.font = '9px monospace';
          ctx.fillText(`Asian High: ${ar.high}`, Math.min(width - 110, renderLeft + 4), Number(yHigh) - 3);
          ctx.restore();
        }

        if (yLow !== null && yLow >= 0) {
          ctx.save();
          ctx.strokeStyle = 'rgba(240, 185, 11, 0.7)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(renderLeft, Number(yLow));
          ctx.lineTo(renderRight, Number(yLow));
          ctx.stroke();

          ctx.fillStyle = 'rgba(240, 185, 11, 0.9)';
          ctx.font = '9px monospace';
          ctx.fillText(`Asian Low: ${ar.low}`, Math.min(width - 110, renderLeft + 4), Number(yLow) + 10);
          ctx.restore();
        }
      }

      // 2. Fair Value Gap (FVG) Rectangles
      for (const fvg of fvgs) {
        const yTop = series.priceToCoordinate(fvg.top);
        const yBottom = series.priceToCoordinate(fvg.bottom);
        if (yTop === null || yBottom === null) continue;

        const xStart = resolveTimeX(timeScale, fvg.t_start, candles);
        const xEnd = resolveTimeX(timeScale, fvg.t_end, candles);

        // Strict off-screen guard
        if (xStart === null && xEnd === null) continue;

        const left = xStart !== null ? xStart : 0;
        const right = xEnd !== null ? xEnd : width;

        if (right < 0 || left > width) continue;

        const renderLeft = Math.max(0, left);
        const renderRight = Math.min(width, right);
        if (renderRight <= renderLeft) continue;

        const boxTop = Math.min(Number(yTop), Number(yBottom));
        const boxHeight = Math.max(3, Math.abs(Number(yBottom) - Number(yTop)));
        const boxWidth = Math.max(6, renderRight - renderLeft);

        const isBull = fvg.dir === 'BULLISH';
        const strokeColor = isBull ? 'rgba(38, 166, 154, 0.72)' : 'rgba(239, 83, 80, 0.72)';
        const textColor = isBull ? '#4dd0e1' : '#ff8a80';

        ctx.save();
        ctx.fillStyle = isBull ? 'rgba(38, 166, 154, 0.12)' : 'rgba(239, 83, 80, 0.12)';
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
        ctx.fillRect(renderLeft, boxTop, boxWidth, boxHeight);
        ctx.strokeRect(renderLeft, boxTop, boxWidth, boxHeight);
        ctx.setLineDash([]);

        if (boxWidth >= 18) {
          const labelY = boxTop >= 18 ? boxTop - 15 : boxTop + 2;
          drawZonePill(isBull ? '+FVG' : '-FVG', renderLeft, labelY, textColor, strokeColor);
        }
        ctx.restore();
      }

      // 3. Breaker Block Rectangles
      for (const brk of breakers) {
        const yTop = series.priceToCoordinate(brk.top);
        const yBottom = series.priceToCoordinate(brk.bottom);
        if (yTop === null || yBottom === null) continue;

        const xStart = resolveTimeX(timeScale, brk.t_start, candles);
        const xEnd = resolveTimeX(timeScale, brk.t_end, candles);

        // Strict off-screen guard
        if (xStart === null && xEnd === null) continue;

        const left = xStart !== null ? xStart : 0;
        const right = xEnd !== null ? xEnd : width;

        if (right < 0 || left > width) continue;

        const renderLeft = Math.max(0, left);
        const renderRight = Math.min(width, right);
        if (renderRight <= renderLeft) continue;

        const boxTop = Math.min(Number(yTop), Number(yBottom));
        const boxHeight = Math.max(3, Math.abs(Number(yBottom) - Number(yTop)));
        const boxWidth = Math.max(6, renderRight - renderLeft);

        const isBull = brk.type.toUpperCase().includes('BULLISH');
        const brkStroke = 'rgba(206, 147, 216, 0.85)';

        ctx.save();
        ctx.fillStyle = 'rgba(171, 71, 188, 0.14)';
        ctx.strokeStyle = brkStroke;
        ctx.lineWidth = 1.25;
        ctx.fillRect(renderLeft, boxTop, boxWidth, boxHeight);
        ctx.strokeRect(renderLeft, boxTop, boxWidth, boxHeight);

        if (boxWidth >= 18) {
          const labelY = boxTop >= 18 ? boxTop - 15 : boxTop + 2;
          drawZonePill(isBull ? '+BRK' : '-BRK', renderLeft, labelY, '#e1bee7', brkStroke);
        }
        ctx.restore();
      }

      // 4. Sweep Flags & Badges
      for (const sweep of sweeps) {
        const x = resolveTimeX(timeScale, sweep.time, candles);
        const y = series.priceToCoordinate(sweep.price);
        if (x === null || y === null) continue;
        if (x < -20 || x > width + 20) continue;

        const isHighSweep = sweep.type === 'HIGH_SWEEP';
        ctx.save();

        // Pin / arrow indicator at the exact wick
        ctx.fillStyle = isHighSweep ? '#ffb300' : '#ffa726';
        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 1;

        ctx.beginPath();
        if (isHighSweep) {
          ctx.moveTo(x, Number(y) - 2);
          ctx.lineTo(x - 4, Number(y) - 8);
          ctx.lineTo(x + 4, Number(y) - 8);
        } else {
          ctx.moveTo(x, Number(y) + 2);
          ctx.lineTo(x - 4, Number(y) + 8);
          ctx.lineTo(x + 4, Number(y) + 8);
        }
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Badge label with collision avoidance
        ctx.font = 'bold 9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        const labelText = isHighSweep ? 'High Sweep' : 'Low Sweep';
        const badgeW = Math.ceil(ctx.measureText(labelText).width) + 10;
        const badgeH = 15;
        const badgeX = Math.max(2, Math.min(width - badgeW - 2, x - badgeW / 2));
        let badgeY = isHighSweep ? Number(y) - 10 - badgeH : Number(y) + 10;
        const step = isHighSweep ? -(badgeH + 3) : badgeH + 3;
        for (let attempt = 0; attempt < 3; attempt++) {
          const candidate: LabelRect = {
            x1: badgeX,
            y1: badgeY,
            x2: badgeX + badgeW,
            y2: badgeY + badgeH,
          };
          if (!collides(candidate)) {
            occupiedLabels.push(candidate);
            ctx.fillStyle = isHighSweep ? 'rgba(255, 179, 0, 0.92)' : 'rgba(255, 167, 38, 0.92)';
            ctx.fillRect(badgeX, badgeY, badgeW, badgeH);
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.45)';
            ctx.strokeRect(badgeX, badgeY, badgeW, badgeH);

            ctx.fillStyle = '#131722';
            ctx.fillText(labelText, badgeX + 5, badgeY + 11);
            break;
          }
          badgeY += step;
        }
        ctx.restore();
      }

      // 5. Selected Trade Read-Only Inspection Box (Entry / SL / TP)
      if (selectedTrade) {
        const yEntry = series.priceToCoordinate(selectedTrade.entry);
        const ySl = series.priceToCoordinate(selectedTrade.sl);
        const yTp = series.priceToCoordinate(selectedTrade.tp);
        if (yEntry !== null && ySl !== null && yTp !== null) {
          const tStart = selectedTrade.fill_time ?? selectedTrade.decision_time;
          const fallbackEnd =
            candles.length > 0 ? candles[candles.length - 1].time : tStart + 3600;
          const tEnd =
            selectedTrade.exit_time &&
            selectedTrade.status !== 'OPEN' &&
            selectedTrade.status !== 'PENDING'
              ? selectedTrade.exit_time
              : Math.max(fallbackEnd, tStart + 1800);

          const xStart = resolveTimeX(timeScale, tStart, candles);
          const xEnd = resolveTimeX(timeScale, tEnd, candles);
          if (xStart !== null || xEnd !== null) {
            const left = xStart !== null ? xStart : 0;
            const right = xEnd !== null ? xEnd : width;
            if (right >= 0 && left <= width) {
              const renderLeft = Math.max(0, left);
              const renderRight = Math.min(width, Math.max(left + 32, right));
              const boxW = Math.max(24, renderRight - renderLeft);

              const entryY = Number(yEntry);
              const slY = Number(ySl);
              const tpY = Number(yTp);

              ctx.save();
              // Reward shade (Entry -> TP)
              const tpTop = Math.min(entryY, tpY);
              const tpH = Math.max(2, Math.abs(tpY - entryY));
              ctx.fillStyle = 'rgba(38, 166, 154, 0.14)';
              ctx.fillRect(renderLeft, tpTop, boxW, tpH);

              // Risk shade (Entry -> SL)
              const slTop = Math.min(entryY, slY);
              const slH = Math.max(2, Math.abs(slY - entryY));
              ctx.fillStyle = 'rgba(239, 83, 80, 0.14)';
              ctx.fillRect(renderLeft, slTop, boxW, slH);

              // Outer highlight border
              const outerTop = Math.min(entryY, slY, tpY);
              const outerBottom = Math.max(entryY, slY, tpY);
              ctx.strokeStyle = 'rgba(240, 185, 11, 0.85)';
              ctx.lineWidth = 1.5;
              ctx.setLineDash([5, 3]);
              ctx.strokeRect(renderLeft, outerTop, boxW, Math.max(4, outerBottom - outerTop));
              ctx.setLineDash([]);

              // Entry / SL / TP boundary lines & pills
              const lines = [
                { y: entryY, color: '#f0b90b', label: `ENTRY ${selectedTrade.entry.toFixed(digits)}` },
                { y: slY, color: '#ef5350', label: `SL ${selectedTrade.sl.toFixed(digits)}` },
                { y: tpY, color: '#26a69a', label: `TP ${selectedTrade.tp.toFixed(digits)}` },
              ];
              for (const ln of lines) {
                ctx.strokeStyle = ln.color;
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(renderLeft, ln.y);
                ctx.lineTo(renderLeft + boxW, ln.y);
                ctx.stroke();
                drawZonePill(ln.label, renderLeft + 4, ln.y - 14, ln.color, ln.color);
              }
              ctx.restore();
            }
          }
        }
      }
    });
  }
}

export class ForensicBoxPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _fvgs: FvgBox[] = [];
  private _breakers: BreakerBox[] = [];
  private _asianRanges: AsianRangeDay[] = [];
  private _sweeps: SweepFlag[] = [];
  private _candles: Candle[] = [];
  private _selectedTrade: ReplayTrade | null = null;
  private _digits: number = 2;
  private _paneView: IPrimitivePaneView;

  constructor() {
    const renderer = new ForensicBoxPaneRenderer(() => ({
      chart: this._chart,
      series: this._series,
      fvgs: this._fvgs,
      breakers: this._breakers,
      asianRanges: this._asianRanges,
      sweeps: this._sweeps,
      candles: this._candles,
      selectedTrade: this._selectedTrade,
      digits: this._digits,
    }));

    this._paneView = {
      zOrder: (): PrimitivePaneViewZOrder => 'bottom',
      renderer: () => renderer,
    };
  }

  updateData(params: {
    fvgs?: FvgBox[];
    breakers?: BreakerBox[];
    asianRanges?: AsianRangeDay[];
    sweeps?: SweepFlag[];
    candles?: Candle[];
    selectedTrade?: ReplayTrade | null;
    digits?: number;
  }): void {
    if (params.fvgs !== undefined) this._fvgs = params.fvgs;
    if (params.breakers !== undefined) this._breakers = params.breakers;
    if (params.asianRanges !== undefined) this._asianRanges = params.asianRanges;
    if (params.sweeps !== undefined) this._sweeps = params.sweeps;
    if (params.candles !== undefined) this._candles = params.candles;
    if (params.selectedTrade !== undefined) this._selectedTrade = params.selectedTrade;
    if (params.digits !== undefined) this._digits = params.digits;
    this._requestUpdate?.();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this._paneView];
  }
}

/* =========================================================================
   3. POSITION R:R BOX PRIMITIVE (Interactive Draggable Handles)
   ========================================================================= */

interface PositionBoxParams {
  chart: IChartApiBase<Time> | null;
  series: ISeriesApi<SeriesType, Time> | null;
  draftTrade: DraftTrade | null;
  symbol: string;
  digits: number;
  hoveredHandle: 'entry' | 'sl' | 'tp' | null;
  isDragging: boolean;
}

class PositionBoxPaneRenderer implements IPrimitivePaneRenderer {
  private _getParams: () => PositionBoxParams;

  constructor(getParams: () => PositionBoxParams) {
    this._getParams = getParams;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const { chart, series, draftTrade, symbol, digits, hoveredHandle, isDragging } =
        this._getParams();
      if (!chart || !series || !draftTrade) return;

      const timeScale = chart.timeScale();
      const ctx = scope.context;
      const { width } = scope.mediaSize;

      const coordEntry = series.priceToCoordinate(draftTrade.entry);
      const coordSl = series.priceToCoordinate(draftTrade.sl);
      const coordTp = series.priceToCoordinate(draftTrade.tp);

      if (coordEntry === null || coordSl === null || coordTp === null) return;

      const entryY = Number(coordEntry);
      const slY = Number(coordSl);
      const tpY = Number(coordTp);

      const xSignal = draftTrade.signal_time
        ? timeScale.timeToCoordinate(draftTrade.signal_time as UTCTimestamp)
        : null;

      const left = Math.max(0, xSignal !== null ? Number(xSignal) : width * 0.4);
      // Main chart width without price scale
      const priceScaleWidth = Math.max(55, chart.priceScale('right')?.width() ?? 65);
      const right = width - priceScaleWidth;
      const boxWidth = Math.max(60, right - left);

      const isLong = draftTrade.direction === 'LONG';
      const rr = computeTradeRR(draftTrade.entry, draftTrade.sl, draftTrade.tp, draftTrade.direction);
      const riskCheck = checkRiskLimitUSD(symbol, draftTrade.entry, draftTrade.sl, 0.01, 20.0);
      const rewardPts = Math.abs(draftTrade.tp - draftTrade.entry);
      const rewardUsd = Number((rewardPts * riskCheck.pipVal).toFixed(2));

      // 1. Shaded Risk Zone (Red)
      const riskTop = Math.min(entryY, slY);
      const riskHeight = Math.max(1, Math.abs(entryY - slY));
      ctx.save();
      ctx.fillStyle = 'rgba(239, 83, 80, 0.22)';
      ctx.fillRect(left, riskTop, boxWidth, riskHeight);
      ctx.strokeStyle = 'rgba(239, 83, 80, 0.6)';
      ctx.strokeRect(left, riskTop, boxWidth, riskHeight);
      ctx.restore();

      // 2. Shaded Reward Zone (Green)
      const rewardTop = Math.min(entryY, tpY);
      const rewardHeight = Math.max(1, Math.abs(entryY - tpY));
      ctx.save();
      ctx.fillStyle = 'rgba(38, 166, 154, 0.22)';
      ctx.fillRect(left, rewardTop, boxWidth, rewardHeight);
      ctx.strokeStyle = 'rgba(38, 166, 154, 0.6)';
      ctx.strokeRect(left, rewardTop, boxWidth, rewardHeight);
      ctx.restore();

      // Horizontal Lines
      const drawPriceLine = (
        y: number,
        color: string,
        label: string,
        badgeBg: string,
        handleType: 'entry' | 'sl' | 'tp'
      ) => {
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.stroke();

        // Interactive Drag Handle Circle
        const handleX = left + 20;
        const isTarget = hoveredHandle === handleType || (isDragging && hoveredHandle === handleType);
        ctx.fillStyle = isTarget ? '#ffffff' : color;
        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(handleX, y, isTarget ? 6 : 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // Right Badge Pill (constrained to main canvas, inside chart area)
        ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace';
        const metrics = ctx.measureText(label);
        const badgeW = metrics.width + 12;
        const badgeH = 18;
        const badgeX = Math.max(left + 50, right - badgeW - 6);
        const badgeY = y - badgeH / 2;

        ctx.fillStyle = badgeBg;
        ctx.fillRect(badgeX, badgeY, badgeW, badgeH);
        ctx.strokeStyle = color;
        ctx.strokeRect(badgeX, badgeY, badgeW, badgeH);

        ctx.fillStyle = '#ffffff';
        ctx.fillText(label, badgeX + 6, badgeY + 13);
        ctx.restore();
      };

      // Draw Lines & Badges
      const dirTag = isLong ? 'LONG' : 'SHORT';
      drawPriceLine(
        entryY,
        '#2962ff',
        `Entry (${dirTag}): ${draftTrade.entry.toFixed(digits)}`,
        '#1a237e',
        'entry'
      );

      const slWarning = riskCheck.exceedsRiskCap ? ' ⚠️ >$20 Risk' : '';
      drawPriceLine(
        slY,
        '#ef5350',
        `SL: ${draftTrade.sl.toFixed(digits)} (-$${riskCheck.riskUsd.toFixed(2)})${slWarning}`,
        '#b71c1c',
        'sl'
      );

      drawPriceLine(
        tpY,
        '#26a69a',
        `TP: ${draftTrade.tp.toFixed(digits)} (+$${rewardUsd.toFixed(2)} | ${rr.toFixed(2)}R)`,
        '#004d40',
        'tp'
      );
    });
  }
}

export class PositionBoxPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _draftTrade: DraftTrade | null = null;
  private _symbol: string = 'XAUUSD_o';
  private _digits: number = 2;
  private _hoveredHandle: 'entry' | 'sl' | 'tp' | null = null;
  private _isDragging: boolean = false;
  private _paneView: IPrimitivePaneView;

  constructor() {
    const renderer = new PositionBoxPaneRenderer(() => ({
      chart: this._chart,
      series: this._series,
      draftTrade: this._draftTrade,
      symbol: this._symbol,
      digits: this._digits,
      hoveredHandle: this._hoveredHandle,
      isDragging: this._isDragging,
    }));

    this._paneView = {
      zOrder: (): PrimitivePaneViewZOrder => 'top',
      renderer: () => renderer,
    };
  }

  updateDraftTrade(
    trade: DraftTrade | null,
    symbol: string = 'XAUUSD_o',
    digits: number = 2
  ): void {
    this._draftTrade = trade;
    this._symbol = symbol;
    this._digits = digits;
    this._requestUpdate?.();
  }

  setHoveredHandle(handle: 'entry' | 'sl' | 'tp' | null, isDragging: boolean = false): void {
    this._hoveredHandle = handle;
    this._isDragging = isDragging;
    this._requestUpdate?.();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this._paneView];
  }

  getSeries(): ISeriesApi<SeriesType, Time> | null {
    return this._series;
  }

  getChart(): IChartApiBase<Time> | null {
    return this._chart;
  }
}
