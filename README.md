# Rakuten EA - XAUUSD 短線做空策略

## 策略概述

基於 **Larry Williams 趨勢強度量化評分** 的 XAUUSD 短線做空策略，用於 Rakuten Securities 自動交易（EA）。

### 核心邏輯

- 指標本質是**做多趨勢強度**指標（滿分 100）
- **Score ≤ 5 = 無做多趨勢 = 做空信號**
- 額外條件：收盤價 < EMA200（確保空頭環境）

### 評分結構

| 維度 | 滿分 | 條件 |
|------|------|------|
| Direction | 40 | EMA20/50/200 排列 + 上升 |
| MACD | 30 | MACD(12,26,9) 柱狀圖動能 |
| FVG (Bull) | 18 | Bull FVG > ATR 閾值 |
| Bonus | 16 | ADX>30(+8) + 量增陽燭(+5) + WPR區間(+3) |

### 交易規格

- 品種：XAUUSD (黃金)
- 手數：0.01 lot (1oz)
- 方向：Short only
- SL/TP：美金金額（非點數），例如 SL=$12 = 金價反彈$12止損
- Short PnL = 入場價 - 出場價（因為 0.01 lot = 1oz，每$1價格變動 = $1盈虧）

## 回測結果（5min 圖表，60日數據）

使用修正後指標（Wilder's RMA ATR + ta.dmi ADX，精確匹配 Pine Script）：

| 排名 | SL | TP | 持倉 | 交易 | 勝率 | PF | 淨利潤 | 月均 |
|------|-----|-----|------|------|------|-----|---------|-------|
| 1 | $12 | $80 | 12h | 119 | 31.1% | 2.01 | +$979.70 | +$458.80 |
| 2 | $15 | $80 | 12h | 107 | 34.6% | 1.93 | +$957.20 | +$448.26 |
| 3 | $10 | $80 | 12h | 135 | 25.9% | 1.96 | +$952.00 | +$445.83 |

## 檔案結構

```
backtest/                    # 回測腳本
├── 01_1h_score5_final.py    # 1H 圖表 - 精細 SL/TP 搜索（730天，冷卻期模式）
├── 02_1h_score5_modes.py    # 1H 圖表 - 冷卻期 vs 立即再入場 vs 不重疊模式比較
├── 03_multitf_detail.py     # 多時間框架比較（1H vs 15min vs 5min）
├── 04_5min_60d.py           # 5min - 格搜索版（有信號不一致 bug，僅供參考）
├── 05_5min_trades_detail.py # 5min - SL=$50/TP=$200 逐筆明細（舊指標）
├── 06_5min_extended.py      # 5min - 擴展數據嘗試（模擬5min）
├── 07_5min_real.py          # 5min - 真實15min+5min數據 SL/TP 搜索
├── 08_5min_fixed.py         # 5min - 完全對齊 Pine Script（SMA種子 EMA + Wilder ATR/ADX）
└── 09_5min_clean.py         # 5min - 最終修正版（Wilder's RMA ATR + ta.dmi ADX）★
```

### 腳本進化歷史

1. **01-03**: 1H 圖表初步研究，確立策略方向
2. **04-05**: 5min 初步回測，發現信號不一致 bug
3. **06-07**: 嘗試擴展數據源，確認 yfinance 5min 限制為 60 天
4. **08**: 完全對齊 Pine Script（EMA 用 SMA 做種子，ATR/ADX 用 Wilder's 平滑）
5. **09**: 最終版本，修正 ATR 為 Wilder's RMA，ADX 精確匹配 ta.dmi(14,14)

## 已知限制

- yfinance 5min 數據最多 60 天（~13,500 根 K 線）
- 60 天樣本量偏少，回測結果不代表未來表現
- 未考慮點差、滑點、佣金
- Python `ewm(adjust=False)` 用首值做 EMA 種子，Pine Script 用 SMA 做種子（500 根後收斂）
- 實盤前建議用更長數據或其他平台驗證

## Pine Script 指標

對應的 TradingView Pine Script 指標：
`Larry Williams 趨勢強度量化評分` (//@version=5)

## 環境

- Python 3.12+
- 依賴：pandas, numpy, yfinance

```bash
pip install pandas numpy yfinance
```