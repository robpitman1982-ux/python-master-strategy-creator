import pandas as pd
import os
import sys

lb_path = sys.argv[1] if len(sys.argv) > 1 else 'Outputs/ultimate_leaderboard_bootcamp.csv'
df = pd.read_csv(lb_path)
df = df[df['bootcamp_score'].astype(float) >= 40]
df = df[df['oos_pf'].astype(float) >= 1.0]
print(f'Candidates passing filter (BC>=40, OOS_PF>=1.0): {len(df)}')

missing = []
found = []
for _, row in df.iterrows():
    run_id = str(row['run_id'])
    dataset = str(row['dataset'])
    parts = dataset.replace('_tradestation.csv','').split('_')
    folder = parts[0] + '_' + parts[1] if len(parts) >= 2 else dataset.replace('.csv','')
    market = str(row['market'])
    tf = folder.split('_')[1]
    stype = str(row['strategy_type'])
    bc = float(row['bootcamp_score'])
    
    p1 = os.path.join('Outputs','runs', run_id, 'Outputs', folder, 'strategy_returns.csv')
    p2 = os.path.join('Outputs','runs', run_id, 'artifacts', 'Outputs', folder, 'strategy_returns.csv')
    
    label = f'{market}_{tf:>5s} {stype:35s} BC={bc:>6.1f} run={run_id[-18:]}'
    if os.path.exists(p1) or os.path.exists(p2):
        found.append(label)
    else:
        missing.append(label)

print(f'\nFound returns: {len(found)}')
print(f'Missing returns: {len(missing)}')
print(f'\n=== MISSING STRATEGIES ===')
for m in sorted(missing):
    print(f'  {m}')

print(f'\n=== RUNS WITH MISSING RETURNS ===')
missing_runs = set()
for _, row in df.iterrows():
    run_id = str(row['run_id'])
    dataset = str(row['dataset'])
    parts = dataset.replace('_tradestation.csv','').split('_')
    folder = parts[0] + '_' + parts[1] if len(parts) >= 2 else dataset.replace('.csv','')
    p1 = os.path.join('Outputs','runs', run_id, 'Outputs', folder, 'strategy_returns.csv')
    p2 = os.path.join('Outputs','runs', run_id, 'artifacts', 'Outputs', folder, 'strategy_returns.csv')
    if not os.path.exists(p1) and not os.path.exists(p2):
        missing_runs.add(run_id)
for r in sorted(missing_runs):
    print(f'  {r}')
