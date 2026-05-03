# Live Portfolio Runner — Spec

> Status: DESIGN ONLY. Nothing here is built yet. This document captures
> what the runner must do so we can implement it cleanly when ready,
> without re-deriving the design from the YAML each time.

## 1. Purpose

Consume a declarative portfolio YAML (e.g.
[configs/live_portfolios/portfolio4_cfd_top.yaml](../configs/live_portfolios/portfolio4_cfd_top.yaml))
and dispatch live MT5 orders against a configured broker account
(The5ers FivePercentOnline-Real, FTMO Demo, or any other MT5 server).

It replaces the current hand-coded MQL5 EA in
[archive/EA/Portfolio3_The5ers.mq5](../archive/EA/Portfolio3_The5ers.mq5),
which is brittle: every portfolio change requires editing MQL5,
recompiling, and redeploying the .ex5 to the Contabo VPS.

The runner is portfolio-agnostic. Swapping portfolios = changing the
YAML it loads. Swapping brokers = changing the symbol mapping field
the runner reads (`the5ers_symbol` vs `ftmo_symbol`).

## 2. Inputs

- **Portfolio YAML** (required): full filter chain, entry/exit/sizing
  per strategy, plus symbol mapping for the active broker.
- **Broker profile** (CLI flag or env var): `the5ers` | `ftmo` —
  selects which symbol field to use and which MT5 login to attach to.
- **MT5 credentials**: login/password/server in `.env` or a
  separate `live_runner_credentials.yaml` (gitignored).
- **State file**: `state/portfolio4_cfd_top__<broker>.json` — last
  bar timestamp processed per (strategy, symbol). Survives restarts so
  we don't double-fire on a bar already actioned.

## 3. Core loop

Daily-frame strategies fire at most once per bar, at broker midnight.
The runner is a long-lived process:

```
on startup:
  load YAML, init MT5 connection, load state file, validate symbols

every minute (or on bar-close trigger):
  for each strategy in YAML:
    fetch latest closed daily bar via mt5.copy_rates_from_pos
    if bar.timestamp <= state[strategy].last_bar: skip
    build feature frame (reuse modules/feature_builder.py)
    instantiate filter chain (reuse modules/filters.py)
    evaluate entry signal at this bar
    if signal:
      compute size from `sizing.micros` and broker contract spec
      submit order with hard stop at entry +/- stop_atr_mult * ATR
      register exit logic (trailing_stop 1.5 ATR or signal_exit)
    update state[strategy].last_bar = bar.timestamp
```

Exits run on every minute tick (not just bar-close) so trailing stops
react intraday — same as the MQL5 EA does today.

## 4. Reusing existing code (zero duplication target)

The whole point of going Python: the backtest engine already has every
component the runner needs. The runner imports them rather than
reimplementing:

| Need                          | Source module                                  |
|-------------------------------|------------------------------------------------|
| Filter classes                | [modules/filters.py](../modules/filters.py)    |
| Feature precompute            | [modules/feature_builder.py](../modules/feature_builder.py) |
| Strategy assembly             | [modules/strategy_types/](../modules/strategy_types/) `build_filter_objects_from_classes` |
| Trade simulation (validation) | [modules/vectorized_trades.py](../modules/vectorized_trades.py) |
| Engine config                 | [modules/engine.py](../modules/engine.py) `EngineConfig` |

If a filter signal differs between backtest and live, it's a parity
bug — and we fix it once in the shared module rather than in two
places.

## 5. MT5 integration

Use the official `MetaTrader5` PyPI package
(https://pypi.org/project/MetaTrader5/). Single Windows-side dependency.

Functions used:
- `mt5.initialize(login, password, server)` — attach to a running MT5
  terminal. Terminal must be installed and logged in once manually.
- `mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, N)` — pull last
  N daily bars for feature computation.
- `mt5.symbol_info(symbol)` — contract size, min lot, tick value, swap.
- `mt5.order_send(request)` — submit market/limit/stop orders with
  attached SL/TP.
- `mt5.positions_get(symbol)` — manage open positions for trailing.
- `mt5.shutdown()` — clean detach on signal.

Magic numbers: one per strategy id, derived deterministically (e.g.
`hash(strategy.id) & 0xFFFFFF`) so positions opened by this runner are
always identifiable and the runner only manages its own.

## 6. Risk envelope enforcement

YAML risk_envelope is informational. The runner enforces:

1. **Daily DD safety margin** (1% in YAML): on every tick compute
   equity vs daily-open equity. If down > 1%, refuse to open new
   positions for the rest of the day. Existing positions still managed.
2. **Per-strategy concurrency**: at most one open position per strategy
   id (no pyramiding for now).
3. **Hard stop** on every entry — non-negotiable, attached at submit
   time. Trailing stop runs on top of it.
4. **Symbol disabled** check: before entry, verify
   `symbol_info(symbol).visible` and trading is allowed; skip if not.

The `expected_p95_dd_pct` field (6.54%) is logged as a sanity threshold
— if realised drawdown exceeds it, an alert fires (see §8) but the
runner does not auto-halt. Operator decides.

## 7. Deployment

Target: Contabo VPS (89.117.72.49), Windows Server, the same machine
currently running the MQL5 EA. Migration path:

1. Install Python 3.12 + `MetaTrader5` package on Contabo.
2. Clone this repo, copy `live_runner_credentials.yaml`.
3. Run as a Windows scheduled task on boot
   (`python -m scripts.live_portfolio_runner --portfolio
   configs/live_portfolios/portfolio4_cfd_top.yaml --broker the5ers`).
4. Once live runner is verified for one full week, remove the MQL5 EA
   from the chart. Both can coexist briefly because each uses its own
   magic number range.

## 8. Observability

- **Log file**: `logs/live_runner_<date>.log` — every signal evaluated,
  every order submitted, every fill, every exit.
- **State file**: written atomically after every bar processed.
- **Heartbeat file**: `state/heartbeat.txt` — touched every loop. A
  cron job on c240 (or the dashboard) can SSH-tail this and alert if
  stale > 5 minutes.
- **Telegram bridge** (optional, later): push order fills + daily DD
  breach warnings to the same Telegram chat used for the betfair bot.

## 9. What this runner does NOT do (out of scope)

- No portfolio re-selection. The YAML is fixed input; selector runs
  offline on c240 and produces new YAMLs by hand.
- No intrabar backtesting / re-validation. We trust the YAML's
  `backtest_metrics` and the offline selector's gating.
- No multi-account orchestration. One YAML + one broker per process.
  Run two processes for two brokers.
- No order-book / slippage modelling. Market orders with attached
  SL/TP, slippage is whatever the broker gives us.

## 10. First milestone

Smallest useful implementation:

1. Parse YAML, validate against strategy_types registry.
2. Connect to MT5, fetch a single daily bar for one symbol.
3. Run the strategy's filter chain on the historical window and confirm
   the resulting signal matches what the backtest produced for the same
   bar.
4. Print "would buy 0.01 lot N225 at <price>, SL <price>" — do not
   submit yet.

Once that prints correctly for all 3 strategies in
`portfolio4_cfd_top.yaml` against the Contabo MT5 terminal, we wire up
`order_send` and let it trade live with 0.01 lot.

## 11. Open questions for next session

- Where does the live runner live in the repo? Probably
  `scripts/live_portfolio_runner.py` + `modules/live_runner/` for
  shared helpers — TBD.
- Do we want to share state with the dashboard (so operator can see
  "next signal evaluation in 03:21")? Probably yes via a small JSON
  status file, same pattern as the sweep dashboard.
- Trailing stop implementation: tick-driven Python loop, or hand off
  the trailing logic to MT5 server-side via `mt5.order_send` with
  `TRAILING_STOP` request? Investigate what the EA does today vs what
  the Python API actually exposes.

---
Last updated: 2026-05-04 (Sprint 95 — design only, nothing built)
