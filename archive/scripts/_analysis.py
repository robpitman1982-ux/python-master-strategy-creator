import csv, json
from pathlib import Path
from collections import Counter

repo = Path(r"C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator")

def sf(v):
    try: return float(str(v).replace(',','').replace('$',''))
    except: return 0.0

lb = repo / "Outputs" / "ultimate_leaderboard.csv"
with open(lb, newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

boot = repo / "Outputs" / "ultimate_leaderboard_bootcamp.csv"
with open(boot, newline='', encoding='utf-8') as f:
    brows = list(csv.DictReader(f))

print(f"TOTAL STRATEGIES: {len(rows)}")
print(f"BOOTCAMP ACCEPTED: {len(brows)}")
print()
# By market
markets = Counter()
for r in rows:
    ds = r.get('dataset', '')
    market = ds.split('_')[0] if ds else '?'
    markets[market] += 1
print("BY MARKET:")
for m, c in sorted(markets.items(), key=lambda x: -x[1]):
    print(f"  {m}: {c}")

# By timeframe
tfs = Counter()
for r in rows:
    ds = r.get('dataset', '')
    parts = ds.split('_')
    tf = parts[1] if len(parts) > 1 else '?'
    tfs[tf] += 1
print("\nBY TIMEFRAME:")
for t, c in sorted(tfs.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}")

# By strategy family
fams = Counter(r.get('strategy_type', '') for r in rows)
print("\nBY FAMILY:")
for f, c in sorted(fams.items(), key=lambda x: -x[1]):
    print(f"  {f}: {c}")
print()
# Quality distribution
flags = Counter(r.get('quality_flag', '') for r in rows)
print("BY QUALITY:")
for fl, c in sorted(flags.items(), key=lambda x: -x[1]):
    print(f"  {fl}: {c}")

# NEW vs OLD markets
new_mkts = {'AD', 'BP', 'JY', 'EC', 'NG', 'TY', 'US', 'W', 'BTC'}
old_mkts = {'ES', 'CL', 'NQ', 'SI', 'HG', 'RTY', 'YM', 'GC'}
new_rows = [r for r in rows if r.get('dataset','').split('_')[0] in new_mkts]
old_rows = [r for r in rows if r.get('dataset','').split('_')[0] in old_mkts]
print(f"\nOLD 8 MARKETS: {len(old_rows)} strategies")
print(f"NEW 9 MARKETS: {len(new_rows)} strategies")

# New market detail
if new_rows:
    nm = Counter()
    for r in new_rows:
        ds = r.get('dataset', '')
        m = ds.split('_')[0]
        nm[m] += 1
    print("\nNEW MARKET BREAKDOWN:")
    for m, c in sorted(nm.items(), key=lambda x: -x[1]):
        print(f"  {m}: {c}")
print()
# Top 25 ROBUST strategies across all markets
robust = [r for r in rows if r.get('quality_flag','') in ('ROBUST','ROBUST_BORDERLINE')]
robust.sort(key=lambda r: -sf(r.get('leader_pf','0')))

print("TOP 25 ROBUST/ROBUST_BORDERLINE STRATEGIES:")
print(f"{'#':<4} {'Market':<6} {'TF':<7} {'Family':<30} {'PF':<7} {'IS':<7} {'OOS':<7} {'12m':<7} {'Trades':<7} {'Quality':<20}")
print("-" * 105)
for i, r in enumerate(robust[:25], 1):
    ds = r.get('dataset','')
    parts = ds.split('_')
    m = parts[0] if parts else ''
    tf = parts[1] if len(parts)>1 else ''
    fam = r.get('strategy_type','')
    pf = sf(r.get('leader_pf','0'))
    isp = sf(r.get('is_pf','0'))
    oop = sf(r.get('oos_pf','0'))
    r12 = sf(r.get('recent_12m_pf','0'))
    tr = r.get('leader_trades','')
    q = r.get('quality_flag','')
    print(f"{i:<4} {m:<6} {tf:<7} {fam:<30} {pf:<7.2f} {isp:<7.2f} {oop:<7.2f} {r12:<7.2f} {tr:<7} {q:<20}")
print()
# New market highlights - best from each new market
print("NEW MARKET HIGHLIGHTS (best accepted per market):")
print(f"{'Market':<6} {'TF':<7} {'Family':<30} {'PF':<7} {'IS':<7} {'OOS':<7} {'Trades':<7} {'Quality':<20} {'BCS':<7}")
print("-" * 105)
seen_markets = set()
new_accepted = [r for r in new_rows if str(r.get('accepted_final','')).strip().lower() in ('true','1','yes')]
new_accepted.sort(key=lambda r: -sf(r.get('leader_pf','0')))
for r in new_accepted:
    ds = r.get('dataset','')
    m = ds.split('_')[0]
    parts = ds.split('_')
    tf = parts[1] if len(parts)>1 else ''
    fam = r.get('strategy_type','')
    pf = sf(r.get('leader_pf','0'))
    isp = sf(r.get('is_pf','0'))
    oop = sf(r.get('oos_pf','0'))
    tr = r.get('leader_trades','')
    q = r.get('quality_flag','')
    bcs = r.get('bootcamp_score','')
    mk = f"{m}_{tf}"
    if mk not in seen_markets:
        seen_markets.add(mk)
        print(f"{m:<6} {tf:<7} {fam:<30} {pf:<7.2f} {isp:<7.2f} {oop:<7.2f} {tr:<7} {q:<20} {bcs:<7}")
print()

# Portfolio potential - count ROBUST per market
print("ROBUST COUNT PER MARKET (portfolio diversity):")
robust_by_mkt = Counter()
for r in rows:
    if r.get('quality_flag','') in ('ROBUST','ROBUST_BORDERLINE'):
        ds = r.get('dataset','')
        m = ds.split('_')[0]
        robust_by_mkt[m] += 1
for m, c in sorted(robust_by_mkt.items(), key=lambda x: -x[1]):
    print(f"  {m}: {c}")
