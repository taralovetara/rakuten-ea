#!/usr/bin/env python3
"""
用真實15min數據 (70天) 做完整SL/TP搜索
加上用真實5min (35天) 驗證
"""
import pandas as pd, numpy as np
import warnings, time
warnings.filterwarnings('ignore')
t0 = time.time()

import yfinance as yf

# 下載真實數據
print("下載數據...")
df_15m = yf.download("GC=F", period="60d", interval="15m", progress=False)
df_5m = yf.download("GC=F", period="30d", interval="5m", progress=False)
if isinstance(df_15m.columns, pd.MultiIndex):
    df_15m.columns = df_15m.columns.get_level_values(0)
if isinstance(df_5m.columns, pd.MultiIndex):
    df_5m.columns = df_5m.columns.get_level_values(0)
df_15m = df_15m.dropna().sort_index()
df_5m = df_5m.dropna().sort_index()

print(f"15min: {len(df_15m)}根, {df_15m.index[0]} ~ {df_15m.index[-1]}")
print(f"5min:  {len(df_5m)}根, {df_5m.index[0]} ~ {df_5m.index[-1]}")

def calc_score(gold):
    C=gold['Close']; H=gold['High']; L=gold['Low']; O=gold['Open']; V=gold['Volume']
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
    scores=np.clip(dirScore+macdSc+fvgSc+bonus,0,100)
    below_ema=(C<ema200).values
    return scores, below_ema

def run_full_bt(gold, scores, below_ema, max_hold, sl_grid, tp_grid, label=""):
    C=gold['Close']; H=gold['High']; L=gold['Low']
    start_bar = 500  # EMA200 穩定
    
    # 先收集信號 (立即再入場, 用預設SL/TP $15/$60做參考)
    sigs = []
    i = start_bar
    while i < len(gold) - max_hold:
        if scores[i] <= 5 and below_ema[i]:
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
        return []
    
    total_days = (gold.index[sigs[-1]] - gold.index[sigs[0]]).days
    months = max(total_days / 30.44, 0.1)
    
    results = []
    for sl_d in sl_grid:
        for tp_d in tp_grid:
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
                'months':months,'monthly':total_pnl/months,'sigs':len(sigs),
                'label':label,
            })
    return results

# ══════════════════════════════════════════════════════════════
# 15min: 搜索
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("15min 數據 SL/TP 搜索")
print(f"{'='*80}")

SL_GRID_15 = [3,5,8,10,12,15,18,20,25,30,40,50]
TP_GRID_15 = [5,8,10,12,15,20,25,30,40,50,60,80,100,120,150,200]
HOLD_15 = 96  # 96根15min = 24h

print(f"\n計算15min Score...", end="", flush=True)
scores_15, below_15 = calc_score(df_15m)
print(f" 完成")

print(f"搜索中 (SL={len(SL_GRID_15)} x TP={len(TP_GRID_15)})...")
r_15 = run_full_bt(df_15m, scores_15, below_15, HOLD_15, SL_GRID_15, TP_GRID_15, "15min 24h")
prof_15 = [r for r in r_15 if r['pnl'] > 0]
prof_15.sort(key=lambda x: x['pf'], reverse=True)

print(f"信號: {r_15[0]['sigs'] if r_15 else 0}筆 | 盈利組合: {len(prof_15)}")
print(f"\n  {'SL':>4} {'TP':>4} {'SL點':>5} {'TP點':>5} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>7}")
print(f"  {'-'*78}")
for r in prof_15[:20]:
    print(f"  ${r['sl']:>3} ${r['tp']:>3} {r['sl']*100:>4}k {r['tp']*100:>4}k {r['total']:>4} {r['tp_c']:>3} {r['sl_c']:>3} {r['to_c']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['monthly']:>+6.2f}")

# 亦試12h持倉
print(f"\n{'─'*80}")
HOLD_15_12h = 48  # 48根15min = 12h
print(f"15min 12h持倉...")
r_15_12h = run_full_bt(df_15m, scores_15, below_15, HOLD_15_12h, SL_GRID_15, TP_GRID_15, "15min 12h")
prof_15_12h = [r for r in r_15_12h if r['pnl'] > 0]
prof_15_12h.sort(key=lambda x: x['pf'], reverse=True)

print(f"信號: {r_15_12h[0]['sigs'] if r_15_12h else 0}筆 | 盈利組合: {len(prof_15_12h)}")
print(f"\n  {'SL':>4} {'TP':>4} {'SL點':>5} {'TP點':>5} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>7}")
print(f"  {'-'*78}")
for r in prof_15_12h[:15]:
    print(f"  ${r['sl']:>3} ${r['tp']:>3} {r['sl']*100:>4}k {r['tp']*100:>4}k {r['total']:>4} {r['tp_c']:>3} {r['sl_c']:>3} {r['to_c']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['monthly']:>+6.2f}")

# ══════════════════════════════════════════════════════════════
# 5min: 搜索
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("5min 數據 SL/TP 搜索")
print(f"{'='*80}")

SL_GRID_5 = [3,5,8,10,12,15,18,20,25,30]
TP_GRID_5 = [5,8,10,12,15,20,25,30,40,50,60,80,100]
HOLD_5 = 288  # 288根5min = 24h

print(f"\n計算5min Score...", end="", flush=True)
scores_5, below_5 = calc_score(df_5m)
print(f" 完成")

print(f"搜索中...")
r_5 = run_full_bt(df_5m, scores_5, below_5, HOLD_5, SL_GRID_5, TP_GRID_5, "5min 24h")
prof_5 = [r for r in r_5 if r['pnl'] > 0]
prof_5.sort(key=lambda x: x['pf'], reverse=True)

print(f"信號: {r_5[0]['sigs'] if r_5 else 0}筆 | 盈利組合: {len(prof_5)}")
print(f"\n  {'SL':>4} {'TP':>4} {'SL點':>5} {'TP點':>5} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>7}")
print(f"  {'-'*78}")
for r in prof_5[:20]:
    print(f"  ${r['sl']:>3} ${r['tp']:>3} {r['sl']*100:>4}k {r['tp']*100:>4}k {r['total']:>4} {r['tp_c']:>3} {r['sl_c']:>3} {r['to_c']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['monthly']:>+6.2f}")

# ══════════════════════════════════════════════════════════════
# 最佳組合月份詳解
# ══════════════════════════════════════════════════════════════
if prof_5:
    best = prof_5[0]
    print(f"\n{'='*80}")
    print(f"5min 最佳: SL=${best['sl']} TP=${best['tp']} 月份詳解")
    print(f"{'='*80}")
    
    # 重新跑, 記錄時間
    C5=df_5m['Close']; H5=df_5m['High']; L5=df_5m['Low']
    sigs_5 = []
    i = 500
    while i < len(df_5m) - HOLD_5:
        if scores_5[i] <= 5 and below_5[i]:
            sigs_5.append(i)
            ep = C5.iloc[i]; exit_bar = HOLD_5
            for j in range(i+1, min(i+HOLD_5, len(df_5m))):
                if L5.iloc[j] <= ep - best['tp'] or H5.iloc[j] >= ep + best['sl']:
                    exit_bar = j - i; break
            i = i + exit_bar + 1
        else:
            i += 1
    
    trades = []
    for idx in sigs_5:
        ep = C5.iloc[idx]; result = None
        for j in range(idx+1, min(idx+HOLD_5, len(df_5m))):
            if L5.iloc[j] <= ep - best['tp']: result='TP'; break
            if H5.iloc[j] >= ep + best['sl']: result='SL'; break
        if result is None:
            result='TO'; xp = C5.iloc[min(idx+HOLD_5, len(df_5m)-1)]
        elif result=='TP': xp = ep - best['tp']
        else: xp = ep + best['sl']
        trades.append({'time': df_5m.index[idx], 'pnl': ep-xp, 'result': result})
    
    df_t = pd.DataFrame(trades)
    df_t['month'] = pd.to_datetime(df_t['time']).dt.to_period('M')
    
    print(f"\n  {'月份':<12} {'交易':>4} {'勝率':>6} {'盈虧$':>8} {'累計$':>8}")
    print(f"  {'-'*42}")
    cum_m = 0
    for m, g in df_t.groupby('month'):
        wr = (g['pnl']>0).mean(); s = g['pnl'].sum(); cum_m += s
        print(f"  {str(m):<12} {len(g):>4} {wr:>5.1%} {s:>+7.2f} {cum_m:>+7.2f}")
    print(f"  {'-'*42}")
    print(f"  {'總計':<12} {len(df_t):>4} {best['wr']:>5.1%} {best['pnl']:>+7.2f}")

print(f"\n總耗時: {time.time()-t0:.1f}s")