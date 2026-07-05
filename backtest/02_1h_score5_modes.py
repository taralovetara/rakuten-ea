#!/usr/bin/env python3
"""
Score<=5 + EMA200: 比較冷卻期 vs 立即再入場
全部精確bar-by-bar, 正確PnL (0.01 lot = 1oz)
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

# ══════════════════════════════════════════════════════════════
# 收集兩種模式嘅信號
# ══════════════════════════════════════════════════════════════
MAX_HOLD = 48

# Mode A: 冷卻期48根
cooldown_sigs = []
i = 200
while i < len(gold) - MAX_HOLD:
    if allScores[i] <= 5 and below_ema200[i]:
        cooldown_sigs.append(i)
        i += MAX_HOLD
    else:
        i += 1

# Mode B: 立即再入場 (出場後下一根K線可再入)
immediate_sigs = []
i = 200
while i < len(gold) - MAX_HOLD:
    if allScores[i] <= 5 and below_ema200[i]:
        immediate_sigs.append(i)
        # 計算呢筆交易幾時出場
        ep = C.iloc[i]
        exit_bar = MAX_HOLD  # default
        for j in range(i+1, min(i+MAX_HOLD, len(gold))):
            # 用一個合理嘅SL/TP做參考, 例如 SL=$10, TP=$15
            if L.iloc[j] <= ep - 15:
                exit_bar = j - i; break
            if H.iloc[j] >= ep + 10:
                exit_bar = j - i; break
        i = i + exit_bar + 1  # 出場後下一根
    else:
        i += 1

# Mode C: 每一根K線都獨立評估 (唔理上一筆有冇出場, 但唔重疊)
# 即: 如果上一筆仲未出場就跳過
overlap_sigs = []
in_trade = False
exit_idx = 0
for i in range(200, len(gold) - MAX_HOLD):
    if in_trade and i <= exit_idx:
        continue
    if allScores[i] <= 5 and below_ema200[i]:
        overlap_sigs.append(i)
        ep = C.iloc[i]
        exit_i = i + MAX_HOLD
        for j in range(i+1, min(i+MAX_HOLD, len(gold))):
            if L.iloc[j] <= ep - 15 or H.iloc[j] >= ep + 10:
                exit_i = j; break
        in_trade = True
        exit_idx = exit_i
    else:
        in_trade = False

print(f"Mode A (冷卻期48根):   {len(cooldown_sigs)}筆信號")
print(f"Mode B (立即再入場):   {len(immediate_sigs)}筆信號")
print(f"Mode C (唔重疊即入):   {len(overlap_sigs)}筆信號")

# ══════════════════════════════════════════════════════════════
# 對三種模式做暴力搜索
# ══════════════════════════════════════════════════════════════
SL_GRID = [3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100]
TP_GRID = [5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200]

def run_bt(sigs, sl_d, tp_d, max_hold=48):
    pnls = []
    res = []
    for idx in sigs:
        ep = C.iloc[idx]
        result = None
        for j in range(idx+1, min(idx+max_hold, len(gold))):
            if L.iloc[j] <= ep - tp_d:
                result='TP'; break
            if H.iloc[j] >= ep + sl_d:
                result='SL'; break
        if result is None:
            result='TO'
            xp = C.iloc[min(idx+max_hold, len(gold)-1)]
        elif result=='TP':
            xp = ep - tp_d
        else:
            xp = ep + sl_d
        pnls.append(ep - xp)
        res.append(result)
    return np.array(pnls), res

for mode_name, sigs in [("A-冷卻期", cooldown_sigs), 
                          ("B-立即再入", immediate_sigs),
                          ("C-唔重疊", overlap_sigs)]:
    print(f"\n{'='*88}")
    print(f"  {mode_name}: {len(sigs)}筆信號")
    print(f"{'='*88}")
    
    results = []
    for sl_d in SL_GRID:
        for tp_d in TP_GRID:
            if tp_d <= sl_d: continue
            pnls, res = run_bt(sigs, sl_d, tp_d)
            tp_c=res.count('TP'); sl_c=res.count('SL'); to_c=res.count('TO')
            total=len(pnls); wins=(pnls>0).sum()
            total_pnl=pnls.sum()
            gw=pnls[pnls>0].sum(); gl=abs(pnls[pnls<0].sum())
            pf=gw/gl if gl>0 else 999
            cum=np.cumsum(pnls)
            max_dd=(cum-np.maximum.accumulate(cum)).min()
            streak=0; ms=0
            for p in pnls:
                if p<0: streak+=1; ms=max(ms,streak)
                else: streak=0
            dd_r=abs(max_dd)/total_pnl if total_pnl>0 else 999
            results.append({
                'sl':sl_d,'tp':tp_d,'tp_c':tp_c,'sl_c':sl_c,'to_c':to_c,
                'total':total,'wins':wins,'wr':wins/total,'pf':pf,
                'pnl':total_pnl,'max_dd':max_dd,'ms':ms,'dd_r':dd_r,
            })
    
    profitable = [r for r in results if r['pnl']>0]
    
    # 綜合評分
    max_pnl = max(r['pnl'] for r in profitable) if profitable else 1
    for r in results:
        if r['pnl']<=0 or r['pf']<1.05: r['score']=-1; continue
        r['score']=(min(r['pf']/2,1)*0.3 + min(r['pnl']/max_pnl,1)*0.3 
                    + max(0,1-r['dd_r']/3)*0.2 + max(0,1-r['ms']/max(r['total']*0.5,1))*0.2)
    
    by_score = sorted([r for r in results if r['score']>0], key=lambda x: x['score'], reverse=True)
    
    if not by_score:
        print("  無盈利組合!")
        continue
    
    total_days = (gold.index[sigs[-1]] - gold.index[sigs[0]]).days
    months = max(total_days/30.44, 1)
    
    print(f"  數據範圍: {gold.index[sigs[0]].strftime('%Y-%m')} ~ {gold.index[sigs[-1]].strftime('%Y-%m')} ({months:.1f}個月)")
    print(f"  盈利組合: {len(profitable)}")
    print(f"\n  {'SL$':>5} {'TP$':>5} {'SL點':>5} {'TP點':>5} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>7} {'評分':>5}")
    print(f"  {'-'*88}")
    for r in by_score[:15]:
        print(f"  ${r['sl']:>3}  ${r['tp']:>3} {r['sl']*100:>4}k {r['tp']*100:>4}k {r['total']:>4} {r['tp_c']:>3} {r['sl_c']:>3} {r['to_c']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['pnl']/months:>+6.2f} {r['score']:>.3f}")

# ══════════════════════════════════════════════════════════════
# 額外: 如果唔計MAX_HOLD, 直接睇Score<=5入場後48h嘅平均價格變化
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*88}")
print(f"  Score<=5 入場後 N 小時平均價格變化 (所有信號, 含重疊)")
print(f"{'='*88}")

all_s5 = [i for i in range(200, len(gold)-48) if allScores[i]<=5 and below_ema200[i]]
print(f"\n  總Score<=5信號: {len(all_s5)}筆")
print(f"\n  {'持倉H':>6} {'平均盈虧$':>10} {'勝率':>7} {'中位數$':>10} {'最大盈利$':>10} {'最大虧損$':>10}")
print(f"  {'-'*60}")

for hold in [1, 2, 4, 6, 8, 12, 18, 24, 30, 36, 42, 48]:
    pnls = []
    for idx in all_s5:
        ep = C.iloc[idx]
        xp = C.iloc[min(idx+hold, len(gold)-1)]
        pnls.append(ep - xp)
    pnls = np.array(pnls)
    wins = (pnls>0).sum()
    print(f"  {hold:>5}h {pnls.mean():>+9.2f} {wins/len(pnls):>6.1%} {np.median(pnls):>+9.2f} {pnls.max():>+9.2f} {pnls.min():>+9.2f}")

print(f"\n  結論: 如果平均盈虧為正, 策略本質上有edge")
print(f"  最佳持倉時間 = 單純持有N小時後平倉嘅最佳回報")

print(f"\n總耗時: {time.time()-t0:.1f}s")