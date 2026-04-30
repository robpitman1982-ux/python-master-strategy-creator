# Instrument Universes

**Purpose:** keep futures discovery, CFD discovery, and The5ers evaluation from
silently sharing the wrong contract economics.

The strategy engine is generic. It does not know whether a price series is a
futures contract or a CFD unless the config tells it. The runner preflight now
requires that every sweep config resolve to exactly one universe before any data
is loaded.

---

## Universes

### `futures_tradestation`

Use for TradeStation futures OHLC files.

Expected examples:

| Market | Data stem | Dollars/point | Tick value |
|--------|-----------|---------------|------------|
| ES | `ES_*_tradestation.csv` | 50.0 | 12.50 |
| NQ | `NQ_*_tradestation.csv` | 20.0 | 5.00 |
| YM | `YM_*_tradestation.csv` | 5.0 | 5.00 |
| GC | `GC_*_tradestation.csv` | 100.0 | 10.00 |
| SI | `SI_*_tradestation.csv` | 5000.0 | 25.00 |
| CL | `CL_*_tradestation.csv` | 1000.0 | 10.00 |

### `cfd_dukascopy`

Use for converted Dukascopy CFD OHLC files.

Expected examples verified for The5ers-mapped symbols:

| Market | Data stem | Dollars/point | Tick value |
|--------|-----------|---------------|------------|
| ES | `ES_*_dukascopy.csv` | 1.0 | 0.01 |
| NQ | `NQ_*_dukascopy.csv` | 1.0 | 0.01 |
| YM | `YM_*_dukascopy.csv` | 1.0 | 0.01 |
| GC | `GC_*_dukascopy.csv` | 100.0 | 1.00 |
| SI | `SI_*_dukascopy.csv` | 5000.0 | 5.00 |
| CL | `CL_*_dukascopy.csv` | 100.0 | 1.00 |

Canonical converted CFD filenames are:

```text
{MARKET}_{TIMEFRAME}_dukascopy.csv
```

Examples: `ES_daily_dukascopy.csv`, `NQ_60m_dukascopy.csv`.

---

## Evaluation Layer

The5ers is **not** a sweep universe. It is a portfolio evaluation and execution
layer applied after CFD-native strategies exist.

Correct flow:

```text
TradeStation futures data -> futures_tradestation sweep -> futures leaderboard
Dukascopy CFD data -> cfd_dukascopy sweep -> CFD leaderboard
CFD leaderboard -> The5ers program rules + MT5 specs -> portfolio MC
```

Do not use The5ers program rules to fix a contaminated sweep. If CFD sweep
economics were wrong, regenerate the trade lists from a correct CFD config.

---

## Guard Rails

`modules/instrument_universe.py` enforces:

- Every sweep config must resolve to `futures_tradestation` or `cfd_dukascopy`.
- Dataset paths may not disagree with the declared universe.
- Known instruments must match their universe-specific `dollars_per_point` and
  `tick_value`.
- CFD Dukascopy dataset basenames must use the canonical no-year format.
- `run_local_sweep.py`, `run_cluster_sweep.py`, and direct
  `master_strategy_engine.py --config ...` execution all run this preflight.

