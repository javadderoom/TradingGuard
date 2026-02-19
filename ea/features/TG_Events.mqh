// Event handlers

void OnTick()
{
    datetime now = TimeCurrent();
    if (now - g_lastRead >= g_readInterval)
    {
        if (ReadSession())
            SyncFromSession();
        g_lastRead = now;
    }
    NotifyAutoCloseWarning(GetAutoCloseWarning());

    if (g_shutdownDone)
    {
        UpdateChartPanel();
        return;
    }

    int tehranHour = 0;
    int tehranMin = 0;
    GetTehranTime(tehranHour, tehranMin);

    bool withinHours = (tehranHour > InpStartHour || (tehranHour == InpStartHour && tehranMin >= 0))
                   && (tehranHour < InpEndHour || (tehranHour == InpEndHour && tehranMin < 60));

    static bool hoursWarningShown = false;
    if (!withinHours && !hoursWarningShown)
    {
        Print("TG: Outside trading hours. Tehran: ", tehranHour, ":", tehranMin,
              " Allowed: ", InpStartHour, "-", InpEndHour);
        hoursWarningShown = true;
    }
    else if (withinHours)
    {
        hoursWarningShown = false;
    }

    if (!withinHours)
    {
        if (PositionsTotal() > 0)
            CloseAllPositions();
        UpdateChartPanel();
        return;
    }

    int breakStartMin = InpBreakHour * 60 + InpBreakMin;
    int breakEndMin = breakStartMin + InpBreakDuration;
    int tehranNowMin = tehranHour * 60 + tehranMin;
    bool isDailyBreak = (tehranNowMin >= breakStartMin && tehranNowMin < breakEndMin);

    static bool breakWarningShown = false;
    if (isDailyBreak && !breakWarningShown)
    {
        Print("TG: Daily break started. Tehran: ", tehranHour, ":", tehranMin);
        breakWarningShown = true;
    }
    else if (!isDailyBreak)
    {
        breakWarningShown = false;
    }

    if (isDailyBreak)
    {
        UpdateChartPanel();
        return;
    }

    if (g_breakActive)
    {
        if (PositionsTotal() > 0)
        {
            Print("TG: Break active - closing all positions");
            CloseAllPositions();
        }
        UpdateChartPanel();
        return;
    }

    if (g_cooldownUntil > 0 && now < g_cooldownUntil)
    {
        MonitorOpenPositions();
        CheckDailyLimits();

        static datetime lastPanelUpdate = 0;
        if (now - lastPanelUpdate >= 5)
        {
            UpdateChartPanel();
            lastPanelUpdate = now;
        }

        static datetime lastCooldownWrite = 0;
        if (now - lastCooldownWrite >= 5)
        {
            WriteSessionUpdate();
            lastCooldownWrite = now;
        }
        return;
    }
    else if (g_cooldownUntil > 0 && now >= g_cooldownUntil)
    {
        g_cooldownUntil = 0;
        g_cooldownStart = 0;
        WriteSessionUpdate();
        Print("TG: Cooldown ended.");
    }

    static datetime lastDebug = 0;
    if (now - lastDebug >= 10)
    {
        Print("DEBUG: cooldownUntil=", g_cooldownUntil,
              " cooldownStart=", g_cooldownStart, " now=", now);
        lastDebug = now;
    }

    if (g_strictMode && (g_bias == "bullish" || g_bias == "bearish") && PositionsTotal() > 0)
    {
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
                Print("TG: Strict mode closing opposite-bias position #", ticket);
                ForceClosePosition(ticket);
            }
        }
    }

    if (!g_tradingAllowed || g_newsLock)
    {
        MonitorOpenPositions();
        CheckDailyLimits();
        UpdateChartPanel();
        return;
    }

    MonitorOpenPositions();
    CheckDailyLimits();
    UpdateChartPanel();
}

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

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
    Print("TG OnTradeTransaction: type=", (int)trans.type,
          " deal=", (ulong)trans.deal,
          " pos=", (ulong)trans.position,
          " symbol=", trans.symbol);

    if (trans.type != TRADE_TRANSACTION_DEAL_ADD)
        return;

    ulong dealTicket = trans.deal;
    if (dealTicket == 0) return;

    datetime from = TimeCurrent() - 86400 * 7;
    datetime to   = TimeCurrent() + 60;
    if (!HistorySelect(from, to))
    {
        Print("TG: HistorySelect failed for ", (ulong)dealTicket);
        return;
    }
    if (!HistoryDealSelect(dealTicket))
    {
        Print("TG: HistoryDealSelect failed for ", (ulong)dealTicket);
        return;
    }

    ENUM_DEAL_ENTRY dealEntry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dealTicket, DEAL_ENTRY);

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
            Print("TG: Strict mode blocking opposite-bias deal ", (ulong)dealTicket,
                  " on symbol ", trans.symbol, " bias=", g_bias);

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
    }

    if (dealEntry == DEAL_ENTRY_IN && g_cooldownUntil > 0 && TimeCurrent() < g_cooldownUntil)
    {
        Print("TG: Cooldown active, closing new entry #", (ulong)dealTicket);
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

    if (dealEntry == DEAL_ENTRY_IN && InpEnforceChecklist && !IsChecklistComplete())
    {
        Print("TG: Checklist incomplete, closing new entry #", (ulong)dealTicket);

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

    if (dealEntry == DEAL_ENTRY_IN)
    {
        double dealVolume = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
        if (dealVolume > InpMaxLot)
        {
            Print("TG: Lot limit exceeded: ", DoubleToString(dealVolume, 2),
                  " > ", DoubleToString(InpMaxLot, 2),
                  " - closing entry ", (ulong)dealTicket);

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
    }

    if (dealEntry == DEAL_ENTRY_IN && PositionsTotal() > 1)
    {
        Print("TG: One-trade rule triggered, closing new entry #", (ulong)dealTicket);
        ulong posTicket = trans.position;
        if (posTicket != 0)
            ForceClosePosition(posTicket);
        else
        {
            ulong newestTicket = 0;
            datetime newestTime = 0;
            for (int i = PositionsTotal() - 1; i >= 0; i--)
            {
                ulong ticket = PositionGetTicket(i);
                if (ticket == 0) continue;
                if (!PositionSelectByTicket(ticket)) continue;
                datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
                if (openTime >= newestTime)
                {
                    newestTime = openTime;
                    newestTicket = ticket;
                }
            }
            if (newestTicket != 0)
                ForceClosePosition(newestTicket);
        }
        return;
    }

    if (dealEntry == DEAL_ENTRY_IN)
    {
        g_cooldownStart = TimeCurrent();
        g_cooldownUntil = g_cooldownStart + (InpCooldownMin * 60);
        WriteSessionUpdate();
        Print("TG: Trade opened - cooldown set: ", InpCooldownMin, " min, until ", g_cooldownUntil);
        UpdateChartPanel();
        return;
    }

    if (dealEntry != DEAL_ENTRY_OUT && dealEntry != DEAL_ENTRY_INOUT && dealEntry != DEAL_ENTRY_OUT_BY)
        return;

    double dealProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
    double dealSwap   = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
    double dealComm   = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
    double netPnl     = dealProfit + dealSwap + dealComm;

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

    if (netPnl < 0 && g_cooldownUntil > TimeCurrent())
    {
        g_cooldownUntil += InpCooldownExtra * 60;
        Print("TG: Trade closed at loss - added ", InpCooldownExtra, " min extra cooldown");
    }
    else if (netPnl < 0)
    {
        g_cooldownUntil = TimeCurrent() + (InpCooldownMin + InpCooldownExtra) * 60;
    }

    string lastResult = (netPnl >= 0) ? "win" : "loss";
    WriteSessionUpdate(lastResult);

    Print("TG: Trade closed: $", DoubleToString(netPnl, 2),
          " | Today: ", g_tradesToday, " trades",
          " | Loss: $", DoubleToString(g_dailyLoss, 2),
          " | Profit: $", DoubleToString(g_dailyProfit, 2));

    CheckDailyLimits();
    UpdateChartPanel();
}
