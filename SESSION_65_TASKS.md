# SESSION_65_TASKS.md — CFD Data Pipeline + Local Sweep Infrastructure

## Context
We are transitioning from:
- **TradeStation futures data** → **Dukascopy CFD tick data (via Tick Data Suite)**
- **GCP cloud sweeps** → **Local compute cluster sweeps (Gen 9 / Gen 8 / R630)**
- Cloud services (GCP, DigitalOcean) will be decommissioned once local sweeps are proven

## TDS Export Format (Metatrader CSV)
```
Date,Time,Open,High,Low,Close,Tick volume
2012.01.16,00:00:00,1290.9,1296.9,1285.9,1295.6,4453
2026.04.15,23:55:00,7031.442,7032.099,7031.036,7031.399,49
```

## TradeStation Format (what engine expects)
```
"Date","Time","Open","High","Low","Close","Vol","OI"
12/31/2007,16:00,1997.50,2001.25,1983.25,1989.50,671363,1720070
```
Daily has Vol+OI columns. Intraday has Up+Down columns instead.

## TDS Symbol → Engine Market Mapping
```
USA_500_Index     → ES    (SP500)
USA_100_Technical → NQ    (NAS100)
USA_30_Index      → YM    (US30)
XAUUSD            → GC    (Gold)
XAGUSD            → SI    (Silver)
US_Light_Crude    → CL    (WTI Crude)
EURUSD            → EC    (Euro FX)
USDJPY            → JY    (Japanese Yen)
GBPUSD            → BP    (British Pound)
AUDUSD            → AD    (Australian Dollar)
High_Grade_Copper → HG    (Copper)
Natural_Gas       → NG    (Natural Gas)
Bitcoin_USD       → BTC   (Bitcoin)
US_Small_Cap_2000 → RTY   (Russell 2000)
Germany_40_Index  → DAX   (DAX)
Japan_225         → N225  (Nikkei)
UK_100_Index      → FTSE  (FTSE 100)
Europe_50_Index   → STOXX (Euro Stoxx 50)
France_40_Index   → CAC   (CAC 40)
USDCAD            → USDCAD
USDCHF            → USDCHF
NZDUSD            → NZDUSD
US_Brent_Crude    → BRENT
Ether_USD         → ETH
```

## File Locations
- TDS exports land at: `C:\Users\Rob\Downloads\Tick Data Suite\Dukascopy\` (Latitude)
- Engine repo: `C:\Users\Rob\Documents\GIT Repos\python-master-strategy-creator\` (Latitude)
- Gen 9 repo: `~/python-master-strategy-creator/` 
- Gen 9 data: `/data/market_data/` (TradeStation CSVs here)
- Gen 9 new data target: `/data/market_data/dukascopy/` (converted CSVs go here)
- Z: drive mapped to `\\192.168.68.69\data`

---

## TASK 1: Format Adapter Script
**File:** `scripts/convert_tds_to_engine.py`

Write a Python script that converts TDS Metatrader CSVs to TradeStation format.

### Input format:
```
Date,Time,Open,High,Low,Close,Tick volume
2012.01.16,00:00:00,1290.9,1296.9,1285.9,1295.6,4453
```

### Output format (must match exactly):
```
"Date","Time","Open","High","Low","Close","Vol","OI"
01/16/2012,00:00,1290.9,1296.9,1285.9,1295.6,4453,0
```

### Requirements:
- Date: `YYYY.MM.DD` → `MM/DD/YYYY`
- Time: `HH:MM:SS` → `HH:MM` (strip seconds)
- Headers: must be quoted, add "OI" column with 0
- Volume: "Tick volume" → "Vol"
- Accept input dir + output dir as args
- Auto-detect market name from filename (extract between first `_` and `_GMT`)
- Auto-detect timeframe from filename suffix (`_D1.csv` → `daily`, `_H1.csv` → `60m`, `_M30.csv` → `30m`, `_M15.csv` → `15m`, `_M5.csv` → `5m`)
- Output filename: `{MARKET}_{timeframe}_{start_year}_{end_year}_dukascopy.csv`
  Example: `ES_15m_2012_2026_dukascopy.csv`
- Use the symbol mapping table above
- Process all CSV files in input dir in one run
- Print summary: files converted, rows per file, date range per file
- Handle edge cases: empty files, missing data, duplicate timestamps

### Verification:
After conversion, load both the original TDS file and converted file, verify:
- Row counts match
- Date range matches
- OHLC values unchanged
- First and last rows printed for visual check

---

## TASK 2: Engine Data Loader Update
**File:** `modules/config_loader.py` and/or `master_strategy_engine.py`

The engine currently loads data via `load_tradestation_csv()`. This function needs to handle the converted Dukascopy files seamlessly. 

### Check:
- Read the existing `load_tradestation_csv()` function
- Verify the converted format from Task 1 is compatible
- If needed, add a `load_dukascopy_csv()` alternative or make the loader auto-detect
- The converted files should work WITHOUT any loader changes if Task 1 output matches exactly

### Key concern:
- TradeStation intraday files use "Up","Down" columns instead of "Vol","OI"
- Check which columns the engine actually reads/uses
- Make sure converted files don't break because of column naming

---

## TASK 3: CFD Market Configuration
**File:** `configs/cfd_markets.yaml`

Create a master config for all 24 CFD markets with engine parameters.

### Per-market config needed:
```yaml
ES:
  source: dukascopy
  tds_symbol: "USA_500_Index"
  data_files:
    5m: "ES_5m_2012_2026_dukascopy.csv"
    15m: "ES_15m_2012_2026_dukascopy.csv"
    30m: "ES_30m_2012_2026_dukascopy.csv"
    60m: "ES_60m_2012_2026_dukascopy.csv"
    daily: "ES_daily_2012_2026_dukascopy.csv"
  engine:
    tick_value: 12.50          # ES futures tick value
    dollars_per_point: 50.0    # $50 per index point
    commission_per_contract: 0  # CFD has no commission, cost is in spread
    slippage_ticks: 0          # Spread handled in cost layer, not engine
  cost_profile:
    spread_pts: 0.50           # Typical SP500 CFD spread
    swap_per_micro_per_night: 0.10
    weekend_multiplier: 3
  oos_split_date: "2020-01-01"  # More recent OOS for CFD (shorter history)
```

### Important decisions:
- `slippage_ticks: 0` and `commission: 0` for CFD sweeps — costs applied in portfolio selector
- `oos_split_date`: Use 2020-01-01 for indices (2012 start) and 2016-01-01 for FX/metals (2008 start)
  This gives ~60% IS / ~40% OOS
- `dollars_per_point`: Must be correct per market (50 for ES, 20 for NQ, 5 for YM, etc.)
  Research and set correctly for each of the 24 markets

---

## TASK 4: Local Sweep Runner
**File:** `run_local_sweep.py`

Create a sweep runner designed for the local cluster (replaces cloud runner).

### Requirements:
- Reads a sweep config YAML (similar to existing cloud configs but simpler)
- Sets PYTHONPATH and runs the engine directly (no Docker, no GCS, no VM provisioning)
- Uses `max_workers` from config to control parallelism
- Supports running a subset of markets/timeframes
- Saves output to `/data/sweep_results/runs/{run_name}/`
- After sweep: auto-updates leaderboard at `/data/leaderboards/`
- Prints progress, ETA, and results summary

### Example config: `configs/sweep_local_es_daily.yaml`
```yaml
sweep:
  name: "es_daily_cfd_v1"
  data_dir: "/data/market_data/dukascopy/"
  output_dir: "/data/sweep_results/runs/"
  
datasets:
  - market: ES
    timeframe: daily
    
strategy_types: "all"  # or list: [mean_reversion, trend, breakout]

engine:
  initial_capital: 250000.0
  risk_per_trade: 0.01
  commission_per_contract: 0
  slippage_ticks: 0
  use_vectorized_trades: true

pipeline:
  max_workers_sweep: 36      # Half of Gen 9's 80 threads (leave headroom)
  max_workers_refinement: 36
  max_candidates_to_refine: 5
  oos_split_date: "2020-01-01"
  skip_portfolio_evaluation: true
  skip_portfolio_selector: true
```

---

## TASK 5: Batch Sweep Launcher
**File:** `run_cluster_sweep.py`

Orchestrates sweeps across all markets/timeframes on the local cluster.

### Requirements:
- Takes a list of markets + timeframes to sweep
- Generates individual sweep configs from template
- Runs them sequentially (or parallel if on different machines)
- Tracks which market/timeframe combos are done
- Writes a manifest: `sweep_manifest.json` with status per combo
- Supports resume (skip completed combos)
- After all sweeps: runs leaderboard aggregator

### Usage:
```bash
# Sweep all priority markets, all timeframes
python run_cluster_sweep.py --markets ES NQ YM GC --timeframes 5m 15m 30m 60m daily

# Sweep single market for testing
python run_cluster_sweep.py --markets ES --timeframes daily

# Resume interrupted sweep
python run_cluster_sweep.py --resume
```

---

## TASK 6: Remove Cloud Dependencies
**Files:** Multiple

### Do NOT delete cloud files yet — just ensure local sweep path works independently.
- Verify `run_local_sweep.py` does NOT import anything from `cloud/`
- Verify `run_cluster_sweep.py` does NOT reference GCS, GCP, SPOT, or DigitalOcean
- Add a note to `HANDOVER.md` that cloud files are deprecated pending deletion
- Do NOT modify `run_spot_resilient.py`, `launch_gcp_run.py`, `run_cloud_sweep.py` etc. — leave them for manual deletion later

---

## TASK 7: Sweep Config Generator
**File:** `scripts/generate_sweep_configs.py`

Generates all sweep config YAMLs for the 24-market × 5-timeframe matrix.

### Requirements:
- Reads `configs/cfd_markets.yaml` for market parameters
- Generates one config per market (all timeframes in one config)
- Output: `configs/local_sweeps/{market}_all_timeframes.yaml`
- Total: 24 config files

---

## TASK 8: Tests
**File:** `tests/test_data_converter.py`

### Tests for the format adapter:
1. Date conversion: `2012.01.16` → `01/16/2012`
2. Time conversion: `00:00:00` → `00:00`
3. Header format matches TradeStation exactly
4. Empty/missing volume handled
5. Round-trip: convert and load with existing engine loader
6. Symbol name extraction from filename
7. Timeframe detection from filename

---

## TASK 9: Update HANDOVER.md
Update relevant sections:
- Add Dukascopy/TDS data pipeline details
- Update strategy engine status (CFD sweep infrastructure)
- Mark cloud services as deprecated
- Add new file locations for CFD data
- Update "On the horizon" checklist
- Add C240 static IP fix (192.168.68.79)
- Note Gen 9 CPU upgrade (pending physical install)
- Note laptop sleep fix (Modern Standby disabled)

---

## Execution Order
1. Task 1 (format adapter) — foundation, everything depends on this
2. Task 8 (tests for adapter) — verify before proceeding
3. Task 2 (engine loader check) — may need no changes
4. Task 3 (market configs) — needed by sweep runner
5. Task 4 (local sweep runner) — core new functionality
6. Task 7 (config generator) — convenience, generates all configs
7. Task 5 (batch launcher) — orchestration layer
8. Task 6 (cloud cleanup notes)
9. Task 9 (handover update)

## Commit Pattern
One commit per task: `git add . ; git commit -m "session 65: task N - description" ; git push`
