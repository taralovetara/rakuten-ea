#!/usr/bin/env python3
"""
5min SL=$50 TP=$200 24h持倉 - 逐筆交易明細
確認 0.01 lot 最終盈利
"""
import pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
gold = yf.download("GC=F", period="60d", interval="5m", progress=False)
if isinstance(gold.columns, pd.MultiIndex):
    gold.columns = gold.columns.get_level_values(0)
gold = gold.dropna().sort_index()

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

allScores=np.clip(dirScore+macdSc+fvgSc+bonus,0,100)
below_ema200=(C<ema200).values

# ══════════════════════════════════════════════════════════════
# SL=$50, TP=$200, 24h=288根, 0.01 lot
# ══════════════════════════════════════════════════════════════
SL_D = 50
TP_D = 200
MAX_HOLD = 288
LOT = 0.01

# 收集信號
sigs = []
i = 500
while i < len(gold) - MAX_HOLD:
    if allScores[i] <= 5 and below_ema200[i]:
        sigs.append(i)
        ep = C.iloc[i]
        exit_bar = MAX_HOLD
        for j in range(i+1, min(i+MAX_HOLD, len(gold))):
            if L.iloc[j] <= ep - TP_D or H.iloc[j] >= ep + SL_D:
                exit_bar = j - i; break
        i = i + exit_bar + 1
    else:
        i += 1

# 逐筆計算
print(f"{'='*90}")
print(f"  5min | SL=${SL_D} | TP=${TP_D} | 24h持倉 | {LOT} lot | 逐筆明細")
print(f"{'='*90}")
print(f"  Lot={LOT} = {LOT*100}oz, Short PnL = (入場價 - 出場價) × {LOT*100}oz")
print(f"  即 PnL$ = 價格變動$ × 1 (因為 0.01 lot = 1oz)")
print()

trades = []
cum_pnl = 0
for idx in sigs:
    entry_time = gold.index[idx]
    entry_price = C.iloc[idx]
    result = None
    exit_bar_idx = min(idx + MAX_HOLD, len(gold) - 1)
    
    for j in range(idx+1, min(idx+MAX_HOLD, len(gold))):
        if L.iloc[j] <= entry_price - TP_D:
            result = 'TP'
            exit_price = entry_price - TP_D
            exit_time = gold.index[j]
            break
        if H.iloc[j] >= entry_price + SL_D:
            result = 'SL'
            exit_price = entry_price + SL_D
            exit_time = gold.index[j]
            break
    
    if result is None:
        result = 'TO'
        exit_price = C.iloc[exit_bar_idx]
        exit_time = gold.index[exit_bar_idx]
    
    # 0.01 lot = 1oz, short PnL = (entry - exit) × 1
    price_change = entry_price - exit_price
    pnl = price_change * 1  # ×1 因為 0.01 lot = 1oz
    cum_pnl += pnl
    
    hold_bars = 0
    for j in range(idx+1, len(gold)):
        if gold.index[j] >= exit_time:
            hold_bars = j - idx
            break
    
    trades.append({
        'no': len(trades)+1,
        'entry_time': entry_time,
        'entry_price': entry_price,
        'exit_time': exit_time,
        'exit_price': exit_price,
        'result': result,
        'price_chg': price_change,
        'pnl': pnl,
        'cum_pnl': cum_pnl,
        'hold_bars': hold_bars,
    })

# 打印逐筆
print(f"  {'#':>3} {'入場時間':>20} {'入場價':>9} {'出場時間':>20} {'出場價':>9} {'結果':>3} {'價差$':>8} {'盈虧$':>8} {'累計$':>9}")
print(f"  {'-'*105}")

for t in trades:
    print(f"  {t['no']:>3} {str(t['entry_time']):>20} {t['entry_price']:>9.2f} {str(t['exit_time']):>20} {t['exit_price']:>9.2f} {t['result']:>3} {t['price_chg']:>+8.2f} {t['pnl']:>+8.2f} {t['cum_pnl']:>+9.2f}")

# 統計
print(f"\n{'='*90}")
print(f"  統計摘要")
print(f"{'='*90}")

tp_trades = [t for t in trades if t['result']=='TP']
sl_trades = [t for t in trades if t['result']=='SL']
to_trades = [t for t in trades if t['result']=='TO']

print(f"  總交易: {len(trades)} 筆")
print(f"  TP (止盈): {len(tp_trades)} 筆 → 盈利 ${sum(t['pnl'] for t in tp_trades):+.2f}")
print(f"  SL (止損): {len(sl_trades)} 筆 → 虧損 ${sum(t['pnl'] for t in sl_trades):+.2f}")
print(f"  TO (超時): {len(to_trades)} 筆 → 盈虧 ${sum(t['pnl'] for t in to_trades):+.2f}")
print()

total_pnl = sum(t['pnl'] for t in trades)
wins = sum(1 for t in trades if t['pnl'] > 0)
total_days = (trades[-1]['entry_time'] - trades[0]['entry_time']).days
months = max(total_days / 30.44, 0.1)

print(f"  ┌─────────────────────────────────────────┐")
print(f"  │  總盈虧:     ${total_pnl:>+10.2f}              │")
print(f"  │  勝率:       {wins}/{len(trades)} ({wins/len(trades):.1%})            │")
print(f"  │  數據天數:   {total_days} 天 ({months:.1f} 個月)          │")
print(f"  │  月均盈利:   ${total_pnl/months:>+10.2f}              │")
print(f"  │  手數:       {LOT} lot (1oz)               │")
print(f"  │  每筆平均:   ${total_pnl/len(trades):>+10.2f}              │")
print(f"  └─────────────────────────────────────────┘")
print()
print(f"  ⚠️  以上全部基於 0.01 lot (1 盎司), 即每$1價格變動 = $1盈虧")
print(f"  ⚠️  數據僅 {months:.1f} 個月, 不代表未來表現")