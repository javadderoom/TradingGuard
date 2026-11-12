//+------------------------------------------------------------------+
//|                                        TradingGuard_Executor.mq5 |
//|                                  Copyright 2026, TradingGuard HITL |
//|                                 https://github.com/TradingGuard   |
//+------------------------------------------------------------------+
#property copyright "TradingGuard HITL"
#property link      "https://github.com/TradingGuard"
#property version   "1.03"
#property description "Native Strategy Tester Execution Bridge for TradingGuard AI Council"

#include <Trade\Trade.mqh>

input string InpOrdersFile = "orders_schedule.csv"; // Schedule file in Common\Files or MQL5\Files
input ulong  InpMagicNumber = 777001;               // Expert Magic Number

struct OrderPlan
{
   string            id;
   string            symbol;
   ENUM_ORDER_TYPE   order_type;
   datetime          trigger_time;
   double            entry;
   double            sl;
   double            tp;
   double            lot;
   int               ttl_minutes;
   bool              placed;
};

OrderPlan g_plans[];
CTrade    g_trade;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(10);
   g_trade.SetTypeFilling(ORDER_FILLING_RETURN); // Pending orders require RETURN filling policy

   ArrayResize(g_plans, 0);

   // Try opening with FILE_COMMON first (for Strategy Tester sandbox compatibility)
   int handle = FileOpen(InpOrdersFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      // Fallback to local MQL5\Files
      handle = FileOpen(InpOrdersFile, FILE_READ | FILE_TXT | FILE_ANSI);
   }

   if(handle == INVALID_HANDLE)
   {
      PrintFormat("[TradingGuard_Executor] ERROR: Unable to open '%s' in Common\\Files or MQL5\\Files! Error: %d",
                  InpOrdersFile, GetLastError());
      return(INIT_SUCCEEDED);
   }

   bool is_header = true;
   while(!FileIsEnding(handle))
   {
      string line = FileReadString(handle);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(line == "" || StringSubstr(line, 0, 1) == "#") continue;

      if(is_header)
      {
         is_header = false;
         if(StringFind(line, "ID") >= 0 || StringFind(line, "Symbol") >= 0)
            continue;
      }

      string fields[];
      int count = StringSplit(line, ',', fields);
      if(count < 7) continue;

      string o_id    = fields[0];
      string o_sym   = (count > 1) ? fields[1] : "AUTO";
      string o_type  = (count > 2) ? fields[2] : "SELL_LIMIT";
      string o_time  = (count > 3) ? fields[3] : "";
      string o_entry = (count > 4) ? fields[4] : "0";
      string o_sl    = (count > 5) ? fields[5] : "0";
      string o_tp    = (count > 6) ? fields[6] : "0";
      string o_lot   = (count > 7) ? fields[7] : "0.01";
      string o_ttl   = (count > 8) ? fields[8] : "360";

      int idx = ArraySize(g_plans);
      ArrayResize(g_plans, idx + 1);

      g_plans[idx].id           = o_id;
      g_plans[idx].symbol       = (o_sym == "" || o_sym == "AUTO") ? _Symbol : o_sym;
      g_plans[idx].trigger_time = StringToTime(o_time);
      g_plans[idx].entry        = StringToDouble(o_entry);
      g_plans[idx].sl           = StringToDouble(o_sl);
      g_plans[idx].tp           = StringToDouble(o_tp);
      g_plans[idx].lot          = (StringToDouble(o_lot) > 0) ? StringToDouble(o_lot) : 0.01;
      g_plans[idx].ttl_minutes  = (int)StringToInteger(o_ttl);
      if(g_plans[idx].ttl_minutes <= 0) g_plans[idx].ttl_minutes = 360;
      g_plans[idx].placed       = false;

      StringToUpper(o_type);
      if(o_type == "BUY")
         g_plans[idx].order_type = ORDER_TYPE_BUY;
      else if(o_type == "SELL")
         g_plans[idx].order_type = ORDER_TYPE_SELL;
      else if(StringFind(o_type, "BUY") >= 0)
         g_plans[idx].order_type = ORDER_TYPE_BUY_LIMIT;
      else
         g_plans[idx].order_type = ORDER_TYPE_SELL_LIMIT;

      PrintFormat("[TradingGuard_Executor] Loaded Plan [%d]: %s %s %s @ %.5f (SL: %.5f, TP: %.5f) Trigger: %s (TTL: %d min)",
                  idx + 1, o_id, g_plans[idx].symbol, o_type, g_plans[idx].entry, g_plans[idx].sl, g_plans[idx].tp,
                  TimeToString(g_plans[idx].trigger_time, TIME_DATE | TIME_SECONDS), g_plans[idx].ttl_minutes);
   }

   FileClose(handle);
   PrintFormat("[TradingGuard_Executor] >>> SUCCESS: Total %d Order Plan(s) Loaded! <<<", ArraySize(g_plans));
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime now = TimeCurrent();
   int total = ArraySize(g_plans);

   // 1. Process Pending Order Plans
   for(int i = 0; i < total; i++)
   {
      if(g_plans[i].placed) continue;

      // Filter by current chart symbol if running in Strategy Tester single-symbol mode
      if(g_plans[i].symbol != _Symbol && g_plans[i].symbol != "AUTO")
         continue;

      if(now >= g_plans[i].trigger_time)
      {
         string sym = (g_plans[i].symbol == "AUTO") ? _Symbol : g_plans[i].symbol;
         int ttl = (g_plans[i].ttl_minutes > 0) ? g_plans[i].ttl_minutes : 480;
         datetime expiry = g_plans[i].trigger_time + (ttl * 60);

         if(now >= expiry)
         {
            g_plans[i].placed = true;
            PrintFormat("[TradingGuard_Executor] Plan %s expired before placement at %s (TTL: %d min)",
                        g_plans[i].id, TimeToString(now, TIME_DATE | TIME_SECONDS), ttl);
            continue;
         }

         MqlTick tick;
         if(!SymbolInfoTick(sym, tick))
         {
            tick.bid = SymbolInfoDouble(sym, SYMBOL_BID);
            tick.ask = SymbolInfoDouble(sym, SYMBOL_ASK);
         }

         int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
         double tick_size = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
         if(tick_size <= 0) tick_size = SymbolInfoDouble(sym, SYMBOL_POINT);
         double point = SymbolInfoDouble(sym, SYMBOL_POINT);
         long stops_level = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
         double min_dist = stops_level * point;

         double entry = NormalizeDouble(MathRound(g_plans[i].entry / tick_size) * tick_size, digits);
         double sl    = (g_plans[i].sl > 0) ? NormalizeDouble(MathRound(g_plans[i].sl / tick_size) * tick_size, digits) : 0;
         double tp    = (g_plans[i].tp > 0) ? NormalizeDouble(MathRound(g_plans[i].tp / tick_size) * tick_size, digits) : 0;
         double lot   = g_plans[i].lot;

         long exp_mode = SymbolInfoInteger(sym, SYMBOL_EXPIRATION_MODE);
         ENUM_ORDER_TYPE_TIME type_time = ORDER_TIME_SPECIFIED;

         if((exp_mode & SYMBOL_EXPIRATION_SPECIFIED) != 0)
         {
            type_time = ORDER_TIME_SPECIFIED;
         }
         else if((exp_mode & SYMBOL_EXPIRATION_DAY) != 0)
         {
            type_time = ORDER_TIME_DAY;
            expiry = 0;
         }
         else if((exp_mode & SYMBOL_EXPIRATION_GTC) != 0)
         {
            type_time = ORDER_TIME_GTC;
            expiry = 0;
         }

         PrintFormat("[TradingGuard_Executor] EXEC ATTEMPT %s: Market Bid=%.5f, Ask=%.5f, Spread=%d, StopsLvl=%d | Order Entry=%.5f, SL=%.5f, TP=%.5f",
                     g_plans[i].id, tick.bid, tick.ask, (int)SymbolInfoInteger(sym, SYMBOL_SPREAD), (int)stops_level, entry, sl, tp);

         bool res = false;
         if(g_plans[i].order_type == ORDER_TYPE_SELL)
         {
            PrintFormat("[TradingGuard_Executor] Executing MARKET SELL for %s @ Bid=%.5f (SL: %.5f, TP: %.5f)",
                        g_plans[i].id, tick.bid, sl, tp);
            res = g_trade.Sell(lot, sym, tick.bid, sl, tp, g_plans[i].id);
         }
         else if(g_plans[i].order_type == ORDER_TYPE_BUY)
         {
            PrintFormat("[TradingGuard_Executor] Executing MARKET BUY for %s @ Ask=%.5f (SL: %.5f, TP: %.5f)",
                        g_plans[i].id, tick.ask, sl, tp);
            res = g_trade.Buy(lot, sym, tick.ask, sl, tp, g_plans[i].id);
         }
         else if(g_plans[i].order_type == ORDER_TYPE_SELL_LIMIT)
         {
            // Structural pre-execution check: If market has already breached SL, trade idea is invalidated!
            if(tick.bid >= sl || (sl > 0 && tick.bid >= sl - min_dist))
            {
               PrintFormat("[TradingGuard_Executor] Plan %s INVALIDATED: Market Bid=%.5f has already breached SL=%.5f! Order cancelled.",
                           g_plans[i].id, tick.bid, sl);
               g_plans[i].placed = true;
               continue;
            }

            // If current market price has already reached or exceeded the Sell Limit price
            if(tick.bid >= entry)
            {
               PrintFormat("[TradingGuard_Executor] Market has already crossed Sell Limit price (Bid=%.5f >= Entry=%.5f). Executing Market SELL directly!",
                           tick.bid, entry);
               res = g_trade.Sell(lot, sym, tick.bid, sl, tp, g_plans[i].id);
            }
            else
            {
               // Price is below market ask: ensure entry is above ask by at least stops_level
               double valid_entry = entry;
               if(valid_entry < tick.ask + min_dist)
               {
                  PrintFormat("[TradingGuard_Executor] WARNING: Entry %.5f violates Ask+Stops (Ask=%.5f, MinDist=%.5f). Adjusting to valid limit price.",
                              entry, tick.ask, min_dist);
                  valid_entry = NormalizeDouble(tick.ask + min_dist + point, digits);
               }
               res = g_trade.SellLimit(lot, valid_entry, sym, sl, tp, type_time, expiry, g_plans[i].id);
            }
         }
         else if(g_plans[i].order_type == ORDER_TYPE_BUY_LIMIT)
         {
            // Structural pre-execution check: If market has already breached SL, trade idea is invalidated!
            if(tick.ask <= sl || (sl > 0 && tick.ask <= sl + min_dist))
            {
               PrintFormat("[TradingGuard_Executor] Plan %s INVALIDATED: Market Ask=%.5f has already breached SL=%.5f! Order cancelled.",
                           g_plans[i].id, tick.ask, sl);
               g_plans[i].placed = true;
               continue;
            }

            if(tick.ask <= entry)
            {
               PrintFormat("[TradingGuard_Executor] Market has already reached Buy Limit price (Ask=%.5f <= Entry=%.5f). Executing Market BUY directly!",
                           tick.ask, entry);
               res = g_trade.Buy(lot, sym, tick.ask, sl, tp, g_plans[i].id);
            }
            else
            {
               double valid_entry = entry;
               if(valid_entry > tick.bid - min_dist)
               {
                  valid_entry = NormalizeDouble(tick.bid - min_dist - point, digits);
               }
               res = g_trade.BuyLimit(lot, valid_entry, sym, sl, tp, type_time, expiry, g_plans[i].id);
            }
         }

         g_plans[i].placed = true;
         if(res)
         {
            PrintFormat("[TradingGuard_Executor] >>> ORDER PLACED: %s %s @ %.5f (SL: %.5f, TP: %.5f, Expiry: %s) at terminal time %s <<<",
                        g_plans[i].id, sym, entry, sl, tp,
                        (expiry > 0 ? TimeToString(expiry, TIME_DATE | TIME_SECONDS) : "GTC/DAY"),
                        TimeToString(now, TIME_DATE | TIME_SECONDS));
         }
         else
         {
            PrintFormat("[TradingGuard_Executor] Order placement FAILED for %s. Retcode: %d (%s)",
                        g_plans[i].id, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
         }
      }
   }

   // 2. Dynamic Position Lifecycle Management (Breakeven Ratchet & Session Expiry)
   ManageActivePositions();
}

//+------------------------------------------------------------------+
//| Manage Active Positions (Breakeven & Session Expiry)             |
//+------------------------------------------------------------------+
void ManageActivePositions()
{
   datetime now = TimeCurrent();
   for(int p = PositionsTotal() - 1; p >= 0; p--)
   {
      ulong ticket = PositionGetTicket(p);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      string comment = PositionGetString(POSITION_COMMENT);
      string sym = PositionGetString(POSITION_SYMBOL);
      ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      double cur_sl = PositionGetDouble(POSITION_SL);
      double cur_tp = PositionGetDouble(POSITION_TP);
      datetime open_time = (datetime)PositionGetInteger(POSITION_TIME);

      // Match plan
      int plan_idx = -1;
      for(int i = 0; i < ArraySize(g_plans); i++)
      {
         if(g_plans[i].id == comment || StringFind(comment, g_plans[i].id) >= 0)
         {
            plan_idx = i;
            break;
         }
      }

      if(plan_idx < 0) continue;

      double risk = MathAbs(g_plans[plan_idx].entry - g_plans[plan_idx].sl);
      if(risk <= 0) continue;

      int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(sym, SYMBOL_POINT);
      double spread = SymbolInfoDouble(sym, SYMBOL_ASK) - SymbolInfoDouble(sym, SYMBOL_BID);

      // A. Session Expiry Check (Dynamic TTL from plan or default 480 minutes)
      int max_ttl = (g_plans[plan_idx].ttl_minutes > 0) ? g_plans[plan_idx].ttl_minutes : 480;
      if(now - open_time >= max_ttl * 60)
      {
         PrintFormat("[TradingGuard_Executor] Max held time exceeded (%d min) for ticket %d (%s). Closing at market.", max_ttl, ticket, comment);
         g_trade.PositionClose(ticket);
         continue;
      }

      // B. Breakeven Ratchet Protocol
      // Index (NQ): 0.8R, Cable: 1.0R, Gold: 1.5R, BTC: 1.8R
      double be_thresh = 1.0;
      if(StringFind(sym, "NQ") >= 0 || StringFind(sym, "NAS") >= 0 || StringFind(sym, "USTEC") >= 0)
         be_thresh = 0.8;
      else if(StringFind(sym, "XAU") >= 0)
         be_thresh = 1.5;
      else if(StringFind(sym, "GBP") >= 0)
         be_thresh = 1.0;
      else if(StringFind(sym, "BTC") >= 0)
         be_thresh = 1.8;

      MqlTick tick;
      if(!SymbolInfoTick(sym, tick))
      {
         tick.bid = SymbolInfoDouble(sym, SYMBOL_BID);
         tick.ask = SymbolInfoDouble(sym, SYMBOL_ASK);
      }

      if(pos_type == POSITION_TYPE_BUY)
      {
         double mfe_r = (tick.bid - open_price) / risk;
         if(mfe_r >= be_thresh && cur_sl < open_price)
         {
            double new_sl = NormalizeDouble(open_price + point, digits);
            PrintFormat("[TradingGuard_Executor] BREAKEVEN TRIGGERED: Ticket %d (%s) MFE=%.2fR >= %.1fR. Ratcheting SL to %.5f",
                        ticket, comment, mfe_r, be_thresh, new_sl);
            g_trade.PositionModify(ticket, new_sl, cur_tp);
         }
      }
      else if(pos_type == POSITION_TYPE_SELL)
      {
         double mfe_r = (open_price - tick.ask) / risk;
         if(mfe_r >= be_thresh && (cur_sl > open_price || cur_sl == 0))
         {
            double new_sl = NormalizeDouble(open_price - point, digits);
            PrintFormat("[TradingGuard_Executor] BREAKEVEN TRIGGERED: Ticket %d (%s) MFE=%.2fR >= %.1fR. Ratcheting SL to %.5f",
                        ticket, comment, mfe_r, be_thresh, new_sl);
            g_trade.PositionModify(ticket, new_sl, cur_tp);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   PrintFormat("[TradingGuard_Executor] Deinitialized. Reason code: %d", reason);
}
