/**
 * TradingGuard HITL Visual Co-Backtester - TypeScript Domain Types
 * Exactly mirrors Tornado backend JSON schemas and lightweight-charts schemas.
 */

export type ClockMode = 'tehran' | 'utc' | 'server';
export type EngineClockMode = 'true_tehran' | 'live_legacy';
export type TradeOrigin = 'BOT' | 'HUMAN_PROPOSED' | 'HUMAN_EDITED_BOT';
export type TradeDirection = 'LONG' | 'SHORT';
export type TradeStatus = 'PENDING' | 'OPEN' | 'WIN' | 'LOSS' | 'BREAKEVEN' | 'INVALID_PARAMS';
export type Timeframe = '1M' | '5M' | '15M' | '1H' | '4H' | '1D';

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface CatalogSymbol {
  symbol: string;
  display_name: string;
  engine_mode: 'SMC' | 'MANUAL_ONLY';
  uncalibrated: boolean;
  spread_pts: number;
  digits: number;
  min_epoch?: number;
  max_epoch?: number;
  min_date?: string;
  max_date?: string;
  total_m1_bars?: number;
}

export interface CatalogResponse {
  symbols: CatalogSymbol[];
  system_risk_limits: {
    account_size_usd: number;
    max_risk_usd: number;
  };
  account_size_usd: number;
  max_risk_usd: number;
}

export interface Killzone {
  name: string;
  label: string;
  start_time: number;
  end_time: number;
  color: string;
}

export interface AsianRangeDay {
  date: string;
  high: number;
  low: number;
  start_time: number;
  end_time: number;
  bars_count: number;
}

export interface FvgBox {
  top: number;
  bottom: number;
  t_start: number;
  t_end: number;
  dir: 'BULLISH' | 'BEARISH';
}

export interface BreakerBox {
  top: number;
  bottom: number;
  t_start: number;
  t_end: number;
  type: string;
}

export interface BotDiagnostic {
  time: number;
  session_hour: number;
  has_setup: boolean;
  archetype_id?: string;
  setup_type: string;
  reason: string;
  phase: string;
  asian_high?: number;
  asian_low?: number;
  fvg_box?: FvgBox | null;
  breaker_box?: BreakerBox | null;
}

export interface BotEvent {
  time: number;
  type: string;
  description: string;
}

export interface ReplayTrade {
  id?: string;
  trade_id: string;
  symbol: string;
  origin: TradeOrigin;
  direction: TradeDirection;
  decision_time: number;
  entry: number;
  sl: number;
  tp: number;
  be_rr?: number | null;
  status: TradeStatus;
  realized_pnl_usd?: number | null;
  rr_realized?: number | null;
  fill_time?: number | null;
  exit_time?: number | null;
  risk_usd_001?: number;
  exceeds_risk_cap?: boolean;
  notes?: string;
  target_optimization?: Record<string, unknown> | null;
  parent_bot_ref?: string | null;
  archetype_id?: string;
  created_at?: string;
}

export interface Scorecard {
  total_trades: number;
  wins: number;
  losses: number;
  breakevens: number;
  win_rate_pct: number;
  net_pnl_usd: number;
  net_rr: number;
  profit_factor: number;
  max_drawdown_usd: number;
}

export interface BotScanResponse {
  killzones: Killzone[];
  asian_ranges_by_day: Record<string, AsianRangeDay>;
  diagnostics: BotDiagnostic[];
  events: BotEvent[];
  bot_trades: ReplayTrade[];
  bot_scorecard: Scorecard;
}

export interface CoTradesResponse {
  trades: ReplayTrade[];
  scorecard: {
    BOT?: Scorecard;
    HUMAN_PROPOSED?: Scorecard;
    HUMAN_EDITED_BOT?: Scorecard;
    ALL?: Scorecard;
    [key: string]: Scorecard | undefined;
  };
}

export interface SimulateTradeRequest {
  symbol: string;
  direction: TradeDirection;
  signal_time: number;
  entry: number;
  sl: number;
  tp: number;
  be_rr?: number;
  max_risk_usd?: number;
  horizon_end?: number;
  lot?: number;
}

export interface SimulateTradeResponse {
  status: TradeStatus;
  realized_pnl_usd: number;
  rr_realized: number | null;
  fill_time: number | null;
  exit_time: number | null;
  risk_usd_001: number;
  exceeds_risk_cap: boolean;
  notes?: string;
  target_optimization?: Record<string, unknown> | null;
}

export interface FeedbackCase {
  id?: string;
  case_id: string;
  symbol: string;
  timestamp: number;
  title: string;
  notes?: string;
  prompt_markdown?: string;
  [key: string]: unknown;
}

export interface DraftTrade {
  direction: TradeDirection;
  entry: number;
  sl: number;
  tp: number;
  symbol?: string;
  signal_time?: number;
}
