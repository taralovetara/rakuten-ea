#!/usr/bin/env python3
"""
5min 回測 - 用 yfinance 60日數據 (最大值)
Score<=5 + 價格<EMA200 + 立即再入場
0.01 lot = 1oz, Short PnL = entry - exit
"""
import pandas as pd, numpy as np
import warnings, time
warnings.filterwarnings('ignore')
t0 = time.time()

import yfinance as yf

# ══════════════════════════════════════════════════════════════
# 下載 60d 5min 數據
# ══════════════════════════════════════════════════════════════
print("下載 GC=F 5min 60d 數據...")
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
atr14=C.rolling(14).apply(lambda x:max(x.max()-x.min(),abs(x.iloc[-1]-x.iloc[-2]) if len(x)>1 else 0),raw=False)

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

adxVal=np.full(n,20.0)
for i in range(28,n):
    pdms,mdms,trs=[],[],[]
    for j in range(i-13,i+1):
        pdm=max(0,H.iloc[j]-H.iloc[j-1]); mdm=max(0,L.iloc[j-1]-L.iloc[j])
        if pdm<mdm: pdm=0
        else: mdm=0
        pdms.append(pdm); mdms.append(mdm)
        trs.append(max(H.iloc[j]-L.iloc[j],abs(H.iloc[j]-C.iloc[j-1]),abs(L.iloc[j]-C.iloc[j-1])))
    sp,sm,st=sum(pdms),sum(mdms),sum(trs)
    if st>0:
        dp,dm=100*sp/st,100*sm/st; ds=dp+dm
        if ds>0:
            dx=100*abs(dp-dm)/ds
            adxVal[i]=(adxVal[i-1]*13+dx)/14 if i>=42 else dx

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

# 統計 Score 分佈
s5_count = (allScores <= 5).sum()
s5_below = ((allScores <= 5) & below_ema200).sum()
print(f"Score<=5: {s5_count}根, 其中價格<EMA200: {s5_below}根")

# ══════════════════════════════════════════════════════════════
# 不同持倉時間測試
# ══════════════════════════════════════════════════════════════
HOLD_CONFIGS = [
    ("4h (48根)", 48),
    ("6h (72根)", 72),
    ("12h (144根)", 144),
    ("24h (288根)", 288),
]

SL_GRID = [3, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40, 50]
TP_GRID = [5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120, 150, 200]

start_bar = 500  # EMA200 穩定

for hold_name, max_hold in HOLD_CONFIGS:
    print(f"\n{'='*85}")
    print(f"  5min 持倉 {hold_name}")
    print(f"{'='*85}")
    
    # 收集信號 (立即再入場, 用參考 SL=$15 TP=$60 判斷出場)
    sigs = []
    i = start_bar
    while i < len(gold) - max_hold:
        if allScores[i] <= 5 and below_ema200[i]:
            sigs.append(i)
            ep = C.iloc[i]
            exit_bar = max_hold
            for j in range(i+1, min(i+max_hold, len(gold))):
                if L.iloc[j] <= ep - 60 or H.iloc[j] >= ep + 15:
                    exit_bar = j - i; break
            i = i + exit_bar + 1
        else:
            i += 1
    
    if len(sigs) == 0:
        print("  無信號"); continue
    
    total_days = (gold.index[sigs[-1]] - gold.index[sigs[0]]).days
    months = max(total_days / 30.44, 0.1)
    
    print(f"  信號: {len(sigs)}筆 | {gold.index[sigs[0]].strftime('%Y-%m-%d')} ~ {gold.index[sigs[-1]].strftime('%Y-%m-%d')} ({total_days}天 / {months:.1f}月)")
    print(f"  預計交易頻率: {len(sigs)/months:.1f}筆/月")
    
    results = []
    for sl_d in SL_GRID:
        for tp_d in TP_GRID:
            if tp_d <= sl_d: continue
            pnls = []; res = []
            for idx in sigs:
                ep = C.iloc[idx]
                result = None
                for j in range(idx+1, min(idx+max_hold, len(gold))):
                    if L.iloc[j] <= ep - tp_d:
                        result='TP'; break
                    if H.iloc[j] >= ep + sl_d:
                        result='SL'; break
                if result is None:
                    result='TO'; xp = C.iloc[min(idx+max_hold, len(gold)-1)]
                elif result=='TP': xp = ep - tp_d
                else: xp = ep + sl_d
                pnls.append(ep - xp)
                res.append(result)
            
            pnls = np.array(pnls)
            tp_c=res.count('TP'); sl_c=res.count('SL'); to_c=res.count('TO')
            total=len(pnls); wins=(pnls>0).sum()
            total_pnl=pnls.sum()
            gw=pnls[pnls>0].sum(); gl=abs(pnls[pnls<0].sum())
            pf=gw/gl if gl>0 else 0
            cum=np.cumsum(pnls)
            max_dd=(cum-np.maximum.accumulate(cum)).min()
            streak=0; ms=0
            for p in pnls:
                if p<0: streak+=1; ms=max(ms,streak)
                else: streak=0
            dd_r=abs(max_dd)/total_pnl if total_pnl>0 else 999
            
            results.append({
                'sl':sl_d,'tp':tp_d,'tp_c':tp_c,'sl_c':sl_c,'to_c':to_c,
                'total':total,'wins':wins,'wr':wins/total if total>0 else 0,
                'pf':pf,'pnl':total_pnl,'max_dd':max_dd,'ms':ms,'dd_r':dd_r,
                'months':months,'monthly':total_pnl/months,
            })
    
    profitable = [r for r in results if r['pnl'] > 0]
    
    # 綜合評分
    max_pnl = max(r['pnl'] for r in profitable) if profitable else 1
    for r in results:
        if r['pnl']<=0 or r['pf']<1.2: r['score']=-1; continue
        r['score']=(min(r['pf']/2,1)*0.25 + min(r['pnl']/max_pnl,1)*0.3 
                    + max(0,1-r['dd_r']/3)*0.2 + max(0,1-r['ms']/max(r['total']*0.5,1))*0.15
                    + min(r['wr']/0.6,1)*0.1)
    
    by_score = sorted([r for r in results if r['score']>0], key=lambda x: x['score'], reverse=True)
    
    if not by_score:
        print("  無盈利組合 (PF>1.2)"); continue
    
    print(f"  盈利組合: {len(profitable)} | 合格(PF>1.2): {len(by_score)}")
    print(f"\n  {'SL':>4} {'TP':>4} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>7} {'評分':>5}")
    print(f"  {'-'*78}")
    for r in by_score[:20]:
        print(f"  ${r['sl']:>3} ${r['tp']:>3} {r['total']:>4} {r['tp_c']:>3} {r['sl_c']:>3} {r['to_c']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['monthly']:>+6.2f} {r['score']:>.3f}")

# ══════════════════════════════════════════════════════════════
# 最佳組合月份詳解
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*85}")
print(f"  最佳組合月份詳解")
print(f"{'='*85}")

# 用 24h 持倉做詳解 (最常見設置)
best_hold = 288
sigs_best = []
i = start_bar
while i < len(gold) - best_hold:
    if allScores[i] <= 5 and below_ema200[i]:
        sigs_best.append(i)
        ep = C.iloc[i]; exit_bar = best_hold
        for j in range(i+1, min(i+best_hold, len(gold))):
            if L.iloc[j] <= ep - 60 or H.iloc[j] >= ep + 15:
                exit_bar = j - i; break
        i = i + exit_bar + 1
    else:
        i += 1

# 跑所有 SL/TP, 找最佳
best_result = None
best_combo = None
for sl_d in SL_GRID:
    for tp_d in TP_GRID:
        if tp_d <= sl_d: continue
        pnls = []; res = []
        for idx in sigs_best:
            ep = C.iloc[idx]; result = None
            for j in range(idx+1, min(idx+best_hold, len(gold))):
                if L.iloc[j] <= ep - tp_d: result='TP'; break
                if H.iloc[j] >= ep + sl_d: result='SL'; break
            if result is None:
                result='TO'; xp = C.iloc[min(idx+best_hold, len(gold)-1)]
            elif result=='TP': xp = ep - tp_d
            else: xp = ep + sl_d
            pnls.append(ep - xp); res.append(result)
        
        pnls = np.array(pnls)
        total_pnl = pnls.sum()
        gw=pnls[pnls>0].sum(); gl=abs(pnls[pnls<0].sum())
        pf=gw/gl if gl>0 else 0
        cum=np.cumsum(pnls); max_dd=(cum-np.maximum.accumulate(cum)).min()
        
        if total_pnl > 0 and pf > 1.5:
            score = pf * 0.4 + (total_pnl / 100) * 0.3 + (1 - abs(max_dd)/total_pnl) * 0.3
            if best_result is None or score > best_result:
                best_result = score
                best_combo = (sl_d, tp_d, pnls, res, sigs_best)

if best_combo:
    sl_d, tp_d, pnls, res, sigs_b = best_combo
    total_days = (gold.index[sigs_b[-1]] - gold.index[sigs_b[0]]).days
    months = max(total_days / 30.44, 0.1)
    
    trades = []
    for idx, p, r in zip(sigs_b, pnls, res):
        trades.append({'time': gold.index[idx], 'pnl': p, 'result': r})
    df_t = pd.DataFrame(trades)
    df_t['month'] = pd.to_datetime(df_t['time']).dt.to_period('M')
    
    print(f"\n  最佳: SL=${sl_d} TP=${tp_d} | 24h持倉 | {len(df_t)}筆交易")
    print(f"  總盈虧: ${pnls.sum():+.2f} | 月均: ${pnls.sum()/months:+.2f}")
    print(f"  勝率: {(pnls>0).mean():.1%} | PF: {pnls[pnls>0].sum()/abs(pnls[pnls<0].sum()):.2f}")
    
    print(f"\n  {'月份':<12} {'交易':>4} {'勝率':>6} {'盈虧$':>8} {'累計$':>8}")
    print(f"  {'-'*42}")
    cum_m = 0
    for m, g in df_t.groupby('month'):
        wr = (g['pnl']>0).mean(); s = g['pnl'].sum(); cum_m += s
        print(f"  {str(m):<12} {len(g):>4} {wr:>5.1%} {s:>+7.2f} {cum_m:>+7.2f}")
    print(f"  {'-'*42}")
    print(f"  {'總計':<12} {len(df_t):>4} {(pnls>0).mean():>5.1%} {pnls.sum():>+7.2f}")
    
    # 周詳解
    print(f"\n  {'週':<14} {'交易':>4} {'勝率':>6} {'盈虧$':>8} {'累計$':>8}")
    print(f"  {'-'*46}")
    df_t['week'] = pd.to_datetime(df_t['time']).dt.isocalendar().week.astype(int)
    df_t['year'] = pd.to_datetime(df_t['time']).dt.year
    cum_w = 0
    for (y, w), g in df_t.groupby(['year', 'week']):
        wr = (g['pnl']>0).mean(); s = g['pnl'].sum(); cum_w += s
        label = f"{y}-W{w:02d}"
        print(f"  {label:<14} {len(g):>4} {wr:>5.1%} {s:>+7.2f} {cum_w:>+7.2f}")

print(f"\n總耗時: {time.time()-t0:.1f}s")