//+------------------------------------------------------------------+
//|                              LarryWilliams_Bidirectional_EA.mq5  |
//|              XAUUSD M5 Long+Short - Larry Williams Score System   |
//|                                                                  |
//|   Scoring EXACTLY matches backtest Python scripts (01-09)        |
//|   Direction(40) + MACD(30) + FVG(18) + Bonus(16) = max 100      |
//|   Long:  Score>=95 + Price>EMA200  -> Buy  SL=-$12  TP=+$80     |
//|   Short: Score<=5  + Price<EMA200  -> Sell SL=+$12  TP=-$80     |
//+------------------------------------------------------------------+
#property copyright "Rakuten EA"
#property version   "1.10"
#property description "Larry Williams 趨勢強度評分雙向策略 (XAUUSD M5)"
#property description "Long:  Score>=95 + Price>EMA200 | SL=$12 TP=$80 12h"
#property description "Short: Score<=5  + Price<EMA200 | SL=$12 TP=$80 12h"
#property description "評分邏輯精確匹配 Python 回測腳本 09_5min_clean.py"
#property strict

#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| 輸入參數                                                          |
//+------------------------------------------------------------------+
input group "=== 交易參數 (回測最佳值) ==="
input double InpLotSize       = 0.01;    // 手數 (0.01 = 1 oz)
input double InpStopLoss      = 12.0;    // 止損 $ (回測最佳)
input double InpTakeProfit    = 80.0;    // 止盈 $ (回測最佳)
input int    InpMaxHoldHrs    = 12;      // 最大持倉 小時 (回測最佳)
input int    InpLongThreshold = 95;      // 做多閾值 (>=此值做多)
input int    InpShortThreshold= 5;       // 做空閾值 (<=此值做空)
input double InpMaxSpread     = 0.50;    // 最大點差 $ (0=關閉)
input ulong  InpMagicNumber   = 20250707;// Magic Number

input group "=== 方向開關 ==="
input bool   InpEnableLong    = true;    // 啟用做多
input bool   InpEnableShort   = true;    // 啟用做空

input group "=== 調試 ==="
input bool   InpDebugPrint    = true;    // 每bar打印分數 (Expert tab)

//+------------------------------------------------------------------+
//| 指標句柄                                                          |
//+------------------------------------------------------------------+
int h_ema20, h_ema50, h_ema200;
int h_ema12, h_ema26;       // MACD 用 EMA12/26 手動計算
int h_atr14, h_adx14, h_wpr14;

//+------------------------------------------------------------------+
//| 全域變數                                                          |
//+------------------------------------------------------------------+
CTrade    trade;
datetime  g_lastBarTime     = 0;
bool      g_macdReady       = false;
double    g_macdSignal      = 0;   // Signal EMA for bar 1
double    g_macdSignalPrev  = 0;   // Signal EMA for bar 2

// 評分明細 (顯示用)
int  g_dirScore  = 0;
int  g_macdScore = 0;
int  g_fvgScore  = 0;
int  g_bonusScore= 0;
int  g_totalScore= -1;

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
{
   //--- 交易設置
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(50);
   trade.SetTypeFilling(DetectFillingMode());

   //--- EMA 句柄 (MT5 iMA 用 SMA 做種子，500根後與 Pine 收斂)
   h_ema20  = iMA(_Symbol, PERIOD_M5, 20, 0, MODE_EMA, PRICE_CLOSE);
   h_ema50  = iMA(_Symbol, PERIOD_M5, 50, 0, MODE_EMA, PRICE_CLOSE);
   h_ema200 = iMA(_Symbol, PERIOD_M5, 200, 0, MODE_EMA, PRICE_CLOSE);
   h_ema12  = iMA(_Symbol, PERIOD_M5, 12, 0, MODE_EMA, PRICE_CLOSE);
   h_ema26  = iMA(_Symbol, PERIOD_M5, 26, 0, MODE_EMA, PRICE_CLOSE);

   //--- ATR / ADX / WPR (內建指標匹配 Pine Script)
   h_atr14 = iATR(_Symbol, PERIOD_M5, 14);
   h_adx14 = iADX(_Symbol, PERIOD_M5, 14);
   h_wpr14 = iWPR(_Symbol, PERIOD_M5, 14);

   //--- 驗證句柄
   if(h_ema20==INVALID_HANDLE || h_ema50==INVALID_HANDLE ||
      h_ema200==INVALID_HANDLE || h_ema12==INVALID_HANDLE ||
      h_ema26==INVALID_HANDLE || h_atr14==INVALID_HANDLE ||
      h_adx14==INVALID_HANDLE || h_wpr14==INVALID_HANDLE)
   {
      Print("ERROR: 指標初始化失敗，請確認 ", _Symbol, " 有 M5 數據");
      return INIT_FAILED;
   }

   //--- 手動初始化 MACD Signal EMA (SMA 種子 + 500 bar walk-forward)
   if(!InitMacdSignal())
   {
      Print("ERROR: MACD Signal 初始化失敗");
      return INIT_FAILED;
   }

   //--- 啟動時如有持倉，同步 bar time 避免重複信號
   if(HasOpenPosition())
      g_lastBarTime = iTime(_Symbol, PERIOD_M5, 0);

   Print("═══════════════════════════════════════════════════════");
   Print("  Larry Williams XAUUSD Bidirectional EA v1.0");
   Print("  品種: ", _Symbol, " | 時間框架: M5 (強制)");
   Print("  Long:  Score>=", InpLongThreshold,  " | Short: Score<=", InpShortThreshold);
   Print("  SL=$", InpStopLoss, " TP=$", InpTakeProfit,
         " MaxHold=", InpMaxHoldHrs, "h");
   Print("  Lot=", InpLotSize, " MaxSpread=$", InpMaxSpread);
   Print("  Enable Long=", InpEnableLong, " Enable Short=", InpEnableShort);
  Print("  Debug Print=", InpDebugPrint);
   Print("  評分: 階梯式 (匹配回測 09_5min_clean.py)");
   Print("═══════════════════════════════════════════════════════");

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
   Comment("");
}

//+------------------------------------------------------------------+
//| OnTick - Main Logic                                               |
//+------------------------------------------------------------------+
void OnTick()
{
   //--- 1) 有持倉 → 只檢查 MaxHold
   if(HasOpenPosition())
   {
      CheckMaxHold();
      return;
   }

   //--- 2) 新 K 線檢測
   datetime curBar = iTime(_Symbol, PERIOD_M5, 0);
   if(curBar == g_lastBarTime)
      return;
   g_lastBarTime = curBar;

   //--- 3) 點差過濾
   if(InpMaxSpread > 0)
   {
      double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                    - SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(spread > InpMaxSpread)
         return;
   }

   //--- 4) 更新 MACD Signal EMA (每根新 K 線)
   UpdateMacdSignal();

   //--- 5) 計算評分
   int score = CalculateScore();
   g_totalScore = score;

   //--- 6) EMA200
   double ema200_buf[1];
   if(CopyBuffer(h_ema200, 0, 1, 1, ema200_buf) < 1)
      return;
   double close1 = iClose(_Symbol, PERIOD_M5, 1);
   double atr_buf[1];
   CopyBuffer(h_atr14, 0, 1, 1, atr_buf);

   //--- 7) Debug: 每根 bar 打印評分
   if(InpDebugPrint)
   {
      string dirName = "";
      if(score >= InpLongThreshold)  dirName = " [LONG ZONE]";
      else if(score <= InpShortThreshold) dirName = " [SHORT ZONE]";
      Print("Bar ", TimeToString(iTime(_Symbol, PERIOD_M5, 1), TIME_DATE|TIME_MINUTES),
            " | Score=", score, dirName,
            " (D=", g_dirScore, " M=", g_macdScore,
            " F=", g_fvgScore, " B=", g_bonusScore, ")",
            " Close=$", DoubleToString(close1, 2),
            " EMA200=$", DoubleToString(ema200_buf[0], 2),
            " Pos=", close1 > ema200_buf[0] ? "ABOVE" : "BELOW");
   }

   //--- 8) 顯示面板
   DrawPanel(score, close1, ema200_buf[0], atr_buf[0]);

   //--- 9) 做多信號: Score>=95 + Price>EMA200
   if(InpEnableLong && score >= InpLongThreshold && close1 > ema200_buf[0])
   {
      Print("SIGNAL LONG: Score=", score,
            " Dir=", g_dirScore, " MACD=", g_macdScore,
            " FVG=", g_fvgScore, " Bonus=", g_bonusScore,
            " @ ", TimeToString(iTime(_Symbol, PERIOD_M5, 1), TIME_DATE|TIME_MINUTES));
      OpenLong(score);
      return;
   }

   //--- 10) 做空信號: Score<=5 + Price<EMA200
   if(InpEnableShort && score <= InpShortThreshold && close1 < ema200_buf[0])
   {
      Print("SIGNAL SHORT: Score=", score,
            " Dir=", g_dirScore, " MACD=", g_macdScore,
            " FVG=", g_fvgScore, " Bonus=", g_bonusScore,
            " @ ", TimeToString(iTime(_Symbol, PERIOD_M5, 1), TIME_DATE|TIME_MINUTES));
      OpenShort(score);
      return;
   }
}

//+------------------------------------------------------------------+
//| InitMacdSignal - SMA 種子 + 500 bar walk-forward                 |
//| 精確匹配 Pine Script: signal = ta.ema(macdLine, 9)               |
//| Pine 用 SMA(9) 做種子，MT5 內建 iMACD 用 EMA 種子，會有偏差     |
//+------------------------------------------------------------------+
bool InitMacdSignal()
{
   int bars = 500;
   double ema12_buf[], ema26_buf[];
   ArraySetAsSeries(ema12_buf, true);
   ArraySetAsSeries(ema26_buf, true);

   if(CopyBuffer(h_ema12, 0, 0, bars, ema12_buf) < bars) return false;
   if(CopyBuffer(h_ema26, 0, 0, bars, ema26_buf) < bars) return false;

   // 計算每根 bar 的 MACD Line = EMA12 - EMA26
   double macd_line[];
   ArrayResize(macd_line, bars);
   for(int i = 0; i < bars; i++)
      macd_line[i] = ema12_buf[i] - ema26_buf[i];

   // 種子: SMA(oldest 9 MACD values)
   double sum = 0;
   for(int i = bars - 9; i < bars; i++)
      sum += macd_line[i];
   double sig = sum / 9.0;

   // Walk forward: oldest (index bars-10) → newest (index 0)
   double alpha = 2.0 / 10.0;  // EMA(9): alpha = 2/(9+1)
   for(int i = bars - 10; i >= 0; i--)
      sig = alpha * macd_line[i] + (1.0 - alpha) * sig;

   g_macdSignal = sig;

   // bar[2] signal: 少走一步
   double sig2 = sum / 9.0;
   for(int i = bars - 10; i >= 1; i--)
      sig2 = alpha * macd_line[i] + (1.0 - alpha) * sig2;
   g_macdSignalPrev = sig2;

   g_macdReady = true;
   return true;
}

//+------------------------------------------------------------------+
//| UpdateMacdSignal - 每根新 K 線更新 Signal EMA                     |
//+------------------------------------------------------------------+
void UpdateMacdSignal()
{
   double ema12_buf[2], ema26_buf[2];
   if(CopyBuffer(h_ema12, 0, 1, 2, ema12_buf) < 2) return;
   if(CopyBuffer(h_ema26, 0, 1, 2, ema26_buf) < 2) return;

   double macd_bar1 = ema12_buf[0] - ema26_buf[0];

   g_macdSignalPrev = g_macdSignal;

   double alpha = 2.0 / 10.0;
   g_macdSignal = alpha * macd_bar1 + (1.0 - alpha) * g_macdSignalPrev;
}

//+------------------------------------------------------------------+
//| CalculateScore - 精確匹配回測腳本 09_5min_clean.py                |
//|                                                                    |
//| 評分結構 (階梯式，非線性加法):                                     |
//|   Direction(40)  EMA 排列 + 斜率                                  |
//|   MACD(30)      MACD 動能 (手動 Signal EMA)                       |
//|   FVG(18)       Bull FVG x ATR 閾值 (漸進式)                     |
//|   Bonus(16)     ADX>30(+8) + 量增陽燭(+5) + WPR區間(+3)          |
//+------------------------------------------------------------------+
int CalculateScore()
{
   double ema20_buf[2], ema50_buf[2];
   double ema12_buf[2], ema26_buf[2];
   double atr_buf[1], adx_buf[1], wpr_buf[2];

   if(CopyBuffer(h_ema20, 0, 1, 2, ema20_buf) < 2) return 100;
   if(CopyBuffer(h_ema50, 0, 1, 2, ema50_buf) < 2) return 100;
   if(CopyBuffer(h_ema12, 0, 1, 2, ema12_buf) < 2) return 100;
   if(CopyBuffer(h_ema26, 0, 1, 2, ema26_buf) < 2) return 100;
   if(CopyBuffer(h_atr14, 0, 1, 1, atr_buf)  < 1) return 100;
   if(CopyBuffer(h_adx14, 0, 0, 1, adx_buf)   < 1) return 100;
   if(CopyBuffer(h_wpr14, 0, 1, 2, wpr_buf)   < 2) return 100;

   double close1 = iClose(_Symbol, PERIOD_M5, 1);
   double open1  = iOpen(_Symbol, PERIOD_M5, 1);

   double e20  = ema20_buf[0];  double e20p = ema20_buf[1];
   double e50  = ema50_buf[0];  double e50p = ema50_buf[1];
   double e200_buf[1];
   CopyBuffer(h_ema200, 0, 1, 1, e200_buf);
   double e200 = e200_buf[0];

   double atr = atr_buf[0];
   double adx = adx_buf[0];
   double wpr = wpr_buf[0];

   // MACD
   double macdLine  = ema12_buf[0] - ema26_buf[0];
   double macdLineP = ema12_buf[1] - ema26_buf[1];
   double macdHist  = macdLine - g_macdSignal;
   double macdHistP = macdLineP - g_macdSignalPrev;

   // FVG: bullFVG = low[1] > high[3] (Pine bar 索引)
   double low_prev   = iLow(_Symbol, PERIOD_M5, 2);
   double high_prev3 = iHigh(_Symbol, PERIOD_M5, 4);
   double bullFVG    = MathMax(0, low_prev - high_prev3);

   // 成交量
   double volSum = 0;
   for(int i = 1; i <= 20; i++)
      volSum += (double)iVolume(_Symbol, PERIOD_M5, i);
   double volSma    = volSum / 20.0;
   double currentVol = (double)iVolume(_Symbol, PERIOD_M5, 1);

   //=============================================================
   // 1. DIRECTION SCORE (Max 40)
   //=============================================================
   g_dirScore = 0;
   if(close1 > e20 && e20 > e50 && e50 > e200 && e20 > e20p && e50 > e50p)
      g_dirScore = 40;
   else if(close1 > e20 && e20 > e50 && e50 > e200)
      g_dirScore = 35;
   else if(close1 > e20 && e20 > e50)
      g_dirScore = 28;
   else if(close1 > e200)
      g_dirScore = 18;

   //=============================================================
   // 2. MACD SCORE (Max 30)
   //=============================================================
   g_macdScore = 0;
   if(macdLine > 0)
   {
      if(macdHist > 0 && macdHist > macdHistP * 1.5)
         g_macdScore = 30;
      else if(macdHist > macdHistP)
         g_macdScore = 25;
      else if(macdLine > g_macdSignal && macdLineP <= g_macdSignalPrev)
         g_macdScore = 22;
      else
         g_macdScore = 15;
   }

   //=============================================================
   // 3. FVG SCORE (Max 18)
   //=============================================================
   g_fvgScore = 0;
   double atrSafe = (atr > 0) ? atr : 10.0;
   if(bullFVG > atrSafe * 0.8)
      g_fvgScore = 18;
   else if(bullFVG > atrSafe * 0.3)
      g_fvgScore = 13;
   else if(bullFVG > 0)
      g_fvgScore = 7;

   //=============================================================
   // 4. BONUS SCORE (Max 16)
   //=============================================================
   g_bonusScore = 0;
   if(adx > 30)
      g_bonusScore += 8;
   if(currentVol > volSma && close1 > open1)
      g_bonusScore += 5;
   if(wpr > -80 && wpr < -20)
      g_bonusScore += 3;

   //=============================================================
   int total = g_dirScore + g_macdScore + g_fvgScore + g_bonusScore;
   return MathMax(0, MathMin(total, 100));
}

//+------------------------------------------------------------------+
//| HasOpenPosition - 檢查任何方向的持倉                              |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) == (long)InpMagicNumber &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| CheckMaxHold                                                     |
//+------------------------------------------------------------------+
void CheckMaxHold()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)InpMagicNumber) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      int holdMinutes = (int)(TimeCurrent() - openTime) / 60;
      int maxHoldMinutes = InpMaxHoldHrs * 60;

      if(holdMinutes >= maxHoldMinutes)
      {
         long posType = PositionGetInteger(POSITION_TYPE);
         string dirStr = (posType == POSITION_TYPE_BUY) ? "LONG" : "SHORT";
         double pnl = PositionGetDouble(POSITION_PROFIT);
         trade.PositionClose(ticket);
         Print("MAX HOLD CLOSE [", dirStr, "]: ", holdMinutes/60, "h ",
               holdMinutes%60, "m | PnL=$", DoubleToString(pnl, 2));
      }
      return;
   }
}

//+------------------------------------------------------------------+
//| OpenLong                                                          |
//+------------------------------------------------------------------+
void OpenLong(int score)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl  = NormalizeDouble(bid - InpStopLoss, _Digits);
   double tp  = NormalizeDouble(bid + InpTakeProfit, _Digits);

   //--- 最小停損距離檢查
   long stopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minDist = stopLevel * _Point * 1.5;
   if(bid - sl < minDist)
   {
      Print("ERROR: SL 太近. 最少 $", DoubleToString(minDist, _Digits));
      return;
   }
   if(tp - bid < minDist)
   {
      Print("ERROR: TP 太近. 最少 $", DoubleToString(minDist, _Digits));
      return;
   }

   string comment = StringFormat("LW-Long S%d SL=$%.0f TP=$%.0f",
                                 score, InpStopLoss, InpTakeProfit);

   if(trade.Buy(InpLotSize, _Symbol, bid, sl, tp, comment))
   {
      Print("OPEN LONG: Bid=", DoubleToString(bid, _Digits),
            " SL=", DoubleToString(sl, _Digits),
            " TP=", DoubleToString(tp, _Digits),
            " | Score=", score,
            "=", g_dirScore, "+", g_macdScore,
            "+", g_fvgScore, "+", g_bonusScore);
   }
   else
   {
      Print("ERROR: ", trade.ResultRetcode(),
            " - ", trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
//| OpenShort                                                         |
//+------------------------------------------------------------------+
void OpenShort(int score)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl  = NormalizeDouble(ask + InpStopLoss, _Digits);
   double tp  = NormalizeDouble(ask - InpTakeProfit, _Digits);

   //--- 最小停損距離檢查
   long stopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minDist = stopLevel * _Point * 1.5;
   if(sl - ask < minDist)
   {
      Print("ERROR: SL 太近. 最少 $", DoubleToString(minDist, _Digits));
      return;
   }
   if(ask - tp < minDist)
   {
      Print("ERROR: TP 太近. 最少 $", DoubleToString(minDist, _Digits));
      return;
   }

   string comment = StringFormat("LW-Short S%d SL=$%.0f TP=$%.0f",
                                 score, InpStopLoss, InpTakeProfit);

   if(trade.Sell(InpLotSize, _Symbol, ask, sl, tp, comment))
   {
      Print("OPEN SHORT: Ask=", DoubleToString(ask, _Digits),
            " SL=", DoubleToString(sl, _Digits),
            " TP=", DoubleToString(tp, _Digits),
            " | Score=", score,
            "=", g_dirScore, "+", g_macdScore,
            "+", g_fvgScore, "+", g_bonusScore);
   }
   else
   {
      Print("ERROR: ", trade.ResultRetcode(),
            " - ", trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
//| DrawPanel - 圖表資訊面板 (雙向)                                   |
//+------------------------------------------------------------------+
void DrawPanel(int score, double close_price, double ema200, double atr)
{
   string sig = "---";
   bool hasPos = HasOpenPosition();

   if(hasPos)
   {
      // 找出持倉方向
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(PositionGetInteger(POSITION_MAGIC) == (long)InpMagicNumber &&
            PositionGetString(POSITION_SYMBOL) == _Symbol)
         {
            long posType = PositionGetInteger(POSITION_TYPE);
            sig = (posType == POSITION_TYPE_BUY) ? "IN LONG" : "IN SHORT";
            break;
         }
      }
   }
   else
   {
      if(InpEnableLong && score >= InpLongThreshold && close_price > ema200)
         sig = "LONG !!";
      else if(InpEnableShort && score <= InpShortThreshold && close_price < ema200)
         sig = "SHORT !!";
      else
         sig = StringFormat("WAIT (S=%d)", score);
   }

   string longSt  = InpEnableLong  ? "ON" : "OFF";
   string shortSt = InpEnableShort ? "ON" : "OFF";

   string info  = "=== LW Bidirectional EA v1.0 ===\n";
   info += StringFormat("Score: %d  (Long>=%d Short<=%d)\n",
                        score, InpLongThreshold, InpShortThreshold);
   info += StringFormat("  Dir(%d) MACD(%d) FVG(%d) Bonus(%d)\n",
                         g_dirScore, g_macdScore, g_fvgScore, g_bonusScore);
   info += StringFormat("Signal: %s\n", sig);
   info += StringFormat("Mode:   Long=%s | Short=%s\n", longSt, shortSt);
   info += "-------------------------\n";
   info += StringFormat("Close:   $%.2f\n", close_price);
   info += StringFormat("EMA200:  $%.2f\n", ema200);
   info += StringFormat("ATR(14): $%.2f\n", atr);
   info += "-------------------------\n";
   info += StringFormat("SL=$%.0f TP=$%.0f Hold=%dh\n",
                         InpStopLoss, InpTakeProfit, InpMaxHoldHrs);
   info += StringFormat("Lot=%.2f Spread=$%.2f\n",
                         InpLotSize,
                         SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                       - SymbolInfoDouble(_Symbol, SYMBOL_BID));
   Comment(info);
}

//+------------------------------------------------------------------+
//| DetectFillingMode - 自動偵測 broker 成交模式                      |
//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING DetectFillingMode()
{
   uint filling = (uint)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}
//+------------------------------------------------------------------+