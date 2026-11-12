import { useState, useMemo } from 'react';
import { ReplayChart } from './components/ReplayChart';
import type {
  Candle,
  ClockMode,
  DraftTrade,
  Killzone,
  ReplayTrade,
} from './types/replay';
import { Clock, TrendingUp, TrendingDown } from 'lucide-react';

// Generates synthetic sample bars for initial standalone view
function generateSampleCandles(): Candle[] {
  const baseTime = 1768485600; // Jan 15, 2026 14:00 server
  const candles: Candle[] = [];
  let price = 2680.0;

  for (let i = 0; i < 80; i++) {
    const t = baseTime + i * 300; // 5M bars
    const change = (Math.sin(i / 5) * 1.5 + (Math.random() - 0.48) * 2.0);
    const open = Number(price.toFixed(2));
    const close = Number((price + change).toFixed(2));
    const high = Number((Math.max(open, close) + Math.random() * 1.2).toFixed(2));
    const low = Number((Math.min(open, close) - Math.random() * 1.2).toFixed(2));
    price = close;
    candles.push({ time: t, open, high, low, close, volume: 100 + Math.floor(Math.random() * 50) });
  }
  return candles;
}

export function App() {
  const [clockMode, setClockMode] = useState<ClockMode>('tehran');
  const [draftTrade, setDraftTrade] = useState<DraftTrade | null>({
    direction: 'LONG',
    entry: 2682.0,
    sl: 2674.0,
    tp: 2698.0,
    symbol: 'XAUUSD_o',
    signal_time: 1768488600,
  });

  const candles = useMemo(() => generateSampleCandles(), []);

  const sampleKillzones: Killzone[] = useMemo(() => [
    {
      name: 'London Open',
      label: 'London Open (11:30)',
      start_time: 1768485600,
      end_time: 1768492800,
      color: 'rgba(41, 98, 255, 0.12)',
    },
    {
      name: 'NY Open',
      label: 'NY Open (16:30)',
      start_time: 1768496400,
      end_time: 1768503600,
      color: 'rgba(255, 109, 0, 0.12)',
    },
  ], []);

  const sampleTrades: ReplayTrade[] = useMemo(() => [
    {
      trade_id: 'BOT-XAUUSD_o-01',
      symbol: 'XAUUSD_o',
      origin: 'BOT',
      direction: 'LONG',
      decision_time: 1768487400,
      fill_time: 1768488000,
      exit_time: 1768494000,
      entry: 2679.5,
      sl: 2674.0,
      tp: 2696.0,
      status: 'WIN',
      realized_pnl_usd: 16.5,
      rr_realized: 3.0,
      risk_usd_001: 5.5,
      exceeds_risk_cap: false,
    },
  ], []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh', backgroundColor: '#131722' }}>
      {/* Top Header Placeholder */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 16px',
          borderBottom: '1px solid #2b2b43',
          backgroundColor: '#1e222d',
          minHeight: '44px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontWeight: 700, fontSize: '14px', letterSpacing: '0.5px', color: '#f0b90b' }}>
            TradingGuard
          </span>
          <span style={{ color: '#787b86', fontSize: '12px' }}>|</span>
          <span style={{ fontWeight: 600, fontSize: '13px', color: '#e0e3eb' }}>
            Visual Co-Backtester
          </span>
          <span
            style={{
              fontSize: '11px',
              padding: '2px 6px',
              borderRadius: '4px',
              backgroundColor: 'rgba(38, 166, 154, 0.2)',
              color: '#26a69a',
              fontWeight: 500,
            }}
          >
            SMC Active
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Clock Mode Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#131722', padding: '2px 4px', borderRadius: '4px', border: '1px solid #2b2b43' }}>
            <Clock size={14} style={{ color: '#787b86', marginLeft: '4px' }} />
            {(['tehran', 'utc', 'server'] as ClockMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setClockMode(mode)}
                style={{
                  padding: '3px 8px',
                  fontSize: '11px',
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

          {/* Position Tools */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={() =>
                setDraftTrade({
                  direction: 'LONG',
                  entry: 2682.0,
                  sl: 2674.0,
                  tp: 2698.0,
                  symbol: 'XAUUSD_o',
                })
              }
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '4px 10px',
                fontSize: '11px',
                fontWeight: 600,
                backgroundColor: 'rgba(38, 166, 154, 0.2)',
                color: '#26a69a',
                border: '1px solid rgba(38, 166, 154, 0.4)',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              <TrendingUp size={13} />
              + Long
            </button>
            <button
              onClick={() =>
                setDraftTrade({
                  direction: 'SHORT',
                  entry: 2682.0,
                  sl: 2690.0,
                  tp: 2666.0,
                  symbol: 'XAUUSD_o',
                })
              }
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '4px 10px',
                fontSize: '11px',
                fontWeight: 600,
                backgroundColor: 'rgba(239, 83, 80, 0.2)',
                color: '#ef5350',
                border: '1px solid rgba(239, 83, 80, 0.4)',
                borderRadius: '4px',
                cursor: 'pointer',
              }}
            >
              <TrendingDown size={13} />
              + Short
            </button>
          </div>
        </div>
      </header>

      {/* Main Chart Area */}
      <main style={{ flex: 1, position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
        <ReplayChart
          candles={candles}
          symbol="XAUUSD_o"
          digits={2}
          clockMode={clockMode}
          killzones={sampleKillzones}
          trades={sampleTrades}
          draftTrade={draftTrade}
          onDraftTradeChange={setDraftTrade}
        />
      </main>
    </div>
  );
}

export default App;
