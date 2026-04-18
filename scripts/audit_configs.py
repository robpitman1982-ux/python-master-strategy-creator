"""Audit configs: inventory, schema sniffing, engine param checking, reference grep."""
from __future__ import annotations
import csv, os, subprocess, yaml
from pathlib import Path

REPO = Path('/home/rob/python-master-strategy-creator')
AUDIT = REPO / 'docs' / 'audit'

def load_yaml(p):
    try:
        with open(p) as f:
            return yaml.safe_load(f)
    except Exception as e:
        return {'_error': str(e)}

def grep_refs(filename):
    """Find references to this config filename in repo code."""
    stem = Path(filename).name
    try:
        r = subprocess.run(['grep', '-rl', stem, '--include=*.py', '--include=*.md', '--include=*.yaml', '--include=*.sh', str(REPO)],
                           capture_output=True, text=True, timeout=10)
        refs = [l.replace(str(REPO)+'/', '') for l in r.stdout.strip().split('\n') if l]
        return [r for r in refs if not r.startswith('docs/audit/')]
    except:
        return []

configs = sorted(REPO.glob('configs/**/*.yaml')) + sorted(REPO.glob('configs/**/*.yml')) + sorted(REPO.glob('configs/**/*.json'))
# Also include top-level config.yaml
configs.append(REPO / 'config.yaml')

rows = []
sweep_rows = []

for cp in configs:
    data = load_yaml(cp)
    if isinstance(data, dict):
        top_keys = sorted(data.keys())
    else:
        top_keys = ['_non_dict']
    refs = grep_refs(cp)
    rel = str(cp.relative_to(REPO))
    issues = []

    # Sweep config checks
    if 'datasets' in (data if isinstance(data, dict) else {}):
        dsets = data.get('datasets', [])
        eng = data.get('engine', {})
        dpp = eng.get('dollars_per_point', 'N/A')
        tv = eng.get('tick_value', 'N/A')
        market = data.get('market', rel.split('/')[-1].split('_')[0])
        for ds in (dsets if isinstance(dsets, list) else []):
            dp = ds.get('path', 'N/A')
            dp_full = Path(dp) if Path(dp).is_absolute() else REPO / dp
            exists = dp_full.exists()
            # Bug heuristic: CFD data path + futures engine params
            is_cfd_path = 'cfd' in str(dp).lower() or 'dukascopy' in str(dp).lower()
            is_futures_params = dpp in (50.0, 20.0, 1000.0, 5000.0, 25000.0, 100.0, 5.0) and not is_cfd_path is False
            bug = ''
            if is_cfd_path and dpp == 50.0 and 'ES' in rel:
                bug = 'CFD data with futures engine params (50x P&L inflation)'
            sweep_rows.append({
                'config': rel, 'market': market, 'dollars_per_point': dpp,
                'tick_value': tv, 'data_path': dp, 'data_exists': exists, 'suspected_bug': bug
            })

    rows.append({
        'path': rel, 'top_keys': '|'.join(str(k) for k in top_keys[:8]),
        'referenced_by': '|'.join(refs[:5]), 'issues': '; '.join(issues) if issues else ''
    })

# Write config inventory
with open(AUDIT / '03_config_inventory.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['path','top_keys','referenced_by','issues'])
    w.writeheader()
    for r in rows: w.writerow(r)

# Write sweep engine params
with open(AUDIT / '03_sweep_config_engine_params.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['config','market','dollars_per_point','tick_value','data_path','data_exists','suspected_bug'])
    w.writeheader()
    for r in sweep_rows: w.writerow(r)

print(f'Total configs: {len(configs)}')
print(f'Sweep configs with datasets: {len(sweep_rows)}')
for r in sweep_rows:
    if r['suspected_bug']:
        print(f'  BUG: {r["config"]} - {r["suspected_bug"]}')
print('DONE')
