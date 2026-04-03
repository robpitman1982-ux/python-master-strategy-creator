//+------------------------------------------------------------------+
//| Portfolio3_The5ers.mq5                                            |
//| Rob Pitman - Strategy Discovery Engine Portfolio #3               |
//| The5ers $5K High Stakes - 4 Strategy EA                          |
//+------------------------------------------------------------------+
#property copyright "Rob Pitman"
#property link      "https://github.com/robpitman1982-ux/python-master-strategy-creator"
#property version   "1.00"
#property description "Portfolio #3: NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR"
#property description "99.6% pass rate, 6.9% P95 DD on $5K High Stakes backtest"

//+------------------------------------------------------------------+
//| INPUTS                                                            |
//+------------------------------------------------------------------+

// --- Global Settings ---
input group "=== Global Settings ==="
input double   LotSize           = 0.01;    // Lot size per strategy (1 micro)
input int      Slippage          = 10;      // Max slippage in points
input int      MagicBase         = 557700;  // Base magic number
input bool     EnableStrategy1   = true;    // Enable NQ Daily MR
input bool     EnableStrategy2   = true;    // Enable YM Daily Short Trend
input bool     EnableStrategy3   = true;    // Enable GC Daily MR
input bool     EnableStrategy4   = true;    // Enable NQ 15m MR
// --- Strategy 1: NQ Daily MR (LONG) on NAS100 ---
input group "=== Strategy 1: NQ Daily MR ==="
input string   S1_Symbol         = "NAS100";   // CFD symbol
input int      S1_FastSMA        = 5;          // Fast SMA period (daily adjusted)
input double   S1_DistBelowATR   = 0.4;        // DistanceBelowSMA min ATR multiplier
input int      S1_ExtremeLookback= 5;          // DistanceFromExtreme lookback
input double   S1_ExtremeThresh  = 1.5;        // DistanceFromExtreme ATR threshold
input int      S1_ATRPeriod      = 20;         // ATR period
input double   S1_StopATR        = 0.4;        // Stop distance in ATR
input int      S1_HoldBars       = 5;          // Hold bars (time stop)

// --- Strategy 2: YM Daily Short Trend (SHORT) on US30 ---
input group "=== Strategy 2: YM Daily Short Trend ==="
input string   S2_Symbol         = "US30";     // CFD symbol
input int      S2_ATRPeriod      = 20;         // ATR period
input double   S2_StopATR        = 0.75;       // Stop distance in ATR
input double   S2_TrailATR       = 1.5;        // Trailing stop in ATR
input int      S2_HoldBars       = 1;          // Hold bars (time stop)

// --- Strategy 3: GC Daily MR (LONG) on XAUUSD ---
input group "=== Strategy 3: GC Daily MR ==="
input string   S3_Symbol         = "XAUUSD";   // CFD symbol
input int      S3_FastSMA        = 5;          // Fast SMA period (daily adjusted)
input double   S3_DistBelowATR   = 0.4;        // DistanceBelowSMA min ATR multiplier
input int      S3_ATRPeriod      = 20;         // ATR period
input double   S3_StopATR        = 0.4;        // Stop distance in ATR
input int      S3_HoldBars       = 5;          // Hold bars (time stop)
// --- Strategy 4: NQ 15m MR (LONG) on NAS100 ---
input group "=== Strategy 4: NQ 15m MR ==="
input string   S4_Symbol         = "NAS100";   // CFD symbol
input int      S4_SlowSMA        = 800;        // Slow SMA period (15m adjusted)
input double   S4_StretchATR     = 1.0;        // StretchFromLongTermSMA min ATR mult
input int      S4_ATRPeriod      = 20;         // ATR period
input double   S4_StopATR        = 0.4;        // Stop distance in ATR
input int      S4_HoldBars       = 16;         // Hold bars (time stop)


//+------------------------------------------------------------------+
//| GLOBAL VARIABLES                                                  |
//+------------------------------------------------------------------+
datetime g_lastBarTime_S1 = 0;
datetime g_lastBarTime_S2 = 0;
datetime g_lastBarTime_S3 = 0;
datetime g_lastBarTime_S4 = 0;

int g_barsHeld_S1 = 0;
int g_barsHeld_S2 = 0;
int g_barsHeld_S3 = 0;
int g_barsHeld_S4 = 0;

#define MAGIC_S1 557701
#define MAGIC_S2 557702
#define MAGIC_S3 557703
#define MAGIC_S4 557704

#include <Trade\Trade.mqh>
CTrade trade;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MagicBase);
   trade.SetDeviationInPoints(Slippage);
   trade.SetTypeFilling(ORDER_FILLING_IOC);
   
   Print("=== Portfolio #3 EA Initialized ===");
   Print("S1: NQ Daily MR (LONG) ", S1_Symbol, " Hold=", S1_HoldBars, " Stop=", S1_StopATR, "ATR");
   Print("S2: YM Short Trend (SHORT) ", S2_Symbol, " Hold=", S2_HoldBars, " Stop=", S2_StopATR, "ATR Trail=", S2_TrailATR, "ATR");
   Print("S3: GC Daily MR (LONG) ", S3_Symbol, " Hold=", S3_HoldBars, " Stop=", S3_StopATR, "ATR");
   Print("S4: NQ 15m MR (LONG) ", S4_Symbol, " Hold=", S4_HoldBars, " Stop=", S4_StopATR, "ATR");
   Print("Lot size: ", LotSize);
   
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   Print("=== Portfolio #3 EA Removed === Reason: ", reason);
}


//+------------------------------------------------------------------+
//| INDICATOR HELPERS                                                 |
//+------------------------------------------------------------------+
double CalcSMA(const string symbol, ENUM_TIMEFRAMES tf, int period, int shift=0)
{
   double arr[];
   if(CopyClose(symbol, tf, shift, period, arr) < period) return 0.0;
   double sum = 0;
   for(int i = 0; i < period; i++) sum += arr[i];
   return sum / period;
}
double CalcATR(const string symbol, ENUM_TIMEFRAMES tf, int period, int shift=0)
{
   double high[], low[], close[];
   if(CopyHigh(symbol, tf, shift, period + 1, high) < period + 1) return 0.0;
   if(CopyLow(symbol, tf, shift, period + 1, low) < period + 1) return 0.0;
   if(CopyClose(symbol, tf, shift, period + 1, close) < period + 1) return 0.0;
   
   double sum = 0;
   for(int i = 1; i <= period; i++)
   {
      double tr1 = high[i] - low[i];
      double tr2 = MathAbs(high[i] - close[i-1]);
      double tr3 = MathAbs(low[i] - close[i-1]);
      sum += MathMax(tr1, MathMax(tr2, tr3));
   }
   return sum / period;
}

double GetClose(const string symbol, ENUM_TIMEFRAMES tf, int shift)
{  double a[]; if(CopyClose(symbol, tf, shift, 1, a) < 1) return 0.0; return a[0]; }

double GetOpen(const string symbol, ENUM_TIMEFRAMES tf, int shift)
{  double a[]; if(CopyOpen(symbol, tf, shift, 1, a) < 1) return 0.0; return a[0]; }

double GetHigh(const string symbol, ENUM_TIMEFRAMES tf, int shift)
{  double a[]; if(CopyHigh(symbol, tf, shift, 1, a) < 1) return 0.0; return a[0]; }

double GetLow(const string symbol, ENUM_TIMEFRAMES tf, int shift)
{  double a[]; if(CopyLow(symbol, tf, shift, 1, a) < 1) return 0.0; return a[0]; }
double RollingHigh(const string symbol, ENUM_TIMEFRAMES tf, int period, int shift=0)
{
   double arr[];
   if(CopyHigh(symbol, tf, shift, period, arr) < period) return 0.0;
   double maxVal = arr[0];
   for(int i = 1; i < period; i++)
      if(arr[i] > maxVal) maxVal = arr[i];
   return maxVal;
}

datetime GetBarTime(const string symbol, ENUM_TIMEFRAMES tf, int shift)
{  datetime a[]; if(CopyTime(symbol, tf, shift, 1, a) < 1) return 0; return a[0]; }


//+------------------------------------------------------------------+
//| POSITION MANAGEMENT                                               |
//+------------------------------------------------------------------+
bool HasPosition(int magic)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) > 0)
         if(PositionGetInteger(POSITION_MAGIC) == magic)
            return true;
   }
   return false;
}
ulong GetPositionTicket(int magic)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
         if(PositionGetInteger(POSITION_MAGIC) == magic)
            return ticket;
   }
   return 0;
}

bool ClosePosition(int magic, const string reason)
{
   ulong ticket = GetPositionTicket(magic);
   if(ticket == 0) return false;
   trade.SetExpertMagicNumber(magic);
   bool result = trade.PositionClose(ticket, Slippage);
   if(result)  Print("Closed magic=", magic, " reason=", reason);
   else        Print("Close FAILED magic=", magic, " err=", GetLastError());
   return result;
}

bool OpenBuy(const string symbol, int magic, double sl, const string comment)
{
   trade.SetExpertMagicNumber(magic);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(ask == 0) return false;
   sl = NormalizeDouble(sl, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
   bool result = trade.Buy(LotSize, symbol, ask, sl, 0, comment);
   if(result) Print("BUY ", symbol, " @", ask, " SL=", sl, " ", comment);
   else       Print("BUY FAIL ", symbol, " err=", GetLastError());
   return result;
}
bool OpenSell(const string symbol, int magic, double sl, const string comment)
{
   trade.SetExpertMagicNumber(magic);
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   if(bid == 0) return false;
   sl = NormalizeDouble(sl, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
   bool result = trade.Sell(LotSize, symbol, bid, sl, 0, comment);
   if(result) Print("SELL ", symbol, " @", bid, " SL=", sl, " ", comment);
   else       Print("SELL FAIL ", symbol, " err=", GetLastError());
   return result;
}

bool ModifySL(int magic, double newSL)
{
   ulong ticket = GetPositionTicket(magic);
   if(ticket == 0) return false;
   double currentSL = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   string symbol = PositionGetString(POSITION_SYMBOL);
   newSL = NormalizeDouble(newSL, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
   if(MathAbs(newSL - currentSL) < SymbolInfoDouble(symbol, SYMBOL_POINT))
      return true;
   trade.SetExpertMagicNumber(magic);
   return trade.PositionModify(ticket, newSL, tp);
}

//+------------------------------------------------------------------+
//| STRATEGY 1: NQ Daily MR (LONG) on NAS100                         |
//| Filters: BelowFastSMA(5) + DistanceBelowSMA(5,0.4) +            |
//|          DistanceFromExtreme(5,20,1.5,"far_from_high")            |
//| Exit: Time stop 5 bars or SL 0.4×ATR                             |
//+------------------------------------------------------------------+
void Strategy1_NQ_Daily_MR()
{
   if(!EnableStrategy1) return;
   string sym = S1_Symbol;
   ENUM_TIMEFRAMES tf = PERIOD_D1;
   int magic = MAGIC_S1;
   
   datetime currentBarTime = GetBarTime(sym, tf, 0);
   if(currentBarTime == g_lastBarTime_S1) return;
   g_lastBarTime_S1 = currentBarTime;
   
   // --- Manage existing position ---
   if(HasPosition(magic))
   {
      g_barsHeld_S1++;
      if(g_barsHeld_S1 >= S1_HoldBars)
      {
         ClosePosition(magic, "TIME_STOP S1 bars=" + IntegerToString(g_barsHeld_S1));
         g_barsHeld_S1 = 0;
      }
      return;
   }   
   // --- Entry filters on COMPLETED bar (shift=1) ---
   double close1 = GetClose(sym, tf, 1);
   if(close1 == 0) return;
   double atr = CalcATR(sym, tf, S1_ATRPeriod, 1);
   if(atr == 0) return;
   
   // Filter 1: BelowFastSMA — Close < SMA(5)
   double fastSMA = CalcSMA(sym, tf, S1_FastSMA, 1);
   if(fastSMA == 0 || close1 >= fastSMA) return;
   
   // Filter 2: DistanceBelowSMA — (SMA - Close) >= ATR × 0.4
   if((fastSMA - close1) < atr * S1_DistBelowATR) return;
   
   // Filter 3: DistanceFromExtreme — (RollingHigh5 - Close) / ATR >= 1.5
   double rollingHigh = RollingHigh(sym, tf, S1_ExtremeLookback, 1);
   if(rollingHigh == 0) return;
   if((rollingHigh - close1) / atr < S1_ExtremeThresh) return;
   
   // --- ENTER LONG ---
   double stopDist = atr * S1_StopATR;
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   if(OpenBuy(sym, magic, ask - stopDist, "S1_NQ_Daily_MR"))
      g_barsHeld_S1 = 0;
}

//+------------------------------------------------------------------+
//| STRATEGY 2: YM Daily Short Trend (SHORT) on US30                  |
//| Filters: LowerHigh + DownCloseShort + LowerLow                   |
//| Exit: Time stop 1 bar, trailing stop 1.5×ATR, or SL 0.75×ATR    |
//+------------------------------------------------------------------+
void Strategy2_YM_Daily_ShortTrend()
{
   if(!EnableStrategy2) return;
   string sym = S2_Symbol;
   ENUM_TIMEFRAMES tf = PERIOD_D1;
   int magic = MAGIC_S2;
   
   datetime currentBarTime = GetBarTime(sym, tf, 0);
   if(currentBarTime == g_lastBarTime_S2) return;
   g_lastBarTime_S2 = currentBarTime;
   
   // --- Manage existing position ---
   if(HasPosition(magic))
   {
      g_barsHeld_S2++;
      
      // Update trailing stop
      double atr_now = CalcATR(sym, tf, S2_ATRPeriod, 1);
      if(atr_now > 0)
      {
         double lowestLow = GetLow(sym, tf, 1);
         double newTrailStop = lowestLow + S2_TrailATR * atr_now;
         ulong ticket = GetPositionTicket(magic);
         if(ticket > 0)
         {
            double currentSL = PositionGetDouble(POSITION_SL);
            // For shorts: only move stop DOWN (tighter)
            if(newTrailStop < currentSL || currentSL == 0)
               ModifySL(magic, newTrailStop);
         }
      }      
      // Time stop
      if(g_barsHeld_S2 >= S2_HoldBars)
      {
         ClosePosition(magic, "TIME_STOP S2 bars=" + IntegerToString(g_barsHeld_S2));
         g_barsHeld_S2 = 0;
      }
      return;
   }
   
   // --- Entry filters on COMPLETED bar (shift=1) ---
   double high1 = GetHigh(sym, tf, 1), high2 = GetHigh(sym, tf, 2);
   double low1  = GetLow(sym, tf, 1),  low2  = GetLow(sym, tf, 2);
   double close1= GetClose(sym, tf, 1), close2= GetClose(sym, tf, 2);
   if(high1 == 0 || high2 == 0) return;
   
   // Filter 1: LowerHigh — High[1] < High[2]
   if(high1 >= high2) return;
   // Filter 2: DownCloseShort — Close[1] < Close[2]
   if(close1 >= close2) return;
   // Filter 3: LowerLow — Low[1] < Low[2]
   if(low1 >= low2) return;
   
   // --- ENTER SHORT ---
   double atr = CalcATR(sym, tf, S2_ATRPeriod, 1);
   if(atr == 0) return;
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   if(OpenSell(sym, magic, bid + atr * S2_StopATR, "S2_YM_ShortTrend"))
      g_barsHeld_S2 = 0;
}

//+------------------------------------------------------------------+
//| STRATEGY 3: GC Daily MR (LONG) on XAUUSD                         |
//| Filters: BelowFastSMA(5) + DistanceBelowSMA(5,0.4) + TwoBarDown |
//| Exit: Time stop 5 bars or SL 0.4×ATR                             |
//+------------------------------------------------------------------+
void Strategy3_GC_Daily_MR()
{
   if(!EnableStrategy3) return;
   string sym = S3_Symbol;
   ENUM_TIMEFRAMES tf = PERIOD_D1;
   int magic = MAGIC_S3;
   
   datetime currentBarTime = GetBarTime(sym, tf, 0);
   if(currentBarTime == g_lastBarTime_S3) return;
   g_lastBarTime_S3 = currentBarTime;
   
   if(HasPosition(magic))
   {
      g_barsHeld_S3++;
      if(g_barsHeld_S3 >= S3_HoldBars)
      {
         ClosePosition(magic, "TIME_STOP S3 bars=" + IntegerToString(g_barsHeld_S3));
         g_barsHeld_S3 = 0;
      }
      return;
   }   
   // --- Entry filters on COMPLETED bar (shift=1) ---
   double close1 = GetClose(sym, tf, 1);
   double close2 = GetClose(sym, tf, 2);
   double close3 = GetClose(sym, tf, 3);
   if(close1 == 0 || close2 == 0 || close3 == 0) return;
   
   double atr = CalcATR(sym, tf, S3_ATRPeriod, 1);
   if(atr == 0) return;
   
   // Filter 1: BelowFastSMA — Close < SMA(5)
   double fastSMA = CalcSMA(sym, tf, S3_FastSMA, 1);
   if(fastSMA == 0 || close1 >= fastSMA) return;
   
   // Filter 2: DistanceBelowSMA — (SMA - Close) >= ATR × 0.4
   if((fastSMA - close1) < atr * S3_DistBelowATR) return;
   
   // Filter 3: TwoBarDown — Close[1] < Close[2] AND Close[2] < Close[3]
   if(close1 >= close2) return;
   if(close2 >= close3) return;
   
   // --- ENTER LONG ---
   double stopDist = atr * S3_StopATR;
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   if(OpenBuy(sym, magic, ask - stopDist, "S3_GC_Daily_MR"))
      g_barsHeld_S3 = 0;
}

//+------------------------------------------------------------------+
//| STRATEGY 4: NQ 15m MR (LONG) on NAS100                           |
//| Filters: ThreeBarDown + ReversalUpBar +                           |
//|          StretchFromLongTermSMA(800, 1.0)                         |
//| Exit: Time stop 16 bars or SL 0.4×ATR                            |
//+------------------------------------------------------------------+
void Strategy4_NQ_15m_MR()
{
   if(!EnableStrategy4) return;
   string sym = S4_Symbol;
   ENUM_TIMEFRAMES tf = PERIOD_M15;
   int magic = MAGIC_S4;
   
   datetime currentBarTime = GetBarTime(sym, tf, 0);
   if(currentBarTime == g_lastBarTime_S4) return;
   g_lastBarTime_S4 = currentBarTime;
   
   if(HasPosition(magic))
   {
      g_barsHeld_S4++;
      if(g_barsHeld_S4 >= S4_HoldBars)
      {
         ClosePosition(magic, "TIME_STOP S4 bars=" + IntegerToString(g_barsHeld_S4));
         g_barsHeld_S4 = 0;
      }
      return;
   }   
   // --- Entry filters on COMPLETED bar (shift=1) ---
   double close1 = GetClose(sym, tf, 1);
   double close2 = GetClose(sym, tf, 2);
   double close3 = GetClose(sym, tf, 3);
   double close4 = GetClose(sym, tf, 4);
   double open1  = GetOpen(sym, tf, 1);
   if(close1 == 0 || close4 == 0) return;
   
   double atr = CalcATR(sym, tf, S4_ATRPeriod, 1);
   if(atr == 0) return;
   
   // Filter 1: ThreeBarDown — Close[1] < Close[2] < Close[3] < Close[4]
   if(close1 >= close2) return;
   if(close2 >= close3) return;
   if(close3 >= close4) return;
   
   // Filter 2: ReversalUpBar — Close[1] > Open[1] (green candle)
   if(close1 <= open1) return;
   
   // Filter 3: StretchFromLongTermSMA — (SMA800 - Close) / ATR >= 1.0
   double slowSMA = CalcSMA(sym, tf, S4_SlowSMA, 1);
   if(slowSMA == 0) return;
   if((slowSMA - close1) / atr < S4_StretchATR) return;
   
   // --- ENTER LONG ---
   double stopDist = atr * S4_StopATR;
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   if(OpenBuy(sym, magic, ask - stopDist, "S4_NQ_15m_MR"))
      g_barsHeld_S4 = 0;
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   Strategy1_NQ_Daily_MR();
   Strategy2_YM_Daily_ShortTrend();
   Strategy3_GC_Daily_MR();
   Strategy4_NQ_15m_MR();
}


//+------------------------------------------------------------------+
//| NOTES FOR THE5ERS COMPLIANCE                                      |
//+------------------------------------------------------------------+
// 1. All entries have visible stop losses — The5ers requires this
// 2. No HFT — daily strategies trade ~1-2x/month, 15m more but still low freq
// 3. No latency arbitrage — simple indicator-based entries
// 4. Overnight holds permitted on The5ers CFD programs
// 5. Each strategy uses 0.01 lots (1 micro equivalent)
// 6. Magic numbers 557701-557704 differentiate strategies
// 7. $5K account, 10% max DD = $500 max loss
// 8. P95 DD from backtest is 6.9% = $345, well under $500 limit
//
// DEPLOYMENT:
// 1. Compile this EA in MetaEditor (MQL5)
// 2. Attach to ANY chart (manages its own symbols/timeframes)
// 3. Ensure symbols in Market Watch: NAS100, US30, XAUUSD
// 4. Enable "Allow Algo Trading" in MT5 settings
// 5. EA runs on every tick but only acts on new bar opens
//
// ENTRY TIMING:
// Engine backtests evaluate on COMPLETED bar, enter at close.
// Live: we check completed bar (shift=1) on first tick of NEW bar,
// enter at market. Minor slippage vs backtest — standard for
// bar-close systems.
//+------------------------------------------------------------------+