// Chart panel and checklist UI

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

void UpdateChartPanel()
{
    EnsureSidePanel();

    double netPnl = g_dailyProfit - g_dailyLoss;

    int tehranHour = 0;
    int tehranMin = 0;
    GetTehranTime(tehranHour, tehranMin);

    bool withinHours = (tehranHour > InpStartHour || (tehranHour == InpStartHour && tehranMin >= 0))
                   && (tehranHour < InpEndHour || (tehranHour == InpEndHour && tehranMin < 60));

    int breakStartMin = InpBreakHour * 60 + InpBreakMin;
    int breakEndMin = breakStartMin + InpBreakDuration;
    int tehranNowMin = tehranHour * 60 + tehranMin;
    bool isDailyBreak = (tehranNowMin >= breakStartMin && tehranNowMin < breakEndMin);
    string autoCloseWarning = GetAutoCloseWarning();

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
    lines[3]  = (autoCloseWarning == "") ? "Next: OK" : "Next: BLOCKED";
    lines[4]  = (autoCloseWarning == "") ? "" : ("Reason: " + autoCloseWarning);
    lines[5]  = "RISK";
    lines[6]  = "Bias: " + g_bias;
    lines[7]  = "Trades: " + IntegerToString(g_tradesToday) + "/" + IntegerToString(InpMaxTrades);
    lines[8]  = "P&L: $" + DoubleToString(netPnl, 2);
    lines[9]  = "Loss: $" + DoubleToString(g_dailyLoss, 2);
    lines[10] = "Profit: $" + DoubleToString(g_dailyProfit, 2);
    lines[11] = "Consec Loss: " + IntegerToString(g_consecLosses);
    lines[12] = "TIME";
    lines[13] = "Cooldown: " + cooldownStr;
    lines[14] = "News: " + (g_newsLock ? "ON" : "OFF");
    lines[15] = "Tehran: " + IntegerToString(tehranHour) + ":" + IntegerToString(tehranMin);
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
        else if (i == 1 || i == 5 || i == 12 || i == 16)
        {
            ObjectSetInteger(0, lineName, OBJPROP_FONTSIZE, 10);
            ObjectSetInteger(0, lineName, OBJPROP_COLOR, clrAqua);
        }
        else if (i == 3 || i == 4)
        {
            ObjectSetInteger(0, lineName, OBJPROP_FONTSIZE, 10);
            ObjectSetInteger(0, lineName, OBJPROP_COLOR, (autoCloseWarning == "") ? clrLightGreen : clrTomato);
        }
        else
        {
            ObjectSetInteger(0, lineName, OBJPROP_FONTSIZE, 10);
            ObjectSetInteger(0, lineName, OBJPROP_COLOR, clrWhite);
        }
    }
}
