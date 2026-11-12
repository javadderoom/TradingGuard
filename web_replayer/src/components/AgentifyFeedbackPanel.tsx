/**
 * TradingGuard HITL Visual Co-Backtester - Agentify Feedback Bridge Panel
 * Captures:
 * - Forensic snapshots of missed setups, veto disagreements, and bot trade adjustments
 * - Persists cases to hitl/memory/visual_feedback_cases.json via POST /api/feedback
 * - Copies clipboard-ready Antigravity prompt markdown directly to user clipboard
 * - Lists past saved feedback cases with instant re-copy and delete actions
 */

import React, { useEffect, useState, useTransition } from 'react';
import {
  Check,
  CheckCircle2,
  Copy,
  FileCode2,
  HelpCircle,
  MessageSquarePlus,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react';

import { replayApi } from '../api/client';
import type {
  BotDiagnostic,
  Candle,
  ClockMode,
  FeedbackCase,
  ReplayTrade,
  SelectedSmcElement,
  Timeframe,
} from '../types/replay';
import {
  buildSmcElementContextMarkdown,
  formatClockTick,
  getQuickQuestionsForSmcElement,
} from '../utils/coTraderLogic';

export interface AgentifyFeedbackPanelProps {
  symbol: string;
  currentTime: number | null;
  clockMode: ClockMode;
  timeframe?: Timeframe;
  digits?: number;
  candles?: Candle[];
  diagnostics?: BotDiagnostic[];
  boundElement?: SelectedSmcElement | null;
  selectedTrade?: ReplayTrade | null;
  onClearBoundElement?: () => void;
  prefillContext?: {
    title?: string;
    category?: 'MISSED_SETUP' | 'BOT_TRADE_EDIT' | 'VETO_DISAGREEMENT' | 'NOTE';
    rationale?: string;
    archetype_id?: string;
    timestamp?: number;
  } | null;
  onCaseCreated?: () => void;
}

type FeedbackCategory = 'MISSED_SETUP' | 'BOT_TRADE_EDIT' | 'VETO_DISAGREEMENT' | 'NOTE';

export const AgentifyFeedbackPanel: React.FC<AgentifyFeedbackPanelProps> = ({
  symbol,
  currentTime,
  clockMode,
  timeframe = '5M',
  digits = 2,
  candles = [],
  diagnostics = [],
  boundElement = null,
  selectedTrade = null,
  onClearBoundElement,
  prefillContext = null,
  onCaseCreated,
}) => {
  const [category, setCategory] = useState<FeedbackCategory>(prefillContext?.category ?? 'MISSED_SETUP');
  const [title, setTitle] = useState<string>(prefillContext?.title ?? '');
  const [rationale, setRationale] = useState<string>(prefillContext?.rationale ?? '');
  const [archetypeId, setArchetypeId] = useState<string>(prefillContext?.archetype_id ?? '');
  const [timestamp, setTimestamp] = useState<number | null>(prefillContext?.timestamp ?? currentTime);

  const [savedCases, setSavedCases] = useState<FeedbackCase[]>([]);
  const [copiedPrompt, setCopiedPrompt] = useState<string | null>(null);
  const [showToast, setShowToast] = useState<boolean>(false);
  const [isSubmitting, startTransition] = useTransition();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [prevPrefill, setPrevPrefill] = useState(prefillContext);
  if (prefillContext !== prevPrefill) {
    setPrevPrefill(prefillContext);
    if (prefillContext?.category) setCategory(prefillContext.category);
    if (prefillContext?.title) setTitle(prefillContext.title);
    if (prefillContext?.rationale) setRationale(prefillContext.rationale);
    if (prefillContext?.archetype_id) setArchetypeId(prefillContext.archetype_id);
    if (prefillContext?.timestamp !== undefined) setTimestamp(prefillContext.timestamp);
  }

  // Load existing feedback cases on mount
  useEffect(() => {
    let active = true;
    replayApi.getFeedbackCases().then((res) => {
      if (active) setSavedCases(res.cases || []);
    }).catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const loadCases = async () => {
    try {
      const res = await replayApi.getFeedbackCases();
      setSavedCases(res.cases || []);
    } catch {
      // Ignore
    }
  };

  const handleCopyText = async (text: string) => {
    setCopiedPrompt(text);
    try {
      await navigator.clipboard.writeText(text);
      setShowToast(true);
      setTimeout(() => setShowToast(false), 3000);
    } catch {
      // Fallback: clipboard permission denied or insecure context, preview still active
    }
  };

  const resolveDiagAt = (t: number | null): BotDiagnostic | null => {
    if (t === null || diagnostics.length === 0) return null;
    const exact = diagnostics.find((d) => d.time === t);
    if (exact) return exact;
    const prior = diagnostics.filter((d) => d.time <= t);
    return prior.length > 0 ? prior[prior.length - 1] : null;
  };

  const handleQuickQuestionClick = async (question: string) => {
    setErrorMsg(null);
    if (boundElement) {
      const diag = resolveDiagAt(boundElement.time);
      const md = buildSmcElementContextMarkdown({
        symbol,
        timeframe,
        clockMode,
        digits,
        element: boundElement,
        candles,
        diagnostic: diag,
        question,
      });
      setCategory('VETO_DISAGREEMENT');
      setTitle(`${boundElement.kind}: ${boundElement.label} — ${question}`);
      setRationale(md);
      setTimestamp(boundElement.time);
      if (diag?.archetype_id) setArchetypeId(diag.archetype_id);
      await handleCopyText(md);
      return;
    }

    if (selectedTrade) {
      const timeStr = formatClockTick(selectedTrade.decision_time, clockMode, true);
      const md = [
        `### Agentify Trade Inquiry — ${symbol} (${timeframe})`,
        `- **Question:** ${question}`,
        `- **Trade:** \`${selectedTrade.trade_id}\` (${selectedTrade.origin} · ${selectedTrade.direction}${selectedTrade.archetype_id ? ` · ${selectedTrade.archetype_id}` : ''})`,
        `- **Time (${clockMode.toUpperCase()}):** \`${timeStr}\``,
        `- **Levels:** Entry \`${selectedTrade.entry.toFixed(digits)}\` | SL \`${selectedTrade.sl.toFixed(digits)}\` | TP \`${selectedTrade.tp.toFixed(digits)}\``,
        `- **Result:** \`${selectedTrade.status}\`${selectedTrade.rr_realized != null ? ` (${selectedTrade.rr_realized.toFixed(2)}R / $${selectedTrade.realized_pnl_usd?.toFixed(2) ?? '0.00'})` : ''}`,
        selectedTrade.notes ? `- **Notes:** ${selectedTrade.notes}` : '',
      ]
        .filter(Boolean)
        .join('\n');
      setCategory('BOT_TRADE_EDIT');
      setTitle(`Trade ${selectedTrade.trade_id}: ${question}`);
      setRationale(md);
      setTimestamp(selectedTrade.decision_time);
      if (selectedTrade.archetype_id) setArchetypeId(selectedTrade.archetype_id);
      await handleCopyText(md);
      return;
    }

    if (currentTime !== null) {
      const diag = resolveDiagAt(currentTime);
      const barElem: SelectedSmcElement = {
        id: `BAR:${currentTime}`,
        kind: 'ASIAN_RANGE',
        label: `Active Candle (${timeframe})`,
        time: currentTime,
      };
      const md = buildSmcElementContextMarkdown({
        symbol,
        timeframe,
        clockMode,
        digits,
        element: { ...barElem, kind: 'FVG', label: `Active Bar (${formatClockTick(currentTime, clockMode, true)})` },
        candles,
        diagnostic: diag,
        question,
      }).replace('Selected Element:** `FVG` —', 'Selected Bar:**');
      setCategory('NOTE');
      setTitle(`Bar @ ${formatClockTick(currentTime, clockMode, false)}: ${question}`);
      setRationale(md);
      setTimestamp(currentTime);
      await handleCopyText(md);
    }
  };

  const handleSubmit = () => {
    const resolvedTitle =
      title.trim() ||
      (boundElement ? `${boundElement.kind}: ${boundElement.label} on ${symbol}` : '');
    if (!resolvedTitle) {
      setErrorMsg('Please select a chart element or enter a title for this feedback case.');
      return;
    }
    setErrorMsg(null);

    const targetTime = timestamp ?? boundElement?.time ?? currentTime ?? Math.floor(Date.now() / 1000);

    startTransition(async () => {
      try {
        const res = await replayApi.createFeedbackCase({
          symbol,
          timestamp: targetTime,
          title: resolvedTitle,
          notes: rationale.trim(),
          category,
          archetype_id: archetypeId.trim() || undefined,
        });

        // Automatically copy prompt markdown to clipboard
        if (res.prompt_markdown) {
          await handleCopyText(res.prompt_markdown);
        }

        // Reset form
        setTitle('');
        setRationale('');
        setArchetypeId('');

        // Reload cases and notify parent
        await loadCases();
        onCaseCreated?.();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setErrorMsg(`Failed to save feedback: ${msg}`);
      }
    });
  };

  const handleDeleteCase = async (caseId: string) => {
    try {
      await replayApi.deleteFeedbackCase(caseId);
      await loadCases();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Failed to delete case: ${msg}`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto', padding: '12px', gap: '12px', backgroundColor: '#141414', color: '#cccccc', fontSize: '12px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #262626', paddingBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Sparkles size={16} style={{ color: '#10b981' }} />
          <span style={{ fontWeight: 700, fontSize: '13px', color: '#ffffff' }}>Agentify Feedback Bridge</span>
        </div>
        <button
          onClick={loadCases}
          title="Refresh cases"
          style={{ background: 'transparent', border: 'none', color: '#737373', cursor: 'pointer', padding: '2px' }}
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Toast Notification */}
      {showToast && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: 'rgba(8, 153, 129, 0.2)', border: '1px solid #089981', padding: '8px 10px', borderRadius: '4px', color: '#089981', fontWeight: 600, fontSize: '11px' }}>
          <CheckCircle2 size={14} />
          Copied Antigravity Alignment Prompt to Clipboard!
        </div>
      )}

      {/* Error Banner */}
      {errorMsg && (
        <div style={{ backgroundColor: 'rgba(207, 92, 96, 0.15)', border: '1px solid #cf5c60', padding: '6px 10px', borderRadius: '4px', color: '#e58589', fontSize: '11px' }}>
          {errorMsg}
        </div>
      )}

      {/* Bound Chart Target & One-Click Inquiry Chips */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', backgroundColor: '#191919', padding: '10px 12px', borderRadius: '6px', border: boundElement || selectedTrade ? '1.5px solid #f0b90b' : '1px solid #262626' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
          <span style={{ fontWeight: 700, fontSize: '11px', color: boundElement || selectedTrade ? '#ffd54f' : '#9c9c9c' }}>
            {boundElement
              ? `🎯 Bound ${boundElement.kind}: ${boundElement.label}`
              : selectedTrade
              ? `🎯 Bound Trade: ${selectedTrade.origin} ${selectedTrade.direction}`
              : currentTime !== null
              ? `🎯 Active Bar (${formatClockTick(currentTime, clockMode, false)})`
              : 'Click any Breaker, FVG, Sweep, or Trade on the chart'}
          </span>
          {boundElement && onClearBoundElement && (
            <button
              onClick={onClearBoundElement}
              style={{ background: 'none', border: 'none', color: '#737373', cursor: 'pointer', fontSize: '10px' }}
            >
              Clear
            </button>
          )}
        </div>

        {boundElement && (
          <div style={{ fontSize: '10px', color: '#9c9c9c', backgroundColor: '#0f0f0f', padding: '5px 8px', borderRadius: '4px' }}>
            {boundElement.top !== undefined && boundElement.bottom !== undefined ? (
              <span>
                Bounds: <b style={{ color: '#ffffff' }}>{boundElement.bottom.toFixed(digits)} – {boundElement.top.toFixed(digits)}</b>
              </span>
            ) : boundElement.price !== undefined ? (
              <span>
                Price: <b style={{ color: '#ffffff' }}>{boundElement.price.toFixed(digits)}</b>
                {boundElement.top !== undefined ? ` (Swept: ${boundElement.top.toFixed(digits)})` : ''}
              </span>
            ) : null}
            <span style={{ marginLeft: '8px', color: '#737373' }}>
              @ {formatClockTick(boundElement.time, clockMode, true)}
            </span>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span style={{ fontSize: '10px', color: '#737373', fontWeight: 600 }}>
            ONE-CLICK QUESTIONS (COPIES CONTEXT + OHLC + VETO):
          </span>
          {getQuickQuestionsForSmcElement(
            boundElement ? boundElement.kind : selectedTrade ? 'TRADE' : 'BAR'
          ).map((q) => (
            <button
              key={q}
              onClick={() => void handleQuickQuestionClick(q)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '6px',
                textAlign: 'left',
                padding: '6px 8px',
                borderRadius: '4px',
                backgroundColor: '#0f0f0f',
                border: '1px solid #262626',
                color: '#cccccc',
                fontSize: '11px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              <span>{q}</span>
              <Copy size={11} style={{ color: '#10b981', flexShrink: 0 }} />
            </button>
          ))}
        </div>
      </div>

      {/* New Feedback Form Card */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', backgroundColor: '#191919', padding: '12px', borderRadius: '6px', border: '1px solid #262626' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 600, color: '#e5e5e5' }}>Capture Forensic Case</span>
          <span style={{ fontSize: '10px', color: '#737373' }}>
            {timestamp !== null ? formatClockTick(timestamp, clockMode, true) : 'Current Bar'}
          </span>
        </div>

        {/* Category Picker */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <label style={{ fontSize: '10px', color: '#737373', fontWeight: 600 }}>CATEGORY</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '4px' }}>
            {(
              [
                ['MISSED_SETUP', 'Missed Setup'],
                ['BOT_TRADE_EDIT', 'Bot Trade Edit'],
                ['VETO_DISAGREEMENT', 'Veto Disagreement'],
                ['NOTE', 'Forensic Note'],
              ] as [FeedbackCategory, string][]
            ).map(([cat, label]) => {
              const isSel = category === cat;
              return (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  style={{
                    padding: '4px 6px',
                    fontSize: '11px',
                    fontWeight: isSel ? 600 : 400,
                    backgroundColor: isSel ? '#089981' : '#0f0f0f',
                    color: isSel ? '#ffffff' : '#9c9c9c',
                    border: `1px solid ${isSel ? '#089981' : '#262626'}`,
                    borderRadius: '4px',
                    cursor: 'pointer',
                    textAlign: 'center',
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Title Input */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <label style={{ fontSize: '10px', color: '#737373', fontWeight: 600 }}>TITLE</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Nov 11 Gold London Judas Sweep missed by screener"
            style={{
              padding: '6px 8px',
              fontSize: '11px',
              backgroundColor: '#0f0f0f',
              border: '1px solid #262626',
              borderRadius: '4px',
              color: '#ffffff',
              outline: 'none',
            }}
          />
        </div>

        {/* Archetype Input */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <label style={{ fontSize: '10px', color: '#737373', fontWeight: 600 }}>ARCHETYPE REF (OPTIONAL)</label>
          <input
            type="text"
            value={archetypeId}
            onChange={(e) => setArchetypeId(e.target.value)}
            placeholder="e.g. SETUP-ARCH-001 or SETUP-ARCH-013"
            style={{
              padding: '6px 8px',
              fontSize: '11px',
              backgroundColor: '#0f0f0f',
              border: '1px solid #262626',
              borderRadius: '4px',
              color: '#ffffff',
              outline: 'none',
            }}
          />
        </div>

        {/* Rationale Textarea */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <label style={{ fontSize: '10px', color: '#737373', fontWeight: 600 }}>RATIONALE & HUMAN FORENSICS</label>
          <textarea
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="Describe what bot should have seen, why veto was incorrect, or how entry/stop was improved..."
            style={{
              padding: '6px 8px',
              fontSize: '11px',
              backgroundColor: '#0f0f0f',
              border: '1px solid #262626',
              borderRadius: '4px',
              color: '#ffffff',
              outline: 'none',
              resize: 'vertical',
            }}
          />
        </div>

        {/* Submit & Copy Prompt Button */}
        <button
          onClick={handleSubmit}
          disabled={isSubmitting}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            backgroundColor: '#10b981',
            color: '#0f0f0f',
            fontWeight: 700,
            fontSize: '11px',
            padding: '7px 12px',
            borderRadius: '4px',
            border: 'none',
            cursor: isSubmitting ? 'not-allowed' : 'pointer',
            opacity: isSubmitting ? 0.7 : 1,
            marginTop: '4px',
          }}
        >
          <Sparkles size={13} />
          {isSubmitting ? 'Generating Prompt...' : 'Save & Copy Antigravity Prompt'}
        </button>
      </div>

      {/* Prompt Preview Card if prompt copied */}
      {copiedPrompt && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', backgroundColor: '#0f0f0f', padding: '10px', borderRadius: '6px', border: '1px solid #262626' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#9c9c9c', fontWeight: 600 }}>
              <FileCode2 size={13} />
              Ready-to-Paste Antigravity Prompt
            </span>
            <button
              onClick={() => handleCopyText(copiedPrompt)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
                background: 'transparent',
                border: '1px solid #262626',
                borderRadius: '3px',
                color: '#cccccc',
                padding: '2px 6px',
                fontSize: '10px',
                cursor: 'pointer',
              }}
            >
              <Copy size={10} />
              Re-copy
            </button>
          </div>
          <pre
            style={{
              fontSize: '10px',
              lineHeight: '1.4',
              color: '#9c9c9c',
              maxHeight: '120px',
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              backgroundColor: '#141414',
              padding: '6px',
              borderRadius: '4px',
            }}
          >
            {copiedPrompt.slice(0, 400)}
            {copiedPrompt.length > 400 ? '...' : ''}
          </pre>
        </div>
      )}

      {/* Saved Feedback Cases List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 600, color: '#e5e5e5', fontSize: '12px' }}>
            Saved Cases ({savedCases.length})
          </span>
        </div>

        {savedCases.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {savedCases.map((c) => {
              const casePrompt = c.prompt_markdown || (c.notes ? `# Case: ${c.title}\n\n${c.notes}` : '');
              const isCopied = copiedPrompt === casePrompt;

              return (
                <div
                  key={c.case_id}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '5px',
                    padding: '8px 10px',
                    backgroundColor: '#191919',
                    borderRadius: '6px',
                    border: '1px solid #262626',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '10px', fontWeight: 600, color: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.1)', padding: '1px 5px', borderRadius: '3px' }}>
                      {c.case_id}
                    </span>
                    <span style={{ fontSize: '10px', color: '#737373' }}>
                      {formatClockTick(c.timestamp, clockMode, false)}
                    </span>
                  </div>

                  <div style={{ fontWeight: 600, color: '#ffffff', fontSize: '11px' }}>
                    {c.title}
                  </div>

                  {c.notes && (
                    <div style={{ color: '#9c9c9c', fontSize: '10px', lineHeight: '1.3' }}>
                      {c.notes}
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px', paddingTop: '4px', borderTop: '1px solid #222222' }}>
                    <button
                      onClick={() => handleCopyText(casePrompt)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '3px',
                        background: isCopied ? '#089981' : '#089981',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '3px',
                        padding: '2px 7px',
                        fontSize: '10px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      {isCopied ? <Check size={10} /> : <Copy size={10} />}
                      {isCopied ? 'Copied' : 'Copy Prompt'}
                    </button>
                    <button
                      onClick={() => handleDeleteCase(c.case_id)}
                      title="Delete case"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        background: 'transparent',
                        border: '1px solid rgba(207, 92, 96, 0.4)',
                        color: '#cf5c60',
                        borderRadius: '3px',
                        padding: '2px 5px',
                        fontSize: '10px',
                        cursor: 'pointer',
                      }}
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ padding: '14px', textAlign: 'center', color: '#737373', fontSize: '11px', backgroundColor: '#191919', borderRadius: '6px' }}>
            <MessageSquarePlus size={18} style={{ opacity: 0.5, marginBottom: '4px' }} />
            <div>No feedback cases recorded yet.</div>
            <div style={{ fontSize: '10px', color: '#4a4a4a', marginTop: '2px' }}>
              Capture a case above to generate prompt markdown for Antigravity.
            </div>
          </div>
        )}
      </div>

      {/* Guide Note */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', backgroundColor: '#0f0f0f', padding: '8px', borderRadius: '4px', border: '1px solid #262626', color: '#737373', fontSize: '10px', lineHeight: '1.4' }}>
        <HelpCircle size={14} style={{ flexShrink: 0, marginTop: '1px' }} />
        <span>
          Feedback cases are saved directly into <code>hitl/memory/visual_feedback_cases.json</code>. The copied prompt can be pasted directly into Antigravity to calibrate Python screener rules without documentation drift.
        </span>
      </div>
    </div>
  );
};

export default AgentifyFeedbackPanel;
