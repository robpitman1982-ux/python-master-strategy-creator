"""Audit module: builds import graph, finds dead code, measures module sizes."""
from __future__ import annotations
import ast, csv, json, os, sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path('/home/rob/python-master-strategy-creator')
AUDIT_DIR = REPO_ROOT / 'docs' / 'audit'
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

def collect_py_files():
    seen = set()
    files = []
    for d in [REPO_ROOT, REPO_ROOT/'modules', REPO_ROOT/'modules'/'strategy_types',
              REPO_ROOT/'scripts', REPO_ROOT/'tests', REPO_ROOT/'cloud']:
        if not d.exists(): continue
        for f in sorted(d.glob('*.py')):
            if f.resolve() not in seen:
                seen.add(f.resolve())
                files.append(f)
    return files

def module_key(path):
    rel = path.resolve().relative_to(REPO_ROOT)
    parts = list(rel.parts)
    if parts[-1] == '__init__.py': parts = parts[:-1]
    else: parts[-1] = parts[-1].replace('.py', '')
    return '.'.join(parts)

def parse_imports(path):
    try:
        tree = ast.parse(path.read_text(errors='replace'))
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names: imports.append(a.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split('.')[0])
    return imports

def count_defs(path):
    try:
        src = path.read_text(errors='replace')
        tree = ast.parse(src)
    except SyntaxError:
        return len(path.read_text(errors='replace').splitlines()), 0, 0
    lines = len(src.splitlines())
    funcs = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    cls = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    return lines, funcs, cls

files = collect_py_files()
print(f'Scanning {len(files)} files...')

key_to_path = {module_key(f): f for f in files}
internal_tops = {k.split('.')[0] for k in key_to_path}

graph = defaultdict(list)
imported_by = defaultdict(set)

for f in files:
    mk = module_key(f)
    for imp in parse_imports(f):
        if imp in internal_tops:
            for tk in key_to_path:
                if tk == imp or tk.startswith(imp + '.'):
                    graph[mk].append(tk)
                    imported_by[tk].add(mk)

entry_points = set()
for k in key_to_path:
    p0 = k.split('.')[0]
    if p0 in ('tests', 'scripts') or p0 not in ('modules',):
        entry_points.add(k)

importable = set(key_to_path) - entry_points
dead = sorted(k for k in importable if not imported_by.get(k))
cloud_only = sorted(k for k in importable if imported_by.get(k) and all('cloud' in i for i in imported_by[k]))

# Write outputs
with open(AUDIT_DIR / '02_module_graph.json', 'w') as f:
    json.dump({k: sorted(set(v)) for k, v in graph.items()}, f, indent=2, sort_keys=True)

with open(AUDIT_DIR / '02_dead_code_candidates.txt', 'w') as f:
    for d in dead: f.write(d + '\n')
    if cloud_only:
        f.write('\n--- Only imported by cloud code ---\n')
        for c in cloud_only: f.write(c + '\n')

with open(AUDIT_DIR / '02_module_sizes.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['module', 'path', 'lines', 'functions', 'classes'])
    for mk in sorted(key_to_path):
        lines, funcs, cls = count_defs(key_to_path[mk])
        w.writerow([mk, str(key_to_path[mk].relative_to(REPO_ROOT)), lines, funcs, cls])

sizes = [(mk, count_defs(key_to_path[mk])[0]) for mk in key_to_path]
sizes.sort(key=lambda x: -x[1])

print(f'Total .py: {len(files)}')
print(f'Dead code candidates: {len(dead)}')
print(f'Cloud-only imported: {len(cloud_only)}')
print('Top 10 by LOC:')
for mk, l in sizes[:10]: print(f'  {l:5d}  {mk}')
print('Dead code:')
for d in dead: print(f'  {d}')
if cloud_only:
    print('Cloud-only:')
    for c in cloud_only: print(f'  {c}')
print('DONE')
