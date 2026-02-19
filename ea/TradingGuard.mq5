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

// Manual checklist (on-chart, before each trade)
input bool     InpEnforceChecklist = true;   // Block new entries until checklist is complete
input string   InpChecklist1   = "Trend aligned";
input string   InpChecklist2   = "Entry setup valid";
input string   InpChecklist3   = "SL/TP defined";
input string   InpChecklist4   = "Risk acceptable";

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
string   g_checklistItems[4];
bool     g_checklistState[4] = {false, false, false, false};
string   g_checkPrefix = "TG_CHECK_";
string   g_panelBgName = "TG_PANEL_BG";
string   g_panelLinePrefix = "TG_PANEL_LINE_";
int      g_panelMaxLines = 20;
int      g_panelWidth = 200;
int      g_panelHeight = 560;
int      g_panelX = 20;
int      g_panelY = 14;

//+------------------------------------------------------------------+
//| Expert initialization                                              |
//+------------------------------------------------------------------+
int OnInit()
{
    g_filePath = InpSessionFile;
    g_checklistItems[0] = InpChecklist1;
    g_checklistItems[1] = InpChecklist2;
    g_checklistItems[2] = InpChecklist3;
    g_checklistItems[3] = InpChecklist4;

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

    CreateChecklistButtons();

    // Initial chart panel
    UpdateChartPanel();
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                            |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    RemoveChecklistButtons();
    Comment("");  // clear chart panel
}

//+------------------------------------------------------------------+
//| Get Tehran clock from GMT (UTC+3:30)                             |
//+------------------------------------------------------------------+
void GetTehranTime(int &hour, int &minute)
{
    MqlDateTime gmtDT;
    TimeToStruct(TimeGMT(), gmtDT);

    hour = gmtDT.hour + 3;
    minute = gmtDT.min + 30;
    if (minute >= 60) { minute -= 60; hour += 1; }
    if (hour >= 24) hour -= 24;
}

int ChecklistDoneCount()
{
    int done = 0;
    for (int i = 0; i < 4; i++)
        if (g_checklistState[i]) done++;
    return done;
}

bool IsChecklistComplete()
{
    return ChecklistDoneCount() == 4;
}

int PanelLineYOffset(const int idx)
{
    // Base 18 px per row + extra gaps before section headers.
    int y = idx * 18;
    if (idx >= 4) y += 8;    // gap before Risk section
    if (idx >= 12) y += 8;   // gap before Time section
    if (idx >= 16) y += 8;   // gap before Checklist section
    return y;
}

void EnsureSidePanel()
{
    int chartWidth = (int)ChartGetInteger(0, CHART_WIDTH_IN_PIXELS, 0);
    if (chartWidth > 0)
        g_panelX = MathMax(10, chartWidth - g_panelWidth - 14);

    if (ObjectFind(0, g_panelBgName) < 0)
        ObjectCreate(0, g_panelBgName, OBJ_RECTANGLE_LABEL, 0, 0, 0);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_XDISTANCE, g_panelX);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_YDISTANCE, g_panelY);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_XSIZE, g_panelWidth);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_YSIZE, g_panelHeight);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_BGCOLOR, clrMidnightBlue);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_COLOR, clrSlateGray);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_BACK, false);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_SELECTABLE, false);
    ObjectSetInteger(0, g_panelBgName, OBJPROP_HIDDEN, true);

    for (int i = 0; i < g_panelMaxLines; i++)
    {
        string lineName = g_panelLinePrefix + IntegerToString(i);
        if (ObjectFind(0, lineName) < 0)
            ObjectCreate(0, lineName, OBJ_LABEL, 0, 0, 0);
        ObjectSetInteger(0, lineName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
        ObjectSetInteger(0, lineName, OBJPROP_XDISTANCE, g_panelX + 10);
        ObjectSetInteger(0, lineName, OBJPROP_YDISTANCE, g_panelY + 10 + PanelLineYOffset(i));
        ObjectSetInteger(0, lineName, OBJPROP_COLOR, clrWhite);
        ObjectSetInteger(0, lineName, OBJPROP_FONTSIZE, 10);
        ObjectSetString(0, lineName, OBJPROP_FONT, "Consolas");
        ObjectSetInteger(0, lineName, OBJPROP_SELECTABLE, false);
        ObjectSetInteger(0, lineName, OBJPROP_HIDDEN, true);
    }
}

void UpdateChecklistButton(const int idx)
{
    string name = g_checkPrefix + IntegerToString(idx + 1);
    string mark = g_checklistState[idx] ? "[x] " : "[ ] ";
    ObjectSetString(0, name, OBJPROP_TEXT, mark + g_checklistItems[idx]);
}

void ResetChecklist()
{
    for (int i = 0; i < 4; i++)
    {
        g_checklistState[i] = false;
        UpdateChecklistButton(i);
    }
}

void CreateChecklistButtons()
{
    EnsureSidePanel();

    for (int i = 0; i < 4; i++)
    {
        string name = g_checkPrefix + IntegerToString(i + 1);
        ObjectDelete(0, name);
        ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0);
        ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
        ObjectSetInteger(0, name, OBJPROP_XDISTANCE, g_panelX + 10);
        ObjectSetInteger(0, name, OBJPROP_YDISTANCE, g_panelY + 410 + (i * 28));
        ObjectSetInteger(0, name, OBJPROP_XSIZE, g_panelWidth - 20);
        ObjectSetInteger(0, name, OBJPROP_YSIZE, 20);
        ObjectSetInteger(0, name, OBJPROP_COLOR, clrWhite);
        ObjectSetInteger(0, name, OBJPROP_BGCOLOR, clrDarkSlateGray);
        UpdateChecklistButton(i);
    }

    string resetName = g_checkPrefix + "RESET";
    ObjectDelete(0, resetName);
    ObjectCreate(0, resetName, OBJ_BUTTON, 0, 0, 0);
    ObjectSetInteger(0, resetName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
    ObjectSetInteger(0, resetName, OBJPROP_XDISTANCE, g_panelX + 10);
    ObjectSetInteger(0, resetName, OBJPROP_YDISTANCE, g_panelY + 524);
    ObjectSetInteger(0, resetName, OBJPROP_XSIZE, g_panelWidth - 20);
    ObjectSetInteger(0, resetName, OBJPROP_YSIZE, 20);
    ObjectSetInteger(0, resetName, OBJPROP_COLOR, clrWhite);
    ObjectSetInteger(0, resetName, OBJPROP_BGCOLOR, clrIndianRed);
    ObjectSetString(0, resetName, OBJPROP_TEXT, "Reset Checklist");
}

void RemoveChecklistButtons()
{
    for (int i = 0; i < 4; i++)
    {
        string name = g_checkPrefix + IntegerToString(i + 1);
        ObjectDelete(0, name);
    }
    ObjectDelete(0, g_checkPrefix + "RESET");
    for (int i = 0; i < g_panelMaxLines; i++)
        ObjectDelete(0, g_panelLinePrefix + IntegerToString(i));
    ObjectDelete(0, g_panelBgName);
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
    int tehranHour = 0;
    int tehranMin = 0;
    GetTehranTime(tehranHour, tehranMin);
    
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
//| Chart event handler (manual checklist buttons)                    |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
    if (id != CHARTEVENT_OBJECT_CLICK)
        return;

    if (sparam == g_checkPrefix + "RESET")
    {
        ResetChecklist();
        UpdateChartPanel();
        return;
    }

    for (int i = 0; i < 4; i++)
    {
        string name = g_checkPrefix + IntegerToString(i + 1);
        if (sparam == name)
        {
            g_checklistState[i] = !g_checklistState[i];
            UpdateChecklistButton(i);
            UpdateChartPanel();
            return;
        }
    }
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

    // Manual checklist enforcement: block new entries until all checks are done.
    if (dealEntry == DEAL_ENTRY_IN && InpEnforceChecklist && !IsChecklistComplete())
    {
        Print("🛑 Checklist incomplete: closing new entry #", (ulong)dealTicket);

        ulong posTicket = trans.position;
        if (posTicket != 0)
            ForceClosePosition(posTicket);
        else
        {
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

    // After N consecutive losses, trigger a temporary 1-hour break.
    // This is not a full daily shutdown.
    if (!g_shutdownDone && g_consecLosses >= InpMaxConsecLoss)
    {
        Print("🛑 BREAK: Consecutive losses (", g_consecLosses,
              ") reached. Starting 1-hour break.");

        // Close all open positions
        CloseAllPositions();

        // Clear cooldown on shutdown
        g_cooldownUntil = 0;
        g_cooldownStart = 0;

        // Signal break mode - Python app will kill MT5 and enforce 1-hour wait.
        g_shutdownDone = true;
        g_breakActive = true;
        g_tradingAllowed = false;

        g_session["shutdown_signal"].Set(false);
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
    EnsureSidePanel();

    double netPnl = g_dailyProfit - g_dailyLoss;
    int tradesLeft = InpMaxTrades - g_tradesToday;

    int tehranHour = 0;
    int tehranMin = 0;
    GetTehranTime(tehranHour, tehranMin);
    
    bool withinHours = (tehranHour > InpStartHour || (tehranHour == InpStartHour && tehranMin >= 0)) 
                   && (tehranHour < InpEndHour || (tehranHour == InpEndHour && tehranMin < 60));
    
    int breakStartMin = InpBreakHour * 60 + InpBreakMin;
    int breakEndMin = breakStartMin + InpBreakDuration;
    int tehranNowMin = tehranHour * 60 + tehranMin;
    bool isDailyBreak = (tehranNowMin >= breakStartMin && tehranNowMin < breakEndMin);

    string cooldownStr = "None";
    if (g_cooldownUntil > 0 && TimeCurrent() < g_cooldownUntil)
    {
        int secLeft = (int)(g_cooldownUntil - TimeCurrent());
        int min = secLeft / 60;
        int sec = secLeft % 60;
        cooldownStr = StringFormat("%02d:%02d", min, sec);
    }

    string lines[20];
    lines[0]  = "TRADING GUARD v1.0";
    lines[1]  = "STATUS";
    if (g_shutdownDone)
        lines[2] = "State: SESSION ENDED";
    else if (!g_tradingAllowed)
        lines[2] = "State: DISABLED";
    else if (g_newsLock)
        lines[2] = "State: NEWS LOCK";
    else
        lines[2] = "State: ACTIVE";
    lines[3]  = "Bias: " + g_bias;
    lines[4]  = "RISK";
    lines[5]  = "Trades: " + IntegerToString(g_tradesToday) + "/" + IntegerToString(InpMaxTrades);
    lines[6]  = "P&L: $" + DoubleToString(netPnl, 2);
    lines[7]  = "Loss: $" + DoubleToString(g_dailyLoss, 2);
    lines[8]  = "Profit: $" + DoubleToString(g_dailyProfit, 2);
    lines[9]  = "Consec Loss: " + IntegerToString(g_consecLosses);
    lines[10] = "Cooldown: " + cooldownStr;
    lines[11] = "News: " + (g_newsLock ? "ON" : "OFF");
    lines[12] = "TIME";
    lines[13] = "Tehran: " + IntegerToString(tehranHour) + ":" + IntegerToString(tehranMin);
    lines[14] = "Hours: " + (withinHours ? "OPEN" : "CLOSED");
    lines[15] = "Break: " + (isDailyBreak ? "ACTIVE" : "No");
    lines[16] = "CHECKLIST";
    lines[17] = "Done: " + IntegerToString(ChecklistDoneCount()) + "/4" + (InpEnforceChecklist ? " ENFORCED" : "");
    lines[18] = "Toggle items below:";
    lines[19] = "Use Reset after each trade";

    for (int i = 0; i < g_panelMaxLines; i++)
    {
        string lineName = g_panelLinePrefix + IntegerToString(i);
        ObjectSetString(0, lineName, OBJPROP_TEXT, lines[i]);
        if (i == 0)
        {
            ObjectSetInteger(0, lineName, OBJPROP_FONTSIZE, 11);
            ObjectSetInteger(0, lineName, OBJPROP_COLOR, clrLightGoldenrod);
        }
        else if (i == 1 || i == 4 || i == 12 || i == 16)
        {
            ObjectSetInteger(0, lineName, OBJPROP_FONTSIZE, 10);
            ObjectSetInteger(0, lineName, OBJPROP_COLOR, clrAqua);
        }
        else
        {
            ObjectSetInteger(0, lineName, OBJPROP_FONTSIZE, 10);
            ObjectSetInteger(0, lineName, OBJPROP_COLOR, clrWhite);
        }
    }
}
//+------------------------------------------------------------------+
