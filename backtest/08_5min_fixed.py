#!/usr/bin/env python3
"""
5min 回測 - 修正版 (完全對齊 TradingView Pine Script)
修正: ATR 用 Wilder's RMA, ADX 用 Wilder's 平滑, EMA 用 SMA 做種子
每個 SL/TP 組合用同一組參數做信號收集+盈虧計算
"""
import pandas as pd, numpy as np
import warnings, time
warnings.filterwarnings('ignore')
t0 = time.time()

import yfinance as yf
gold = yf.download("GC=F", period="60d", interval="5m", progress=False)
if isinstance(gold.columns, pd.MultiIndex):
    gold.columns = gold.columns.get_level_values(0)
gold = gold.dropna().sort_index()
print(f"數據: {len(gold)}根, {gold.index[0]} ~ {gold.index[-1]}")

C=gold['Close']; H=gold['High']; L=gold['Low']; O=gold['Open']; V=gold['Volume']
n = len(gold)

# ══════════════════════════════════════════════════════════════
# 修正1: EMA - 用 SMA 做種子 (對齊 TradingView ta.ema)
# ══════════════════════════════════════════════════════════════
print("計算指標 (修正版)...", end="", flush=True)

def tv_ema(src, period):
    """對齊 TradingView ta.ema: SMA做種子, 然後 EMA"""
    alpha = 2.0 / (period + 1)
    vals = src.values.copy().astype(float)
    length = len(vals)
    ema = np.full(length, np.nan)
    # 找第一個非 NaN
    valid = np.where(~np.isnan(vals))[0]
    if len(valid) < period:
        return pd.Series(ema, index=src.index)
    # 種子 = 前 period 個有效值嘅 SMA (從第一個有效值開始)
    start_idx = valid[0]
    if start_idx + period > length:
        return pd.Series(ema, index=src.index)
    seed = np.nanmean(vals[start_idx:start_idx + period])
    ema[start_idx + period - 1] = seed
    for i in range(start_idx + period, length):
        if np.isnan(vals[i]):
            ema[i] = ema[i-1]
        else:
            ema[i] = alpha * vals[i] + (1 - alpha) * ema[i-1]
    return pd.Series(ema, index=src.index)

ema20 = tv_ema(C, 20)
ema50 = tv_ema(C, 50)
ema200 = tv_ema(C, 200)

# ══════════════════════════════════════════════════════════════
# 修正2: MACD - 對齊 TradingView ta.macd(close, 12, 26, 9)
# ══════════════════════════════════════════════════════════════
ema12 = tv_ema(C, 12)
ema26 = tv_ema(C, 26)
macdLine = ema12 - ema26
signalLine = tv_ema(macdLine, 9)
macdHist = macdLine - signalLine

# ══════════════════════════════════════════════════════════════
# 修正3: ATR - 用 Wilder's RMA (對齊 TradingView ta.atr)
# ══════════════════════════════════════════════════════════════
def tv_atr(high, low, close, period=14):
    """對齊 TradingView ta.atr: SMA種子 + Wilder's RMA"""
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    
    atr = np.full(n, np.nan)
    if len(tr.iloc[:period].dropna()) < period:
        return pd.Series(atr, index=high.index)
    
    # 種子 = 前 period 根 TR 嘅 SMA
    atr[period-1] = tr.iloc[:period].mean()
    # Wilder's RMA: atr = (prev_atr * (period-1) + current_tr) / period
    for i in range(period, n):
        if np.isnan(tr.iloc[i]) or np.isnan(atr[i-1]):
            atr[i] = atr[i-1] if not np.isnan(atr[i-1]) else tr.iloc[i]
        else:
            atr[i] = (atr[i-1] * (period - 1) + tr.iloc[i]) / period
    return pd.Series(atr, index=high.index)

atr14 = tv_atr(H, L, C, 14)

# ══════════════════════════════════════════════════════════════
# 修正4: ADX - 用 Wilder's 平滑 (對齊 TradingView ta.dmi(14,14))
# ══════════════════════════════════════════════════════════════
def tv_dmi(high, low, close, di_len=14, adx_len=14):
    """對齊 TradingView ta.dmi(diLength, adxSmoothing)"""
    # True Range
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    
    # +DM / -DM
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=high.index)
    
    # Wilder's smoothing for TR, +DM, -DM
    atr = np.full(n, np.nan)
    smooth_plus_dm = np.full(n, np.nan)
    smooth_minus_dm = np.full(n, np.nan)
    
    start = di_len - 1
    atr[start] = tr.iloc[:di_len].mean()
    smooth_plus_dm[start] = plus_dm.iloc[:di_len].sum()
    smooth_minus_dm[start] = minus_dm.iloc[:di_len].sum()
    
    for i in range(di_len, n):
        atr[i] = (atr[i-1] * (di_len - 1) + tr.iloc[i]) / di_len
        smooth_plus_dm[i] = (smooth_plus_dm[i-1] * (di_len - 1) + plus_dm.iloc[i]) / di_len
        smooth_minus_dm[i] = (smooth_minus_dm[i-1] * (di_len - 1) + minus_dm.iloc[i]) / di_len
    
    # DI+ and DI-
    di_plus = 100 * smooth_plus_dm / atr
    di_minus = 100 * smooth_minus_dm / atr
    
    # DX
    di_sum = di_plus + di_minus
    dx = np.full(n, np.nan)
    for i in range(di_len, n):
        if di_sum[i] > 0:
            dx[i] = 100 * abs(di_plus[i] - di_minus[i]) / di_sum[i]
    
    # ADX - Wilder's smoothing of DX
    adx = np.full(n, np.nan)
    # 種子 = 前 adx_len 根 DX 嘅平均
    dx_start = di_len  # DX starts from di_len
    adx_seed_start = dx_start + adx_len - 1
    if adx_seed_start < n:
        adx[adx_seed_start] = np.nanmean(dx[dx_start:adx_seed_start+1])
        for i in range(adx_seed_start + 1, n):
            if not np.isnan(adx[i-1]) and not np.isnan(dx[i]):
                adx[i] = (adx[i-1] * (adx_len - 1) + dx[i]) / adx_len
            elif not np.isnan(adx[i-1]):
                adx[i] = adx[i-1]
    
    return di_plus, di_minus, pd.Series(adx, index=high.index)

di_plus, di_minus, adxVal = tv_dmi(H, L, C, 14, 14)

# ══════════════════════════════════════════════════════════════
# Williams %R - 對齊 TradingView ta.wpr(14)
# ══════════════════════════════════════════════════════════════
willR = pd.Series(np.full(n, -50.0), index=C.index)
for i in range(13, n):  # ta.wpr(14) looks back 14 bars (0 to 13)
    hh = H.iloc[i-13:i+1].max()
    ll = L.iloc[i-13:i+1].min()
    if hh - ll > 0:
        willR.iloc[i] = -100 * (hh - C.iloc[i]) / (hh - ll)

# ══════════════════════════════════════════════════════════════
# Volume - 對齊 TradingView: volume > ta.sma(volume, 20)
# ══════════════════════════════════════════════════════════════
vol_sma = V.rolling(20).mean()
volRising = (V > vol_sma)

# ══════════════════════════════════════════════════════════════
# Scoring (完全對齊 Pine Script)
# ══════════════════════════════════════════════════════════════
# Direction Score (Max 40)
dirScore = np.zeros(n)
for i in range(1, n):
    c = C.iloc[i]
    e20 = ema20.iloc[i]; e50 = ema50.iloc[i]; e200 = ema200.iloc[i]
    e20p = ema20.iloc[i-1]; e50p = ema50.iloc[i-1]
    if np.isnan(e20) or np.isnan(e50) or np.isnan(e200) or np.isnan(e20p) or np.isnan(e50p):
        continue
    if c > e20 and e20 > e50 and e50 > e200 and e20 > e20p and e50 > e50p:
        dirScore[i] = 40
    elif c > e20 and e20 > e50 and e50 > e200:
        dirScore[i] = 35
    elif c > e20 and e20 > e50:
        dirScore[i] = 28
    elif c > e200:
        dirScore[i] = 18

# MACD Score (Max 30)
macdSc = np.zeros(n)
for i in range(1, n):
    ml = macdLine.iloc[i]; sl = signalLine.iloc[i]
    h = macdHist.iloc[i]; hp = macdHist.iloc[i-1]
    if np.isnan(ml) or np.isnan(sl) or np.isnan(h) or np.isnan(hp):
        continue
    # ta.crossover(macdLine, signalLine): ml > sl AND ml_prev <= sl_prev
    if ml > 0 and h > 0 and h > hp * 1.5:
        macdSc[i] = 30
    elif ml > 0 and h > hp:
        macdSc[i] = 25
    elif ml > sl and ml > 0 and macdLine.iloc[i-1] <= signalLine.iloc[i-1]:
        macdSc[i] = 22
    elif ml > 0:
        macdSc[i] = 15

# FVG Score - 用修正後嘅 ATR
fvgSc = np.zeros(n)
for i in range(3, n):
    bullFVG = L.iloc[i-1] - H.iloc[i-3] if L.iloc[i-1] > H.iloc[i-3] else 0.0
    atr = atr14.iloc[i] if not np.isnan(atr14.iloc[i]) else 10.0
    if bullFVG > atr * 0.8:
        fvgSc[i] = 18
    elif bullFVG > atr * 0.3:
        fvgSc[i] = 13
    elif bullFVG > 0:
        fvgSc[i] = 7

# Bonus
bonus = np.zeros(n)
for i in range(n):
    b = 0
    adx = adxVal.iloc[i] if not np.isnan(adxVal.iloc[i]) else 0.0
    if adx > 30:
        b += 8
    if volRising.iloc[i] and C.iloc[i] > O.iloc[i]:
        b += 5
    if -80 < willR.iloc[i] < -20:
        b += 3
    bonus[i] = b

allScores = np.clip(dirScore + macdSc + fvgSc + bonus, 0, 100)
below_ema200 = (C < ema200).values
print(" 完成")

s5_total = (allScores <= 5).sum()
s5_below = ((allScores <= 5) & below_ema200).sum()
print(f"Score<=5: {s5_total}根, 價格<EMA200: {s5_below}根")

# ══════════════════════════════════════════════════════════════
# 一致回測函數
# ══════════════════════════════════════════════════════════════
def run_consistent_bt(sl_d, tp_d, max_hold, start_bar=500):
    sigs = []
    i = start_bar
    while i < n - max_hold:
        if allScores[i] <= 5 and below_ema200[i]:
            sigs.append(i)
            ep = C.iloc[i]
            exit_bar = max_hold
            for j in range(i+1, min(i+max_hold, n)):
                if L.iloc[j] <= ep - tp_d or H.iloc[j] >= ep + sl_d:
                    exit_bar = j - i; break
            i = i + exit_bar + 1
        else:
            i += 1
    if not sigs:
        return []
    
    trades = []
    for idx in sigs:
        ep = C.iloc[idx]
        result = None
        for j in range(idx+1, min(idx+max_hold, n)):
            if L.iloc[j] <= ep - tp_d:
                result='TP'; xp=ep-tp_d; exit_i=j; break
            if H.iloc[j] >= ep + sl_d:
                result='SL'; xp=ep+sl_d; exit_i=j; break
        if result is None:
            result='TO'; xp=C.iloc[min(idx+max_hold, n-1)]; exit_i=min(idx+max_hold, n-1)
        trades.append({
            'entry_time': gold.index[idx], 'entry_price': ep,
            'exit_time': gold.index[exit_i], 'exit_price': xp,
            'result': result, 'pnl': ep - xp,
        })
    return trades

def calc_stats(trades):
    if not trades: return None
    pnls = np.array([t['pnl'] for t in trades])
    tp_c = sum(1 for t in trades if t['result']=='TP')
    sl_c = sum(1 for t in trades if t['result']=='SL')
    to_c = sum(1 for t in trades if t['result']=='TO')
    total = len(pnls)
    wins = (pnls>0).sum()
    total_pnl = pnls.sum()
    gw = pnls[pnls>0].sum(); gl = abs(pnls[pnls<0].sum())
    pf = gw/gl if gl>0 else 0
    cum = np.cumsum(pnls)
    max_dd = (cum - np.maximum.accumulate(cum)).min()
    streak=0; ms=0
    for p in pnls:
        if p<0: streak+=1; ms=max(ms,streak)
        else: streak=0
    total_days = (trades[-1]['entry_time'] - trades[0]['entry_time']).days
    months = max(total_days / 30.44, 0.1)
    return {
        'total': total, 'tp': tp_c, 'sl': sl_c, 'to': to_c,
        'wins': int(wins), 'wr': wins/total,
        'pf': pf, 'pnl': total_pnl, 'max_dd': max_dd, 'ms': ms,
        'months': months, 'monthly': total_pnl/months, 'days': total_days,
    }

# ══════════════════════════════════════════════════════════════
# 測試
# ══════════════════════════════════════════════════════════════
HOLD_CONFIGS = [
    ("4h", 48),
    ("12h", 144),
    ("24h", 288),
]

SL_GRID = [5, 8, 10, 12, 15, 18, 20, 25, 30, 40, 50]
TP_GRID = [8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200]

for hold_name, max_hold in HOLD_CONFIGS:
    print(f"\n{'='*82}")
    print(f"  5min 持倉 {hold_name} ({max_hold}根) [修正版 - 對齊 Pine Script]")
    print(f"{'='*82}")
    
    results = []
    for sl_d in SL_GRID:
        for tp_d in TP_GRID:
            if tp_d <= sl_d: continue
            trades = run_consistent_bt(sl_d, tp_d, max_hold)
            if not trades: continue
            stats = calc_stats(trades)
            if stats is None: continue
            stats['sl'] = sl_d; stats['tp'] = tp_d
            results.append(stats)
    
    profitable = [r for r in results if r['pnl'] > 0]
    if not profitable:
        print("  無盈利組合"); continue
    
    profitable.sort(key=lambda x: x['monthly'], reverse=True)
    print(f"  盈利組合: {len(profitable)} / {len(results)}")
    print(f"\n  {'SL':>4} {'TP':>4} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>8}")
    print(f"  {'-'*78}")
    for r in profitable[:12]:
        print(f"  ${r['sl']:>3} ${r['tp']:>3} {r['total']:>4} {r['tp']:>3} {r['sl']:>3} {r['to']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['monthly']:>+7.2f}")

# ══════════════════════════════════════════════════════════════
# Top 2 逐筆驗證
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*82}")
print(f"  Top 2 組合逐筆驗證 [修正版]")
print(f"{'='*82}")

all_results = []
for hold_name, max_hold in HOLD_CONFIGS:
    for sl_d in SL_GRID:
        for tp_d in TP_GRID:
            if tp_d <= sl_d: continue
            trades = run_consistent_bt(sl_d, tp_d, max_hold)
            if not trades: continue
            stats = calc_stats(trades)
            if stats and stats['pnl'] > 0 and stats['pf'] > 1.2:
                stats['sl'] = sl_d; stats['tp'] = tp_d
                stats['hold'] = hold_name; stats['hold_bars'] = max_hold
                all_results.append(stats)

all_results.sort(key=lambda x: x['monthly'], reverse=True)

for rank, best in enumerate(all_results[:2], 1):
    sl_d, tp_d = best['sl'], best['tp']
    trades = run_consistent_bt(sl_d, tp_d, best['hold_bars'])
    stats = calc_stats(trades)
    manual_pnl = sum(t['pnl'] for t in trades)
    manual_tp = sum(1 for t in trades if t['result']=='TP')
    manual_sl = sum(1 for t in trades if t['result']=='SL')
    manual_to = sum(1 for t in trades if t['result']=='TO')
    
    print(f"\n  ── 第{rank}名: SL=${sl_d} TP=${tp_d} 持倉{best['hold']} ──")
    print(f"  交易: {len(trades)}筆 | {stats['days']}天 | {stats['months']:.1f}月")
    print(f"  TP:{manual_tp} SL:{manual_sl} TO:{manual_to} | 總盈虧:${manual_pnl:+.2f} | 月均:${stats['monthly']:+.2f}")
    print(f"  驗證: PnL一致={abs(manual_pnl - stats['pnl'])<0.01}")
    
    print(f"\n  {'#':>3} {'入場時間':>19} {'入場價':>9} {'出場價':>9} {'結果':>3} {'盈虧$':>8} {'累計$':>9}")
    print(f"  {'-'*68}")
    cum = 0
    for idx, t in enumerate(trades, 1):
        cum += t['pnl']
        print(f"  {idx:>3} {str(t['entry_time'])[:19]:>19} {t['entry_price']:>9.2f} {t['exit_price']:>9.2f} {t['result']:>3} {t['pnl']:>+8.2f} {cum:>+9.2f}")
    print(f"  {'─'*68}")
    print(f"  總計: ${manual_pnl:+.2f} | 月均: ${stats['monthly']:+.2f}")

print(f"\n總耗時: {time.time()-t0:.1f}s")