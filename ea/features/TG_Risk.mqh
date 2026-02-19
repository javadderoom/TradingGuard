// risk and execution enforcement

void ForceClosePosition(ulong ticket);
void CloseAllPositions();
void WriteSessionUpdate(string lastResult = "");

void MonitorOpenPositions()
{
    double totalFloatingPnl = 0.0;
    for (int j = PositionsTotal() - 1; j >= 0; j--)
    {
        ulong t = PositionGetTicket(j);
        if (t == 0) continue;
        if (!PositionSelectByTicket(t)) continue;
        totalFloatingPnl += PositionGetDouble(POSITION_PROFIT)
                         + PositionGetDouble(POSITION_SWAP);
    }

    if (PositionsTotal() > 0 && (g_dailyProfit + totalFloatingPnl) >= InpMaxDailyProfit)
    {
        Print("TG: Daily profit target reached with open PnL ($",
              DoubleToString(g_dailyProfit + totalFloatingPnl, 2),
              ") - closing all positions.");
        CloseAllPositions();
        return;
    }

    for (int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (!PositionSelectByTicket(ticket)) continue;

        double volume = PositionGetDouble(POSITION_VOLUME);
        if (volume > InpMaxLot)
        {
            Print("TG: Force closing #", ticket,
                  " - lot ", DoubleToString(volume, 2),
                  " exceeds max ", DoubleToString(InpMaxLot, 2));
            ForceClosePosition(ticket);
            continue;
        }

        if (g_strictMode && (g_bias == "bullish" || g_bias == "bearish"))
        {
            ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            bool opposite =
                (g_bias == "bullish" && posType == POSITION_TYPE_SELL) ||
                (g_bias == "bearish" && posType == POSITION_TYPE_BUY);

            if (opposite)
            {
                Print("TG: Strict mode closing opposite-bias position #", ticket);
                ForceClosePosition(ticket);
                continue;
            }
        }

        double floatingPnl = PositionGetDouble(POSITION_PROFIT)
                           + PositionGetDouble(POSITION_SWAP);

        if (floatingPnl <= -InpRiskPerTrade)
        {
            Print("TG: Force closing #", ticket,
                  " - floating loss $", DoubleToString(MathAbs(floatingPnl), 2));
            ForceClosePosition(ticket);
        }
    }
}

CTrade g_trade;
void ForceClosePosition(ulong ticket)
{
    g_trade.SetDeviationInPoints(100);
    g_trade.SetTypeFilling(ORDER_FILLING_IOC);

    bool result = g_trade.PositionClose(ticket);
    if (result)
    {
        Print("TG: Closed position #", ticket, " via CTrade");
        return;
    }

    Print("TG: CTrade close failed for #", ticket, " error: ", g_trade.ResultRetcode());

    if (!PositionSelectByTicket(ticket))
    {
        Print("TG: Could not select position #", ticket);
        return;
    }

    string symbol = PositionGetString(POSITION_SYMBOL);
    double volume = PositionGetDouble(POSITION_VOLUME);
    ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

    for (int retry = 0; retry < 3; retry++)
    {
        if (!PositionSelectByTicket(ticket))
        {
            Print("TG: Position #", ticket, " no longer exists");
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
                Print("TG: Position #", ticket, " closed successfully (fallback)");
                return;
            }
            Print("TG: Close retcode: ", tradeResult.retcode);
        }
        else
        {
            Print("TG: OrderSend error: ", GetLastError());
        }

        Sleep(500);
    }

    Print("TG: Force close failed after retries: #", ticket);
}

void CheckDailyLimits()
{
    if (g_shutdownDone) return;

    if (!g_shutdownDone && g_consecLosses >= InpMaxConsecLoss)
    {
        Print("TG: BREAK: Consecutive losses (", g_consecLosses, ") reached. Starting 1-hour break.");

        CloseAllPositions();
        g_cooldownUntil = 0;
        g_cooldownStart = 0;

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
        Print("TG: SHUTDOWN: ", reason);
        CloseAllPositions();
        g_cooldownUntil = 0;
        g_cooldownStart = 0;

        g_shutdownDone = true;
        g_tradingAllowed = false;
        g_session["shutdown_signal"].Set(true);
        g_session["trading_allowed"].Set(false);
        g_session["session_active"].Set(false);
        g_session["cooldown_until"].Set("");
        WriteSessionUpdate();
    }
}

void CloseAllPositions()
{
    for (int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        ForceClosePosition(ticket);
    }
}

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
    lot = MathFloor(lot / lotStep) * lotStep;
    lot = MathMax(lot, minLot);
    lot = MathMin(lot, maxLot);

    return NormalizeDouble(lot, 2);
}
