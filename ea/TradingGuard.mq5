//+------------------------------------------------------------------+
//| TradingGuard.mq5 - Behavioral Enforcement Expert Advisor          |
//| Main entry file: configuration + globals + lifecycle hooks.       |
//+------------------------------------------------------------------+
#property copyright "TradingGuard"
#property version   "1.00"
#property strict

#include "JAson.mqh"
#include <Trade\Trade.mqh>

// Inputs
input string   InpSessionFile   = "session.json";
input double   InpRiskPerTrade  = 12.0;
input double   InpMaxDailyLoss  = 24.0;
input double   InpMaxDailyProfit= 35.0;
input int      InpMaxTrades     = 3;
input int      InpMaxConsecLoss = 2;
input int      InpCooldownMin   = 15;
input int      InpCooldownExtra = 10;
input double   InpDefaultSL     = 50.0;
input double   InpMaxLot        = 0.02;

input int      InpStartHour     = 11;
input int      InpEndHour       = 21;

input int      InpBreakHour     = 16;
input int      InpBreakMin      = 20;
input int      InpBreakDuration = 12;

input bool     InpEnforceChecklist = true;
input string   InpChecklist1   = "Trend aligned";
input string   InpChecklist2   = "Entry setup valid";
input string   InpChecklist3   = "SL/TP defined";
input string   InpChecklist4   = "Risk acceptable";

// Shared global state
CJAVal  g_session;
datetime g_lastRead       = 0;
int      g_readInterval   = 2;

double   g_dailyLoss       = 0.0;
double   g_dailyProfit     = 0.0;
int      g_tradesToday     = 0;
int      g_consecLosses    = 0;
int      g_lossesSinceBias = 0;
bool     g_tradingAllowed  = false;
bool     g_shutdownDone    = false;
datetime g_cooldownUntil   = 0;
datetime g_cooldownStart   = 0;
string   g_bias            = "neutral";
bool     g_newsLock        = false;
bool     g_strictMode      = false;
bool     g_biasExpired     = false;
bool     g_breakActive     = false;

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
string   g_lastAutoCloseWarning = "";

#include "features\TG_Common.mqh"
#include "features\TG_UI.mqh"
#include "features\TG_Bridge.mqh"
#include "features\TG_Risk.mqh"
#include "features\TG_Events.mqh"

int OnInit()
{
    g_filePath = InpSessionFile;
    g_checklistItems[0] = InpChecklist1;
    g_checklistItems[1] = InpChecklist2;
    g_checklistItems[2] = InpChecklist3;
    g_checklistItems[3] = InpChecklist4;

    if (!ReadSession())
    {
        Print("TG: Could not read ", g_filePath, " - will retry on ticks.");
    }
    else
    {
        SyncFromSession();
        Print("TG: Initialized, session loaded.");
    }

    CreateChecklistButtons();
    UpdateChartPanel();
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
    RemoveChecklistButtons();
    Comment("");
}
