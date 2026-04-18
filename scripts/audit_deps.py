"""Audit dependencies: compare requirements.txt vs actual imports."""
from __future__ import annotations
import ast, csv, re
from pathlib import Path

REPO = Path('/home/rob/python-master-strategy-creator')
AUDIT = REPO / 'docs' / 'audit'

# Common import-name to package-name mapping
IMPORT_TO_PKG = {
    'yaml': 'pyyaml', 'PIL': 'pillow', 'cv2': 'opencv-python',
    'sklearn': 'scikit-learn', 'bs4': 'beautifulsoup4',
    'dateutil': 'python-dateutil', 'attr': 'attrs',
}

STDLIB = {
    'abc','argparse','ast','atexit','base64','bisect','builtins','calendar',
    'cmath','codecs','collections','concurrent','configparser','contextlib',
    'copy','csv','ctypes','dataclasses','datetime','decimal','difflib',
    'email','enum','errno','faulthandler','fileinput','fnmatch','fractions',
    'functools','gc','getpass','gettext','glob','gzip','hashlib','heapq',
    'html','http','importlib','inspect','io','itertools','json','keyword',
    'linecache','locale','logging','lzma','math','mimetypes','multiprocessing',
    'numbers','operator','os','pathlib','pickle','platform','pprint',
    'profile','queue','random','re','readline','secrets','select',
    'shelve','shlex','shutil','signal','site','socket','sqlite3',
    'ssl','stat','statistics','string','struct','subprocess','sys',
    'sysconfig','tempfile','textwrap','threading','time','timeit',
    'tkinter','token','tokenize','tomllib','traceback','tracemalloc',
    'turtle','types','typing','unicodedata','unittest','urllib',
    'uuid','venv','warnings','wave','weakref','webbrowser','xml',
    'xmlrpc','zipfile','zipimport','zlib','_thread','posixpath','ntpath',
    'distutils','imp','pipes','resource','grp','pwd','fcntl','termios',
}

def parse_requirements(path):
    pkgs = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'([a-zA-Z0-9_-]+)', line)
        if m:
            pkgs[m.group(1).lower()] = line
    return pkgs

def collect_imports():
    imports = set()
    for f in REPO.rglob('*.py'):
        if 'venv' in f.parts or '.git' in f.parts or '__pycache__' in f.parts:
            continue
        try:
            tree = ast.parse(f.read_text(errors='replace'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        imports.add(a.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split('.')[0])
        except SyntaxError:
            pass
    return imports

reqs = parse_requirements(REPO / 'requirements.txt')
imports = collect_imports()

# Filter to external imports
ext_imports = {i for i in imports if i not in STDLIB and not (REPO / i).exists() and not (REPO / (i + '.py')).exists() and not (REPO / i / '__init__.py').exists()}

# Map imports to package names
import_pkg_map = {}
for imp in ext_imports:
    pkg = IMPORT_TO_PKG.get(imp, imp).lower()
    import_pkg_map[imp] = pkg

declared = set(reqs.keys())
used_pkgs = set(import_pkg_map.values())

missing = used_pkgs - declared - {'modules', 'cloud', 'tests', 'scripts', 'paths', 'config', 'dashboard', 'dashboard_utils', 'generate_returns', 'master_strategy_engine', 'run_local_sweep', 'run_cluster_sweep', 'run_evaluator', 'run_high_stakes', 'run_portfolio_all_programs', 'run_cloud_job', 'run_cloud_parallel', 'run_cloud_sweep', 'run_spot_resilient', 'archive'}
unused = declared - used_pkgs

print(f'Declared packages: {len(declared)}')
print(f'External imports found: {len(ext_imports)}')
print(f'Missing from requirements: {sorted(missing)}')
print(f'In requirements but not imported: {sorted(unused)}')
print('DONE')
