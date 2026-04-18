# Session 68 — Pipeline Review: First Clean CFD Sweep

**Purpose:** Before running the first local cluster sweep, lock down the data/config/naming architecture so discovery sweeps produce correct P&L, match what trades on The5ers, and scale cleanly to 24 markets.

**Author:** Claude (architecture planning) → Claude Code (execution)
**Scope of Session 68:** ES daily, c240 only, end-to-end validation. No workers, no multi-market.

---

## 1. The three-naming problem

| Role | ES example | Source | Used where |
|---|---|---|---|
| Futures ticker | `ES` | Engine + leaderboards | All existing code |
| The5ers CFD symbol | `SP500` | MT5 execution | `modules/cfd_mapping.py`, live EA |
| Dukascopy filename stem | `USA_500_Index` | TDS export | `/data/market_data/cfds/ohlc/*.csv` |

**Decision:** **Futures ticker (`ES`, `NQ`, `YM`, `GC`, `SI`, `CL`, ...) is the canonical project identifier.** All sweep configs, leaderboards, strategy IDs, and portfolio outputs use it. The other two names exist only at the boundaries (data loading; live trade execution) and are mapped inside `modules/cfd_mapping.py` and a new `modules/dukascopy_filename_map.py`.

---

## 2. Data source decision for discovery

The repo currently has TWO fully-populated sources:

- `/data/market_data/futures/` — TradeStation futures OHLC (2008–2026, all majors, 5 TFs)
- `/data/market_data/cfds/ohlc/` — Dukascopy raw CFD OHLC (2012+, 24 symbols, 5 TFs, native filenames)

**Session 63 architectural decision stands: Dukascopy CFD for discovery, The5ers ticks for execution validation.** Rationale:
- Strategies traded on The5ers will execute against CFD spreads/swaps, not futures cost structure
- Dukascopy CFD price series are the closest high-quality proxy for what actually fills on The5ers MT5
- Futures backtests transfer *direction* but not *cost economics* — funding-timeline estimates need CFD costs

### Sweep scope — ALL 24 CFD markets (firm-agnostic)
Discovery sweeps run on the full 24-market Dukascopy CFD universe regardless of which prop firm we eventually deploy to. Per-firm `excluded_markets` filtering happens in the portfolio selector, NOT at sweep time. Rationale:
- One strategy leaderboard serves all firm targets (The5ers, FTMO, Darwinex Zero, FundedNext)
- Compute is reused across firms, not duplicated
- When a new firm is added to scope, no new sweep is needed — only a new portfolio-selector config

**Session 70 validates the pipeline on ES daily specifically because it's the only file converted to engine format so far.** Session 71 scales to the remaining 92 market/TF combinations. Once the full universe is populated, portfolio selection produces one set of candidates per firm.

**However:** only ONE Dukascopy file has been converted to the engine's expected schema so far (`ES_daily_2012_2026_dukascopy.csv`). The rest (23 symbols × 4 TFs = 92 conversions) are pending. Session 68 proves the pipeline on that one file; Session 69+ scales.

**Fallback rule:** If Dukascopy data is missing for a market, the sweep is skipped — we do **not** silently fall back to TradeStation futures data, because the engine params differ and that would corrupt the leaderboard.

---

## 3. Engine parameters — CFD ≠ futures (critical)

The engine's `dollars_per_point` and `tick_value` **must match the data's price series**. Running futures params against CFD data (or vice versa) silently produces P&L off by 10–100×.

### Correct CFD params per market (source: `modules/cfd_mapping.py`)

| Market | `dollars_per_point` (CFD) | `tick_value` | Notes |
|---|---|---|---|
| ES (SP500) | **1.0** | 0.01 | was 50.0 for futures |
| NQ (NAS100) | **1.0** | 0.01 | was 20.0 |
| YM (US30) | **1.0** | 0.01 | was 5.0 |
| GC (XAUUSD) | **100.0** | 0.01 | same magnitude as futures |
| SI (XAGUSD) | **5000.0** | 0.001 | 1 lot = 5000 oz |
| CL (XTIUSD) | needs verification | TBD | The5ers may not offer |

### Also critical for CFDs
- `commission_per_contract`: 0 for indices, 0.001% for metals — from `cfd_mapping.py`
- `slippage_ticks`: indices have floating spread, typically 0.4–1.0 pt on SP500 during RTH. Use **conservative 1.0** for now.
- Swap costs (`cfd_swap_long`, `cfd_swap_short`): NOT YET modeled in MC simulator (known gap #9 in HANDOVER). Will be session 69+.

### Decision for Session 68
The `ES_daily_cfd_v1.yaml` config currently has **futures** engine params (`dollars_per_point: 50.0`). This is a bug, not a feature. Task 3 rewrites it with CFD params.

---

## 4. Canonical data layout (going forward)

```
/data/market_data/
├── futures/                          # TradeStation CSVs (reference, not default)
│   └── {SYM}_{TF}_2008_2026_tradestation.csv
└── cfds/
    ├── ohlc/                         # Raw Dukascopy exports (TDS native names)
    │   └── {LongName}_GMT+0_NO-DST_{TF_CODE}.csv
    ├── ohlc_engine/                  # NEW — converted, engine-ready (canonical sweep input)
    │   └── {SYM}_{TF}_dukascopy.csv        e.g. ES_daily_dukascopy.csv
    ├── ticks_dukascopy_tds/          # Raw .bfc tick cache (for re-export only)
    ├── ticks_dukascopy_raw/          # Future: dukascopy-python parquet
    └── ticks_mt5_the5ers/            # Future: The5ers tick exports
```

**Rule:** Sweep configs reference data files by **basename only**. The runner's `--data-dir` flag supplies the absolute dir. This keeps configs portable between workers.

**Session 68 target dir:** `/data/market_data/cfds/ohlc_engine/`

**Session 68 required file:** `/data/market_data/cfds/ohlc_engine/ES_daily_dukascopy.csv` (copied/renamed from existing `~/python-master-strategy-creator/Data/ES_daily_2012_2026_dukascopy.csv`)

---

## 5. Sweep config template (canonical)

```yaml
# configs/local_sweeps/ES_daily.yaml
sweep:
  name: "es_daily_dukascopy_v1"
  output_dir: "Outputs"

datasets:
  - path: "ES_daily_dukascopy.csv"   # basename only — --data-dir prepended at runtime
    market: "ES"
    timeframe: "daily"

strategy_types: "all"

engine:
  initial_capital: 250000.0          # sweep-sim capital, NOT live account size
  risk_per_trade: 0.01
  commission_per_contract: 0         # indices on The5ers: 0
  slippage_ticks: 1                  # conservative SP500 spread ~1pt
  tick_value: 0.01                   # CFD SP500 min tick
  dollars_per_point: 1.0             # CFD SP500 1 lot = $1/pt  (NOT 50 — that's futures ES)
  use_vectorized_trades: true

pipeline:
  max_workers_sweep: 36              # c240 has 80 threads; 36 leaves headroom
  max_workers_refinement: 36
  max_candidates_to_refine: 5
  oos_split_date: "2020-01-01"
  skip_portfolio_evaluation: true
  skip_portfolio_selector: true

promotion_gate:
  min_profit_factor: 1.00
  min_average_trade: 0.00
  require_positive_net_pnl: false
  min_trades: 50
  min_trades_per_year: 3.0
  max_promoted_candidates: 20

leaderboard:
  min_net_pnl: 0.0
  min_pf: 1.00
  min_oos_pf: 1.00
  min_total_trades: 60
```

**Invocation:**
```bash
python run_local_sweep.py \
  --config configs/local_sweeps/ES_daily.yaml \
  --data-dir /data/market_data/cfds/ohlc_engine/
```

---

## 6. What does NOT change in Session 68

- Engine code (`modules/master_strategy_engine.py`, vectorized trade loop, filters, strategy families)
- Portfolio selector
- CFD mapping module (`modules/cfd_mapping.py`) — already correct
- Existing leaderboards (454-strategy futures leaderboard stays archived, untouched)
- Worker servers (gen8, r630) — stay asleep, joined in Session 69
- Cloud decommission — deferred

## 7. Known gaps acknowledged but deferred

1. **Swap costs not in MC simulator** (HANDOVER issue #9). First CFD sweep will produce strategies; MC pass rates against The5ers will be optimistic until swaps land. Don't deploy anything live off Session 68 output.
2. **Only ES daily Dukascopy data converted.** 23 more markets × 4 TFs pending TDS export + conversion. Scale plan is Session 69+.
3. **Dashboard Live Monitor broken** — not touched this session.
4. **Session 61 test failure** — not touched.

---

## 8. Success criteria for Session 68

The sweep is "working" when ALL of the following are true:

1. ✅ `python run_cluster_sweep.py --markets ES --timeframes daily --dry-run` plans 1 job and exits clean
2. ✅ `python run_local_sweep.py --config configs/local_sweeps/ES_daily.yaml --data-dir /data/market_data/cfds/ohlc_engine/` runs to completion without Python exceptions
3. ✅ Wall time < 30 minutes on c240 (80 threads, daily TF)
4. ✅ `Outputs/es_daily_dukascopy_v1/` contains `leaderboard.csv` with > 0 rows
5. ✅ Sampled strategy has plausible P&L — check one strategy manually: `net_pnl`, `profit_factor`, `total_trades` in sensible ranges (NOT 50× inflated like the bug would produce)
6. ✅ No orphan child processes on c240 after completion
7. ✅ HANDOVER.md updated, one commit per task, pushed to GitHub

If any of 1–6 fail, stop and leave diagnostic output for next session. Don't force-fix.

---

## 9. References

- `HANDOVER.md` — live ops state (as of Session 67)
- `modules/cfd_mapping.py` — verified CFD symbol + cost mapping
- `scripts/convert_tds_to_engine.py` — TDS → engine format converter
- `configs/cfd_markets.yaml` — 24-market master config (used by sweep config generator)
- Session 63 memory — Dukascopy architectural decision
- Session 65 memory — CFD pipeline built
