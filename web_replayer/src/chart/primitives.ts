/**
 * TradingGuard HITL Visual Co-Backtester - Custom Series Primitives (lightweight-charts v5)
 * Implements:
 * 1. KillzonePrimitive: Vertical Session Killzone shading (Asian, London Open, NY Open)
 * 2. ForensicBoxPrimitive: Asian range bounds, FVG boxes, and Breaker Block rectangles
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
  DraftTrade,
  FvgBox,
  Killzone,
} from '../types/replay';
import {
  checkRiskLimitUSD,
  computeTradeRR,
} from '../utils/coTraderLogic';

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
   2. FORENSIC BOX PRIMITIVE (FVG, Breakers, Asian Range Lines)
   ========================================================================= */

interface ForensicBoxParams {
  chart: IChartApiBase<Time> | null;
  series: ISeriesApi<SeriesType, Time> | null;
  fvgs: FvgBox[];
  breakers: BreakerBox[];
  asianRanges: AsianRangeDay[];
}

class ForensicBoxPaneRenderer implements IPrimitivePaneRenderer {
  private _getParams: () => ForensicBoxParams;

  constructor(getParams: () => ForensicBoxParams) {
    this._getParams = getParams;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const { chart, series, fvgs, breakers, asianRanges } = this._getParams();
      if (!chart || !series) return;

      const timeScale = chart.timeScale();
      const ctx = scope.context;
      const { width } = scope.mediaSize;

      // 1. Asian Range High/Low lines
      for (const ar of asianRanges) {
        const yHigh = series.priceToCoordinate(ar.high);
        const yLow = series.priceToCoordinate(ar.low);
        const xStart = timeScale.timeToCoordinate(ar.start_time as UTCTimestamp);
        const xEnd = timeScale.timeToCoordinate(ar.end_time as UTCTimestamp);

        const left = xStart !== null ? Number(xStart) : 0;
        const right = xEnd !== null ? Number(xEnd) : width;

        if (yHigh !== null && yHigh >= 0) {
          ctx.save();
          ctx.strokeStyle = 'rgba(240, 185, 11, 0.7)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(left, Number(yHigh));
          ctx.lineTo(right, Number(yHigh));
          ctx.stroke();

          ctx.fillStyle = 'rgba(240, 185, 11, 0.9)';
          ctx.font = '9px monospace';
          ctx.fillText(`Asian High: ${ar.high}`, Math.min(width - 110, left + 4), Number(yHigh) - 3);
          ctx.restore();
        }

        if (yLow !== null && yLow >= 0) {
          ctx.save();
          ctx.strokeStyle = 'rgba(240, 185, 11, 0.7)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(left, Number(yLow));
          ctx.lineTo(right, Number(yLow));
          ctx.stroke();

          ctx.fillStyle = 'rgba(240, 185, 11, 0.9)';
          ctx.font = '9px monospace';
          ctx.fillText(`Asian Low: ${ar.low}`, Math.min(width - 110, left + 4), Number(yLow) + 10);
          ctx.restore();
        }
      }

      // 2. Fair Value Gap (FVG) Rectangles
      for (const fvg of fvgs) {
        const yTop = series.priceToCoordinate(fvg.top);
        const yBottom = series.priceToCoordinate(fvg.bottom);
        const xStart = timeScale.timeToCoordinate(fvg.t_start as UTCTimestamp);
        const xEnd = timeScale.timeToCoordinate(fvg.t_end as UTCTimestamp);

        if (yTop === null || yBottom === null) continue;
        const left = xStart !== null ? Number(xStart) : 0;
        const right = xEnd !== null ? Number(xEnd) : width;
        const boxTop = Math.min(Number(yTop), Number(yBottom));
        const boxHeight = Math.max(2, Math.abs(Number(yBottom) - Number(yTop)));
        const boxWidth = Math.max(4, right - left);

        const isBull = fvg.dir === 'BULLISH';
        ctx.save();
        ctx.fillStyle = isBull ? 'rgba(38, 166, 154, 0.18)' : 'rgba(239, 83, 80, 0.18)';
        ctx.strokeStyle = isBull ? 'rgba(38, 166, 154, 0.7)' : 'rgba(239, 83, 80, 0.7)';
        ctx.lineWidth = 1;
        ctx.fillRect(left, boxTop, boxWidth, boxHeight);
        ctx.strokeRect(left, boxTop, boxWidth, boxHeight);

        ctx.fillStyle = isBull ? 'rgba(38, 166, 154, 0.95)' : 'rgba(239, 83, 80, 0.95)';
        ctx.font = '9px sans-serif';
        ctx.fillText(`FVG ${fvg.dir[0]}`, left + 4, boxTop + Math.min(boxHeight - 2, 11));
        ctx.restore();
      }

      // 3. Breaker Block Rectangles
      for (const brk of breakers) {
        const yTop = series.priceToCoordinate(brk.top);
        const yBottom = series.priceToCoordinate(brk.bottom);
        const xStart = timeScale.timeToCoordinate(brk.t_start as UTCTimestamp);
        const xEnd = timeScale.timeToCoordinate(brk.t_end as UTCTimestamp);

        if (yTop === null || yBottom === null) continue;
        const left = xStart !== null ? Number(xStart) : 0;
        const right = xEnd !== null ? Number(xEnd) : width;
        const boxTop = Math.min(Number(yTop), Number(yBottom));
        const boxHeight = Math.max(2, Math.abs(Number(yBottom) - Number(yTop)));
        const boxWidth = Math.max(4, right - left);

        ctx.save();
        ctx.fillStyle = 'rgba(156, 39, 176, 0.18)';
        ctx.strokeStyle = 'rgba(156, 39, 176, 0.75)';
        ctx.lineWidth = 1;
        ctx.fillRect(left, boxTop, boxWidth, boxHeight);
        ctx.strokeRect(left, boxTop, boxWidth, boxHeight);

        ctx.fillStyle = 'rgba(206, 147, 216, 0.95)';
        ctx.font = '9px sans-serif';
        ctx.fillText('Breaker', left + 4, boxTop + Math.min(boxHeight - 2, 11));
        ctx.restore();
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
  private _paneView: IPrimitivePaneView;

  constructor() {
    const renderer = new ForensicBoxPaneRenderer(() => ({
      chart: this._chart,
      series: this._series,
      fvgs: this._fvgs,
      breakers: this._breakers,
      asianRanges: this._asianRanges,
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
  }): void {
    if (params.fvgs !== undefined) this._fvgs = params.fvgs;
    if (params.breakers !== undefined) this._breakers = params.breakers;
    if (params.asianRanges !== undefined) this._asianRanges = params.asianRanges;
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
      const right = width;
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

        // Right Badge Pill
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
