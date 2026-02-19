// session.json bridge sync

bool ReadSession()
{
    g_session.Clear();
    if (g_session.ReadFromFile(g_filePath))
        return true;
    return false;
}

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

    if (g_cooldownUntil == 0 || g_cooldownUntil <= TimeCurrent())
    {
        string cooldownStr = "0";
        if (g_session["cooldown_until"] != NULL)
            cooldownStr = g_session["cooldown_until"].GetStr();

        int minLeft = (int)StringToInteger(cooldownStr);
        if (minLeft > 0 && minLeft <= 60)
        {
            g_cooldownUntil = TimeCurrent() + minLeft * 60;
            g_cooldownStart = g_cooldownUntil - minLeft * 60;
            Print("TG: Loaded cooldown: ", minLeft, " minutes");
        }
    }

    Print("TG Sync: bias=", g_bias, " strict=", g_strictMode, " cooldown_until=", g_cooldownUntil);
}

void WriteSessionUpdate(string lastResult = "")
{
    g_session["daily_loss_usd"].Set(g_dailyLoss);
    g_session["daily_profit_usd"].Set(g_dailyProfit);
    g_session["trades_today"].Set((long)g_tradesToday);
    g_session["consecutive_losses"].Set((long)g_consecLosses);
    g_session["losses_since_bias"].Set((long)g_lossesSinceBias);

    if (g_cooldownUntil > 0 && TimeCurrent() < g_cooldownUntil)
    {
        int minLeft = (int)((g_cooldownUntil - TimeCurrent()) / 60);
        g_session["cooldown_until"].Set(IntegerToString(minLeft));
    }
    else
    {
        g_session["cooldown_until"].Set("0");
    }

    if (lastResult != "")
        g_session["last_trade_result"].Set(lastResult);

    g_session["timestamp"].Set(TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS));

    if (!g_session.WriteToFile(g_filePath))
        Print("TG: FAILED to write session file: ", g_filePath);
}
