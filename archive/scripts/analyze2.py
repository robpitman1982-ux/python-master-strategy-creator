import csv
from pathlib import Path
from collections import Counter

repo = Path(r"C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator")

def safe_float(v):
    try: return float(str(v).replace(',','').replace('$',''))
    except: return 0.0

# Read ultimate leaderboard
lb_path = repo / "Outputs" / "ultimate_leaderboard.csv"
with open(lb_path, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"TOTAL STRATEGIES: {len(rows)}")
print()

# Bootcamp
boot_path = repo / "Outputs" / "ultimate_leaderboard_bootcamp.csv"
with open(boot_path, newline='', encoding='utf-8') as f:
    boot_rows = list(csv.DictReader(f))
print(f"BOOTCAMP ACCEPTED: {len(boot_rows)}")
print()

# By market
markets = Counter()
for r in rows:
    ds = r.get('dataset', '')
    market = ds.split('_')[0] if ds else 'unknown'
    markets[market] += 1
print("BY MARKET:")
for m, c in sorted(markets.items(), key=lambda x: -x[1]):
    print(f"  {m}: {c}")
