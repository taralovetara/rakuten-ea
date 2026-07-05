#!/usr/bin/env python3
"""
Score<=5 + EMA200 + 冷却期48根: 修正PnL (0.01 lot = 1oz, PnL = 價格變動 × 1)
"""
import pandas as pd, numpy as np
import warnings, time
warnings.filterwarnings('ignore')

t0 = time.time()

gold = pd.read_csv('/tmp/my-project/xauusd_1h_730d.csv', index_col=0, parse_dates=True)
gold.index = pd.to_datetime(gold.index, utc=True)
gold = gold.dropna().sort_index()
C=gold['Close']; H=gold['High']; L=gold['Low']; O=gold['Open']; V=gold['Volume']

ema20=C.ewm(span=20,adjust=False).mean(); ema50=C.ewm(span=50,adjust=False).mean()
ema200=C.ewm(span=200,adjust=False).mean()
ema12=C.ewm(span=12,adjust=False).mean(); ema26=C.ewm(span=26,adjust=False).mean()
macdLine=ema12-ema26; signalLine=macdLine.ewm(span=9,adjust=False).mean(); macdHist=macdLine-signalLine
atr14=C.rolling(14).apply(lambda x:max(x.max()-x.min(),abs(x.iloc[-1]-x.iloc[-2]) if len(x)>1 else 0),raw=False)

dirScore=np.zeros(len(gold))
for i in range(1,len(gold)):
    c,e20,e50,e200=C.iloc[i],ema20.iloc[i],ema50.iloc[i],ema200.iloc[i]
    e20p,e50p=ema20.iloc[i-1],ema50.iloc[i-1]
    if c>e20 and e20>e50 and e50>e200 and e20>e20p and e50>e50p: dirScore[i]=40
    elif c>e20 and e20>e50 and e50>e200: dirScore[i]=35
    elif c>e20 and e20>e50: dirScore[i]=28
    elif c>e200: dirScore[i]=18

macdSc=np.zeros(len(gold))
for i in range(1,len(gold)):
    ml,sl,h,hp=macdLine.iloc[i],signalLine.iloc[i],macdHist.iloc[i],macdHist.iloc[i-1]
    if ml>0 and h>0 and h>hp*1.5: macdSc[i]=30
    elif ml>0 and h>hp: macdSc[i]=25
    elif ml>sl and ml>0 and macdLine.iloc[i-1]<=signalLine.iloc[i-1]: macdSc[i]=22
    elif ml>0: macdSc[i]=15

fvgSc=np.zeros(len(gold))
for i in range(3,len(gold)):
    bf=max(0,L.iloc[i-1]-H.iloc[i-3]); atr=atr14.iloc[i] if atr14.iloc[i]>0 else 10
    if bf>atr*0.8: fvgSc[i]=18
    elif bf>atr*0.3: fvgSc[i]=13
    elif bf>0: fvgSc[i]=7

willR=np.full(len(gold),-50.0)
for i in range(14,len(gold)):
    hh=H.iloc[i-13:i+1].max();ll=L.iloc[i-13:i+1].min()
    if hh-ll>0: willR[i]=-100*(hh-C.iloc[i])/(hh-ll)

adxVal=np.full(len(gold),20.0)
for i in range(28,len(gold)):
    pdms,mdms,trs=[],[],[]
    for j in range(i-13,i+1):
        pdm=max(0,H.iloc[j]-H.iloc[j-1]);mdm=max(0,L.iloc[j-1]-L.iloc[j])
        if pdm<mdm:pdm=0
        else:mdm=0
        pdms.append(pdm);mdms.append(mdm)
        trs.append(max(H.iloc[j]-L.iloc[j],abs(H.iloc[j]-C.iloc[j-1]),abs(L.iloc[j]-C.iloc[j-1])))
    sp,sm,st=sum(pdms),sum(mdms),sum(trs)
    if st>0:
        dp,dm=100*sp/st,100*sm/st;ds=dp+dm
        if ds>0:
            dx=100*abs(dp-dm)/ds
            adxVal[i]=(adxVal[i-1]*13+dx)/14 if i>=42 else dx

volRatio=V/(V.rolling(20).mean()+1)
bonus=np.zeros(len(gold))
for i in range(len(gold)):
    b=0
    if adxVal[i]>30:b+=8
    if volRatio.iloc[i]>1 and C.iloc[i]>O.iloc[i]:b+=5
    if -80<willR[i]<-20:b+=3
    bonus[i]=b

allScores=np.clip(dirScore+macdSc+fvgSc+bonus,0,100)
below_ema200=(C<ema200).values
MAX_HOLD=48

# 收集信號
signal_indices = []
i = 200
while i < len(gold) - MAX_HOLD:
    if allScores[i] <= 5 and below_ema200[i]:
        signal_indices.append(i)
        i += MAX_HOLD
    else:
        i += 1

print(f"信號: {len(signal_indices)}筆 | 範圍: {gold.index[signal_indices[0]]} ~ {gold.index[signal_indices[-1]]}")
print(f"0.01 lot = 1oz, PnL = 價格變動($)")
print()

# ══════════════════════════════════════════════════════════════
# 精細搜索 (用金額$, 唔用點子)
# 0.01 lot: 金價變$1 = 賺/蝕$1
# ══════════════════════════════════════════════════════════════
# SL: $2 ~ $150 (200 ~ 15000點)
# TP: $5 ~ $500 (500 ~ 50000點)
SL_GRID = list(range(2, 41)) + [45, 50, 55, 60, 65, 70, 80, 90, 100, 120, 150]
TP_GRID = list(range(5, 101, 5)) + [120, 150, 180, 200, 250, 300, 400, 500]

def run_bt(sl_d, tp_d):
    pnls = []
    results = []
    for idx in signal_indices:
        ep = C.iloc[idx]
        result = None
        for j in range(idx+1, min(idx+MAX_HOLD, len(gold))):
            if L.iloc[j] <= ep - tp_d:
                result = 'TP'; break
            if H.iloc[j] >= ep + sl_d:
                result = 'SL'; break
        if result is None:
            result = 'TO'
            exit_p = C.iloc[min(idx+MAX_HOLD, len(gold)-1)]
        elif result == 'TP':
            exit_p = ep - tp_d
        else:
            exit_p = ep + sl_d
        # 0.01 lot = 1oz, short PnL = (entry - exit)
        pnl = ep - exit_p
        pnls.append(pnl)
        results.append(result)
    return np.array(pnls), results

print("搜索中...")
all_results = []
for sl_d in SL_GRID:
    for tp_d in TP_GRID:
        if tp_d <= sl_d: continue
        pnls, res = run_bt(sl_d, tp_d)
        tp_c = res.count('TP'); sl_c = res.count('SL'); to_c = res.count('TO')
        total = len(pnls)
        wins = (pnls > 0).sum()
        total_pnl = pnls.sum()
        gw = pnls[pnls>0].sum(); gl = abs(pnls[pnls<0].sum())
        pf = gw/gl if gl>0 else 999
        cum = np.cumsum(pnls)
        max_dd = (cum - np.maximum.accumulate(cum)).min()
        streak=0; ms=0
        for p in pnls:
            if p<0: streak+=1; ms=max(ms,streak)
            else: streak=0
        dd_r = abs(max_dd)/total_pnl if total_pnl>0 else 999
        all_results.append({
            'sl':sl_d,'tp':tp_d,'tp_c':tp_c,'sl_c':sl_c,'to_c':to_c,
            'total':total,'wins':wins,'wr':wins/total,'pf':pf,
            'pnl':total_pnl,'max_dd':max_dd,'ms':ms,'dd_r':dd_r,
        })

profitable = [r for r in all_results if r['pnl'] > 0]
print(f"盈利組合: {len(profitable)} / {len(all_results)}")

# ══════════════════════════════════════════════════════════════
# 4維排序
# ══════════════════════════════════════════════════════════════
def show(title, data, n=15):
    print(f"\n{'='*88}")
    print(f"  {title}")
    print(f"{'='*88}")
    if not data: print("  無"); return
    print(f"  {'SL':>5} {'TP':>5} {'SL點':>6} {'TP點':>6} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3}")
    print(f"  {'-'*80}")
    for r in data[:n]:
        print(f"  ${r['sl']:>3}  ${r['tp']:>3} {r['sl']*100:>5}k {r['tp']*100:>5}k {r['total']:>4} {r['tp_c']:>3} {r['sl_c']:>3} {r['to_c']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3}")

by_pf = sorted(profitable, key=lambda x: x['pf'], reverse=True)
show("1. PF最高 (盈虧比)", by_pf)

by_pnl = sorted(profitable, key=lambda x: x['pnl'], reverse=True)
show("2. 總盈利最高", by_pnl)

by_dd = sorted([r for r in profitable if r['dd_r']<5], key=lambda x: x['dd_r'])
show("3. 回撤/盈利比最低 (最穩)", by_dd)

by_ms = sorted(profitable, key=lambda x: x['ms'])
show("4. 最大連虧最少", by_ms[:15])

# ══════════════════════════════════════════════════════════════
# 綜合評分
# ══════════════════════════════════════════════════════════════
max_pnl = max(r['pnl'] for r in profitable) if profitable else 1
for r in all_results:
    if r['pnl']<=0 or r['pf']<1.05: r['score']=-1; continue
    r['score'] = (min(r['pf']/2,1)*0.3 + min(r['pnl']/max_pnl,1)*0.3 
                  + max(0,1-r['dd_r']/3)*0.2 + max(0,1-r['ms']/40)*0.2)

by_score = sorted([r for r in all_results if r['score']>0], key=lambda x: x['score'], reverse=True)
print(f"\n{'='*88}")
print(f"  綜合評分 Top 15")
print(f"{'='*88}")
print(f"  {'SL':>5} {'TP':>5} {'SL點':>6} {'TP點':>6} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'評分':>5}")
print(f"  {'-'*86}")
for r in by_score[:15]:
    print(f"  ${r['sl']:>3}  ${r['tp']:>3} {r['sl']*100:>5}k {r['tp']*100:>5}k {r['total']:>4} {r['tp_c']:>3} {r['sl_c']:>3} {r['to_c']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['score']:>.3f}")

# ══════════════════════════════════════════════════════════════
# Top 3 詳細月份 + TO明細
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*88}")
print(f"  綜合最佳 Top 3 詳解")
print(f"{'='*88}")

for pr in by_score[:3]:
    sl_d, tp_d = pr['sl'], pr['tp']
    pnls, res = run_bt(sl_d, tp_d)
    df = pd.DataFrame({'time':[gold.index[i] for i in signal_indices],'pnl':pnls,'result':res})
    df['month'] = pd.to_datetime(df['time']).dt.to_period('M')
    total_days = (df['time'].max()-df['time'].min()).days
    months = max(total_days/30.44, 1)
    
    print(f"\n{'─'*55}")
    print(f"  SL=${sl_d}({sl_d*100}點) TP=${tp_d}({tp_d*100}點)")
    print(f"  PF={pr['pf']:.2f} | 盈利=${pr['pnl']:+.2f} | 回撤=${pr['max_dd']:+.2f}")
    print(f"  月均=${pr['pnl']/months:+.2f} | 連虧={pr['ms']}筆 | 勝率={pr['wr']:.1%}")
    print(f"  TP:{pr['tp_c']}筆 SL:{pr['sl_c']}筆 TO:{pr['to_c']}筆")
    print(f"{'─'*55}")
    
    print(f"\n  {'月份':<12} {'交易':>4} {'勝率':>6} {'盈虧$':>8} {'累計$':>8}")
    print(f"  {'-'*42}")
    cum_m=0
    for m, g in df.groupby('month'):
        wr=(g['pnl']>0).mean(); s=g['pnl'].sum(); cum_m+=s
        print(f"  {str(m):<12} {len(g):>4} {wr:>5.1%} {s:>+7.2f} {cum_m:>+7.2f}")
    print(f"  {'-'*42}")
    print(f"  {'總計':<12} {len(df):>4} {pr['wr']:>5.1%} {pr['pnl']:>+7.2f}")
    
    to_df = df[df['result']=='TO']
    if len(to_df)>0:
        print(f"\n  超時平倉({len(to_df)}筆) 總盈虧: ${to_df['pnl'].sum():+.2f}")
        for _,t in to_df.iterrows():
            print(f"    {str(t['time']):>20}  ${t['pnl']:>+7.2f}")