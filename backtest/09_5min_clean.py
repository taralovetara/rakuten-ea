#!/usr/bin/env python3
"""
5min 回測 (乾淨版) - 每個 SL/TP 組合用同一組參數做信號收集+盈虧計算
Score<=5 + 價格<EMA200 + 立即再入場 + 0.01 lot (1oz)
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

# ══════════════════════════════════════════════════════════════
# 計算 Larry Williams Score
# ══════════════════════════════════════════════════════════════
print("計算指標...", end="", flush=True)
ema20=C.ewm(span=20,adjust=False).mean(); ema50=C.ewm(span=50,adjust=False).mean()
ema200=C.ewm(span=200,adjust=False).mean()
ema12=C.ewm(span=12,adjust=False).mean(); ema26=C.ewm(span=26,adjust=False).mean()
macdLine=ema12-ema26; signalLine=macdLine.ewm(span=9,adjust=False).mean(); macdHist=macdLine-signalLine
# ATR: Wilder's RMA (alpha=1/14) — 匹配 Pine ta.atr(14)
tr_series = pd.concat([H-L, (H-C.shift(1)).abs(), (L-C.shift(1)).abs()], axis=1).max(axis=1)
tr_series.iloc[0] = H.iloc[0] - L.iloc[0]
atr14 = tr_series.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

n=len(gold)
dirScore=np.zeros(n)
for i in range(1,n):
    c,e20,e50,e200=C.iloc[i],ema20.iloc[i],ema50.iloc[i],ema200.iloc[i]
    e20p,e50p=ema20.iloc[i-1],ema50.iloc[i-1]
    if c>e20 and e20>e50 and e50>e200 and e20>e20p and e50>e50p: dirScore[i]=40
    elif c>e20 and e20>e50 and e50>e200: dirScore[i]=35
    elif c>e20 and e20>e50: dirScore[i]=28
    elif c>e200: dirScore[i]=18

macdSc=np.zeros(n)
for i in range(1,n):
    ml,sl,h,hp=macdLine.iloc[i],signalLine.iloc[i],macdHist.iloc[i],macdHist.iloc[i-1]
    if ml>0 and h>0 and h>hp*1.5: macdSc[i]=30
    elif ml>0 and h>hp: macdSc[i]=25
    elif ml>sl and ml>0 and macdLine.iloc[i-1]<=signalLine.iloc[i-1]: macdSc[i]=22
    elif ml>0: macdSc[i]=15

fvgSc=np.zeros(n)
for i in range(3,n):
    bf=max(0,L.iloc[i-1]-H.iloc[i-3]); atr=atr14.iloc[i] if atr14.iloc[i]>0 else 10
    if bf>atr*0.8: fvgSc[i]=18
    elif bf>atr*0.3: fvgSc[i]=13
    elif bf>0: fvgSc[i]=7

willR=np.full(n,-50.0)
for i in range(14,n):
    hh=H.iloc[i-13:i+1].max(); ll=L.iloc[i-13:i+1].min()
    if hh-ll>0: willR[i]=-100*(hh-C.iloc[i])/(hh-ll)

# ADX: 精確匹配 Pine ta.dmi(14,14)
# +DM / -DM / TR 然後各自做 Wilder's RMA, 再算 DX -> ADX RMA
plus_dm = pd.Series(0.0, index=gold.index)
minus_dm = pd.Series(0.0, index=gold.index)
for i in range(1, n):
    up = H.iloc[i] - H.iloc[i-1]
    dn = L.iloc[i-1] - L.iloc[i]
    if up > dn and up > 0:
        plus_dm.iloc[i] = up
    if dn > up and dn > 0:
        minus_dm.iloc[i] = dn

# Wilder's RMA for +DM, -DM, TR (alpha=1/14, min_periods=14)
plus_di14 = (plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
             / tr_series.ewm(alpha=1/14, adjust=False, min_periods=14).mean() * 100)
minus_di14 = (minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
              / tr_series.ewm(alpha=1/14, adjust=False, min_periods=14).mean() * 100)
plus_di14 = plus_di14.fillna(0)
minus_di14 = minus_di14.fillna(0)

di_sum = plus_di14 + minus_di14
dx_series = pd.Series(0.0, index=gold.index)
mask = di_sum > 0
dx_series[mask] = 100 * (plus_di14[mask] - minus_di14[mask]).abs() / di_sum[mask]
adxVal = dx_series.ewm(alpha=1/14, adjust=False, min_periods=14).mean().fillna(20.0).values

volRatio=V/(V.rolling(20).mean()+1)
bonus=np.zeros(n)
for i in range(n):
    b=0
    if adxVal[i]>30: b+=8
    if volRatio.iloc[i]>1 and C.iloc[i]>O.iloc[i]: b+=5
    if -80<willR[i]<-20: b+=3
    bonus[i]=b

allScores=np.clip(dirScore+macdSc+fvgSc+bonus,0,100)
below_ema200=(C<ema200).values
print(" 完成")

# ══════════════════════════════════════════════════════════════
# 核心函數: 用指定 SL/TP 收集信號 + 計盈虧 (一致)
# ══════════════════════════════════════════════════════════════
def run_consistent_bt(sl_d, tp_d, max_hold, start_bar=500):
    """
    用同一組 sl_d/tp_d 做:
    1. 信號收集 (出場後下一根可再入)
    2. 盈虧計算
    返回 trades list
    """
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
        
        pnl = ep - xp  # 0.01 lot = 1oz, short
        trades.append({
            'idx': idx,
            'entry_time': gold.index[idx],
            'entry_price': ep,
            'exit_time': gold.index[exit_i],
            'exit_price': xp,
            'result': result,
            'pnl': pnl,
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
    gw = pnls[pnls>0].sum()
    gl = abs(pnls[pnls<0].sum())
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
        'months': months, 'monthly': total_pnl/months,
        'days': total_days,
    }

# ══════════════════════════════════════════════════════════════
# 持倉時間測試
# ══════════════════════════════════════════════════════════════
HOLD_CONFIGS = [
    ("4h", 48),
    ("6h", 72),
    ("12h", 144),
    ("24h", 288),
]

SL_GRID = [5, 8, 10, 12, 15, 18, 20, 25, 30, 40, 50]
TP_GRID = [8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120, 150, 200]

for hold_name, max_hold in HOLD_CONFIGS:
    print(f"\n{'='*82}")
    print(f"  5min 持倉 {hold_name} ({max_hold}根)")
    print(f"{'='*82}")
    
    results = []
    for sl_d in SL_GRID:
        for tp_d in TP_GRID:
            if tp_d <= sl_d: continue
            trades = run_consistent_bt(sl_d, tp_d, max_hold)
            if not trades: continue
            stats = calc_stats(trades)
            if stats is None: continue
            stats['sl'] = sl_d
            stats['tp'] = tp_d
            results.append(stats)
    
    profitable = [r for r in results if r['pnl'] > 0]
    
    if not profitable:
        print("  無盈利組合"); continue
    
    # 按月均排序
    profitable.sort(key=lambda x: x['monthly'], reverse=True)
    
    print(f"  盈利組合: {len(profitable)} / {len(results)}")
    print(f"\n  {'SL':>4} {'TP':>4} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>8}")
    print(f"  {'-'*78}")
    
    for r in profitable[:15]:
        print(f"  ${r['sl']:>3} ${r['tp']:>3} {r['total']:>4} {r['tp']:>3} {r['sl']:>3} {r['to']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['monthly']:>+7.2f}")

# ══════════════════════════════════════════════════════════════
# Top 3 逐筆驗證
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*82}")
print(f"  Top 3 組合逐筆驗證 (確保數字一致)")
print(f"{'='*82}")

# 收集所有結果, 找整體最佳
all_results = []
for hold_name, max_hold in HOLD_CONFIGS:
    for sl_d in SL_GRID:
        for tp_d in TP_GRID:
            if tp_d <= sl_d: continue
            trades = run_consistent_bt(sl_d, tp_d, max_hold)
            if not trades: continue
            stats = calc_stats(trades)
            if stats and stats['pnl'] > 0 and stats['pf'] > 1.2:
                stats['sl'] = sl_d
                stats['tp'] = tp_d
                stats['hold'] = hold_name
                stats['hold_bars'] = max_hold
                all_results.append(stats)

all_results.sort(key=lambda x: x['monthly'], reverse=True)

for rank, best in enumerate(all_results[:3], 1):
    sl_d, tp_d = best['sl'], best['tp']
    max_hold = best['hold_bars']
    
    trades = run_consistent_bt(sl_d, tp_d, max_hold)
    stats = calc_stats(trades)
    
    # 交叉驗證
    manual_pnl = sum(t['pnl'] for t in trades)
    manual_tp = sum(1 for t in trades if t['result']=='TP')
    manual_sl = sum(1 for t in trades if t['result']=='SL')
    manual_to = sum(1 for t in trades if t['result']=='TO')
    
    print(f"\n  ── 第{rank}名: SL=${sl_d} TP=${tp_d} 持倉{best['hold']} ──")
    print(f"  交易: {len(trades)}筆 | 天數: {stats['days']}天 | {stats['months']:.1f}月")
    print(f"  TP:{manual_tp} SL:{manual_sl} TO:{manual_to} | 總盈虧:${manual_pnl:+.2f}")
    print(f"  驗證: PnL一致={abs(manual_pnl - stats['pnl'])<0.01}")
    
    print(f"\n  {'#':>3} {'入場時間':>19} {'入場價':>9} {'出場價':>9} {'結果':>3} {'盈虧$':>8} {'累計$':>9}")
    print(f"  {'-'*68}")
    cum = 0
    for t in trades:
        cum += t['pnl']
        print(f"  {trades.index(t)+1:>3} {str(t['entry_time'])[:19]:>19} {t['entry_price']:>9.2f} {t['exit_price']:>9.2f} {t['result']:>3} {t['pnl']:>+8.2f} {cum:>+9.2f}")
    
    print(f"  {'─'*68}")
    print(f"  總計: ${manual_pnl:+.2f} | 月均: ${stats['monthly']:+.2f}")

print(f"\n總耗時: {time.time()-t0:.1f}s")