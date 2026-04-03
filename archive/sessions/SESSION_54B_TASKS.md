# SESSION 54B TASKS — CFD Pivot for The5ers Prop Firm
# Date: 2026-04-01
# Priority: HIGH — enables prop firm entry
# Scope: ADDITIVE ONLY — zero changes to existing futures logic
#
# PRINCIPLE: Futures engine is the research layer. CFD is the execution layer.
# All strategy discovery stays on futures data (it's better data anyway).
# CFD translation happens at portfolio selector output time only.
#
# ============================================================
# CONTEXT: Why This Works
# ============================================================
#
# The5ers CFD instruments track the same underlyings as our futures:
#   ES futures → US500 CFD (same S&P 500 index)
#   NQ futures → NAS100 CFD (same Nasdaq 100 index)
#   CL futures → USOIL CFD (same WTI crude)
#   GC futures → XAUUSD CFD (same gold spot)
#   SI futures → XAGUSD CFD (same silver spot)
#   YM futures → US30 CFD (same Dow Jones)
#   RTY futures → US2000 CFD (same Russell 2000)
#   HG futures → COPPER CFD (same copper)
# Price action is identical — a 50-point ES move = 50-point US500 move.
# Our backtested PF, DD, quality flags, correlations all transfer.
# Only transaction costs and position sizing math differ.
#
# ============================================================
# Task 1: Add CFD instrument mapping config
# ============================================================
#
# File: NEW — modules/cfd_mapping.py
#
# Create a mapping dictionary that translates futures symbols to
# CFD equivalents with correct execution parameters:
#
# CFD_INSTRUMENT_MAP = {
#     "ES": {
#         "cfd_symbol": "US500",
#         "cfd_dollars_per_point": 1.0,  # 1 lot US500 = $1/point (check The5ers spec)
#         "cfd_min_lot": 0.01,
#         "cfd_lot_step": 0.01,
#         "cfd_spread_points": 0.4,      # typical spread in points
#         "cfd_commission_per_lot": 0.0,  # spread-only on indices
#         "futures_dollars_per_point": 50.0,  # our backtest reference
#         "micro_to_lot_ratio": 0.1,     # 1 micro ES ≈ 0.1 lot US500 (approximate)
#     },
#     "NQ": {
#         "cfd_symbol": "NAS100",
#         "cfd_dollars_per_point": 1.0,
#         "cfd_min_lot": 0.01,
#         "cfd_lot_step": 0.01,
#         "cfd_spread_points": 1.0,
#         "cfd_commission_per_lot": 0.0,
#         "futures_dollars_per_point": 20.0,
#         "micro_to_lot_ratio": 0.1,
#     },
#     "CL": {
#         "cfd_symbol": "USOIL",
#         "cfd_dollars_per_point": 1.0,
#         "cfd_min_lot": 0.01,
#         "cfd_lot_step": 0.01,
#         "cfd_spread_points": 0.03,
#         "cfd_commission_per_lot": 0.0,
#         "futures_dollars_per_point": 1000.0,
#         "micro_to_lot_ratio": 0.01,
#     },
#     "GC": { "cfd_symbol": "XAUUSD", ... },
#     "SI": { "cfd_symbol": "XAGUSD", ... },
#     "YM": { "cfd_symbol": "US30", ... },
#     "RTY": { "cfd_symbol": "US2000", ... },
#     "HG": { "cfd_symbol": "COPPER", ... },
# }
#
# IMPORTANT: The exact cfd_dollars_per_point and spread values need
# verification against The5ers live MT5 platform. These are estimates.
# The trader (Rob) will verify by opening a demo/eval account and
# checking the actual contract specifications in MT5.
#
# Also add helper functions:
#   def futures_micros_to_cfd_lots(market: str, n_micros: int) -> float:
#       """Convert micro contract count to CFD lot size."""
#
#   def estimate_cfd_spread_cost(market: str, n_lots: float) -> float:
#       """Estimate round-trip spread cost for a CFD trade."""
#
#   def get_cfd_symbol(futures_market: str) -> str:
#       """Map futures symbol to CFD symbol."""
#
# Commit: "feat: add CFD instrument mapping module"

# ============================================================
# Task 2: Add The5ers CFD prop firm configs
# ============================================================
#
# File: modules/prop_firm_simulator.py
#
# Add new factory functions alongside existing ones (DO NOT modify existing):
#
# def The5ersCFDBootcampConfig(target: float = 250_000) -> PropFirmConfig:
#     """The5ers Bootcamp on CFD — 3 steps, 5% DD, 6% target per step."""
#     return PropFirmConfig(
#         firm_name="The5ers",
#         program_name="CFD_Bootcamp",
#         n_steps=3,
#         step_balances=[target * 0.40, target * 0.60, target * 0.80],
#         target_balance=target,
#         profit_target_pct=0.06,
#         max_drawdown_pct=0.05,
#         max_daily_drawdown_pct=None,  # No daily DD for Bootcamp
#         leverage=30.0,
#         entry_fee=225.0,
#         # ... same structure as existing The5ersBootcampConfig
#     )
#
# def The5ersCFDHighStakesConfig(target: float = 100_000) -> PropFirmConfig:
#     """The5ers High Stakes on CFD — 2 steps, 10% DD, 8%+5% targets."""
#     # Same as existing The5ersHighStakesConfig
#
# def The5ersCFDProGrowthConfig(target: float = 20_000) -> PropFirmConfig:
#     """The5ers Pro Growth on CFD — 1 step, 6% DD, 10% target."""
#     # Same as existing The5ersProGrowthConfig
#
# Register in _PROGRAM_FACTORIES in portfolio_selector.py:
#   "cfd_bootcamp": The5ersCFDBootcampConfig,
#   "cfd_high_stakes": The5ersCFDHighStakesConfig,
#   "cfd_pro_growth": The5ersCFDProGrowthConfig,
#
# NOTE: The CFD configs are IDENTICAL to the existing futures configs
# in terms of DD/target rules. The difference is in execution (lot sizing),
# not evaluation rules. So we can actually just reuse the existing configs
# and add "cfd_" prefix aliases. The prop firm rules don't change between
# futures and CFDs — only the execution parameters do.
#
# Commit: "feat: add CFD-specific prop firm config aliases"

# ============================================================
# Task 3: Add CFD execution report to portfolio selector output
# ============================================================
#
# File: modules/portfolio_selector.py (ADD to _write_report, don't modify existing)
#
# After the existing report CSV is written, also write a companion file:
#   Outputs/portfolio_cfd_execution_guide.csv
#
# For each strategy in the top portfolios, include:
#   - futures_market (e.g., "ES")
#   - cfd_symbol (e.g., "US500")
#   - strategy_name
#   - micro_weight (from sizing optimizer, e.g., 0.3 = 3 micros)
#   - cfd_lot_size (converted from micros via cfd_mapping)
#   - strategy_family (e.g., "mean_reversion")
#   - timeframe (e.g., "daily")
#   - direction (e.g., "LONG")
#   - hold_bars
#   - stop_distance_atr
#   - exit_type
#   - estimated_spread_cost_per_trade
#
# This gives Rob a ready-to-implement execution sheet for MT5.
#
# Commit: "feat: add CFD execution guide output to portfolio selector"

# ============================================================
# Task 4: Update config.yaml with CFD program options
# ============================================================
#
# Add to config.yaml portfolio_selector section:
#   portfolio_selector:
#     prop_firm_program: "cfd_bootcamp"  # or "bootcamp" for futures
#     prop_firm_target: 250000
#     execution_mode: "cfd"  # NEW — "futures" or "cfd"
#     # ... rest unchanged
#
# When execution_mode is "cfd", the report writer also generates
# the CFD execution guide. When "futures", it doesn't.
#
# Commit: "feat: add execution_mode config for CFD/futures output"

# ============================================================
# Task 5: Verify The5ers CFD contract specs (MANUAL — Rob)
# ============================================================
#
# This is NOT a code task. Rob needs to:
# 1. Buy cheapest The5ers eval ($39 High Stakes $5K)
# 2. Download MT5, connect to The5ers server
# 3. Open Market Watch, right-click each symbol → Specification
# 4. Record for each of US500, NAS100, USOIL, XAUUSD, XAGUSD,
#    US30, US2000, COPPER:
#    - Contract size (units per 1.0 lot)
#    - Minimum lot / lot step
#    - Typical spread (during US session)
#    - Commission (if any)
#    - Margin requirement per lot
# 5. Update cfd_mapping.py with verified values
#
# This is the ONLY step that requires manual verification.
# Everything else is derived from the verified contract specs.

# ============================================================
# WHAT DOES NOT CHANGE (explicitly preserved)
# ============================================================
#
# - modules/filters.py — ALL filters stay, work on OHLCV regardless of CFD/futures
# - modules/engine.py — Backtest engine stays, runs on futures data always
# - modules/strategies.py — All strategy logic stays
# - modules/strategy_types/* — All families stay
# - modules/refiner.py — Refinement stays
# - All cloud configs — Stay as futures configs
# - All existing prop firm configs — Stay (futures-native)
# - generate_returns.py — Stays (produces returns from futures backtests)
# - Outputs/ultimate_leaderboard_bootcamp.csv — Stays (futures-based)
# - Data/ directory — Stays (TradeStation futures data)
#
# The ONLY new files are:
# - modules/cfd_mapping.py (NEW)
# - Outputs/portfolio_cfd_execution_guide.csv (NEW, generated)
# - Config additions (additive only)
#
# ============================================================
# EXECUTION ORDER
# ============================================================
#
# 1. Wait for Session 54 (filter improvements) to complete
# 2. Wait for cloud sweep results to come back
# 3. Run portfolio selector with best program config
# 4. Execute Tasks 1-4 above (code changes)
# 5. Rob does Task 5 (manual MT5 verification)
# 6. Update cfd_mapping.py with verified values
# 7. Re-run portfolio selector → get CFD execution guide
# 8. Rob builds MT5 EA from execution guide
# 9. Test on demo, then go live on cheapest eval
#
# ============================================================
# FUTURE: When You Trade Your Own Futures Account
# ============================================================
#
# When Rob eventually trades real futures (own account, not prop firm):
# - The engine already produces futures-native output
# - Just use the existing portfolio_selector_report.csv directly
# - micro_multiplier column = exact micro contracts to trade
# - No CFD mapping needed
# - TradeStation or NinjaTrader execution from Python signals
#
# The futures path is ALWAYS available. CFD is an overlay, not a replacement.