import csv, os, json
from pathlib import Path
from collections import Counter

repo = Path(r"C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator")
runs_dir = repo / "Outputs" / "runs"

print("=" * 80)
print("ANALYSIS OF ALL DOWNLOADED RUNS")
print("=" * 80)

# Check new runs from Nikola bucket
new_runs = sorted([d for d in runs_dir.iterdir() if d.is_dir() and ("sweep-60m" in d.name or "sweep-ad-daily" in d.name)])
print(f"\nNew market runs found: {len(new_runs)}")
for rd in new_runs:
    lb = rd / "artifacts" / "Outputs" / "master_leaderboard.csv"
    art_dir = rd / "artifacts" / "Outputs"
    subdirs = []
    if art_dir.exists():
        subdirs = [x.name for x in art_dir.iterdir() if x.is_dir()]
    
    lb_count = 0
    if lb.exists():
        with open(lb, newline='', encoding='utf-8') as f:
            lb_count = sum(1 for _ in csv.DictReader(f))
    
    # Check for family summary
    fam_files = list(rd.rglob("family_summary_results.csv"))
    fam_info = ""
    if fam_files:
        with open(fam_files[0], newline='', encoding='utf-8') as f:
            fam_rows = list(csv.DictReader(f))
        for fr in fam_rows:
            status = fr.get('promotion_status', '')
            stype = fr.get('strategy_type', '')
            promoted = fr.get('promoted_candidates', '0')
            fam_info += f"  {stype}: {status} (promoted={promoted}) "
    
    print(f"  {rd.name}: leaderboard={lb_count}, datasets={subdirs}, families={fam_info}")

# Now analyze the full ultimate leaderboard
print("\n" + "=" * 80)
print("ULTIMATE LEADERBOARD ANALYSIS")
print("=" * 80)

lb_path = repo / "Outputs" / "ultimate_leaderboard.csv"
with open(lb_path, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"\nTotal strategies: {len(rows)}")

# By market
markets = Counter()
for r in rows:
    ds = r.get('dataset', '')
    market = ds.split('_')[0] if ds else 'unknown'
    markets[market] += 1

print("\nStrategies by MARKET:")
for m, c in sorted(markets.items(), key=lambda x: -x[1]):
    print(f"  {m}: {c}")

# By timeframe
timeframes = Counter()
for r in rows:
    ds = r.get('dataset', '')
    parts = ds.split('_')
    tf = parts[1] if len(parts) > 1 else 'unknown'
    timeframes[tf] += 1

print("\nStrategies by TIMEFRAME:")
for tf, c in sorted(timeframes.items(), key=lambda x: -x[1]):
    print(f"  {tf}: {c}")

# By strategy type
stypes = Counter(r.get('strategy_type', '') for r in rows)
print("\nStrategies by FAMILY:")
for st, c in sorted(stypes.items(), key=lambda x: -x[1]):
    print(f"  {st}: {c}")

# By quality flag
flags = Counter(r.get('quality_flag', '') for r in rows)
print("\nStrategies by QUALITY FLAG:")
for fl, c in sorted(flags.items(), key=lambda x: -x[1]):
    print(f"  {fl}: {c}")

# Top 20 by profit factor
print("\n" + "=" * 80)
print("TOP 20 STRATEGIES BY PROFIT FACTOR")
print("=" * 80)

def safe_float(v):
    try: return float(str(v).replace(',','').replace('$',''))
    except: return 0.0

pf_col = 'leader_pf'
rows_sorted = sorted(rows, key=lambda r: -safe_float(r.get(pf_col, '0')))

print(f"{'Rank':<5} {'Market':<8} {'TF':<8} {'Family':<15} {'PF':<8} {'IS_PF':<8} {'OOS_PF':<8} {'12m_PF':<8} {'Trades':<8} {'Quality':<20}")
print("-" * 98)
for i, r in enumerate(rows_sorted[:20], 1):
    ds = r.get('dataset', '')
    parts = ds.split('_')
    market = parts[0] if parts else ''
    tf = parts[1] if len(parts) > 1 else ''
    family = r.get('strategy_type', '')
    pf = safe_float(r.get('leader_pf', '0'))
    is_pf = safe_float(r.get('is_pf', '0'))
    oos_pf = safe_float(r.get('oos_pf', '0'))
    r12m = safe_float(r.get('recent_12m_pf', '0'))
    trades = r.get('leader_trades', '')
    quality = r.get('quality_flag', '')
    print(f"{i:<5} {market:<8} {tf:<8} {family:<15} {pf:<8.2f} {is_pf:<8.2f} {oos_pf:<8.2f} {r12m:<8.2f} {trades:<8} {quality:<20}")

# Check new market data specifically - what happened with AD, BP, JY, EC 60m runs?
print("\n" + "=" * 80)
print("NEW MARKET RUN DETAILS")
print("=" * 80)

for rd in new_runs:
    print(f"\n--- {rd.name} ---")
    
    # Check family_summary
    fam_files = list(rd.rglob("family_summary_results.csv"))
    if fam_files:
        with open(fam_files[0], newline='', encoding='utf-8') as f:
            fam_rows = list(csv.DictReader(f))
        for fr in fam_rows:
            stype = fr.get('strategy_type', '')
            status = fr.get('promotion_status', '')
            promoted = fr.get('promoted_candidates', '0')
            total_combos = fr.get('total_combinations', '')
            best_pf = fr.get('best_combo_profit_factor', '')
            best_quality = fr.get('best_combo_quality_flag', '')
            best_trades = fr.get('best_combo_total_trades', '')
            refined_pf = fr.get('best_refined_profit_factor', '')
            refined_quality = fr.get('best_refined_quality_flag', '')
            accepted = fr.get('accepted_refinement_rows', '0')
            runtime = fr.get('family_runtime_seconds', '')
            print(f"  {stype}: status={status}, combos={total_combos}, promoted={promoted}")
            print(f"    Best combo: PF={best_pf}, trades={best_trades}, quality={best_quality}")
            print(f"    Refined: PF={refined_pf}, quality={refined_quality}, accepted={accepted}")
            if runtime:
                try:
                    mins = float(runtime) / 60
                    print(f"    Runtime: {mins:.1f} min")
                except: pass
    else:
        print("  No family_summary_results.csv found")
    
    # Check leaderboard
    lb_files = list(rd.rglob("family_leaderboard_results.csv"))
    if lb_files:
        with open(lb_files[0], newline='', encoding='utf-8') as f:
            lb_rows = list(csv.DictReader(f))
        for lr in lb_rows:
            stype = lr.get('strategy_type', '')
            accepted = lr.get('accepted_final', '')
            quality = lr.get('quality_flag', '')
            lpf = lr.get('leader_pf', '')
            is_pf = lr.get('is_pf', '')
            oos_pf = lr.get('oos_pf', '')
            trades = lr.get('leader_trades', '')
            print(f"  Leaderboard {stype}: accepted={accepted}, PF={lpf}, IS={is_pf}, OOS={oos_pf}, trades={trades}, quality={quality}")

# Cross-reference: which markets have NO strategies at all?
print("\n" + "=" * 80)
print("MARKET COVERAGE GAPS")
print("=" * 80)
all_markets = set(['ES','CL','NQ','SI','HG','RTY','YM','GC','AD','BP','JY','EC','NG','TY','US','W','BTC'])
found_markets = set()
for r in rows:
    ds = r.get('dataset', '')
    m = ds.split('_')[0] if ds else ''
    found_markets.add(m)
missing = all_markets - found_markets
print(f"Markets WITH strategies: {sorted(found_markets)}")
print(f"Markets WITHOUT strategies: {sorted(missing)}")
print(f"New markets pending (daily/30m/15m still running): AD, BP, JY, EC, NG, TY, US, W, BTC")
