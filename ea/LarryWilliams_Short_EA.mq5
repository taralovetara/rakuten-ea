//+------------------------------------------------------------------+
//|                                       LarryWilliams_Short_EA.mq5 |
//|                           XAUUSD M5 Short Strategy (Rakuten EA) |
//|                                                                  |
//|   Larry Williams Trend Strength Score <= 5 + Price < EMA200     |
//|   Direction(40) + MACD(30) + FVG(18) + Bonus(16) = 100          |
//+------------------------------------------------------------------+
#property copyright "Rakuten EA"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| Input Parameters                                                  |
//+------------------------------------------------------------------+
input group "=== Trade Settings ==="
input double InpLotSize       = 0.01;    // Lot Size (0.01 = 1oz)
input double InpStopLoss      = 12.0;    // Stop Loss ($ above entry)
input double InpTakeProfit    = 80.0;    // Take Profit ($ below entry)
input int    InpMaxHoldHrs    = 12;      // Max Hold Time (hours)
input int    InpScoreThreshold= 5;       // Score <= this = Short signal
input double InpMaxSpread     = 0.50;    // Max Spread ($) - 0 = disabled
input ulong  InpMagicNumber   = 20260705;// Magic Number

//+------------------------------------------------------------------+
//| Indicator Handles                                                 |
//+------------------------------------------------------------------+
int h_ema20, h_ema50, h_ema200;
int h_ema12, h_ema26;
int h_atr14, h_adx14, h_wpr14;

//+------------------------------------------------------------------+
//| Global Variables                                                  |
//+------------------------------------------------------------------+
CTrade         trade;
datetime       g_lastBarTime     = 0;
bool           g_macdInitialized = false;
double         g_macdSignal      = 0;   // EMA(signal) of MACD line for bar 1
double         g_macdSignalPrev  = 0;   // EMA(signal) of MACD line for bar 2

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(10);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   // --- EMA Handles (MT5 iMA uses SMA seed, matches Pine ta.ema) ---
   h_ema20  = iMA(_Symbol, PERIOD_M5, 20, 0, MODE_EMA, PRICE_CLOSE);
   h_ema50  = iMA(_Symbol, PERIOD_M5, 50, 0, MODE_EMA, PRICE_CLOSE);
   h_ema200 = iMA(_Symbol, PERIOD_M5, 200, 0, MODE_EMA, PRICE_CLOSE);
   h_ema12  = iMA(_Symbol, PERIOD_M5, 12, 0, MODE_EMA, PRICE_CLOSE);
   h_ema26  = iMA(_Symbol, PERIOD_M5, 26, 0, MODE_EMA, PRICE_CLOSE);

   // --- ATR, ADX, WPR (built-in matches Pine Script) ---
   h_atr14 = iATR(_Symbol, PERIOD_M5, 14);
   h_adx14 = iADX(_Symbol, PERIOD_M5, 14);
   h_wpr14 = iWPR(_Symbol, PERIOD_M5, 14);

   // --- Validate handles ---
   if (h_ema20 == INVALID_HANDLE || h_ema50 == INVALID_HANDLE ||
       h_ema200 == INVALID_HANDLE || h_ema12 == INVALID_HANDLE ||
       h_ema26 == INVALID_HANDLE || h_atr14 == INVALID_HANDLE ||
       h_adx14 == INVALID_HANDLE || h_wpr14 == INVALID_HANDLE)
   {
      Print("ERROR: Failed to create indicator handles");
      return INIT_FAILED;
   }

   // --- Initialize MACD signal line EMA from history ---
   if (!InitializeMacdSignal())
   {
      Print("ERROR: Failed to initialize MACD signal line");
      return INIT_FAILED;
   }

   // --- Check for existing open position on startup ---
   if (HasOpenPosition())
      g_lastBarTime = iTime(_Symbol, PERIOD_M5, 0);

   Print("EA initialized OK | SL=$", InpStopLoss,
         " TP=$", InpTakeProfit,
         " MaxHold=", InpMaxHoldHrs, "h",
         " Score<=", InpScoreThreshold);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(h_ema20);
   IndicatorRelease(h_ema50);
   IndicatorRelease(h_ema200);
   IndicatorRelease(h_ema12);
   IndicatorRelease(h_ema26);
   IndicatorRelease(h_atr14);
   IndicatorRelease(h_adx14);
   IndicatorRelease(h_wpr14);
}

//+------------------------------------------------------------------+
//| OnTick - Main Logic                                               |
//+------------------------------------------------------------------+
void OnTick()
{
   // --- Max hold check (runs every tick) ---
   if (HasOpenPosition())
   {
      CheckMaxHold();
      return;  // Only one position at a time
   }

   // --- New bar detection ---
   datetime currentBarTime = iTime(_Symbol, PERIOD_M5, 0);
   if (currentBarTime == g_lastBarTime)
      return;  // Still on the same bar
   g_lastBarTime = currentBarTime;

   // --- Spread filter ---
   if (InpMaxSpread > 0)
   {
      double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                    - SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if (spread > InpMaxSpread)
      {
         Print("Spread too wide: $", DoubleToString(spread, 2),
               " > max $", DoubleToString(InpMaxSpread, 2));
         return;
      }
   }

   // --- Update MACD signal line ---
   UpdateMacdSignal();

   // --- Calculate Larry Williams Score ---
   int score = CalculateScore();

   // --- Get EMA200 for filter ---
   double ema200_val[1];
   if (CopyBuffer(h_ema200, 0, 1, 1, ema200_val) < 1) return;
   double close1 = iClose(_Symbol, PERIOD_M5, 1);

   // --- Signal: Score <= threshold AND Price < EMA200 ---
   if (score <= InpScoreThreshold && close1 < ema200_val[0])
   {
      Print("SIGNAL: Score=", score,
            " Close=", DoubleToString(close1, _Digits),
            " EMA200=", DoubleToString(ema200_val[0], _Digits),
            " @ ", TimeToString(iTime(_Symbol, PERIOD_M5, 1)));
      OpenShortPosition(score);
   }
}

//+------------------------------------------------------------------+
//| InitializeMacdSignal - Walk 500 bars history to seed signal EMA  |
//+------------------------------------------------------------------+
bool InitializeMacdSignal()
{
   int bars = 500;
   double ema12_buf[], ema26_buf[];

   ArraySetAsSeries(ema12_buf, true);
   ArraySetAsSeries(ema26_buf, true);

   if (CopyBuffer(h_ema12, 0, 0, bars, ema12_buf) < bars) return false;
   if (CopyBuffer(h_ema26, 0, 0, bars, ema26_buf) < bars) return false;

   // Calculate MACD line for each bar
   // Array is series: [0]=current bar, [bars-1]=oldest
   double macd_line[];
   ArrayResize(macd_line, bars);
   for (int i = 0; i < bars; i++)
      macd_line[i] = ema12_buf[i] - ema26_buf[i];

   // Seed: SMA of oldest 9 MACD values
   // Oldest 9 are at indices [bars-1] down to [bars-9]
   double sum = 0;
   for (int i = bars - 9; i < bars; i++)
      sum += macd_line[i];
   double sig = sum / 9.0;

   // Walk forward from oldest to newest (index bars-10 down to 0)
   double alpha = 2.0 / 10.0;  // EMA period = 9, alpha = 2/(9+1)
   for (int i = bars - 10; i >= 0; i--)
      sig = alpha * macd_line[i] + (1.0 - alpha) * sig;

   // 'sig' is now the signal value for bar 0 (current forming bar)
   // We want bar 1 (last completed), so we need one more step
   // But bar 0 is still forming, so we use the value as bar 1's signal
   // (It's close enough; on the next new bar it will be precisely updated)
   g_macdSignal = sig;

   // For bar 2's signal, we walk one less step
   double sig2 = sum / 9.0;
   for (int i = bars - 10; i >= 1; i--)
      sig2 = alpha * macd_line[i] + (1.0 - alpha) * sig2;
   g_macdSignalPrev = sig2;

   g_macdInitialized = true;
   return true;
}

//+------------------------------------------------------------------+
//| UpdateMacdSignal - Called on each new bar                        |
//+------------------------------------------------------------------+
void UpdateMacdSignal()
{
   double ema12_buf[2], ema26_buf[2];
   if (CopyBuffer(h_ema12, 0, 1, 2, ema12_buf) < 2) return;
   if (CopyBuffer(h_ema26, 0, 1, 2, ema26_buf) < 2) return;

   // buf[0] = bar 1 (last completed), buf[1] = bar 2
   double macd_bar1 = ema12_buf[0] - ema26_buf[0];

   // Shift: previous bar1 signal becomes bar2 signal
   g_macdSignalPrev = g_macdSignal;

   // Update bar1 signal with EMA formula
   double alpha = 2.0 / 10.0;
   g_macdSignal = alpha * macd_bar1 + (1.0 - alpha) * g_macdSignalPrev;
}

//+------------------------------------------------------------------+
//| CalculateScore - Larry Williams Trend Strength Score              |
//+------------------------------------------------------------------+
int CalculateScore()
{
   // --- Get indicator values for bar 1 (last completed) and bar 2 ---
   double ema20_buf[2], ema50_buf[2];
   double ema12_buf[2], ema26_buf[2];
   double atr_buf[1], adx_buf[1], wpr_buf[2];

   if (CopyBuffer(h_ema20, 0, 1, 2, ema20_buf) < 2) return 100;
   if (CopyBuffer(h_ema50, 0, 1, 2, ema50_buf) < 2) return 100;
   if (CopyBuffer(h_ema12, 0, 1, 2, ema12_buf) < 2) return 100;
   if (CopyBuffer(h_ema26, 0, 1, 2, ema26_buf) < 2) return 100;
   if (CopyBuffer(h_atr14, 0, 1, 1, atr_buf)  < 1) return 100;
   if (CopyBuffer(h_adx14, 0, 0, 1, adx_buf)   < 1) return 100;  // ADX main line
   if (CopyBuffer(h_wpr14, 0, 1, 2, wpr_buf)   < 2) return 100;

   double close1  = iClose(_Symbol, PERIOD_M5, 1);
   double open1   = iOpen(_Symbol, PERIOD_M5, 1);

   double e20  = ema20_buf[0];   double e20p = ema20_buf[1];
   double e50  = ema50_buf[0];   double e50p = ema50_buf[1];
   double atr  = atr_buf[0];
   double adx  = adx_buf[0];
   double wpr  = wpr_buf[0];
   double wprP = wpr_buf[1];

   // MACD line and histogram
   double macdLine  = ema12_buf[0] - ema26_buf[0];
   double macdLineP = ema12_buf[1] - ema26_buf[1];
   double macdHist  = macdLine - g_macdSignal;     // histogram for bar 1
   double macdHistP = macdLineP - g_macdSignalPrev; // histogram for bar 2

   // FVG: bullFVG = low[1] > high[3] (relative to signal bar = bar 1)
   // Pine low[1] = bar i-1 = MT5 bar 2, Pine high[3] = bar i-3 = MT5 bar 4
   double low_prev  = iLow(_Symbol, PERIOD_M5, 2);
   double high_prev3= iHigh(_Symbol, PERIOD_M5, 4);
   double bullFVG = MathMax(0, low_prev - high_prev3);

   // Volume ratio: volume > SMA(volume, 20)
   double volSum = 0;
   for (int i = 1; i <= 20; i++)
      volSum += (double)iVolume(_Symbol, PERIOD_M5, i);
   double volSma = volSum / 20.0;
   double currentVol = (double)iVolume(_Symbol, PERIOD_M5, 1);

   // ============================================================
   // 1. Direction Score (Max 40)
   // ============================================================
   int dirScore = 0;
   if      (close1 > e20 && e20 > e50 && e50 > e200 && e20 > e20p && e50 > e50p) dirScore = 40;
   else if (close1 > e20 && e20 > e50 && e50 > e200) dirScore = 35;
   else if (close1 > e20 && e20 > e50) dirScore = 28;
   else if (close1 > e200) dirScore = 18;

   // ============================================================
   // 2. MACD Score (Max 30)
   // ============================================================
   int macdScore = 0;
   if (macdLine > 0)
   {
      if      (macdHist > 0 && macdHist > macdHistP * 1.5) macdScore = 30;
      else if (macdHist > macdHistP)                         macdScore = 25;
      else if (macdLine > g_macdSignal && macdLineP <= g_macdSignalPrev) macdScore = 22;
      else                                                      macdScore = 15;
   }

   // ============================================================
   // 3. FVG Score (Max 18)
   // ============================================================
   int fvgScore = 0;
   double atrSafe = (atr > 0) ? atr : 10.0;
   if      (bullFVG > atrSafe * 0.8) fvgScore = 18;
   else if (bullFVG > atrSafe * 0.3) fvgScore = 13;
   else if (bullFVG > 0)              fvgScore = 7;

   // ============================================================
   // 4. Bonus Score (Max 16)
   // ============================================================
   int bonus = 0;
   if (adx > 30)                          bonus += 8;
   if (currentVol > volSma && close1 > open1) bonus += 5;
   if (wpr > -80 && wpr < -20)            bonus += 3;

   // ============================================================
   // Total Score
   // ============================================================
   int totalScore = dirScore + macdScore + fvgScore + bonus;
   return MathMax(0, MathMin(totalScore, 100));
}

//+------------------------------------------------------------------+
//| HasOpenPosition - Check if we have an open short position        |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for (int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if (ticket == 0) continue;
      if (PositionGetInteger(POSITION_MAGIC) == InpMagicNumber &&
          PositionGetString(POSITION_SYMBOL) == _Symbol &&
          PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_SELL)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| CheckMaxHold - Close position if max hold time exceeded          |
//+------------------------------------------------------------------+
void CheckMaxHold()
{
   for (int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if (ticket == 0) continue;
      if (PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      if (PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      int holdMinutes = (int)(TimeCurrent() - openTime) / 60;
      int maxHoldMinutes = InpMaxHoldHrs * 60;

      if (holdMinutes >= maxHoldMinutes)
      {
         double pnl = PositionGetDouble(POSITION_PROFIT);
         trade.PositionClose(ticket);
         Print("MAX HOLD CLOSE: ", holdMinutes, "min, PnL=$",
               DoubleToString(pnl, 2), " @ ", TimeToString(TimeCurrent()));
      }
   }
}

//+------------------------------------------------------------------+
//| OpenShortPosition                                                 |
//+------------------------------------------------------------------+
void OpenShortPosition(int score)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl  = NormalizeDouble(ask + InpStopLoss, _Digits);
   double tp  = NormalizeDouble(ask - InpTakeProfit, _Digits);

   // Verify SL/TP against minimum stop level
   long stopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minDist = stopLevel * _Point * 1.5;  // 1.5x safety margin
   if (sl - ask < minDist)
   {
      Print("ERROR: SL too close. Need $", DoubleToString(minDist, _Digits),
            ", have $", DoubleToString(InpStopLoss, _Digits));
      return;
   }
   if (ask - tp < minDist)
   {
      Print("ERROR: TP too close. Need $", DoubleToString(minDist, _Digits),
            ", have $", DoubleToString(InpTakeProfit, _Digits));
      return;
   }

   // Build comment
   string comment = StringFormat("LW-Short Score=%d SL=$%.0f TP=$%.0f",
                                 score, InpStopLoss, InpTakeProfit);

   if (trade.Sell(InpLotSize, _Symbol, ask, sl, tp, comment))
   {
      Print("OPEN SHORT: Price=", DoubleToString(ask, _Digits),
            " SL=", DoubleToString(sl, _Digits),
            " TP=", DoubleToString(tp, _Digits),
            " Score=", score,
            " Lot=", DoubleToString(InpLotSize, 2));
   }
   else
   {
      Print("ERROR opening short: ", trade.ResultRetcode(),
            " - ", trade.ResultRetcodeDescription());
   }
}
//+------------------------------------------------------------------+