/**
 * TradingGuard HITL Visual Co-Backtester - Typed REST API Client
 * Wraps all Tornado backend endpoints (/api/catalog, /api/candles, /api/bot-scan,
 * /api/simulate-trade, /api/co-trades, /api/feedback, /api/sync-mt5).
 */

import type {
  BotScanResponse,
  Candle,
  CatalogResponse,
  CoTradesResponse,
  EngineClockMode,
  FeedbackCase,
  ReplayTrade,
  SimulateTradeRequest,
  SimulateTradeResponse,
  Timeframe,
} from '../types/replay';

const BASE_URL = ''; // Relative path, handled by Vite proxy in dev & Tornado in prod

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMsg = `HTTP Error ${res.status} ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson && errJson.error) {
        errorMsg = errJson.error;
      }
    } catch {
      // Non-JSON error body
    }
    throw new Error(errorMsg);
  }
  return res.json();
}

export const replayApi = {
  /**
   * Fetches the registered symbol catalog with cached date ranges and system risk limits.
   */
  async getCatalog(): Promise<CatalogResponse> {
    const res = await fetch(`${BASE_URL}/api/catalog`);
    return handleResponse<CatalogResponse>(res);
  },

  /**
   * Fetches causal candlestick series up to replay_to with zero-lookahead.
   */
  async getCandles(params: {
    symbol: string;
    tf: Timeframe;
    start: number;
    end: number;
    replay_to?: number | null;
    max_bars?: number;
  }): Promise<Candle[]> {
    const q = new URLSearchParams({
      symbol: params.symbol,
      tf: params.tf,
      start: String(params.start),
      end: String(params.end),
    });
    if (params.replay_to !== undefined && params.replay_to !== null) {
      q.set('replay_to', String(params.replay_to));
    }
    if (params.max_bars !== undefined) {
      q.set('max_bars', String(params.max_bars));
    }
    const res = await fetch(`${BASE_URL}/api/candles?${q.toString()}`);
    const data = await handleResponse<{ bars?: Candle[] } | Candle[]>(res);
    return Array.isArray(data) ? data : (data.bars ?? []);
  },

  /**
   * Runs chronological SMC forensic session scan over 5M bars with system risk governor.
   */
  async getBotScan(params: {
    symbol: string;
    start: number;
    end: number;
    clock_mode?: EngineClockMode;
    account_size?: number;
    max_risk?: number;
    horizon?: string;
  }): Promise<BotScanResponse> {
    const q = new URLSearchParams({
      symbol: params.symbol,
      start: String(params.start),
      end: String(params.end),
      clock_mode: params.clock_mode ?? 'true_tehran',
    });
    if (params.account_size !== undefined) {
      q.set('account_size', String(params.account_size));
    }
    if (params.max_risk !== undefined) {
      q.set('max_risk', String(params.max_risk));
    }
    if (params.horizon) {
      q.set('horizon', params.horizon);
    }
    const res = await fetch(`${BASE_URL}/api/bot-scan?${q.toString()}`);
    return handleResponse<BotScanResponse>(res);
  },

  /**
   * Simulates a human-proposed or edited trade setup using canonical M1 evaluator.
   */
  async simulateTrade(req: SimulateTradeRequest): Promise<SimulateTradeResponse> {
    const res = await fetch(`${BASE_URL}/api/simulate-trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<SimulateTradeResponse>(res);
  },

  /**
   * Fetches shared co-trade ledger and scorecard grouped by origin.
   */
  async getCoTrades(symbol?: string): Promise<CoTradesResponse> {
    const q = symbol ? `?symbol=${encodeURIComponent(symbol)}` : '';
    const res = await fetch(`${BASE_URL}/api/co-trades${q}`);
    return handleResponse<CoTradesResponse>(res);
  },

  /**
   * Adds a new trade record to the shared ledger.
   */
  async createCoTrade(trade: Partial<ReplayTrade>): Promise<ReplayTrade> {
    const res = await fetch(`${BASE_URL}/api/co-trades`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(trade),
    });
    return handleResponse<ReplayTrade>(res);
  },

  /**
   * Updates an existing trade record by trade_id.
   */
  async updateCoTrade(
    tradeId: string,
    patch: Partial<ReplayTrade>
  ): Promise<ReplayTrade> {
    const res = await fetch(`${BASE_URL}/api/co-trades/${encodeURIComponent(tradeId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    return handleResponse<ReplayTrade>(res);
  },

  /**
   * Deletes a trade record by trade_id.
   */
  async deleteCoTrade(tradeId: string): Promise<{ success: boolean; trade_id: string }> {
    const res = await fetch(`${BASE_URL}/api/co-trades/${encodeURIComponent(tradeId)}`, {
      method: 'DELETE',
    });
    return handleResponse<{ success: boolean; trade_id: string }>(res);
  },

  /**
   * Lists forensic Agentify feedback cases.
   */
  async getFeedbackCases(): Promise<{ cases: FeedbackCase[] }> {
    const res = await fetch(`${BASE_URL}/api/feedback`);
    return handleResponse<{ cases: FeedbackCase[] }>(res);
  },

  /**
   * Creates a new forensic Agentify feedback case and receives clipboard prompt markdown.
   */
  async createFeedbackCase(
    payload: Partial<FeedbackCase>
  ): Promise<{ case: FeedbackCase; prompt_markdown: string }> {
    const res = await fetch(`${BASE_URL}/api/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<{ case: FeedbackCase; prompt_markdown: string }>(res);
  },

  /**
   * Deletes an Agentify feedback case by case_id.
   */
  async deleteFeedbackCase(caseId: string): Promise<{ success: boolean; case_id: string }> {
    const res = await fetch(`${BASE_URL}/api/feedback/${encodeURIComponent(caseId)}`, {
      method: 'DELETE',
    });
    return handleResponse<{ success: boolean; case_id: string }>(res);
  },

  /**
   * Syncs latest M1 candles directly from MetaTrader 5 terminal.
   */
  async syncMt5(symbol: string, daysBack: number = 5): Promise<{ success: boolean; [key: string]: unknown }> {
    const res = await fetch(`${BASE_URL}/api/sync-mt5`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, days_back: daysBack }),
    });
    return handleResponse<{ success: boolean; [key: string]: unknown }>(res);
  },
};
