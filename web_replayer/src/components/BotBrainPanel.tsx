/**
 * TradingGuard HITL Visual Co-Backtester - Bot Brain Inspector Panel
 * Displays:
 * - Algorithmic screener verdict on the active/selected bar
 * - Archetype ID, phase, session hour, Asian levels, and FVG/Breaker presence
 * - Veto rationale callout with "Analyze Why Bot Vetoed" / "Capture Veto as Feedback" action
 * - Key events timeline with clickable bar jumps
 */

import React, { useMemo } from 'react';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock,
  Layers,
  MessageSquarePlus,
  ShieldAlert,
} from 'lucide-react';

import type {
  BotDiagnostic,
  BotEvent,
  ClockMode,
  EngineClockMode,
  ReplayTrade,
  SelectedSmcElement,
} from '../types/replay';
import { formatClockTick } from '../utils/coTraderLogic';

export interface BotBrainPanelProps {
  symbol: string;
  currentTime: number | null;
  diagnostics: BotDiagnostic[];
  events: BotEvent[];
  clockMode: ClockMode;
  engineClockMode: EngineClockMode;
  digits?: number;
  tradesNearBar?: ReplayTrade[];
  selectedTradeId?: string | null;
  onSelectTrade?: (trade: ReplayTrade) => void;
  onSelectElement?: (element: SelectedSmcElement) => void;
  onSelectEventTime?: (time: number) => void;
  onTriggerFeedback?: (context: {
    title: string;
    category: 'MISSED_SETUP' | 'BOT_TRADE_EDIT' | 'VETO_DISAGREEMENT' | 'NOTE';
    rationale: string;
    archetype_id?: string;
    timestamp?: number;
  }) => void;
  onTriggerTradeFeedback?: (trade: ReplayTrade) => void;
}

export const BotBrainPanel: React.FC<BotBrainPanelProps> = ({
  symbol,
  currentTime,
  diagnostics = [],
  events = [],
  clockMode,
  engineClockMode,
  digits = 2,
  tradesNearBar = [],
  selectedTradeId = null,
  onSelectTrade,
  onSelectElement,
  onSelectEventTime,
  onTriggerFeedback,
  onTriggerTradeFeedback,
}) => {
  // Find diagnostic at currentTime or closest prior diagnostic
  const activeDiag = useMemo(() => {
    if (currentTime === null || diagnostics.length === 0) return null;
    const exact = diagnostics.find((d) => d.time === currentTime);
    if (exact) return exact;
    const prior = diagnostics.filter((d) => d.time <= currentTime);
    return prior.length > 0 ? prior[prior.length - 1] : null;
  }, [diagnostics, currentTime]);

  // Anti-spoiler events filter (only events up to currentTime if set)
  const visibleEvents = useMemo(() => {
    const list = currentTime === null
      ? events
      : events.filter((e) => e.time <= currentTime);
    // Display in reverse chronological order (newest first)
    return [...list].sort((a, b) => b.time - a.time);
  }, [events, currentTime]);

  const handleVetoFeedbackClick = () => {
    if (!activeDiag) return;
    const timeStr = formatClockTick(activeDiag.time, clockMode, true);
    onTriggerFeedback?.({
      title: `Veto Analysis: ${activeDiag.archetype_id || 'SMC Screener'} on ${symbol}`,
      category: 'VETO_DISAGREEMENT',
      rationale: `Diagnostic at ${timeStr} (${clockMode.toUpperCase()}):
Session Hour: ${activeDiag.session_hour}
Phase: ${activeDiag.phase}
Reason / Veto: ${activeDiag.reason || 'None'}
Clock Mode: ${engineClockMode}`,
      archetype_id: activeDiag.archetype_id,
      timestamp: activeDiag.time,
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto', padding: '12px', gap: '14px', backgroundColor: '#141414', color: '#cccccc', fontSize: '12px' }}>
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #262626', paddingBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Bot size={16} style={{ color: '#089981' }} />
          <span style={{ fontWeight: 700, fontSize: '13px', color: '#ffffff' }}>Bot Brain Inspector</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ padding: '2px 6px', borderRadius: '4px', backgroundColor: '#262626', color: '#9c9c9c', fontSize: '10px', fontWeight: 600 }}>
            {engineClockMode}
          </span>
          <span style={{ padding: '2px 6px', borderRadius: '4px', backgroundColor: '#262626', color: '#ffd54f', fontSize: '10px', fontWeight: 600 }}>
            {symbol}
          </span>
        </div>
      </div>

      {/* Active Bar Timestamp */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#191919', padding: '8px 10px', borderRadius: '6px', border: '1px solid #262626' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Clock size={13} style={{ color: '#737373' }} />
          <span style={{ color: '#737373' }}>Active Bar:</span>
        </div>
        <span style={{ fontWeight: 600, color: '#e5e5e5' }}>
          {currentTime !== null ? formatClockTick(currentTime, clockMode, true) : 'No Bar Selected'}
        </span>
      </div>

      {/* Diagnostic Verdict Card */}
      {activeDiag ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', backgroundColor: '#191919', padding: '12px', borderRadius: '6px', border: `1px solid ${activeDiag.has_setup ? 'rgba(8, 153, 129, 0.4)' : '#262626'}` }}>
          {/* Verdict Status */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: '#737373', fontWeight: 500 }}>Verdict:</span>
            {activeDiag.has_setup ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', backgroundColor: 'rgba(8, 153, 129, 0.2)', color: '#089981', fontWeight: 700 }}>
                <CheckCircle2 size={13} />
                SETUP DETECTED
              </span>
            ) : (
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', backgroundColor: 'rgba(207, 92, 96, 0.15)', color: '#cf5c60', fontWeight: 600 }}>
                <AlertTriangle size={13} />
                NO SETUP / VETOED
              </span>
            )}
          </div>

          {/* Archetype & Phase */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', paddingTop: '4px', borderTop: '1px solid #222222' }}>
            <div>
              <div style={{ color: '#737373', fontSize: '11px' }}>Archetype:</div>
              <div style={{ fontWeight: 600, color: activeDiag.archetype_id ? '#9c9c9c' : '#cccccc' }}>
                {activeDiag.archetype_id || activeDiag.setup_type || 'None'}
              </div>
            </div>
            <div>
              <div style={{ color: '#737373', fontSize: '11px' }}>Phase:</div>
              <div style={{ fontWeight: 600, color: '#cccccc' }}>
                {activeDiag.phase || 'IDLE'}
              </div>
            </div>
          </div>

          {/* Session Hour & Asian Levels */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', paddingTop: '4px', borderTop: '1px solid #222222' }}>
            <div>
              <div style={{ color: '#737373', fontSize: '11px' }}>Session Hour:</div>
              <div style={{ fontWeight: 500 }}>{activeDiag.session_hour}</div>
            </div>
            <div>
              <div style={{ color: '#737373', fontSize: '11px' }}>Asian Bounds:</div>
              <div style={{ fontWeight: 500 }}>
                {activeDiag.asian_high ? `${activeDiag.asian_high.toFixed(digits)} / ${activeDiag.asian_low?.toFixed(digits)}` : 'N/A'}
              </div>
            </div>
          </div>

          {/* Structural Overlays (Clickable for Chart & Agentify Inspection) */}
          {(activeDiag.fvg_box || activeDiag.breaker_box) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', paddingTop: '6px', borderTop: '1px solid #222222' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#737373', fontSize: '11px' }}>
                <Layers size={11} />
                <span>Detected Zones (click to inspect / ask):</span>
              </div>
              {activeDiag.fvg_box && (
                <button
                  onClick={() => {
                    const fvg = activeDiag.fvg_box!;
                    onSelectElement?.({
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
                  }}
                  style={{
                    textAlign: 'left',
                    fontSize: '11px',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    backgroundColor: '#0f0f0f',
                    border: '1px solid rgba(8, 153, 129, 0.4)',
                    color: activeDiag.fvg_box.dir === 'BULLISH' ? '#34d399' : '#e58589',
                    cursor: 'pointer',
                  }}
                >
                  • FVG {activeDiag.fvg_box.dir} [{activeDiag.fvg_box.bottom.toFixed(digits)} – {activeDiag.fvg_box.top.toFixed(digits)}]
                </button>
              )}
              {activeDiag.breaker_box && (
                <button
                  onClick={() => {
                    const brk = activeDiag.breaker_box!;
                    onSelectElement?.({
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
                  }}
                  style={{
                    textAlign: 'left',
                    fontSize: '11px',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    backgroundColor: '#0f0f0f',
                    border: '1px solid rgba(206, 147, 216, 0.45)',
                    color: '#e1bee7',
                    cursor: 'pointer',
                  }}
                >
                  • Breaker {activeDiag.breaker_box.type} [{activeDiag.breaker_box.bottom.toFixed(digits)} – {activeDiag.breaker_box.top.toFixed(digits)}]
                </button>
              )}
            </div>
          )}

          {/* Veto Reason Callout */}
          {activeDiag.reason && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', backgroundColor: 'rgba(207, 92, 96, 0.08)', border: '1px solid rgba(207, 92, 96, 0.25)', padding: '8px', borderRadius: '4px', marginTop: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#cf5c60', fontWeight: 600, fontSize: '11px' }}>
                <ShieldAlert size={12} />
                <span>Veto / Rationale:</span>
              </div>
              <div style={{ color: '#f2b8ba', fontSize: '11px', lineHeight: '1.4' }}>
                {activeDiag.reason}
              </div>
              <button
                onClick={handleVetoFeedbackClick}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '5px',
                  backgroundColor: '#089981',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '4px',
                  padding: '5px 8px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  marginTop: '4px',
                }}
              >
                <MessageSquarePlus size={12} />
                Analyze Why Bot Vetoed
              </button>
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 12px', textAlign: 'center', backgroundColor: '#191919', borderRadius: '6px', border: '1px dashed #262626', color: '#737373', gap: '6px' }}>
          <Bot size={24} style={{ opacity: 0.5 }} />
          <span>Click any candle on the chart or scrub replay cursor to inspect screener diagnostics.</span>
        </div>
      )}

      {/* Key Events Timeline */}
      {tradesNearBar.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 600, color: '#ffd54f', fontSize: '12px' }}>
              Trades Near Active Bar ({tradesNearBar.length})
            </span>
          </div>
          {tradesNearBar.map((t) => {
            const isSel = selectedTradeId === t.trade_id;
            return (
              <div
                key={t.trade_id}
                onClick={() => onSelectTrade?.(t)}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  padding: '8px',
                  borderRadius: '6px',
                  backgroundColor: isSel ? '#1e1e1e' : '#191919',
                  border: isSel ? '1.5px solid #f0b90b' : '1px solid #262626',
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 700, fontSize: '11px', color: t.direction === 'LONG' ? '#089981' : '#cf5c60' }}>
                    {t.origin} · {t.direction} {t.archetype_id ? `(${t.archetype_id})` : ''}
                  </span>
                  <span style={{ fontSize: '11px', fontWeight: 700, color: t.status === 'WIN' ? '#089981' : t.status === 'LOSS' ? '#cf5c60' : '#9c9c9c' }}>
                    {t.status}{t.rr_realized != null ? ` ${t.rr_realized >= 0 ? '+' : ''}${t.rr_realized.toFixed(2)}R` : ''}
                  </span>
                </div>
                <div style={{ fontSize: '10px', color: '#9c9c9c' }}>
                  E: {t.entry.toFixed(digits)} | SL: {t.sl.toFixed(digits)} | TP: {t.tp.toFixed(digits)}
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectTrade?.(t);
                    }}
                    style={{
                      padding: '2px 7px',
                      fontSize: '10px',
                      borderRadius: '3px',
                      backgroundColor: isSel ? '#f0b90b' : '#262626',
                      color: isSel ? '#0f0f0f' : '#cccccc',
                      border: 'none',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    {isSel ? 'Selected' : 'Select'}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectTrade?.(t);
                      onTriggerTradeFeedback?.(t);
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '3px',
                      padding: '2px 7px',
                      fontSize: '10px',
                      borderRadius: '3px',
                      backgroundColor: '#089981',
                      color: '#ffffff',
                      border: 'none',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <MessageSquarePlus size={10} />
                    Ask / Feedback
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Key Events Timeline */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 600, color: '#e5e5e5', fontSize: '12px' }}>
            Key Events Timeline
          </span>
          <span style={{ fontSize: '10px', backgroundColor: '#262626', padding: '1px 6px', borderRadius: '10px', color: '#737373' }}>
            {visibleEvents.length} events
          </span>
        </div>

        {visibleEvents.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '280px', overflowY: 'auto' }}>
            {visibleEvents.map((ev, idx) => (
              <div
                key={`${ev.time}-${idx}`}
                onClick={() => onSelectEventTime?.(ev.time)}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '3px',
                  padding: '7px 9px',
                  backgroundColor: '#191919',
                  borderRadius: '4px',
                  border: '1px solid #262626',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#089981';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#262626';
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ color: '#9c9c9c', fontWeight: 600, fontSize: '11px' }}>
                    {ev.type}
                  </span>
                  <span style={{ color: '#737373', fontSize: '10px' }}>
                    {formatClockTick(ev.time, clockMode, false)}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#cccccc', fontSize: '11px' }}>
                  <span>{ev.description}</span>
                  <ChevronRight size={12} style={{ color: '#737373' }} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: '12px', textAlign: 'center', color: '#737373', fontSize: '11px', backgroundColor: '#191919', borderRadius: '4px' }}>
            No events recorded up to current bar.
          </div>
        )}
      </div>
    </div>
  );
};

export default BotBrainPanel;
