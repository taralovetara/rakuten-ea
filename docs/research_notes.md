# 回測研究筆記

## 指標對齊 Pine Script 的過程

### 問題 1: ATR 計算
- **錯誤**: `C.rolling(14).max() - C.rolling(14).min()` (簡單方法)
- **正確**: Wilder's RMA (alpha=1/14)，匹配 Pine `ta.atr(14)`
- **影響**: FVG Score 的 18 分門檻會變

### 問題 2: ADX 計算
- **錯誤**: 手寫 ADX 用簡單 14 週期窗口
- **正確**: +DM/-DM/TR 各自做 Wilder's RMA → DI+/DI- → DX → ADX RMA
- **影響**: Bonus 的 8 分 (ADX>30) 門檻會變

### 問題 3: 信號收集與盈虧不一致 (嚴重 bug)
- **錯誤**: 用 SL=$15/TP=$60 收集 89 筆信號，但用 SL=$50/TP=$200 算盈虧
- **正確**: 每個 SL/TP 組合用自己參數同時做信號收集 + 盈虧計算
- **結果**: 89 筆 → 正確的 38 筆（SL=$50/TP=$200 時），TP 次數從錯誤的 2 次變為 0 次

### 問題 4: EMA 種子
- Python `ewm(adjust=False)` 用第一個值做種子
- Pine Script `ta.ema()` 用 SMA(period) 做種子
- 500 根後兩者收斂，5min 圖表 start_bar=500 已覆蓋

### 問題 5: SL/TP 單位
- SL/TP 是**美金金額**（每盎司價格變動），不是點數
- 0.01 lot = 1oz，所以 Short PnL = 入場價 - 出場價（直接美元）

## 數據限制

- yfinance 5min 硬限制 = 60 天
- 分批下載測試：最多只拉到 60 天
- 嘗試過模擬 5min（1H 拆分 + 隨機噪音），但內部走勢不可靠

## 結論

最終使用 `09_5min_clean.py` 的結果，ATR 和 ADX 已修正為匹配 Pine Script。