//+------------------------------------------------------------------+
//| TradingGuard.mq5 — Behavioral Enforcement Expert Advisor          |
//| Reads session.json from the Python bridge, enforces risk rules,   |
//| and writes trade results back.                                     |
//+------------------------------------------------------------------+
#property copyright "TradingGuard"
#property version   "1.00"
#property strict

#include "JAson.mqh"

//+------------------------------------------------------------------+
//| Input Parameters                                                   |
//+------------------------------------------------------------------+
input string   InpSessionFile   = "session.json";  // Bridge file name (in MQL5\Files or Common)
input double   InpRiskPerTrade  = 12.0;      // Max $ loss per trade
input double   InpMaxDailyLoss  = 24.0;      // Daily loss shutdown ($)
input double   InpMaxDailyProfit= 35.0;      // Daily profit lock ($)
input int      InpMaxTrades     = 3;         // Max trades per day
input int      InpMaxConsecLoss = 2;         // Stop after N consecutive losses
input int      InpCooldownMin   = 15;        // Cooldown minutes after trade
input int      InpCooldownExtra = 10;        // Extra cooldown after a loss
input double   InpDefaultSL     = 50.0;      // Default stop-loss in points (if none)

//+------------------------------------------------------------------+
//| Global State                                                       |
//+------------------------------------------------------------------+
CJAVal  g_session;              // parsed session.json
datetime g_lastRead      = 0;   // throttle file reads
int      g_readInterval  = 2;   // seconds between reads

// Daily tracking (in-EA, synced to JSON)
double   g_dailyLoss     = 0.0;
double   g_dailyProfit   = 0.0;
int      g_tradesToday   = 0;
int      g_consecLosses  = 0;
bool     g_tradingAllowed= false;
bool     g_shutdownDone  = false;
datetime g_cooldownUntil = 0;
string   g_bias          = "neutral";
bool     g_newsLock      = false;

// File path — we look in both MQL5\Files and actual disk path
string   g_filePath      = "";

//+------------------------------------------------------------------+
//| Expert initialization                                              |
//+------------------------------------------------------------------+
int OnInit()
{
    g_filePath = InpSessionFile;

    // Try to read session on init
    if (!ReadSession())
    {
        Print("⚠ TradingGuard: Could not read ", g_filePath,
              " — will retry on ticks.");
    }
    else
    {
        SyncFromSession();
        Print("✅ TradingGuard initialized. Session loaded.");
    }

    // Initial chart panel
    UpdateChartPanel();
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                            |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Comment("");  // clear chart panel
}

//+------------------------------------------------------------------+
//| Expert tick function                                                |
//+------------------------------------------------------------------+
void OnTick()
{
    // ── 1. Throttled session read ────────────────────────────────────
    if (TimeCurrent() - g_lastRead >= g_readInterval)
    {
        if (ReadSession())
            SyncFromSession();
        g_lastRead = TimeCurrent();
    }

    // ── 2. Shutdown already done? ────────────────────────────────────
    if (g_shutdownDone)
    {
        UpdateChartPanel();
        return;
    }

    // ── 3. Check if trading is allowed ───────────────────────────────
    if (!g_tradingAllowed || g_newsLock)
    {
        UpdateChartPanel();
        return;
    }

    // ── 4. Check cooldown ────────────────────────────────────────────
    if (g_cooldownUntil > 0 && TimeCurrent() < g_cooldownUntil)
    {
        UpdateChartPanel();
        return;
    }

    // ── 5. Monitor open positions for $12 max loss ───────────────────
    MonitorOpenPositions();

    // ── 6. Check daily limits ────────────────────────────────────────
    CheckDailyLimits();

    // ── 7. Update chart ──────────────────────────────────────────────
    UpdateChartPanel();
}

//+------------------------------------------------------------------+
//| Trade transaction handler                                          |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
    // We care about deal additions (trade closed)
    if (trans.type != TRADE_TRANSACTION_DEAL_ADD)
        return;

    // Get deal info
    ulong dealTicket = trans.deal;
    if (dealTicket == 0) return;

    // Make sure the deal is on our symbol
    if (trans.symbol != _Symbol) return;

    ENUM_DEAL_ENTRY dealEntry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
    if (dealEntry != DEAL_ENTRY_OUT && dealEntry != DEAL_ENTRY_INOUT)
        return;  // only care about closing deals

    double dealProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
    double dealSwap   = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
    double dealComm   = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
    double netPnl     = dealProfit + dealSwap + dealComm;

    // Update daily tracking
    g_tradesToday++;
    if (netPnl >= 0)
    {
        g_dailyProfit += netPnl;
        g_consecLosses = 0;
    }
    else
    {
        g_dailyLoss += MathAbs(netPnl);
        g_consecLosses++;
    }

    // Set cooldown
    int cooldownSec = InpCooldownMin * 60;
    if (netPnl < 0)
        cooldownSec += InpCooldownExtra * 60;
    g_cooldownUntil = TimeCurrent() + cooldownSec;

    // Write results back to session.json
    string lastResult = (netPnl >= 0) ? "win" : "loss";
    WriteSessionUpdate(lastResult);

    Print("📊 Trade closed: $", DoubleToString(netPnl, 2),
          " | Today: ", g_tradesToday, " trades",
          " | Loss: $", DoubleToString(g_dailyLoss, 2),
          " | Profit: $", DoubleToString(g_dailyProfit, 2));

    // Immediate limit check after trade
    CheckDailyLimits();
    UpdateChartPanel();
}

//+------------------------------------------------------------------+
//| Read session.json into g_session                                   |
//+------------------------------------------------------------------+
bool ReadSession()
{
    // Read directly into g_session — avoids dangling pointers
    // from a local CJAVal going out of scope and deleting children.
    g_session.Clear();
    if (g_session.ReadFromFile(g_filePath))
        return true;
    return false;
}

//+------------------------------------------------------------------+
//| Sync local vars from parsed session                                |
//+------------------------------------------------------------------+
void SyncFromSession()
{
    if (g_session["trading_allowed"] != NULL)
        g_tradingAllowed = g_session["trading_allowed"].ToBool();
    if (g_session["news_lock"] != NULL)
        g_newsLock = g_session["news_lock"].ToBool();
    if (g_session["bias"] != NULL)
        g_bias = g_session["bias"].GetStr();
    if (g_session["shutdown_signal"] != NULL && g_session["shutdown_signal"].ToBool())
        g_shutdownDone = true;

    // Sync daily values from JSON (in case Python app set them)
    if (g_session["daily_loss_usd"] != NULL)
        g_dailyLoss = g_session["daily_loss_usd"].ToDouble();
    if (g_session["daily_profit_usd"] != NULL)
        g_dailyProfit = g_session["daily_profit_usd"].ToDouble();
    if (g_session["trades_today"] != NULL)
        g_tradesToday = (int)g_session["trades_today"].ToInt();
    if (g_session["consecutive_losses"] != NULL)
        g_consecLosses = (int)g_session["consecutive_losses"].ToInt();
}

//+------------------------------------------------------------------+
//| Write updated values back to session.json                          |
//+------------------------------------------------------------------+
void WriteSessionUpdate(string lastResult = "")
{
    g_session["daily_loss_usd"].Set(g_dailyLoss);
    g_session["daily_profit_usd"].Set(g_dailyProfit);
    g_session["trades_today"].Set((long)g_tradesToday);
    g_session["consecutive_losses"].Set((long)g_consecLosses);

    // Format cooldown time
    if (g_cooldownUntil > 0 && TimeCurrent() < g_cooldownUntil)
    {
        MqlDateTime dt;
        TimeToStruct(g_cooldownUntil, dt);
        g_session["cooldown_until"].Set(
            StringFormat("%02d:%02d:%02d", dt.hour, dt.min, dt.sec));
    }
    else
    {
        g_session["cooldown_until"].Set("");
    }

    if (lastResult != "")
        g_session["last_trade_result"].Set(lastResult);

    // Timestamp
    g_session["timestamp"].Set(TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS));

    g_session.WriteToFile(g_filePath);
}

//+------------------------------------------------------------------+
//| Monitor open positions — force close if floating loss >= $12       |
//+------------------------------------------------------------------+
void MonitorOpenPositions()
{
    for (int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

        double floatingPnl = PositionGetDouble(POSITION_PROFIT)
                           + PositionGetDouble(POSITION_SWAP);

        if (floatingPnl <= -InpRiskPerTrade)
        {
            Print("🛑 Force closing position #", ticket,
                  " — floating loss $", DoubleToString(MathAbs(floatingPnl), 2));
            ForceClosePosition(ticket);
        }
    }
}

//+------------------------------------------------------------------+
//| Force close a position by ticket                                   |
//+------------------------------------------------------------------+
void ForceClosePosition(ulong ticket)
{
    if (!PositionSelectByTicket(ticket)) return;

    MqlTradeRequest request = {};
    MqlTradeResult  result = {};

    request.action   = TRADE_ACTION_DEAL;
    request.position = ticket;
    request.symbol   = PositionGetString(POSITION_SYMBOL);
    request.volume   = PositionGetDouble(POSITION_VOLUME);
    request.deviation= 20;

    ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)
        PositionGetInteger(POSITION_TYPE);
    if (posType == POSITION_TYPE_BUY)
    {
        request.type  = ORDER_TYPE_SELL;
        request.price = SymbolInfoDouble(request.symbol, SYMBOL_BID);
    }
    else
    {
        request.type  = ORDER_TYPE_BUY;
        request.price = SymbolInfoDouble(request.symbol, SYMBOL_ASK);
    }

    if (!OrderSend(request, result))
        Print("❌ Force close failed: ", GetLastError());
}

//+------------------------------------------------------------------+
//| Check daily limits and trigger shutdown if breached                 |
//+------------------------------------------------------------------+
void CheckDailyLimits()
{
    if (g_shutdownDone) return;

    bool shouldShutdown = false;
    string reason = "";

    if (g_dailyLoss >= InpMaxDailyLoss)
    {
        shouldShutdown = true;
        reason = "Daily loss limit ($" + DoubleToString(InpMaxDailyLoss, 0) + ") reached";
    }
    else if (g_dailyProfit >= InpMaxDailyProfit)
    {
        shouldShutdown = true;
        reason = "Daily profit target ($" + DoubleToString(InpMaxDailyProfit, 0) + ") reached";
    }
    else if (g_tradesToday >= InpMaxTrades)
    {
        shouldShutdown = true;
        reason = "Max trades (" + IntegerToString(InpMaxTrades) + ") reached";
    }
    else if (g_consecLosses >= InpMaxConsecLoss)
    {
        shouldShutdown = true;
        reason = "Consecutive losses (" + IntegerToString(InpMaxConsecLoss) + ") reached";
    }

    if (shouldShutdown)
    {
        Print("🛑 SHUTDOWN: ", reason);

        // Close all open positions
        CloseAllPositions();

        // Signal shutdown
        g_shutdownDone = true;
        g_tradingAllowed = false;
        g_session["shutdown_signal"].Set(true);
        g_session["trading_allowed"].Set(false);
        g_session["session_active"].Set(false);
        WriteSessionUpdate();
    }
}

//+------------------------------------------------------------------+
//| Close all open positions on current symbol                         |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
    for (int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
        ForceClosePosition(ticket);
    }
}

//+------------------------------------------------------------------+
//| Calculate lot size based on dollar risk                            |
//+------------------------------------------------------------------+
double CalculateLotSize(double slPoints)
{
    if (slPoints <= 0) slPoints = InpDefaultSL;

    double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double minLot    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double lotStep   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

    if (tickValue <= 0 || tickSize <= 0) return minLot;

    double lot = InpRiskPerTrade / (slPoints * tickValue / tickSize);

    // Round to lot step
    lot = MathFloor(lot / lotStep) * lotStep;
    lot = MathMax(lot, minLot);
    lot = MathMin(lot, maxLot);

    return NormalizeDouble(lot, 2);
}

//+------------------------------------------------------------------+
//| Update on-chart status panel                                       |
//+------------------------------------------------------------------+
void UpdateChartPanel()
{
    double netPnl = g_dailyProfit - g_dailyLoss;
    int tradesLeft = InpMaxTrades - g_tradesToday;

    string cooldownStr = "None";
    if (g_cooldownUntil > 0 && TimeCurrent() < g_cooldownUntil)
    {
        int secLeft = (int)(g_cooldownUntil - TimeCurrent());
        int min = secLeft / 60;
        int sec = secLeft % 60;
        cooldownStr = StringFormat("%02d:%02d", min, sec);
    }

    string panel = "";
    panel += "═══════════════════════════════\n";
    panel += "       TRADING GUARD v1.0\n";
    panel += "═══════════════════════════════\n";
    panel += "\n";

    if (g_shutdownDone)
        panel += "  ⛔  SESSION ENDED — LIMITS HIT\n\n";
    else if (!g_tradingAllowed)
        panel += "  🚫  TRADING DISABLED\n\n";
    else if (g_newsLock)
        panel += "  🔒  NEWS LOCK ACTIVE\n\n";
    else
        panel += "  ✅  TRADING ACTIVE\n\n";

    panel += "  Bias:           " + g_bias + "\n";
    panel += "  Trades Today:   " + IntegerToString(g_tradesToday) +
             " / " + IntegerToString(InpMaxTrades) +
             "  (" + IntegerToString(tradesLeft) + " left)\n";
    panel += "  Daily P&L:      $" + DoubleToString(netPnl, 2) + "\n";
    panel += "  Daily Loss:     $" + DoubleToString(g_dailyLoss, 2) +
             " / $" + DoubleToString(InpMaxDailyLoss, 0) + "\n";
    panel += "  Daily Profit:   $" + DoubleToString(g_dailyProfit, 2) +
             " / $" + DoubleToString(InpMaxDailyProfit, 0) + "\n";
    panel += "  Consec Losses:  " + IntegerToString(g_consecLosses) +
             " / " + IntegerToString(InpMaxConsecLoss) + "\n";
    panel += "  Cooldown:       " + cooldownStr + "\n";
    panel += "  News Lock:      " + (g_newsLock ? "ON" : "OFF") + "\n";
    panel += "\n";
    panel += "═══════════════════════════════\n";

    Comment(panel);
}
//+------------------------------------------------------------------+
