/**
 * TradingGuard HITL Visual Co-Backtester - Co-Trade Scorecard & Ledger Panel
 * Displays:
 * - Dynamic side-by-side or tabbed performance metrics (ALL / BOT / HUMAN_PROPOSED / HUMAN_EDITED_BOT)
 * - Anti-spoiler Blind Replay masking (trades open at replayTo have outcomes hidden)
 * - Trade ledger table/cards with Clone & Adjust, Delete, Jump, and Agentify Feedback triggers
 * - $20 system risk limit warning compliance badges
 */

import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Award,
  CheckCircle2,
  Copy,
  ExternalLink,
  MessageSquarePlus,
  Trash2,
  TrendingDown,
  TrendingUp,
  XCircle,
} from 'lucide-react';

import type {
  ClockMode,
  ReplayTrade,
  TradeOrigin,
} from '../types/replay';
import {
  computeReplayScorecard,
  formatClockTick,
  maskBlindReplayTrade,
} from '../utils/coTraderLogic';

export interface ScorecardPanelProps {
  trades: ReplayTrade[];
  replayTo: number | null;
  clockMode: ClockMode;
  digits?: number;
  selectedTradeId?: string | null;
  onCloneTrade?: (trade: ReplayTrade) => void;
  onDeleteTrade?: (tradeId: string) => void;
  onSelectTrade?: (trade: ReplayTrade) => void;
  onTriggerFeedback?: (trade: ReplayTrade) => void;
}

type TabOrigin = 'ALL' | TradeOrigin;

export const ScorecardPanel: React.FC<ScorecardPanelProps> = ({
  trades = [],
  replayTo = null,
  clockMode,
  digits = 2,
  selectedTradeId = null,
  onCloneTrade,
  onDeleteTrade,
  onSelectTrade,
  onTriggerFeedback,
}) => {
  const [selectedTab, setSelectedTab] = useState<TabOrigin>('ALL');

  // Filter trades visible at replayTo (decision_time <= replayTo if replayTo set)
  const visibleTrades = useMemo(() => {
    return trades
      .filter((t) => (replayTo !== null ? t.decision_time <= replayTo : true))
      .map((t) => maskBlindReplayTrade(t, replayTo));
  }, [trades, replayTo]);

  // Subset for selected tab
  const tabTrades = useMemo(() => {
    if (selectedTab === 'ALL') return visibleTrades;
    return visibleTrades.filter((t) => t.origin === selectedTab);
  }, [visibleTrades, selectedTab]);

  // Compute metrics dynamically respecting blind replay masking
  const scorecard = useMemo(() => {
    return computeReplayScorecard(tabTrades, replayTo);
  }, [tabTrades, replayTo]);

  // Pre-compute counts for badges
  const originCounts = useMemo(() => {
    return {
      ALL: visibleTrades.length,
      BOT: visibleTrades.filter((t) => t.origin === 'BOT').length,
      HUMAN_PROPOSED: visibleTrades.filter((t) => t.origin === 'HUMAN_PROPOSED').length,
      HUMAN_EDITED_BOT: visibleTrades.filter((t) => t.origin === 'HUMAN_EDITED_BOT').length,
    };
  }, [visibleTrades]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto', padding: '12px', gap: '12px', backgroundColor: '#181b24', color: '#d1d4dc', fontSize: '12px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #2a2e39', paddingBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Award size={16} style={{ color: '#ffd54f' }} />
          <span style={{ fontWeight: 700, fontSize: '13px', color: '#ffffff' }}>Co-Trade Scorecard & Ledger</span>
        </div>
        {replayTo !== null && (
          <span style={{ padding: '2px 6px', borderRadius: '4px', backgroundColor: 'rgba(255, 179, 0, 0.15)', color: '#ffb300', fontSize: '10px', fontWeight: 600 }}>
            Blind Replay Active
          </span>
        )}
      </div>

      {/* Origin Filter Tabs */}
      <div style={{ display: 'flex', gap: '4px', backgroundColor: '#1e222d', padding: '3px', borderRadius: '6px', border: '1px solid #2a2e39' }}>
        {(['ALL', 'BOT', 'HUMAN_PROPOSED', 'HUMAN_EDITED_BOT'] as TabOrigin[]).map((tab) => {
          const isActive = selectedTab === tab;
          let label = 'ALL';
          if (tab === 'BOT') label = 'Bot';
          else if (tab === 'HUMAN_PROPOSED') label = 'Human';
          else if (tab === 'HUMAN_EDITED_BOT') label = 'Edited';

          return (
            <button
              key={tab}
              onClick={() => setSelectedTab(tab)}
              style={{
                flex: 1,
                padding: '5px 4px',
                fontSize: '11px',
                fontWeight: isActive ? 600 : 400,
                backgroundColor: isActive ? '#2962ff' : 'transparent',
                color: isActive ? '#ffffff' : '#787b86',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '4px',
                transition: 'all 0.15s ease',
              }}
            >
              <span>{label}</span>
              <span style={{ fontSize: '9px', opacity: 0.8, backgroundColor: isActive ? 'rgba(255,255,255,0.2)' : '#2a2e39', padding: '1px 4px', borderRadius: '8px' }}>
                {originCounts[tab]}
              </span>
            </button>
          );
        })}
      </div>

      {/* Scorecard Metrics Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
        {/* Net PnL */}
        <div style={{ backgroundColor: '#1e222d', padding: '8px', borderRadius: '6px', border: '1px solid #2a2e39', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ color: '#787b86', fontSize: '10px' }}>Net PnL</span>
          <span style={{ fontWeight: 700, fontSize: '13px', color: scorecard.net_pnl_usd >= 0 ? '#26a69a' : '#ef5350' }}>
            {scorecard.net_pnl_usd >= 0 ? '+' : ''}${scorecard.net_pnl_usd.toFixed(2)}
          </span>
        </div>

        {/* Net R */}
        <div style={{ backgroundColor: '#1e222d', padding: '8px', borderRadius: '6px', border: '1px solid #2a2e39', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ color: '#787b86', fontSize: '10px' }}>Net R</span>
          <span style={{ fontWeight: 700, fontSize: '13px', color: scorecard.net_rr >= 0 ? '#26a69a' : '#ef5350' }}>
            {scorecard.net_rr >= 0 ? '+' : ''}{scorecard.net_rr.toFixed(2)}R
          </span>
        </div>

        {/* Win Rate */}
        <div style={{ backgroundColor: '#1e222d', padding: '8px', borderRadius: '6px', border: '1px solid #2a2e39', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ color: '#787b86', fontSize: '10px' }}>Win Rate</span>
          <span style={{ fontWeight: 700, fontSize: '13px', color: '#e0e3eb' }}>
            {scorecard.win_rate_pct.toFixed(1)}%
          </span>
        </div>

        {/* Profit Factor */}
        <div style={{ backgroundColor: '#1e222d', padding: '8px', borderRadius: '6px', border: '1px solid #2a2e39', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ color: '#787b86', fontSize: '10px' }}>Profit Factor</span>
          <span style={{ fontWeight: 700, fontSize: '13px', color: '#e0e3eb' }}>
            {scorecard.profit_factor.toFixed(2)}
          </span>
        </div>

        {/* Max Drawdown */}
        <div style={{ backgroundColor: '#1e222d', padding: '8px', borderRadius: '6px', border: '1px solid #2a2e39', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ color: '#787b86', fontSize: '10px' }}>Max DD</span>
          <span style={{ fontWeight: 700, fontSize: '13px', color: '#ef5350' }}>
            ${scorecard.max_drawdown_usd.toFixed(2)}
          </span>
        </div>

        {/* W / L / BE Breakdown */}
        <div style={{ backgroundColor: '#1e222d', padding: '8px', borderRadius: '6px', border: '1px solid #2a2e39', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ color: '#787b86', fontSize: '10px' }}>W / L / BE</span>
          <span style={{ fontWeight: 600, fontSize: '12px', color: '#e0e3eb' }}>
            {scorecard.wins}W / {scorecard.losses}L / {scorecard.breakevens}B
          </span>
        </div>
      </div>

      {/* Trades Ledger List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 600, color: '#e0e3eb', fontSize: '12px' }}>
            Trade Records ({tabTrades.length})
          </span>
        </div>

        {tabTrades.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {tabTrades.map((t) => {
              const isLong = t.direction === 'LONG';
              const isWin = t.status === 'WIN';
              const isLoss = t.status === 'LOSS';
              const isOpen = t.status === 'OPEN';
              const isPending = t.status === 'PENDING';

              const isSelected = selectedTradeId === t.trade_id;

              return (
                <div
                  key={t.trade_id}
                  onClick={() => onSelectTrade?.(t)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    padding: '8px 10px',
                    backgroundColor: isSelected ? '#232837' : '#1e222d',
                    borderRadius: '6px',
                    border: isSelected ? '1.5px solid #f0b90b' : '1px solid #2a2e39',
                    cursor: 'pointer',
                  }}
                >
                  {/* Top row: Badges & Realized Status */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      {/* Origin Badge */}
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 700,
                          padding: '2px 5px',
                          borderRadius: '3px',
                          backgroundColor:
                            t.origin === 'BOT'
                              ? 'rgba(41, 98, 255, 0.2)'
                              : t.origin === 'HUMAN_PROPOSED'
                              ? 'rgba(38, 166, 154, 0.2)'
                              : 'rgba(255, 179, 0, 0.2)',
                          color:
                            t.origin === 'BOT'
                              ? '#90caf9'
                              : t.origin === 'HUMAN_PROPOSED'
                              ? '#80cbc4'
                              : '#ffe082',
                        }}
                      >
                        {t.origin === 'BOT' ? 'BOT' : t.origin === 'HUMAN_PROPOSED' ? 'HUMAN' : 'EDITED'}
                      </span>

                      {/* Direction */}
                      <span
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '2px',
                          fontSize: '10px',
                          fontWeight: 700,
                          color: isLong ? '#26a69a' : '#ef5350',
                        }}
                      >
                        {isLong ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                        {t.direction}
                      </span>
                    </div>

                    {/* Status / Realized Outcome */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {isWin && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '2px', color: '#26a69a', fontWeight: 700, fontSize: '11px' }}>
                          <CheckCircle2 size={12} />
                          +{t.rr_realized?.toFixed(2)}R (+${t.realized_pnl_usd?.toFixed(2)})
                        </span>
                      )}
                      {isLoss && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '2px', color: '#ef5350', fontWeight: 700, fontSize: '11px' }}>
                          <XCircle size={12} />
                          {t.rr_realized?.toFixed(2)}R (${t.realized_pnl_usd?.toFixed(2)})
                        </span>
                      )}
                      {t.status === 'BREAKEVEN' && (
                        <span style={{ color: '#ffb300', fontWeight: 700, fontSize: '11px' }}>
                          BE (${t.realized_pnl_usd?.toFixed(2)})
                        </span>
                      )}
                      {isOpen && (
                        <span style={{ color: '#2962ff', fontWeight: 600, fontSize: '11px' }}>
                          ● OPEN
                        </span>
                      )}
                      {isPending && (
                        <span style={{ color: '#787b86', fontWeight: 500, fontSize: '11px' }}>
                          ○ PENDING
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Price Levels: Entry / SL / TP */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: '#b2b5be', backgroundColor: '#131722', padding: '4px 6px', borderRadius: '4px' }}>
                    <span>E: <b style={{ color: '#ffffff' }}>{t.entry.toFixed(digits)}</b></span>
                    <span>SL: <b style={{ color: '#ef5350' }}>{t.sl.toFixed(digits)}</b></span>
                    <span>TP: <b style={{ color: '#26a69a' }}>{t.tp.toFixed(digits)}</b></span>
                  </div>

                  {/* Risk & Time info */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10px', color: '#787b86' }}>
                    <span>
                      {formatClockTick(t.decision_time, clockMode, false)}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {t.exceeds_risk_cap && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '2px', color: '#ffb300', backgroundColor: 'rgba(255, 179, 0, 0.1)', padding: '1px 4px', borderRadius: '3px' }}>
                          <AlertTriangle size={10} />
                          &gt;$20 Risk
                        </span>
                      )}
                      {t.risk_usd_001 !== undefined && (
                        <span>Risk: ${t.risk_usd_001.toFixed(2)}</span>
                      )}
                    </div>
                  </div>

                  {/* Actions Bar */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px', paddingTop: '4px', borderTop: '1px solid #262b36' }}>
                    {/* Jump / Inspect */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectTrade?.(t);
                      }}
                      title="Select & Inspect Trade on Chart"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '3px',
                        background: isSelected ? 'rgba(240, 185, 11, 0.16)' : 'transparent',
                        border: isSelected ? '1px solid #f0b90b' : '1px solid #2a2e39',
                        borderRadius: '3px',
                        color: isSelected ? '#ffd54f' : '#b2b5be',
                        padding: '2px 6px',
                        fontSize: '10px',
                        cursor: 'pointer',
                      }}
                    >
                      <ExternalLink size={10} />
                      {isSelected ? 'Selected' : 'Inspect'}
                    </button>

                    {/* Clone & Adjust */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onCloneTrade?.(t);
                      }}
                      title="Clone & Adjust Trade"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '3px',
                        background: '#2962ff',
                        border: 'none',
                        borderRadius: '3px',
                        color: '#ffffff',
                        padding: '2px 7px',
                        fontSize: '10px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <Copy size={10} />
                      Clone & Adjust
                    </button>

                    {/* Ask / Feedback */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectTrade?.(t);
                        onTriggerFeedback?.(t);
                      }}
                      title="Ask a question or give feedback on this trade"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '3px',
                        background: 'transparent',
                        border: '1px solid #2a2e39',
                        borderRadius: '3px',
                        color: '#90caf9',
                        padding: '2px 6px',
                        fontSize: '10px',
                        cursor: 'pointer',
                      }}
                    >
                      <MessageSquarePlus size={10} />
                      Ask
                    </button>

                    {/* Delete for human trades */}
                    {t.origin !== 'BOT' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteTrade?.(t.trade_id);
                        }}
                        title="Delete Trade from Ledger"
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '3px',
                          background: 'transparent',
                          border: '1px solid rgba(239, 83, 80, 0.4)',
                          borderRadius: '3px',
                          color: '#ef5350',
                          padding: '2px 5px',
                          fontSize: '10px',
                          cursor: 'pointer',
                        }}
                      >
                        <Trash2 size={10} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ padding: '16px', textAlign: 'center', color: '#787b86', fontSize: '11px', backgroundColor: '#1e222d', borderRadius: '6px' }}>
            No trades recorded for this category yet.
          </div>
        )}
      </div>
    </div>
  );
};

export default ScorecardPanel;
