# SESSION 57-58 PRE-REVIEW — Critical Issues to Watch For
# ============================================================
# Read this BEFORE executing SESSION_57_TASKS.md or SESSION_58_TASKS.md
# ============================================================

## CRITICAL: Do NOT break existing functionality

1. The existing portfolio_monte_carlo() function with shuffle-interleave MUST be preserved.
   Add block bootstrap as a NEW function, not a replacement.
   Use a config flag to switch between them. Default to block_bootstrap.

2. The existing compute_correlation_matrix() MUST be preserved.
   Add multi-layer correlation as a NEW function alongside it.
   Use a config flag. Default to multi_layer.

3. The existing _compute_dd_overlap() MUST be preserved.
   Add ECD as a NEW function. Use ECD as primary gate, keep dd_overlap as utility.

4. All existing tests must continue to pass.

## Key files that will be modified

- modules/portfolio_selector.py (~1300 lines) — main changes
- modules/prop_firm_simulator.py — daily DD addition
- tests/test_portfolio_selector.py — new tests
- CHANGELOG_DEV.md — documentation

## Testing approach

After each task:
- Run: python -m pytest tests/ -v
- ALL tests must pass (both old and new)
- If a test fails, fix it before moving to next task

## Import conventions

- Use numpy as np, pandas as pd
- Use random.Random(seed) for reproducibility (not np.random)
- Use logging.getLogger(__name__) for all log messages
- Follow existing code style in portfolio_selector.py

