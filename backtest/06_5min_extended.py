#!/usr/bin/env python3
"""
下載盡可能多嘅 XAUUSD 5min 數據
嘗試多個數據源
"""
import pandas as pd, numpy as np
import warnings, time, datetime
warnings.filterwarnings('ignore')
t0 = time.time()

# ══════════════════════════════════════════════════════════════
# 方法1: yfinance 循環下載 (GC=F, 可能分批拉)
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("方法1: yfinance GC=F 5min 分批下載")
print("=" * 60)

import yfinance as yf

all_5m = pd.DataFrame()

# 嘗試用 start/end 分批拉
# yfinance 5min: 最多拉30天, 我哋試下分批
chunks = []
end_date = datetime.datetime(2026, 7, 3)
for i in range(12):  # 嘗試拉12個月
    start_date = end_date - datetime.timedelta(days=30)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    try:
        df = yf.download("GC=F", start=start_str, end=end_str, interval="5m", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) > 0:
            chunks.append(df)
            print(f"  {start_str} ~ {end_str}: {len(df)}根")
        else:
            print(f"  {start_str} ~ {end_str}: 無數據")
    except Exception as e:
        print(f"  {start_str} ~ {end_str}: 失敗 - {e}")
    
    end_date = start_date - datetime.timedelta(days=1)
    
    if i > 0 and len(chunks) > 0 and i >= 3:
        # 如果第4批都無數據就停
        if len(chunks[-1]) == 0:
            break

if chunks:
    all_5m_yf = pd.concat(chunks).sort_index()
    all_5m_yf = all_5m_yf[~all_5m_yf.index.duplicated(keep='first')]
    print(f"\n  yfinance GC=F 5min 總計: {len(all_5m_yf)}根")
    print(f"  範圍: {all_5m_yf.index[0]} ~ {all_5m_yf.index[-1]}")
else:
    all_5m_yf = pd.DataFrame()
    print("  無數據")

# ══════════════════════════════════════════════════════════════
# 方法2: yfinance 用不同ticker
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("方法2: 嘗試其他 yfinance ticker")
print("=" * 60)

tickers = ["XAUUSD=X", "GOLD=F", "GLD"]  # GLD是ETF, 有5min數據但價格不同

for ticker in tickers:
    try:
        df = yf.download(ticker, period="60d", interval="5m", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) > 10:
            print(f"  {ticker}: {len(df)}根, {df.index[0]} ~ {df.index[-1]}, 價格範圍 {df['Close'].min():.2f}~{df['Close'].max():.2f}")
        else:
            print(f"  {ticker}: 數據太少")
    except Exception as e:
        print(f"  {ticker}: 失敗 - {e}")

# ══════════════════════════════════════════════════════════════
# 方法3: 用 1H 數據 resample + 隨機插值 模擬5min
# (最後手段, 加入合理噪音)
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("方法3: 用1H數據生成模擬5min (加入真實波動特徵)")
print("=" * 60)

gold_1h = pd.read_csv('/tmp/my-project/xauusd_1h_730d.csv', index_col=0, parse_dates=True)
gold_1h.index = pd.to_datetime(gold_1h.index, utc=True)
gold_1h = gold_1h.dropna().sort_index()
print(f"  1H數據: {len(gold_1h)}根, {gold_1h.index[0]} ~ {gold_1h.index[-1]}")

# 每根1H K線拆成12根5min K線
np.random.seed(42)
sim_5m_rows = []

for idx, row in gold_1h.iterrows():
    o, h, l, c, v = row['Open'], row['High'], row['Low'], row['Close'], row['Volume']
    bar_range = h - l
    
    if bar_range <= 0:
        # 無波動, 直接填充
        for m in range(12):
            t = idx + pd.Timedelta(minutes=m*5)
            sim_5m_rows.append({'datetime': t, 'Open': o, 'High': o+0.01, 'Low': o-0.01, 'Close': o, 'Volume': v/12})
        continue
    
    # 用隨機遊走模擬12個5min區間
    # 約束: 最終收市價=1H收市價, 最高/最低價唔超過1H範圍
    prices = [o]
    for m in range(11):
        # 每步隨機偏移, 但偏向最終目標c
        remaining = 11 - m
        target = c
        bias = (target - prices[-1]) / remaining * 0.3  # 30%偏向目標
        noise = np.random.normal(0, bar_range * 0.15)  # 噪音
        step = bias + noise
        new_price = prices[-1] + step
        # 約束在H/L範圍內 (留少少margin)
        new_price = np.clip(new_price, l + 0.01, h - 0.01)
        prices.append(new_price)
    
    # 確保最後一個價格 = c
    prices[-1] = c
    
    # 生成每5min的OHLCV
    for m in range(12):
        t = idx + pd.Timedelta(minutes=m*5)
        # 每5min區間可能有2-3個tick, 模擬OHLC
        sub_prices = []
        if m > 0:
            sub_prices.append(prices[m-1])  # 開盤 = 上一個收盤
        sub_prices.append(prices[m])
        # 加入1-2個隨機中間價
        for _ in range(np.random.randint(1, 3)):
            mid = np.random.uniform(l, h)
            sub_prices.append(mid)
        
        sub_o = sub_prices[0]
        sub_c = sub_prices[-1]
        sub_h = max(sub_prices)
        sub_l = min(sub_prices)
        sub_v = v / 12 * np.random.uniform(0.5, 1.5)
        
        sim_5m_rows.append({
            'datetime': t, 'Open': sub_o, 'High': sub_h, 
            'Low': sub_l, 'Close': sub_c, 'Volume': sub_v
        })

sim_5m = pd.DataFrame(sim_5m_rows)
sim_5m['datetime'] = pd.to_datetime(sim_5m['datetime'], utc=True)
sim_5m = sim_5m.set_index('datetime').sort_index()
sim_5m = sim_5m[~sim_5m.index.duplicated(keep='first')]

print(f"  模擬5min: {len(sim_5m)}根, {sim_5m.index[0]} ~ {sim_5m.index[-1]}")

# 驗證: 模擬數據嘅1H收市價應該 ≈ 真實1H收市價
sim_1h = sim_5m.resample('1h').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'})
common_idx = sim_1h.index.intersection(gold_1h.index)
if len(common_idx) > 0:
    diff = (sim_1h.loc[common_idx, 'Close'] - gold_1h.loc[common_idx, 'Close']).abs()
    print(f"  驗證: 模擬vs真實1H收市價 平均偏差: ${diff.mean():.4f}, 最大: ${diff.max():.4f}")

# ══════════════════════════════════════════════════════════════
# 方法4: 如果yfinance拉到長數據, 合併
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("數據總結")
print("=" * 60)

# 用模擬5min做主要測試 (因為有730天數據)
# 用yfinance真實5min做驗證
print(f"\n  數據源              K線數     範圍")
print(f"  {'-'*55}")
print(f"  yfinance 5min (真實)  {len(all_5m_yf):>6}   {all_5m_yf.index[0] if len(all_5m_yf)>0 else 'N/A'} ~ {all_5m_yf.index[-1] if len(all_5m_yf)>0 else 'N/A'}")
print(f"  模擬5min (1H拆分)    {len(sim_5m):>6}   {sim_5m.index[0]} ~ {sim_5m.index[-1]}")
print(f"  真實1H (基準)        {len(gold_1h):>6}   {gold_1h.index[0]} ~ {gold_1h.index[-1]}")

# ══════════════════════════════════════════════════════════════
# Step 5: 用模擬5min數據跑完整回測
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("模擬5min 回測 (Score<=5, 立即再入場)")
print(f"{'='*70}")

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

# 5min圖表: 唔同持倉時間
# 288根5min = 24小時, 144根 = 12小時, 576根 = 48小時
hold_configs = [
    ("5min 持倉12h (144根)", 144),
    ("5min 持倉24h (288根)", 288),
    ("5min 持倉48h (576根)", 576),
    ("5min 持倉6h (72根)", 72),
    ("5min 持倉4h (48根)", 48),
]

# 5min用嘅SL/TP (因為波幅更細, 用更細嘅值)
SL_TP_combos = [
    ("$8/$30", 8, 30),
    ("$10/$40", 10, 40),
    ("$15/$60", 15, 60),
    ("$20/$80", 20, 80),
    ("$30/$120", 30, 120),
    ("$50/$200", 50, 200),
]

print(f"\n計算 Score (模擬5min, {len(sim_5m)}根)...", end="", flush=True)
scores_5m, below_5m = calc_score(sim_5m)
print(" 完成")

# 等EMA200穩定 (200根5min = ~16.7小時)
start_bar = 500  # 多留啲buffer

for hold_name, max_hold in hold_configs:
    print(f"\n{'─'*70}")
    print(f"  {hold_name}")
    print(f"{'─'*70}")
    
    # 收集信號 (立即再入場)
    sigs = []
    i = start_bar
    C5=sim_5m['Close']; H5=sim_5m['High']; L5=sim_5m['Low']
    while i < len(sim_5m) - max_hold:
        if scores_5m[i] <= 5 and below_5m[i]:
            sigs.append(i)
            ep = C5.iloc[i]
            exit_bar = max_hold
            for j in range(i+1, min(i+max_hold, len(sim_5m))):
                if L5.iloc[j] <= ep - 30 or H5.iloc[j] >= ep + 10:  # 用預設SL/TP做信號
                    exit_bar = j - i; break
            i = i + exit_bar + 1
        else:
            i += 1
    
    if len(sigs) == 0:
        print("  無信號"); continue
    
    total_days = (sim_5m.index[sigs[-1]] - sim_5m.index[sigs[0]]).days
    months = max(total_days / 30.44, 0.1)
    
    print(f"  信號: {len(sigs)}筆 | 範圍: {sim_5m.index[sigs[0]].strftime('%Y-%m-%d')} ~ {sim_5m.index[sigs[-1]].strftime('%Y-%m-%d')} ({months:.1f}月)")
    
    print(f"\n  {'SL/TP':<10} {'交易':>4} {'TP':>3} {'SL':>3} {'TO':>3} {'勝率':>6} {'PF':>5} {'盈虧$':>8} {'回撤$':>8} {'連虧':>3} {'月均$':>7}")
    print(f"  {'-'*68}")
    
    best_pnl = -999
    best_combo = None
    for combo_name, sl_d, tp_d in SL_TP_combos:
        pnls = []; results = []
        for idx in sigs:
            ep = C5.iloc[idx]
            result = None
            for j in range(idx+1, min(idx+max_hold, len(sim_5m))):
                if L5.iloc[j] <= ep - tp_d:
                    result='TP'; break
                if H5.iloc[j] >= ep + sl_d:
                    result='SL'; break
            if result is None:
                result='TO'; xp = C5.iloc[min(idx+max_hold, len(sim_5m)-1)]
            elif result=='TP': xp = ep - tp_d
            else: xp = ep + sl_d
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
        
        if total_pnl > best_pnl:
            best_pnl = total_pnl
            best_combo = combo_name
        
        print(f"  {combo_name:<10} {total:>4} {tp_c:>3} {sl_c:>3} {to_c:>3} {wins/total if total>0 else 0:>5.1%} {pf:>4.2f} {total_pnl:>+7.2f} {max_dd:>+7.2f} {ms:>3} {total_pnl/months:>+6.2f}")

print(f"\n總耗時: {time.time()-t0:.1f}s")
print(f"\n注意: 模擬5min數據係由1H拆分而嚟, 內部價格走勢係隨機模擬")
print(f"真正嘅5min edge需要真實5min數據驗證")