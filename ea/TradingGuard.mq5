//+------------------------------------------------------------------+
//| TradingGuard.mq5 — Behavioral Enforcement Expert Advisor          |
//| Reads session.json from the Python bridge, enforces risk rules,   |
//| and writes trade results back.                                     |
//+------------------------------------------------------------------+
#property copyright "TradingGuard"
#property version   "1.00"
#property strict

#include "JAson.mqh"
#include <Trade\Trade.mqh>

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

// Trading hours (Tehran time: UTC+3:30)
input int      InpStartHour     = 11;        // Trading start hour (Tehran)
input int      InpEndHour       = 21;        // Trading end hour (Tehran)

// Daily break time (Tehran time)
input int      InpBreakHour     = 16;        // Daily break hour (Tehran)
input int      InpBreakMin      = 20;        // Daily break minute
input int      InpBreakDuration = 12;         // Break duration in minutes

//+------------------------------------------------------------------+
//| Global State                                                       |
//+------------------------------------------------------------------+
CJAVal  g_session;              // parsed session.json
datetime g_lastRead      = 0;   // throttle file reads
int      g_readInterval  = 2;   // seconds between reads

// Daily tracking (in-EA, synced to JSON)
double   g_dailyLoss       = 0.0;
double   g_dailyProfit     = 0.0;
int      g_tradesToday     = 0;
int      g_consecLosses    = 0;
int      g_lossesSinceBias = 0;
bool     g_tradingAllowed  = false;
bool     g_shutdownDone    = false;
datetime g_cooldownUntil   = 0;
datetime g_cooldownStart    = 0;   // when cooldown started (to avoid closing current trade)
string   g_bias            = "neutral";
bool     g_newsLock        = false;
bool     g_strictMode      = false;
bool     g_biasExpired     = false;

// Extended behavior: 1-hour break after consecutive losses
bool     g_breakActive     = false;

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
    // ── 1. Throttled session read (every 2 seconds) ─────────────────
    datetime now = TimeCurrent();
    if (now - g_lastRead >= g_readInterval)
    {
        if (ReadSession())
            SyncFromSession();
        g_lastRead = now;
    }

    // ── 2. Shutdown already done? ────────────────────────────────────
    if (g_shutdownDone)
    {
        UpdateChartPanel();
        return;
    }

    // ── 2a. Check trading hours (Tehran time: UTC+3:30) ───────────────
    MqlDateTime utcDT;
    TimeToStruct(TimeCurrent(), utcDT);
    int utcHour = utcDT.hour;
    int utcMin = utcDT.min;
    
    // Tehran is UTC+3:30
    int tehranHour = utcHour + 3;
    int tehranMin = utcMin + 30;
    if (tehranMin >= 60) { tehranMin -= 60; tehranHour += 1; }
    if (tehranHour >= 24) tehranHour -= 24;
    
    bool withinHours = (tehranHour > InpStartHour || (tehranHour == InpStartHour && tehranMin >= 0)) 
                   && (tehranHour < InpEndHour || (tehranHour == InpEndHour && tehranMin < 60));
    
    static bool hoursWarningShown = false;
    if (!withinHours && !hoursWarningShown)
    {
        Print("🛑 Outside trading hours. Tehran: ", tehranHour, ":", tehranMin, " Allowed: ", InpStartHour, "-", InpEndHour);
        hoursWarningShown = true;
    }
    else if (withinHours)
    {
        hoursWarningShown = false;
    }
    
    if (!withinHours)
    {
        // Close all positions if open during non-trading hours
        if (PositionsTotal() > 0)
            CloseAllPositions();
        UpdateChartPanel();
        return;
    }

    // ── 2b. Check daily break time (16:30 Tehran) ────────────────────────
    int breakStartMin = InpBreakHour * 60 + InpBreakMin;
    int breakEndMin = breakStartMin + InpBreakDuration;
    int tehranNowMin = tehranHour * 60 + tehranMin;
    
    bool isDailyBreak = (tehranNowMin >= breakStartMin && tehranNowMin < breakEndMin);
    
    static bool breakWarningShown = false;
    if (isDailyBreak && !breakWarningShown)
    {
        Print("🛑 Daily break started. Tehran: ", tehranHour, ":", tehranMin);
        breakWarningShown = true;
    }
    else if (!isDailyBreak)
    {
        breakWarningShown = false;
    }
    
    if (isDailyBreak)
    {
        // Just update panel - Python app will kill MT5
        UpdateChartPanel();
        return;
    }

    // ── 2c. Long break after consecutive losses ──────────────────────
    if (g_breakActive)
    {
        if (PositionsTotal() > 0)
        {
            Print("🛑 Break active - closing all positions");
            CloseAllPositions();
        }
        UpdateChartPanel();
        return;
    }

    // ── 2d. Check cooldown FIRST - close any positions opened BEFORE cooldown started
    if (g_cooldownUntil > 0 && now < g_cooldownUntil)
    {
        int secLeft = (int)(g_cooldownUntil - now);
        if (PositionsTotal() > 0)
        {
            // Only close positions that were opened BEFORE cooldown started
            for (int i = PositionsTotal() - 1; i >= 0; i--)
            {
                ulong ticket = PositionGetTicket(i);
                if (ticket == 0) continue;
                if (!PositionSelectByTicket(ticket)) continue;
                
                datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
                
                // Only close if position was opened BEFORE cooldown started
                if (openTime < g_cooldownStart)
                {
                    Print("🛑 Cooldown: closing position #", ticket);
                    ForceClosePosition(ticket);
                }
            }
        }
        // Only update panel every 5 seconds to reduce spam
        static datetime lastPanelUpdate = 0;
        if (now - lastPanelUpdate >= 5)
        {
            UpdateChartPanel();
            lastPanelUpdate = now;
        }
        return;
    }
    
    // Debug: show cooldown state
    static datetime lastDebug = 0;
    if (now - lastDebug >= 10)
    {
        Print("DEBUG: cooldownUntil=", g_cooldownUntil, " cooldownStart=", g_cooldownStart, " now=", now);
        lastDebug = now;
    }

    // ── 2e. Strict mode: close any opposite-bias positions immediately ───
    if (g_strictMode && (g_bias == "bullish" || g_bias == "bearish") && PositionsTotal() > 0)
    {
        // Only log and check occasionally
        static datetime lastStrictCheck = 0;
        if (now - lastStrictCheck >= 5)
        {
            Print("TG Strict: bias=", g_bias, " strict=", g_strictMode);
            lastStrictCheck = now;
        }
        for (int i = PositionsTotal() - 1; i >= 0; i--)
        {
            ulong ticket = PositionGetTicket(i);
            if (ticket == 0) continue;
            if (!PositionSelectByTicket(ticket)) continue;

            ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            bool opposite =
                (g_bias == "bullish" && posType == POSITION_TYPE_SELL) ||
                (g_bias == "bearish" && posType == POSITION_TYPE_BUY);

            if (opposite)
            {
                Print("🛑 Strict mode: closing opposite-bias position #", ticket, " type=", EnumToString(posType));
                ForceClosePosition(ticket);
            }
        }
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
        // During cooldown, no trades are allowed. If the user manages to open
        // a position manually, close it immediately so that manual attempts
        // are effectively ignored.
        if (PositionsTotal() > 0)
            CloseAllPositions();

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
    // Diagnostic: confirm we are receiving trade events at all.
    // (Shows up in the MT5 Experts log.)
    Print("TG OnTradeTransaction: type=", (int)trans.type,
          " deal=", (ulong)trans.deal,
          " pos=", (ulong)trans.position,
          " symbol=", trans.symbol);

    // We care about deal additions (deals created in history)
    if (trans.type != TRADE_TRANSACTION_DEAL_ADD)
        return;

    // Get deal info
    ulong dealTicket = trans.deal;
    if (dealTicket == 0) return;

    // Ensure deal history is available; otherwise HistoryDealGet* can return defaults.
    datetime from = TimeCurrent() - 86400 * 7;
    datetime to   = TimeCurrent() + 60;
    if (!HistorySelect(from, to))
    {
        Print("TG: HistorySelect failed; cannot read deal details for ", (ulong)dealTicket);
        return;
    }
    if (!HistoryDealSelect(dealTicket))
    {
        Print("TG: HistoryDealSelect failed for deal ", (ulong)dealTicket);
        return;
    }

    ENUM_DEAL_ENTRY dealEntry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dealTicket, DEAL_ENTRY);

    // Strict mode: block opposite-direction entries immediately.
    if (dealEntry == DEAL_ENTRY_IN && g_strictMode && (g_bias == "bullish" || g_bias == "bearish"))
    {
        ENUM_DEAL_TYPE dealType = (ENUM_DEAL_TYPE)HistoryDealGetInteger(dealTicket, DEAL_TYPE);
        bool isBuy  = (dealType == DEAL_TYPE_BUY);
        bool isSell = (dealType == DEAL_TYPE_SELL);
        bool opposite =
            (g_bias == "bullish" && isSell) ||
            (g_bias == "bearish" && isBuy);

        if (opposite)
        {
            Print("🛑 Strict mode: blocking opposite-bias deal ", (ulong)dealTicket,
                  " on symbol ", trans.symbol, " bias=", g_bias);
            
            // Try to close using position ticket from transaction
            ulong posTicket = trans.position;
            if (posTicket != 0)
                ForceClosePosition(posTicket);
            else
            {
                // Fallback: find position by symbol
                for (int i = PositionsTotal() - 1; i >= 0; i--)
                {
                    ulong ticket = PositionGetTicket(i);
                    if (ticket == 0) continue;
                    if (PositionGetString(POSITION_SYMBOL) == trans.symbol)
                    {
                        ForceClosePosition(ticket);
                        break;
                    }
                }
            }
            return;
        }
    }

    // When a trade OPENS, set base cooldown (15 minutes)
    if (dealEntry == DEAL_ENTRY_IN)
    {
        g_cooldownStart = TimeCurrent();
        g_cooldownUntil = g_cooldownStart + (InpCooldownMin * 60);
        WriteSessionUpdate();
        Print("📊 Trade opened — cooldown set: ", InpCooldownMin, " min, until ", g_cooldownUntil);
        
        // Force immediate panel update
        UpdateChartPanel();
        return;
    }

    // Some brokers/operations close via OUT_BY (close-by). For P&L and limits
    // we only care about closing deals.
    if (dealEntry != DEAL_ENTRY_OUT && dealEntry != DEAL_ENTRY_INOUT && dealEntry != DEAL_ENTRY_OUT_BY)
        return;

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
        g_lossesSinceBias++;
    }

    // Extend cooldown if trade was a loss (add extra 10 min to current cooldown)
    if (netPnl < 0 && g_cooldownUntil > TimeCurrent())
    {
        g_cooldownUntil += InpCooldownExtra * 60;
        Print("📊 Trade closed at loss — added ", InpCooldownExtra, " min extra cooldown");
    }
    else if (netPnl < 0)
    {
        // No active cooldown, set base + extra for loss
        g_cooldownUntil = TimeCurrent() + (InpCooldownMin + InpCooldownExtra) * 60;
    }

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
    if (g_session["strict_mode"] != NULL)
        g_strictMode = g_session["strict_mode"].ToBool();
    if (g_session["bias_expired"] != NULL)
        g_biasExpired = g_session["bias_expired"].ToBool();
    if (g_session["break_active"] != NULL)
        g_breakActive = g_session["break_active"].ToBool();
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
    if (g_session["losses_since_bias"] != NULL)
        g_lossesSinceBias = (int)g_session["losses_since_bias"].ToInt();
    
    // Sync cooldown from session.json - read minutes remaining
    // Only use if we don't have an active cooldown in memory
    if (g_cooldownUntil == 0 || g_cooldownUntil <= TimeCurrent())
    {
        string cooldownStr = "0";
        if (g_session["cooldown_until"] != NULL)
            cooldownStr = g_session["cooldown_until"].GetStr();
        
        int minLeft = (int)StringToInteger(cooldownStr);
        
        // Only accept reasonable values (1-60 minutes)
        if (minLeft > 0 && minLeft <= 60)
        {
            g_cooldownUntil = TimeCurrent() + minLeft * 60;
            g_cooldownStart = g_cooldownUntil - minLeft * 60;
            Print("📊 Loaded cooldown: ", minLeft, " minutes");
        }
    }
    
    // Debug: Print sync values
    Print("TG Sync: bias=", g_bias, " strict=", g_strictMode, " cooldown_until=", g_cooldownUntil);
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
    g_session["losses_since_bias"].Set((long)g_lossesSinceBias);

    // Format cooldown time as minutes from now (e.g., "15" = 15 minutes)
    if (g_cooldownUntil > 0 && TimeCurrent() < g_cooldownUntil)
    {
        int minLeft = (int)((g_cooldownUntil - TimeCurrent()) / 60);
        g_session["cooldown_until"].Set(IntegerToString(minLeft)); // Simple format: minutes left
    }
    else
    {
        g_session["cooldown_until"].Set("0");
    }

    if (lastResult != "")
        g_session["last_trade_result"].Set(lastResult);

    // Timestamp
    g_session["timestamp"].Set(TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS));

    if (!g_session.WriteToFile(g_filePath))
    {
        Print("TG: FAILED to write session file: ", g_filePath);
    }
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

        // Strict mode: immediately close positions that are opposite to the
        // declared bias direction.
        if (g_strictMode && (g_bias == "bullish" || g_bias == "bearish"))
        {
            if (!PositionSelectByTicket(ticket))
                continue;

            ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)
                PositionGetInteger(POSITION_TYPE);

            bool opposite =
                (g_bias == "bullish" && posType == POSITION_TYPE_SELL) ||
                (g_bias == "bearish" && posType == POSITION_TYPE_BUY);

            if (opposite)
            {
                Print("🛑 Strict mode: closing opposite-bias position #", ticket);
                ForceClosePosition(ticket);
                continue;
            }
        }

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
//| Force close a position by ticket - using CTrade for reliability    |
//+------------------------------------------------------------------+
#include <Trade\Trade.mqh>
CTrade g_trade;  // Global trade object

void ForceClosePosition(ulong ticket)
{
    // Set larger deviation and faster execution
    g_trade.SetDeviationInPoints(100);
    g_trade.SetTypeFilling(ORDER_FILLING_IOC);
    
    // Try to close using CTrade
    bool result = g_trade.PositionClose(ticket);
    
    if (result)
    {
        Print("✅ Closed position #", ticket, " via CTrade");
    }
    else
    {
        Print("❌ CTrade close failed for #", ticket, " error: ", g_trade.ResultRetcode());
        
        // Fallback: try manual close
        if (!PositionSelectByTicket(ticket))
        {
            Print("❌ Could not select position #", ticket);
            return;
        }
        
        string symbol = PositionGetString(POSITION_SYMBOL);
        double volume = PositionGetDouble(POSITION_VOLUME);
        ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
        
        // Re-select for each retry to get fresh data
        for (int retry = 0; retry < 3; retry++)
        {
            if (!PositionSelectByTicket(ticket))
            {
                Print("✅ Position #", ticket, " no longer exists");
                return;
            }
            
            MqlTradeRequest request = {};
            MqlTradeResult tradeResult = {};

            request.action = TRADE_ACTION_DEAL;
            request.position = ticket;
            request.symbol = symbol;
            request.volume = volume;
            request.deviation = 100;
            request.type_filling = ORDER_FILLING_IOC;

            if (posType == POSITION_TYPE_BUY)
            {
                request.type = ORDER_TYPE_SELL;
                request.price = SymbolInfoDouble(symbol, SYMBOL_BID);
            }
            else
            {
                request.type = ORDER_TYPE_BUY;
                request.price = SymbolInfoDouble(symbol, SYMBOL_ASK);
            }

            if (OrderSend(request, tradeResult))
            {
                if (tradeResult.retcode == TRADE_RETCODE_DONE || tradeResult.retcode == TRADE_RETCODE_PLACED)
                {
                    Print("✅ Position #", ticket, " closed successfully (fallback)");
                    return;
                }
                else
                {
                    Print("⚠️ Close retcode: ", tradeResult.retcode);
                }
            }
            else
            {
                Print("⚠️ OrderSend error: ", GetLastError());
            }
            
            Sleep(500);
        }
    
        Print("❌ Force close failed after retries: #", ticket);
    }
}

//+------------------------------------------------------------------+
//| Check daily limits and trigger shutdown if breached                 |
//+------------------------------------------------------------------+
void CheckDailyLimits()
{
    if (g_shutdownDone) return;

    // After N consecutive losses, trigger full shutdown with 1-hour break.
    // MT5 will be killed by the Python app, and blocked from reopening for 1 hour.
    if (!g_shutdownDone && g_consecLosses >= InpMaxConsecLoss)
    {
        Print("🛑 SHUTDOWN: Consecutive losses (", g_consecLosses,
              ") reached. Killing MT5 for 1-hour break.");

        // Close all open positions
        CloseAllPositions();

        // Clear cooldown on shutdown
        g_cooldownUntil = 0;
        g_cooldownStart = 0;

        // Signal full shutdown - Python app will kill MT5 and enforce 1-hour wait
        g_shutdownDone = true;
        g_breakActive = true;
        g_tradingAllowed = false;

        g_session["shutdown_signal"].Set(true);
        g_session["break_active"].Set(true);
        g_session["trading_allowed"].Set(false);
        g_session["session_active"].Set(false);
        g_session["cooldown_until"].Set("");
        WriteSessionUpdate();
        return;
    }

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

    if (shouldShutdown)
    {
        Print("🛑 SHUTDOWN: ", reason);

        // Close all open positions
        CloseAllPositions();

        // Clear cooldown on shutdown
        g_cooldownUntil = 0;
        g_cooldownStart = 0;

        // Signal shutdown
        g_shutdownDone = true;
        g_tradingAllowed = false;
        g_session["shutdown_signal"].Set(true);
        g_session["trading_allowed"].Set(false);
        g_session["session_active"].Set(false);
        g_session["cooldown_until"].Set("");
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

    // Calculate Tehran time (UTC+3:30)
    MqlDateTime utcDT;
    TimeToStruct(TimeCurrent(), utcDT);
    int tehranHour = utcDT.hour + 3;
    int tehranMin = utcDT.min + 30;
    if (tehranMin >= 60) { tehranMin -= 60; tehranHour += 1; }
    if (tehranHour >= 24) tehranHour -= 24;
    
    bool withinHours = (tehranHour > InpStartHour || (tehranHour == InpStartHour && tehranMin >= 0)) 
                   && (tehranHour < InpEndHour || (tehranHour == InpEndHour && tehranMin < 60));

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
    panel += "  Tehran Time:    " + tehranHour + ":" + tehranMin + " (Trade " + (withinHours ? "OK" : "CLOSED") + ")\n";
    panel += "  Daily Break:    " + (isDailyBreak ? "ACTIVE" : "No") + "\n";
    panel += "\n";
    panel += "═══════════════════════════════\n";

    Comment(panel);
}
//+------------------------------------------------------------------+
