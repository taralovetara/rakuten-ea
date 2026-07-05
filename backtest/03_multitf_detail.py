#!/usr/bin/env python3
"""
Score<=5 指標放喺唔同時間框架 (1H vs 15min vs 5min)
嘗試下載真實數據, 比較效果
"""
import pandas as pd, numpy as np
import warnings, time
warnings.filterwarnings('ignore')

t0 = time.time()

# ══════════════════════════════════════════════════════════════
# Step 1: 下載數據
# ══════════════════════════════════════════════════════════════
print("=" * 70)
print("Step 1: 下載 XAUUSD 數據")
print("=" * 70)

# 嘗試用 yfinance 下載
import yfinance as yf

data_1h = None
data_15m = None
data_5m = None

# 1H: 盡量拉長
print("\n下載 1H 數據...")
try:
    data_1h = yf.download("GC=F", period="730d", interval="1h", progress=False)
    if len(data_1h) > 100:
        print(f"  1H: {len(data_1h)}根K線, {data_1h.index[0]} ~ {data_1h.index[-1]}")
    else:
        data_1h = None; print("  1H: 數據太少")
except Exception as e:
    print(f"  1H: 失敗 - {e}")

# 15min: yfinance通常只提供最近60天
print("\n下載 15min 數據...")
try:
    data_15m = yf.download("GC=F", period="60d", interval="15m", progress=False)
    if len(data_15m) > 100:
        print(f"  15min: {len(data_15m)}根K線, {data_15m.index[0]} ~ {data_15m.index[-1]}")
    else:
        data_15m = None; print("  15min: 數據太少")
except Exception as e:
    print(f"  15min: 失敗 - {e}")

# 5min: yfinance通常只提供最近30天
print("\n下載 5min 數據...")
try:
    data_5m = yf.download("GC=F", period="30d", interval="5m", progress=False)
    if len(data_5m) > 100:
        print(f"  5min: {len(data_5m)}根K線, {data_5m.index[0]} ~ {data_5m.index[-1]}")
    else:
        data_5m = None; print("  5min: 數據太少")
except Exception as e:
    print(f"  5min: 失敗 - {e}")

# ══════════════════════════════════════════════════════════════
# Step 2: 亦用現有1H數據 resample 做對比
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("Step 2: 補充 - 用現有730天1H數據做基準")
print("=" * 70)

gold_1h = pd.read_csv('/tmp/my-project/xauusd_1h_730d.csv', index_col=0, parse_dates=True)
gold_1h.index = pd.to_datetime(gold_1h.index, utc=True)
gold_1h = gold_1h.dropna().sort_index()
print(f"現有1H: {len(gold_1h)}根, {gold_1h.index[0]} ~ {gold_1h.index[-1]}")

# ══════════════════════════════════════════════════════════════
# Step 3: 計算 Larry Williams Score
# ══════════════════════════════════════════════════════════════
def calc_score(gold):
    """計算Larry Williams趨勢強度評分"""
    C=gold['Close']; H=gold['High']; L=gold['Low']; O=gold['Open']; V=gold['Volume']
    
    ema20=C.ewm(span=20,adjust=False).mean()
    ema50=C.ewm(span=50,adjust=False).mean()
    ema200=C.ewm(span=200,adjust=False).mean()
    ema12=C.ewm(span=12,adjust=False).mean()
    ema26=C.ewm(span=26,adjust=False).mean()
    macdLine=ema12-ema26
    signalLine=macdLine.ewm(span=9,adjust=False).mean()
    macdHist=macdLine-signalLine
    atr14=C.rolling(14).apply(lambda x:max(x.max()-x.min(),abs(x.iloc[-1]-x.iloc[-2]) if len(x)>1 else 0),raw=False)
    
    n = len(gold)
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
        bf=max(0,L.iloc[i-1]-H.iloc[i-3])
        atr=atr14.iloc[i] if atr14.iloc[i]>0 else 10
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
    
    scores = np.clip(dirScore+macdSc+fvgSc+bonus, 0, 100)
    below_ema = (C < ema200).values
    return scores, below_ema

# ══════════════════════════════════════════════════════════════
# Step 4: 對每個時間框架做回測
# ══════════════════════════════════════════════════════════════
def run_backtest(gold, scores, below_ema, max_hold, sl_d, tp_d, label=""):
    """立即再入場模式回測"""
    C=gold['Close']; H=gold['High']; L=gold['Low']
    
    sigs = []
    i = 200
    while i < len(gold) - max_hold:
        if scores[i] <= 5 and below_ema[i]:
            sigs.append(i)
            ep = C.iloc[i]
            exit_bar = max_hold
            for j in range(i+1, min(i+max_hold, len(gold))):
                if L.iloc[j] <= ep - tp_d or H.iloc[j] >= ep + sl_d:
                    exit_bar = j - i; break
            i = i + exit_bar + 1
        else:
            i += 1
    
    if len(sigs) == 0:
        return None
    
    pnls = []; results = []
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
        results.append(result)
    
    pnls = np.array(pnls)
    tp_c=results.count('TP'); sl_c=results.count('SL'); to_c=results.count('TO')
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
    
    total_days = (gold.index[sigs[-1]] - gold.index[sigs[0]]).days
    months = max(total_days/30.44, 0.1)
    
    return {
        'label': label, 'sigs': len(sigs), 'total': total,
        'tp_c': tp_c, 'sl_c': sl_c, 'to_c': to_c,
        'wr': wins/total if total>0 else 0,
        'pnl': total_pnl, 'pf': pf, 'max_dd': max_dd,
        'ms': ms, 'months': months, 'monthly': total_pnl/months,
    }

# ══════════════════════════════════════════════════════════════
# 對每個時間框架測試
# ══════════════════════════════════════════════════════════════
test_configs = []

# 現有1H數據 (730天)
if gold_1h is not None and len(gold_1h) > 200:
    test_configs.append(('730天 1H (現有)', gold_1h, 48))

# yfinance下載的數據
if data_1h is not None and len(data_1h) > 200:
    # yfinance returns MultiIndex columns sometimes
    if isinstance(data_1h.columns, pd.MultiIndex):
        data_1h.columns = data_1h.columns.get_level_values(0)
    data_1h = data_1h.dropna().sort_index()
    test_configs.append(('yf 1H', data_1h, 48))

if data_15m is not None and len(data_15m) > 200:
    if isinstance(data_15m.columns, pd.MultiIndex):
        data_15m.columns = data_15m.columns.get_level_values(0)
    data_15m = data_15m.dropna().sort_index()
    # 15min: 48根 = 12小時
    test_configs.append(('yf 15min (48根=12h)', data_15m, 48))
    # 亦試96根 = 24小時
    test_configs.append(('yf 15min (96根=24h)', data_15m, 96))

if data_5m is not None and len(data_5m) > 200:
    if isinstance(data_5m.columns, pd.MultiIndex):
        data_5m.columns = data_5m.columns.get_level_values(0)
    data_5m = data_5m.dropna().sort_index()
    # 5min: 48根 = 4小時
    test_configs.append(('yf 5min (48根=4h)', data_5m, 48))
    # 5min: 288根 = 24小時
    test_configs.append(('yf 5min (288根=24h)', data_5m, 288))

# 固定 SL/TP = 最佳組合
SL = 50  # $50
TP = 200  # $200

print(f"\n{'='*70}")
print(f"回測比較 (SL=${SL}, TP=${TP}, 0.01 lot, 立即再入場)")
print(f"{'='*70}")

results_all = []
for label, gold, max_hold in test_configs:
    if len(gold) < 300:  # EMA200需要至少200+數據
        print(f"\n  {label}: 數據太少 ({len(gold)}根), 跳過")
        continue
    
    print(f"\n  計算 {label} ({len(gold)}根K線)...", end="", flush=True)
    scores, below_ema = calc_score(gold)
    
    r = run_backtest(gold, scores, below_ema, max_hold, SL, TP, label)
    if r:
        results_all.append(r)
        print(f" {r['sigs']}筆交易, 盈利${r['pnl']:+.2f}")
    else:
        print(" 無信號")

if results_all:
    print(f"\n{'='*90}")
    print(f"最終比較")
    print(f"{'='*90}")
    print(f"\n  {'時間框架':<30} {'信號':>4} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>7} {'持倉H':>5}")
    print(f"  {'-'*90}")
    for r in results_all:
        hold_h = r['label'].split('=')[-1].replace('h)','').strip() if '=' in r['label'] else '?'
        print(f"  {r['label']:<30} {r['sigs']:>4} {r['total']:>4} {r['tp_c']:>3} {r['sl_c']:>3} {r['to_c']:>3} {r['wr']:>5.1%} {r['pf']:>4.2f} {r['pnl']:>+7.2f} {r['max_dd']:>+7.2f} {r['ms']:>3} {r['monthly']:>+6.2f} {hold_h:>5}")

# ══════════════════════════════════════════════════════════════
# 如果無法下載低時間框架數據, 做理論分析
# ══════════════════════════════════════════════════════════════
if (data_15m is None or data_15m.empty) and (data_5m is None or data_5m.empty):
    print(f"\n{'='*90}")
    print(f"理論分析: 指標放喺更低時間框架嘅影響")
    print(f"{'='*90}")
    
    # 計算1H數據中 Score<=5 嘅分佈
    scores_1h, below_1h = calc_score(gold_1h)
    
    # Score分佈
    print(f"\n  1H 圖表 Score 分佈:")
    for threshold in [0, 3, 5, 7, 10, 15, 20]:
        count = (scores_1h[200:] <= threshold).sum()
        total = len(scores_1h) - 200
        print(f"    Score<={threshold:>2}: {count:>5}筆 ({count/total:.1%})")
    
    print(f"\n  關鍵差異 (1H vs 15min vs 5min):")
    print(f"  {'─'*70}")
    print(f"  {'維度':<15} {'1H':>12} {'15min':>12} {'5min':>12}")
    print(f"  {'-'*55}")
    print(f"  {'K線數量(730天)':<15} {'~17,520':>12} {'~70,080':>12} {'~210,240':>12}")
    print(f"  {'信號頻率':<15} {'月均2.6筆':>12} {'預估月均10+筆':>12} {'預估月均30+筆':>12}")
    print(f"  {'每筆噪音':<15} {'低':>12} {'中':>12} {'高':>12}")
    print(f"  {'EMA200穩定性':<15} {'好':>12} {'較好':>12} {'差(需更多數據)':>12}")
    print(f"  {'點差影響':<15} {'小(0.2%)':>12} {'中(0.2%)':>12} {'大(0.2%但波幅小)':>12}")
    print(f"  {'SL/TP需要':<15} {'$50/$200':>12} {'可能$20/$80':>12} {'可能$8/$30':>12}")
    
    print(f"\n  預期效果:")
    print(f"  1. 信號會多3-10倍 (更多交易機會)")
    print(f"  2. 每筆利潤會細 (因為持倉時間短, 價格波幅小)")
    print(f"  3. 點差佔比變大 (5min圖表$8止損, 點差可能佔10-20%)")
    print(f"  4. EMA200需要200根K線先穩定: 5min=1000小時≈42天, 15min=50小時≈2天")
    print(f"  5. FVG/MACD信號會更頻密但信噪比更低")
    
    print(f"\n  結論:")
    print(f"  - 15min可能值得試 (平衡信號數量同噪音)")
    print(f"  - 5min大概率會被點差吃掉利潤")
    print(f"  - 建議: 如果要試低時間框架, SL/TP要相應調細, "
          f"而且一定要用實盤點差計算")

print(f"\n總耗時: {time.time()-t0:.1f}s")