// Shared helper utilities for TradingGuard EA

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
    int y = idx * 18;
    if (idx >= 4) y += 8;
    if (idx >= 12) y += 8;
    if (idx >= 16) y += 8;
    return y;
}

string GetAutoCloseWarning()
{
    int tehranHour = 0;
    int tehranMin = 0;
    GetTehranTime(tehranHour, tehranMin);

    bool withinHours = (tehranHour > InpStartHour || (tehranHour == InpStartHour && tehranMin >= 0))
                   && (tehranHour < InpEndHour || (tehranHour == InpEndHour && tehranMin < 60));
    if (!withinHours)
        return "Out of hours";

    int breakStartMin = InpBreakHour * 60 + InpBreakMin;
    int breakEndMin = breakStartMin + InpBreakDuration;
    int tehranNowMin = tehranHour * 60 + tehranMin;
    bool isDailyBreak = (tehranNowMin >= breakStartMin && tehranNowMin < breakEndMin);
    if (isDailyBreak)
        return "Daily break";

    if (g_breakActive)
        return "Loss break";

    if (g_cooldownUntil > 0 && TimeCurrent() < g_cooldownUntil)
        return "Cooldown";

    if (InpEnforceChecklist && !IsChecklistComplete())
        return "Checklist";

    return "";
}

void NotifyAutoCloseWarning(const string warning)
{
    if (warning == g_lastAutoCloseWarning)
        return;

    g_lastAutoCloseWarning = warning;
    if (warning == "")
    {
        Print("TG: Auto-close warning cleared.");
        return;
    }

    string msg = "TradingGuard: NEXT TRADE WILL AUTO-CLOSE - " + warning;
    Print(msg);
    Alert(msg);
}
