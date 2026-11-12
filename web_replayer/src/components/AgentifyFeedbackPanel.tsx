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
  ClockMode,
  FeedbackCase,
} from '../types/replay';
import { formatClockTick } from '../utils/coTraderLogic';

export interface AgentifyFeedbackPanelProps {
  symbol: string;
  currentTime: number | null;
  clockMode: ClockMode;
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

  const handleSubmit = () => {
    if (!title.trim()) {
      setErrorMsg('Please enter a descriptive title for this feedback case.');
      return;
    }
    setErrorMsg(null);

    const targetTime = timestamp ?? currentTime ?? Math.floor(Date.now() / 1000);

    startTransition(async () => {
      try {
        const res = await replayApi.createFeedbackCase({
          symbol,
          timestamp: targetTime,
          title: title.trim(),
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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto', padding: '12px', gap: '12px', backgroundColor: '#181b24', color: '#d1d4dc', fontSize: '12px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #2a2e39', paddingBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Sparkles size={16} style={{ color: '#00e676' }} />
          <span style={{ fontWeight: 700, fontSize: '13px', color: '#ffffff' }}>Agentify Feedback Bridge</span>
        </div>
        <button
          onClick={loadCases}
          title="Refresh cases"
          style={{ background: 'transparent', border: 'none', color: '#787b86', cursor: 'pointer', padding: '2px' }}
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Toast Notification */}
      {showToast && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: 'rgba(38, 166, 154, 0.2)', border: '1px solid #26a69a', padding: '8px 10px', borderRadius: '4px', color: '#26a69a', fontWeight: 600, fontSize: '11px' }}>
          <CheckCircle2 size={14} />
          Copied Antigravity Alignment Prompt to Clipboard!
        </div>
      )}

      {/* Error Banner */}
      {errorMsg && (
        <div style={{ backgroundColor: 'rgba(239, 83, 80, 0.15)', border: '1px solid #ef5350', padding: '6px 10px', borderRadius: '4px', color: '#ff8a80', fontSize: '11px' }}>
          {errorMsg}
        </div>
      )}

      {/* New Feedback Form Card */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', backgroundColor: '#1e222d', padding: '12px', borderRadius: '6px', border: '1px solid #2a2e39' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 600, color: '#e0e3eb' }}>Capture Forensic Case</span>
          <span style={{ fontSize: '10px', color: '#787b86' }}>
            {timestamp !== null ? formatClockTick(timestamp, clockMode, true) : 'Current Bar'}
          </span>
        </div>

        {/* Category Picker */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <label style={{ fontSize: '10px', color: '#787b86', fontWeight: 600 }}>CATEGORY</label>
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
                    backgroundColor: isSel ? '#2962ff' : '#131722',
                    color: isSel ? '#ffffff' : '#b2b5be',
                    border: `1px solid ${isSel ? '#2962ff' : '#2a2e39'}`,
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
          <label style={{ fontSize: '10px', color: '#787b86', fontWeight: 600 }}>TITLE</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Nov 11 Gold London Judas Sweep missed by screener"
            style={{
              padding: '6px 8px',
              fontSize: '11px',
              backgroundColor: '#131722',
              border: '1px solid #2a2e39',
              borderRadius: '4px',
              color: '#ffffff',
              outline: 'none',
            }}
          />
        </div>

        {/* Archetype Input */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <label style={{ fontSize: '10px', color: '#787b86', fontWeight: 600 }}>ARCHETYPE REF (OPTIONAL)</label>
          <input
            type="text"
            value={archetypeId}
            onChange={(e) => setArchetypeId(e.target.value)}
            placeholder="e.g. SETUP-ARCH-001 or SETUP-ARCH-013"
            style={{
              padding: '6px 8px',
              fontSize: '11px',
              backgroundColor: '#131722',
              border: '1px solid #2a2e39',
              borderRadius: '4px',
              color: '#ffffff',
              outline: 'none',
            }}
          />
        </div>

        {/* Rationale Textarea */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <label style={{ fontSize: '10px', color: '#787b86', fontWeight: 600 }}>RATIONALE & HUMAN FORENSICS</label>
          <textarea
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="Describe what bot should have seen, why veto was incorrect, or how entry/stop was improved..."
            style={{
              padding: '6px 8px',
              fontSize: '11px',
              backgroundColor: '#131722',
              border: '1px solid #2a2e39',
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
            backgroundColor: '#00e676',
            color: '#121418',
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', backgroundColor: '#131722', padding: '10px', borderRadius: '6px', border: '1px solid #2a2e39' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#90caf9', fontWeight: 600 }}>
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
                border: '1px solid #2a2e39',
                borderRadius: '3px',
                color: '#d1d4dc',
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
              color: '#a0a3b0',
              maxHeight: '120px',
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              backgroundColor: '#181b24',
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
          <span style={{ fontWeight: 600, color: '#e0e3eb', fontSize: '12px' }}>
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
                    backgroundColor: '#1e222d',
                    borderRadius: '6px',
                    border: '1px solid #2a2e39',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '10px', fontWeight: 600, color: '#00e676', backgroundColor: 'rgba(0, 230, 118, 0.1)', padding: '1px 5px', borderRadius: '3px' }}>
                      {c.case_id}
                    </span>
                    <span style={{ fontSize: '10px', color: '#787b86' }}>
                      {formatClockTick(c.timestamp, clockMode, false)}
                    </span>
                  </div>

                  <div style={{ fontWeight: 600, color: '#ffffff', fontSize: '11px' }}>
                    {c.title}
                  </div>

                  {c.notes && (
                    <div style={{ color: '#a0a3b0', fontSize: '10px', lineHeight: '1.3' }}>
                      {c.notes}
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px', paddingTop: '4px', borderTop: '1px solid #262b36' }}>
                    <button
                      onClick={() => handleCopyText(casePrompt)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '3px',
                        background: isCopied ? '#26a69a' : '#2962ff',
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
                        border: '1px solid rgba(239, 83, 80, 0.4)',
                        color: '#ef5350',
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
          <div style={{ padding: '14px', textAlign: 'center', color: '#787b86', fontSize: '11px', backgroundColor: '#1e222d', borderRadius: '6px' }}>
            <MessageSquarePlus size={18} style={{ opacity: 0.5, marginBottom: '4px' }} />
            <div>No feedback cases recorded yet.</div>
            <div style={{ fontSize: '10px', color: '#565a65', marginTop: '2px' }}>
              Capture a case above to generate prompt markdown for Antigravity.
            </div>
          </div>
        )}
      </div>

      {/* Guide Note */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', backgroundColor: '#131722', padding: '8px', borderRadius: '4px', border: '1px solid #2a2e39', color: '#787b86', fontSize: '10px', lineHeight: '1.4' }}>
        <HelpCircle size={14} style={{ flexShrink: 0, marginTop: '1px' }} />
        <span>
          Feedback cases are saved directly into <code>hitl/memory/visual_feedback_cases.json</code>. The copied prompt can be pasted directly into Antigravity to calibrate Python screener rules without documentation drift.
        </span>
      </div>
    </div>
  );
};

export default AgentifyFeedbackPanel;
