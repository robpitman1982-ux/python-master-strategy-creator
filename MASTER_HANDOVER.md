Last updated: 2026-05-05 (Session 97 close: 3 rebuild parity bugs fixed; 10-market overnight 5m sweep launched; SHM feature design doc saved)
Current status: **Session 97 wrap (2026-05-04 -> 2026-05-05). Started from a NQ 5m family-split distributed-run validation that surfaced 3 PARITY_FAILED on gen8 short strategies. Hunted three independent rebuild bugs to root cause, fixed all three with regression tests, validated end-to-end on real NQ 5m data (15/15 strategies bit-exact OK), then launched a 10-market overnight 5m sweep across all 3 cluster hosts. Bug #1 (commit `f4424ce`): `_rebuild_strategy_from_leaderboard_row()` constructed EngineConfig without `direction=`, defaulting "long" — ShortMR/ShortTrend/ShortBreakout traded the wrong way on rebuild, opposite-sign PnL. Fix: pull `direction = strategy_type.get_engine_direction()` and pass to EngineConfig. Bug #2 (commit `235f993`): rebuild always called `engine.run()` (Python loop, long-only signal_exit at engine.py:223) regardless of `cfg.use_vectorized_trades`. Short signal_exit silently fell back to time_stop. Fix: dispatch to `engine.run_vectorized()` when configured. Bug #3 (commit `aa961ff`): leaderboard recorded `best_combo_filter_class_names` (best raw-sweep combo) but never recorded which promoted candidate's refinement actually produced the leader. When the winning refined row came from a different candidate's combo, rebuild loaded the wrong filters → 35% PnL divergence on r630 long trend ($8.8M rebuilt vs $13.4M leader). Fix: master_strategy_engine.py writes `best_refined_filters` + `best_refined_filter_class_names` to family_leaderboard; rebuild prefers those when leader_source == "refined". Backfill script `scripts/backfill_best_refined_filters.py` (commit `1f1c50d`) walks existing leaderboards and reads refinement_narrow CSVs to populate the missing column on pre-fix runs without re-running the sweep. Workflow: backfill leaderboard -> re-emit trade_artifacts via existing `scripts/backfill_trade_emission.py --force`. Validated on r630 NQ 5m long bases (which previously FAILED on trend) -> 3/3 OK with bit-exact $13,412,390.85. Test count grew 80 -> 87 (7 new parity regression tests covering long+short × time_stop+signal_exit/fast_sma + the routing bug). 10-market overnight 5m sweep launched ~09:35-11:13 UTC across 3 hosts with Sprint 98 RAM flags ON. Distribution: r630 (88T, 62GB) -> ES, CL, GC, YM at workers=40; gen8 (48T, 78GB) -> SI, EC, JY at workers=36; g9 (48T, 31GB) -> BP, AD, BTC at workers=24. NQ already done from earlier validation. Per-host queues run sequentially via `scripts/run_5ers_overnight_queue.sh`. By session close: 5 markets complete (ES 150min, CL 148min, GC 186min on r630; SI 426min on gen8; BP 267min on g9), 68 strategies accepted across all completed leaderboards, **0 PARITY_FAILED** anywhere. YM, EC, JY, AD, BTC still active or queued. Forecast: 8-9 of 10 markets complete by morning; gen8's EC + JY likely the laggards (7h+ FX wall-times). Live RAM observation: r630 at 4GB swap, gen8 at 6GB swap even at conservative worker counts — bottleneck is per-worker RSS (1.4M-row × 21-col features DataFrame copied per worker on fork = 800MB-1.2GB/worker). CPU is not the limit; RAM is. **Next sprint design saved: `docs/SHARED_MEMORY_FEATURES_DESIGN.md`** — uses stdlib `multiprocessing.shared_memory` to back features with named POSIX shm segments. Workers attach by name and reconstruct zero-copy DataFrame views. Expected r630 worker RSS 793MB -> ~250MB, headroom for 70-80 workers vs current 40, ~30-40% faster wall-time on big 5m markets. Estimated 1 working day to ship. Today's commits on main: `f4424ce` (Bug #1), `235f993` (Bug #2), `aa961ff` (Bug #3), `1f1c50d` (backfill script), `b74d27e` (10 5m configs + generator), `34015ec` (queue runner). Persistent monitor `bwn5klbbo` arms 60-min check-ins for queue progress; queue runner script keeps going past failures (no set -e) so one market crash doesn't kill its host's queue. Previous: 2026-05-04 (Session 96 close: deferred verdict gates resolved; Sprint 98 promoted to CANDIDATES on 5m heavy A/B; Sprint 99-bis is_enabled fix shipped) **Session 96 wrap (2026-05-04). Two deferred verdict gates resolved + an unplanned bug discovered and fixed. (1) Sprint 96 HRP A/B on c240 (program=high_stakes_5k, gated CFD leaderboard, runs from /data/sweep_results/runs/2026-05-01_10market_cfd_non5m): both runs ~670s, top portfolio identical down to strategy_names. HRP fired correctly (15 clusters across 25 strategies) but the current top 3-strategy combo already spans 3 distinct clusters (max diversity). Verdict: SUSPICIOUS as predicted by the pre-reg's "Honest expected outcome" - HRP infrastructure pays off when candidate pool grows beyond the daily-dominated set. (2) Sprint 98 5m heavy A/B (r630 treatment with flags ON, c240 control with flags OFF, both ES_5m_dukascopy.csv with sane max_workers=40): treatment peak RSS 35.8 GB vs control 51.6 GB = **30.6% reduction**, control hit **3.2 GB swap-thrash** at family transition while treatment stayed at 108 MB clean. Pre-reg verdict gate (>=30% peak RSS reduction) MET. Sprint 98 promoted: SUSPICIOUS -> CANDIDATES. RSS evidence archived at Outputs/sprint98_rss_evidence/r630_treatment_rss.csv. (3) Sprint 99 (Trade-array refactor) trial via cProfile on gen8: RED on original scope - bottleneck wasn't Trade-objects, it was Sprints 94/95's is_enabled() functions calling load_config()/yaml.safe_load() on every combo. 1500 combos x 2 cache flag checks = 3000 yaml loads, 73% of cumulative profile time. (4) Sprint 99-bis spin-off: 30-line fix caches is_enabled() result at module level across modules/filter_mask_cache.py, modules/signal_mask_memo.py, modules/strategy_types/sweep_worker_pool.py + reset_*_cache test helpers. Shipped as `be0ee0e`. Sequential profile speedup verified at 3.4x (78.76s -> 23.40s). HOWEVER on parallel sweeps (40 workers) the fix is noise (1-2%) because each worker forks once and amortises yaml-load across many combos - yaml was never the parallel-run bottleneck. Net Sprint 94 + 95 verdicts UNCHANGED at SUSPICIOUS even after the fix; the cache benefits are genuinely small in absolute terms. Test count 462 -> 488. Today's commit chain on session 96 close: `4435f0e` (HRP A/B + Sprint 98 5m launch infra) -> `8b0de29` (Sprint 99 pre-reg) -> `40f2fd8` (Sprint 99 cherry-pick into followup) -> `be0ee0e` (Sprint 99-bis is_enabled fix, on main). What's actually solved this arc: Sprint 93 resume (kill+restart cheap), Sprint 98 RAM (5m sweeps stably complete), Sprint 99-bis (dev/profile workflow 3.4x faster), Sprints 87/89/92 cost realism (pre-session 95). What hit ceiling: 2-5x engine speedup on production parallel runs - vectorised engine is already where Python+numpy can take it. What's still open architecturally: walk-forward at family-leaderboard stage, Layer C tail co-loss replacement, per-cluster candidate cap in selector. LLM briefing at docs/LLM_CONSULTATION_RAM_PRESSURE.md updated to Round 5 with all measured numbers replacing speculative ones; Q8-R5 asks LLMs which architectural Round-6 priority to pursue for selector quality (not engine speed). 5m runs killed pre-emptively after first family transition gave the verdict-gate evidence; remaining ~2-4 hours of run time saved. Cluster idle. Previous: 2026-05-04 (Session 95 close: Sprints 93/94/95/96/98 all on main; 97 skipped per honest profiling)
Current status: **Session 95 wrap (2026-05-04). Five sprints landed on main this session: 93 (engine resume logic - CANDIDATES), 94 (filter mask cache - SUSPICIOUS), 95 (signal-mask memoisation - SUSPICIOUS), 96 (HRP clustering for selector - infrastructure shipped, A/B verdict deferred), 98 (RAM prevention - recycling pool + sequential families - CANDIDATES on parity, RAM proof deferred). Sprint 97 (Numba JIT on vectorized_trades.py) skipped after honest profile reading - the inner kernel is already pure numpy + 14-23x faster than the original loop, the only remaining Python loops are 7-line overlap prevention + Trade-object construction; realistic Numba speedup would be 5-15% bounded by Amdahl, not the 2-5x Gemini Round 2 predicted. The bigger Trade-object refactor that WOULD deliver 2-5x exists but carries parity risk on a parity-tested codebase. Test count grew 287 -> 462 across the session (17 resume + 14 filter cache + 14 signal memo + 10 recycling pool + 18 HRP). All 5 shipped sprints are default-OFF in config; zero behaviour change for normal runs. Cross-LLM consultation Round 4 took place mid-session: ChatGPT-5 picked option (e) "diagnostic harness first then ruthlessly decide", Gemini 2.5 Pro picked (c) "skip verification, ship Numba" - my synthesis split the difference: shipped 98 for RAM, 96 for selector, dropped 97. Today's commit chain on main: `267b381` (93) -> `d5ac7bb` (handover) -> `909c81f` (94) -> `37e0e58` (95 + briefing v2 reframed) -> `0478c54` (98) -> `8885a1b` (96). Pre-sprint diagnostics: (1) FTMO Australia 1:100 Friday-close rule (Gemini Q14) verified absent for Rob's Swing accounts - Sprint 1 in synthesis list closed negative. (2) `pmap -X` on a live r630 worker showed Private_Dirty 190 MB / Shared_Clean 93 MB on 100 MB dataset - CoW partially working but per-worker private accumulation is the binding cost. Sprint 98 directly addresses this. Cluster cleanup: all compromised 5m sweeps killed cluster-wide before sprint cycle. Open verdict gates deferred to next session: (a) Sprint 98 RAM benefit verification needs first 5m heavy run with PSC_RECYCLING_POOL=1 + sequential_families=true and RSS instrumentation. (b) Sprint 96 diversity improvement needs HRP=ON A/B run against current 7-program top-portfolio output. Both are cheap to run with Sprint 93's resume logic in place. Cluster currently idle: r630/gen8/c240 each ~2-4 GB RAM used; g9 still offline from earlier swap-thrash death (no urgency). New scipy>=1.13.0 dependency added for Sprint 96 - installed 1.17.1 on Latitude + r630 venv. Drive backups still healthy via x1 mirror task. Previous: 2026-05-03 (Sprints 87/88/85B/89/90/91/92 all shipped; 7-program selector results live on Drive)
Current status: **Session 95 (2026-05-04). Sprint 93 (engine resume logic) shipped to main as `267b381` after passing all 5 verdict-gate stages on r630. Per-family resume via on-disk CSV detection + sha256 config fingerprint guard + `--force-fresh` opt-out; engine now persists refinement-results CSV per family (was in-memory only) so resume reproduces the refined leader instead of falling back to combo. Smoke-test on ES daily: control 75.5s -> resumed 34.0s = 55% wall-clock saved (6 of 15 families resumed including the heavy mean_reversion + breakout). Behavioural parity zero-tolerance on net_pnl/PF/oos_pf row-by-row; 4 strategy_name tie-break warnings on freshly-recomputed families confirmed as PRE-EXISTING engine non-determinism by running two fresh control runs back-to-back which also disagreed on 1 row each. Tests: 402/402 green (385 baseline + 17 new resume tests). New files: `modules/engine_resume.py`, `tests/test_engine_resume.py`, `scripts/verify_resume_parity.py`, `sessions/SPRINT_93_engine_resume_logic.md`. `master_strategy_engine.py` got `--force-fresh` arg, fingerprint guard at dataset entry, per-family resume hook in both large + small family loops, and refinement CSV persist+stale-cleanup. Unblocks every subsequent RAM/speed sprint by reducing kill+restart cost from O(hours of completed family work lost) to O(in-flight family lost). Pre-sprint diagnostics: (1) FTMO Australia 1:100 Friday-close rule (Gemini Q14 premise) verified absent - Rob's Swing accounts use 1:30 leverage and explicitly waive news + weekend restrictions per `modules/prop_firm_simulator.py:336-406`; the 1:100 tier is a different FTMO product, no MC rule change needed. (2) `pmap -X` on a live r630 worker (PID 1148945) showed VmRSS 360 MB / RssAnon 342 MB / Shared_Clean 93 MB / Private_Dirty 190 MB / SwapPss 40 MB on a ~100 MB dataset - CoW partially working (93 MB shared) but per-worker private accumulation (190 MB private dirty) is the binding cost. Implication: shared-memory savings are modest (~93 MB/worker = 15 GB on a 165-worker run); float32 + maxtasksperchild + smaller per-task state are bigger levers than originally framed in the briefing. Cluster cleanup: killed all running 5m sweeps cluster-wide (r630/g9/gen8/c240) - they were producing compromised CSVs (~25% combos missing per family from silent worker death cycles in the swap-thrash pattern observed earlier in the session). Today's commit chain on main: `38e0270` (high_stakes_5k registry) -> `95b9ca1` (portfolio4 ext + projection + archive fix) -> `c4e5771` (portfolio4 yaml + runner spec) -> `14d7337` (RAM-pressure briefing v1) -> `561c232` (briefing v2 reframed for current sprint state) -> `324fe1b` (Sprint 93 pre-reg) -> `267b381` (Sprint 93 deliverable). LLM briefing at `docs/LLM_CONSULTATION_RAM_PRESSURE.md` rewritten to reflect post-Sprint-92 state (no more "fix trade emission" recommendation - that shipped in Sprint 84) and to ask reframed questions about RAM crisis and 5m sweep value. Cross-LLM round 2 took place: ChatGPT-5 returned an implementation-ready filter-mask cache prompt; Gemini 2.5 Pro returned divergent Q9-Q16 takes including the strong HRP-clustering recommendation for the selector and the (verified-incorrect) FTMO 1:100 premise. Synthesis sequence locked in: Sprint 93 (DONE, this commit) -> Sprint 94 filter mask cache (next) -> Sprint 95 signal-mask memoisation for MR -> Sprint 96 HRP clustering -> Sprint 97 Numba JIT on vectorized_trades. Open work next session: kick off Sprint 94. Cluster currently idle (r630/gen8/c240 all post-kill, ~2-4 GB RAM used each; g9 still offline from earlier swap-thrash death). Drive backups still healthy via the x1 mirror task. Previous: **Massive day. 7 sprints landed (87 The5ers cost overlay → 88 account-aware deployability → 85B signal mask round-trip → 89 6500x cost-MC vectorisation → 90 cross-host orphan ingest → 91 5m family-split CLI → 92 FTMO firm overlay + multi-firm support). Pipeline now cleanly handles The5ers AND FTMO with separate per-firm cost overlays auto-selected from `prop_config.firm_name`. 108/108 tests pass. 14 commits pushed to main. End-to-end results: same top portfolio (N225 daily Breakout + CAC daily Breakout + YM daily Trend) wins ALL 7 program tracks with 99.8-100% pass rate and 6.14-6.54% p95 DD. FTMO 1-Step $130K = sweet spot (RECOMMENDED, 100% pass, 3.9 months to fund, 6.54% DD vs 10% trailing limit). Drive backup folder live at `G:/My Drive/strategy-data-backup/portfolio_selector/` with timestamped per-run subdirs and a master `portfolio_runs_history.csv` (100 rows = 10 portfolios × 7 programs × 2 runs); auto-archival baked into `run_portfolio_all_programs.py`. Cluster jobs cleared: 10market backfill done (35/35 in 4h22m, then re-run with Sprint 85B fix), N225_15m sweep on g9 done (manually ingested via host-mismatch workaround → motivates Sprint 90), gated leaderboard grew 22 → 147 → 196 strategies. Cost-aware MC now 6500x faster after Sprint 89 (legacy 158s → vectorised 24ms at 3 strats × 100 trades × 200 sims). 3 FTMO programs re-run in PARALLEL on c240 (3x speedup vs sequential, 14 min wall) using REAL FTMO swap data captured from operator's Free Trial demo via `scripts/ftmo_symbol_spec_export.mq5` + `scripts/import_ftmo_specs.py`. FTMO MT5 specs CSV (130+ symbols) committed to `data/ftmo_symbol_specs.csv`; firm-specific overlay at `configs/ftmo_mt5_specs.yaml` populated. FTMO has NO excluded markets vs The5ers' 6 (W/NG/US/TY/RTY/HG); FTMO Gold swap 3x cheaper, Silver 5x cheaper, BTC 400x cheaper, CL pays positive long swap. Today's commit chain: `f76ff8b` (87) → `21b8dbe` (88) → `43e04d7` (85B) → `be8a005` (handover) → `1eb15ae` (89) → `5ce4158` (MT5 export script) → `25580ec` (Sprint 88 spec) → `69cc5cc` (FTMO configs) → `3116ab8` (90+91) → `876931c` (FTMO YAML populated) → `06736a4` (firm-aware overlay) → `437ce0c` (Drive archival). Previous: **Sprints 87 (The5ers MT5 cost overlay), 88 (account-aware deployability check), and 85B (rebuild signal mask round-trip) all shipped to main 2026-05-03 back-to-back. 98/98 tests green across all sprint suites. Selector now reads asymmetric long/short swap, custom triple-day rules (CL Friday=10x, BTC daily-no-triple), and round-trip commission from `configs/the5ers_mt5_specs.yaml` when `pipeline.portfolio_selector.use_the5ers_overlay: true` is set; default false for A/B comparison. With overlay on, portfolio reports flag deployability per actual operator account size — e.g. $5K Pro Growth rejects portfolios where any strategy weight scales below MT5 min_lot 0.01 (verdict `INFEASIBLE_AT_ACCOUNT_SIZE`). Sprint 85B fixes residual refined-subtype parity by passing the same `compute_combined_signal_mask` output to `engine.run` that the original sweep/refinement used, eliminating silent entry-bar drift when `min_avg_range = 0.0` sentinel meets hardcoded `build_candidate_specific_strategy` defaults. Empirical 85B impact (parity-pass-rate uplift) measured next backfill cycle since current c240 backfill PID 173730 was started before Sprint 85B commit (43e04d7). Commits on main today: `f76ff8b` (87), `21b8dbe` (88), `43e04d7` (85B); pushed `25580ec..43e04d7`. New files: `tests/test_the5ers_overlay.py`, `tests/test_account_aware_sizing.py`, `tests/test_sprint85b_signal_mask.py`, `sessions/SPRINT_87_the5ers_cost_overlay.md`. Modified: `modules/portfolio_selector.py` (+overlay loader, `_set_the5ers_overlay_enabled` toggle, asymmetric swap selection by direction, commission via entry_price, account_balance helper, deployability check, 5 new report columns, INFEASIBLE_AT_ACCOUNT_SIZE verdict), `modules/portfolio_evaluator.py` (+signal mask round-trip in rebuild path), `config.yaml` (+`use_the5ers_overlay: false` default), `sessions/SPRINT_85_rebuild_parity_investigation.md` (Phase B section), `sessions/SPRINT_88_account_aware_sizing.md` (Result section). Background jobs still healthy: 10market backfill on c240 ~11/37 datasets done (CAC×4, DAX×4, ES×3, FTSE_15m in progress; ~14min/dataset average; ETA ~6h to finish all 37); N225 15m sweep on g9 at 15% with 5h49m ETA. Pipeline gate funnel now has 16 stages from sweep entry to final RECOMMENDED verdict (sweep > quality flag > consistency > promotion > refinement > family leader > master agg > parity check > post-ultimate gate > selector hard filter > multi-layer correlation > combination sweep > regime survival > Monte Carlo > sizing optimisation > robustness test > deployability > verdict). Previous: Sprint 84 (canonical trade emission) + Sprint 85 Phase A (CFD config plumbing fix) + post-ultimate gate threshold calibration shipped to main 2026-05-03. Gated leaderboard pass rate 96.4% -> 4.5% on the validation run, 22 real strategies surviving. Top 3: NQ daily breakout_compression_squeeze (oos_pf 4.40), NQ daily trend_slope_recovery (oos_pf 2.38), ES daily breakout_compression_squeeze (oos_pf 1.97).** Background: Cross-LLM consultation (ChatGPT-5 + Gemini 2.5 Pro) on portfolio selector identified that `strategy_trades.csv` reliability is the binding bottleneck. Sprint 84 baked per-trade artifact emission (with parity check) into the canonical sweep finalize path so every accepted strategy now produces `strategy_trades.csv` + `strategy_returns.csv` regardless of `skip_portfolio_evaluation`. Post-ultimate gate updated to fail-closed on missing/parity-failed artifacts. The parity check then surfaced a major hidden bug: `_rebuild_strategy_from_leaderboard_row` was using futures `EngineConfig` defaults on CFD data, producing 100x slippage cost per side and inverted-sign rebuilt PnL. Sprint 85 Phase A fixed it by loading per-market values from `configs/cfd_markets.yaml`. Validation backfill on `2026-04-30_es_nq_validation` post-fix now shows ~40-60% PARITY_OK exact-match (was 0% before). Residual ~30-50% PARITY_FAILED rows have a smaller, parameter-specific bug class (Phase B, deferred): when leaderboard `min_avg_range = 0.0` sentinel is used for "default", rebuild's default differs from what original refinement saw via `precomputed_signals`. Phase B fix path = round-trip filter parameters from `{family}_promoted_candidates.csv`. Live EA strategies are NOT affected (driven by sweep output, not rebuild). Backfills running on c240 to retro-emit trade artifacts on validation + 10market_cfd_non5m runs; finalize-run + comparison via `scripts/compare_gate_pass_rates.py` is the next step. Files added: `configs/the5ers_mt5_specs.yaml` (consolidated firm-specific cost overlay built from existing `archive/sessions/SESSION_HANDOVER_swap_discovery.md` + `modules/cfd_mapping.py`), `modules/trade_emission.py`, `scripts/backfill_trade_emission.py`, `scripts/compare_gate_pass_rates.py`, `sessions/SPRINT_84_canonical_trade_emission.md`, `sessions/SPRINT_85_rebuild_parity_investigation.md`, `tests/test_trade_emission.py`. Tests: 335/335 non-parity green. Commits on main: `a20fe25 d2e1ed4 d1f4fd1 eff8f8c 45b9499 27292b6 7acd6ec 82c10a7`. Previous: c240 RAID-1 single-drive rebuild complete (2026-05-02-03). Old c240 lost the original 10 TiB drive; surviving partner gives a fresh 3.6 TB Ubuntu 24.04 install with 80 threads + 62 GB RAM intact. New IPs: LAN `192.168.68.80` (was `.53`), Tailscale `100.69.123.38` (was `100.120.11.35`; old `c240-1` device deleted from admin). `/data` recreated as 3.5 TB ext4 LV `data-lv` in `ubuntu-vg`, owned by rob. All packages reinstalled, repo cloned to `~/python-master-strategy-creator` with venv at `~/venv` (Python 3.12.3, requirements installed, 39/39 smoke tests pass). Always-on hardening reapplied (sleep/suspend/hibernate masked, ssh-recover.service enabled, ARP-flush cron). Samba `[data]` and `[photos]` shares live with smbpasswd for rob. Full SSH mesh re-established: c240 <-> gen8/r630/g9 + Latitude + x1. Worker `post_sweep.sh` retargeted to new c240 IP. Data restored end-to-end: leaderboards (4 ultimate CSVs + storage subdir), recovery exports, 35/35 historical sweep runs (1.4 GB) from Google Drive backup; 120 CFD `ohlc_engine` files (2 GB) rsynced from r630; 48 TradeStation futures CSVs (1.9 GB) pushed from Latitude repo. Net loss from drive failure: zero irreplaceable. CFD raw TDS OHLC + 32 GB tick data (`ticks_dukascopy_tds`) not yet restored to c240 but the 33 GB original Latitude TDS source still exists at `C:\Users\Rob\Downloads\Tick Data Suite\Dukascopy\` (Open Issue #1 was never actioned). Active 10-market CFD run `2026-05-01_10market_cfd_non5m` recovered: 33/40 jobs ingested (was 14/40 when c240 went down; 17 worker-side completed datasets caught up via manual ingest pass; +1 c240 job since via patched watcher). Remaining 7 jobs distributed across all 4 hosts: c240 (NQ:30m, RTY:daily, STOXX:30m), r630 (ES:15m, FTSE:60m), gen8 (YM:15m), g9 (N225:15m). Watcher daemon `auto_ingest_distributed_run.py` runs continuously on c240 (PID 104304+) with `--control-host=localhost --poll-seconds=60` and three local-host patches: `_is_local_control` recognises hostname, `_remote_text/_remote_file_exists/_host_reachable` short-circuit to local file ops, ingest source-root check honors local-host case. Ingest pipeline targets `/data/sweep_results/runs/<run_id>/`; auto-finalize rebuilds `/data/sweep_results/exports/` after each ingest. **Drive mirror role moved off c240 onto x1 Carbon**: x1 has Z: mounted at `\\192.168.68.80\data` and Drive at `G:\My Drive\strategy-data-backup\`; scheduled task `PSC_Mirror_Drive` on x1 runs `mirror_now.ps1` every 10 minutes, which calls `run_cluster_results.py mirror-backup` plus an explicit belt-and-braces copy of `cluster_run_manifest.json` and `meta/` into the Drive run dir (the in-tree mirror was previously dropping these). **Streamlit dashboard moved off c240 onto x1**: scheduled task `PSC_Dashboard` (TaskScheduler, AtLogOn + AtStartup triggers, `dashboard_serve.ps1` launcher) starts streamlit at port 8511 reading from `Z:\sweep_results` with PSC_DASHBOARD_REMOTE_STATUS=1; reachable at `http://100.86.154.65:8511` over Tailscale or `http://192.168.68.73:8511` on LAN. Dashboard heavily patched for x1 use: `_ssh_subprocess_run` paramiko shim replaces three `subprocess.run(["ssh", ...])` sites because Windows OpenSSH+Python subprocess+capture_output hangs without TTY; live-status probe gained `_status_mtime` and a 60-minute stale filter to hide orphan status.json files left over from killed `run_cluster_sweep.py` invocations; per-dataset card now shows whole-timeframe ETA via family-weighted projection (mean_reversion ~35% of total compute, base trend/breakout ~16-17%, short bases ~5-8%, 9 subtypes ~1.5% each) instead of current-family-only; progress bar shows total dataset progress instead of just the current family; Live Monitor cache TTL bumped from 120s to 300s (5 min) and meta-refresh tag matches. The same `auto_ingest_distributed_run.py` patches (paramiko-friendly SSH opts including `-T`, longer per-call timeouts for the ingest CLI, host=local handling) are pushed to both c240 and x1 so a future migration to x1-resident watcher is one config flip. Open work tomorrow: (1) properly migrate watcher off c240 onto x1 using the paramiko shim end-to-end, (2) confirm RAID 1 is mirror-Optimal-2-PD via LSI WebBIOS at next reboot, (3) tighten ETA calibration once the 7 remaining jobs finish (real wall clocks become the next baseline), (4) fix `mirror_storage_to_backup` so it copies manifest+meta in one shot rather than relying on the explicit shim. Previous state: Dashboard completely remade (2026-05-01). Primary view is now Live Monitor: per-dataset cards with gradient progress bar, large ETA display, family-group mini bars (6 groups, 15 families), host badge, and stage line. On c240 the dashboard reads `/tmp/psc_*/Outputs/*/status.json` directly via local file probe -- no self-SSH. For remote hosts, SSH uses BatchMode=yes to prevent password-prompt hangs. st.cache_data(ttl=30/60) prevents blocking on page load. Tab order: Live Monitor, Results, Run History, System, Ultimate Leaderboard. Ultimate Leaderboard tab has raw/gated toggle (Bootcamp toggle retired). Previous state: Codex had added the first post-ultimate gate layer on top of the canonical local-cluster publish path, turned the dormant distributed-sweep planning helpers into a real CLI planning mode for multi-host load splitting, pushed the portfolio selector into its first genuinely challenge-aware cost-model tranche, and repaired the neglected Streamlit dashboard so it behaves like a local-cluster console instead of a half-broken GCP relic. Finalize emits the raw cumulative ultimate files plus derived audited gate outputs: `ultimate_leaderboard_FUTURES_post_gate_audit.csv`, `ultimate_leaderboard_FUTURES_gated.csv`, legacy alias `ultimate_leaderboard_post_gate_audit.csv`, legacy alias `ultimate_leaderboard_gated.csv`, and the CFD equivalents under `/data/sweep_results/exports/`. The current v1 gate is intentionally a derived layer, not an in-place mutation of ultimate: it uses trade concentration checks from `strategy_trades.csv` where available plus neighbor-based parameter-fragility evidence from the accepted raw pool, then hard-culls explicit fails into the survivor-only gated file while preserving the full audit CSV. Selector hardening is now beyond simple filtering: `run_portfolio_selection()` can explicitly prefer `*_gated.csv` inputs, live hard filtering honors per-program `excluded_markets` from `PropFirmConfig` (The5ers configs carry `W, NG, US, TY, RTY, HG`), `generate_returns.py` now preserves richer `strategy_trades.csv` fields (`entry_time`, `exit_time`, `direction`, `entry_price`, `exit_price`, `bars_held`), and selector Monte Carlo can now consume spread/swap market costs from `configs/cfd_markets.yaml` when rich trade artifacts exist. Portfolio reports now surface behavior diagnostics such as max overnight-hold share, max weekend-hold share, and max swap-per-micro-per-night so challenge-inappropriate carry exposure is visible instead of hidden inside aggregate returns. Dashboard note: `dashboard.py` / `dashboard_utils.py` have now been de-clouded enough to be useful again for the local era. The app no longer crashes on the history tab due to missing cloud-cost fields, quick commands now reference `run_cluster_sweep.py` / `run_cluster_results.py`, and the live monitor can probe cluster hosts directly for active `/tmp/*/Outputs/*/status.json` files so manual runs on `r630`/`c240`/`g9` can show up even when they were never launched through the old strategy-console flow. Important scope note: both the selector and the dashboard are now materially more honest, but neither is "finished architecture." Cost-aware MC only activates when run artifacts are rich enough, `selection_mode` (challenge vs funded) is still not explicit, walk-forward results are still not wired into live selector orchestration, and the dashboard still has room for richer host telemetry and raw-vs-gated result toggles. Separately, `run_cluster_sweep.py` now supports `--distributed-plan --hosts HOST:WORKERS ... --remote-root ... [--plan-output ...]` to generate weighted per-host exact-job plans and ready-to-run commands, which is the safe first step toward splitting 5m-heavy batches across idle servers without compromising research integrity. The validated CFD run `2026-04-30_es_nq_validation` is still finalized on c240 under `/data/sweep_results/runs/2026-04-30_es_nq_validation`; Drive cold backup and recovery exports remain in place; and the historical futures corpus remains preserved locally at `Outputs/ultimate_leaderboard.csv` and in Drive as `ultimate_leaderboard_LEGACY_FUTURES_649rows_2026-04-04.csv`. Latest cluster timing checkpoint on `r630`: `ES:5m` was at breakout sweep 20.0% (`3294/16473`) at `2026-04-30T21:42:30+00:00` with family ETA `133.7 min`, then 40.0% (`6588/16473`) at `2026-04-30T22:24:13+00:00` with family ETA `112.7 min`; host check at `2026-04-30T22:31:49+00:00` still showed the box healthy and CPU-saturated. These timing checkpoints should be reused as the baseline for future ETA estimates instead of stale progress banners. Also verified: the conservative MT5/The5ers-first 10-market CFD set (`ES NQ YM RTY DAX N225 FTSE STOXX CAC GC`) exists across all four hosts for `5m/15m/30m/60m/daily` and looks ready for the first distributed batch once `r630` is free. Important scope note on distributed execution: the current distributed mode is a planner/command generator, not an autonomous SSH dispatcher yet. Hardware note for next week: `g9` is expected to receive dual replacement CPUs matching `c240` plus an extra 32 GB RAM, taking it to roughly 80 threads / 64 GB and making it a serious 5m workload target once durably onboarded.

---

## Active Run

- **2026-05-01 10-market CFD batch is live.** Purpose: produce current CFD strategy candidates for the running The5ers evaluation, avoiding the futures-portfolio mismatch.
- **Scope:** `ES NQ YM RTY DAX N225 FTSE STOXX CAC GC` across `daily 60m 30m 15m` only. **No 5m jobs included.** 5m markets are deferred until this non-5m set is complete.
- **Remote root:** `/tmp/psc_10market_20260501`
- **Logs:** `/tmp/psc_logs/psc_10market_c240.log`, `/tmp/psc_logs/psc_10market_r630.log`, `/tmp/psc_logs/psc_10market_gen8.log`, `/tmp/psc_logs/psc_10market_g9.log`
- **Worker split:** c240 72 workers / 13 jobs; r630 80 workers / 14 jobs; gen8 44 workers / 7 jobs; g9 36 workers / 6 jobs. Plan normalized load was balanced at ~0.43-0.44 across hosts.
- **Publish rule from 2026-05-01 onward:** every `run_cluster_results.py ingest-host` auto-finalizes by default, rebuilding master, ultimate, gated ultimate, and backup/recovery exports immediately after that host's datasets are copied. The CLI also mirrors finalized exports/run artifacts to the Google Drive clone by default when a backup root is provided or discoverable. Use `--no-finalize` / `--no-mirror-backup` only for deliberate dry or staging work.
- **Google Drive clone target:** `G:\My Drive\strategy-data-backup` on Latitude/X1, or `STRATEGY_BACKUP_ROOT` / `PSC_BACKUP_ROOT` if running elsewhere. If the canonical ingest is run on c240 and no Drive mount is visible there, immediately follow from Latitude with `python run_cluster_results.py mirror-backup --storage-root <canonical_storage_root> --backup-root "G:\My Drive\strategy-data-backup" --run-id <run_id>`.
- **Drive leaderboard folder hygiene:** the visible `leaderboards\` root is intentionally kept to four operator-facing files only: `ultimate_leaderboard_cfd.csv`, `ultimate_leaderboard_FUTURES.csv`, `ultimate_leaderboard_cfd_gated.csv`, and `ultimate_leaderboard_FUTURES_gated.csv`. Masters, run-specific exports, post-gate audits, legacy aliases, and timestamped fallback files belong under `leaderboards\storage\`.
- **Locked spreadsheet behavior:** if LibreOffice has a cloned leaderboard open, the mirror writes a timestamped `*_UPDATED_YYYYMMDDTHHMMSSZ.csv` copy instead of dropping the update.
- **Partial publish status:** `CAC:daily` from c240 and `DAX:daily` from r630 have been ingested into run `2026-05-01_10market_cfd_non5m`. Current cumulative Drive-visible CFD ultimate/gated row count is 133, including `CAC daily` 15 rows and `DAX daily` 15 rows.
- **Auto-ingest watcher:** Latitude is running `scripts/auto_ingest_distributed_run.py` for `2026-05-01_10market_cfd_non5m`, polling every 300 seconds. PID is recorded in `.tmp_auto_ingest_10market.pid`; stdout/stderr are `logs/auto_ingest_10market.out.log` and `logs/auto_ingest_10market.err.log`. It reads `.tmp_10market_plan.json`, skips jobs already present in c240's canonical manifest, ingests each newly `DONE` dataset into `/data/sweep_results`, and mirrors the refreshed exports/run artifacts to `G:\My Drive\strategy-data-backup`.
- **Permanent distributed-run rule:** every future distributed plan must include `--run-id <canonical_run_id>` and keep the generated `auto_ingest` block. `run_cluster_sweep.py --distributed-plan` now writes both a foreground watcher command and a hidden PowerShell starter command into the plan JSON. Start the hidden watcher as soon as the host sweep commands are launched; do not wait for the whole run to finish.
- **Next action:** let the auto-ingest watcher publish each completed dataset. If the watcher is stopped or Latitude is offline, fall back to manual `run_cluster_results.py ingest-host` for each completed host/dataset so master, ultimate, gated, recovery, and Google Drive clone outputs publish immediately.

## ETA Baselines

- **Rule:** when estimating cluster ETAs, prefer recorded checkpoint deltas over stale in-run banners. Re-check `status.json`, process health, and recent log milestones before giving an estimate.
- **Current timing baseline (`r630`, ES full batch, 2026-05-01 AEST / 2026-04-30 UTC):**
  - `2026-04-30T21:42:30+00:00`: `breakout` sweep at `3294/16473` (20.0%), family ETA `133.7 min`
  - `2026-04-30T22:24:13+00:00`: `breakout` sweep at `6588/16473` (40.0%), family ETA `112.7 min`
  - `2026-04-30T22:31:49+00:00`: host still alive and CPU-saturated; `run_cluster_sweep.py --jobs ES:5m ES:daily --workers 80` active with many `master_strategy_engine.py` workers at ~97% CPU
- **Interpretation note:** those ETAs apply to the current `breakout` family only, not the whole `ES:5m` job. At the 40% checkpoint, `mean_reversion` and `trend` were complete and 12 families still remained after `breakout`.

## Current State

### Live Trading
- **Portfolio #3 EA** deployed on Contabo VPS (89.117.72.49, Windows Server, US East)
  - Strategies: NQ Daily MR + YM Daily Short Trend + GC Daily MR + NQ 15m MR (all 0.01 lots)
  - First live trade confirmed: YM Daily Short Trend, SELL US30
  - Projected: 99.6% pass rate, 6.9% DD, ~13.4 months to fund
- **Portfolio #1 EA** also live on same VPS
- **The5ers** account 26213568 on FivePercentOnline-Real (MT5), $5K High Stakes
- **MT5 on Contabo:** Hedge mode working ✅, CFD symbols available, portfolio running

### CFD Data Pipeline (Session 65 — NEW)
- **Architecture decision:** Dukascopy tick data for strategy discovery (deep history, 2003+), The5ers tick data for execution validation (real spreads)
- **Dukascopy strategies are portable** across all CFD prop firms, not just The5ers
- **Pipeline:** TDS Metatrader exports (Dukascopy via Tick Data Suite) -> `scripts/convert_tds_to_engine.py` -> TradeStation-format CSVs -> engine sweep -> MT5 Strategy Tester validation
- **Format converter built (Session 65):** `scripts/convert_tds_to_engine.py` handles 24 markets, 5 timeframe codes, verified with OHLC exact match. 26 tests passing.
- **Engine loader updated:** `load_tradestation_csv()` now recognizes "Vol" column header from converted Dukascopy files
- **24 CFD market configs:** `configs/cfd_markets.yaml` with engine params, cost profiles, OOS split dates
- **Local sweep infrastructure:** `run_local_sweep.py` (single market) + `run_cluster_sweep.py` (batch orchestrator with resume) + `scripts/generate_sweep_configs.py` (24 configs generated in `configs/local_sweeps/`)
- **TDS export location (Latitude):** `C:\Users\Rob\Downloads\Tick Data Suite\Dukascopy\`
- **TDS symbol naming:** `{SYMBOL}_GMT+0_NO-DST_{TIMEFRAME}.csv` (e.g., `USA_500_Index_GMT+0_NO-DST_H1.csv`)
- **Converted data files:** 120 files on c240 at `/data/market_data/cfds/ohlc_engine/` (all 24 markets × 5 TFs)
- **dukascopy-python** v4.0.1 was installed on the OLD Gen 9 (pre-Session 66 decommissioning) for raw tick downloads. NOT installed on the current `g9` (which is a separate autonomous-business host).
- **SP500 Dukascopy download COMPLETE** — 3.4GB, 2012-01 through 2026-04 (bid + ask parquets), originally stored at `/data/dukascopy/raw_ticks/sp500/` on the OLD Gen 9. Data drives moved to c240 Session 66; specific path may or may not be preserved under the c240 /data restructure (Session 67).
- **Gen 9 storage notes (OLD Gen 9, pre-decommission):** `/data/dukascopy/raw_ticks/` and `/data/dukascopy/ohlc_bars/` existed with 437 GB free — historical reference only.
- **Converted data target (OLD plan):** `/data/market_data/dukascopy/` on Gen 9 — superseded. Current target is `/data/market_data/cfds/ohlc_engine/` on c240.
- **The5ers MT5 tick exports** (manual via Ctrl+U -> Ticks -> Export, saved to `Z:\market_data\mt5_ticks\`):
  - SP500: 3.1 GB, 76.5M ticks from 2022-05-23
  - NAS100: 10.6 GB, 245.8M ticks from 2022-05-23
  - US30 through UK100: in progress (manual export)
  - XAUUSD: only 5 days of data on The5ers — useless for backtesting, need Dukascopy
- **The5ers tick data depth varies wildly:** indices have ~4 years, XAUUSD has 5 days, FX unknown

### Home Lab Infrastructure

#### Power Policy (Session 72h/73, 2026-04-21) — ALL SERVERS ALWAYS-ON (HARD RULE)
- **HARD RULE: All cluster servers (c240, g9, gen8, r630) stay powered on 24/7. DO NOT SHUT DOWN ANY SERVER UNDER ANY CIRCUMSTANCES.** No auto-shutdown crons, no manual power-off, no suspend, no hibernate, no "just this once". The only acceptable power cycles are: (a) planned hardware installs requiring physical work, (b) unplanned power failure.
- **Rationale:** Rob has home solar + battery + off-peak AUD $0.08/kWh (00:00–06:00) and free solar 11:00–14:00. Idle cost ~AUD $0.50–$1/server/month — negligible vs. reliability pain of WOL failures, Gen 8's 5-min POST, r630's flaky first-WOL behaviour, and interrupted sweeps.
- **Implementation status:** c240 + g9 already always-on. **gen8 + r630 need auto-shutdown crons removed** (see Open Issue). Gen 8 joins the always-on pool when replacement fans arrive (~27 Apr–4 May 2026). WOL scripts retained as emergency wake-only fallback.

#### Lenovo Latitude (desktop-k2u9o61) — MAIN CONTROL & DEVELOPMENT MACHINE
- Windows 10 Pro, Tailscale 100.79.72.125
- Rob's primary laptop for scripting, development, and project building
- Used at home AND in the field — this is where Rob works day-to-day
- **Modern Standby disabled** (registry: PlatformAoAcOverride=0) — prevents random wake/sleep issues
- OpenSSH Server installed, key auth working, firewall port 22 open
- **Google Drive for Desktop** installed, syncing "Google Drive - Master Strat Creator" folder
- **Z: drive** mapped to `\\192.168.68.69\data` (Gen 9 Samba, creds: rob/Ubuntu123.)
- **rclone** installed via winget (used for headless OAuth token generation)
- **MT5** installed, connected to The5ers (Hedge mode) — used for manual tick data exports

#### X1 Carbon (desktop-2kc70vg) — ALWAYS-ON NETWORK HUB
- Windows 10 Pro, IP 192.168.68.70, Tailscale 100.86.154.65
- In a drawer, lid down, permanently connected to home LAN
- Always-on Claude.ai + Desktop Commander endpoint
- **Dual Remote Control hubs live here now:** `betfair-trader` and `python-master-strategy-creator` run side-by-side as separate Claude Remote Control sessions. They do not share state.
- **Strategy hub paths (Session 74, 2026-04-24):** `C:\Users\rob_p\strategy-ops\strategy-hub-watchdog.ps1`, `C:\Users\rob_p\strategy-ops\logs\strategy-hub.log`, Startup entry `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StrategyHubWatchdog.vbs`, scheduled pull task `StrategyRepoPull`, repo mirror `C:\Users\rob_p\Documents\GIT Repos\python-master-strategy-creator`.
- **Strategy pull automation:** `C:\Users\rob_p\strategy-ops\pull-repo.ps1` plus `pull-repo.bat` run every 5 minutes via Task Scheduler, but bail if the repo is dirty or not on `main`.
- **Dispatch path:** Claude mobile app -> X1 Carbon strategy hub -> SSH/Git actions -> c240/r630/gen8. Heavy compute stays on Linux; the X1 is only the control plane.
- SSH config at C:\Users\rob_p\.ssh\config with aliases: gen9, gen9-ts, gen8, gen8-ts, homepc, contabo
- WOL scripts: wake-gen9.bat, wake-gen8.bat, wake-all.bat in C:\Users\rob_p\
- Port 22 firewall opened for inbound SSH
- **Google Drive for Desktop** installed, syncing "Google Drive - Master Strat Creator" folder
- **Samba drive** mapped to `\\192.168.68.69\data`
- **Back online** (2026-04-14) — power supply had died, replaced

#### Gen 9 (DL360, `g9`) — COMPUTE WORKER (joining cluster)
- **Role (Session 75):** Compute worker, like c240/gen8/r630. Crunches sweeps when needed. Hermes/OpenClaw fully decommissioned and removed 2026-04-26.
- **Revived Session 71b (2026-04-19)** — bent CPU pins straightened, fresh Ubuntu install on new 128 GB SATA SSD boot drive.
- **Session 72g (2026-04-21):** Second CPU installed (E5-2650 v4 into CPU2 socket, bent pins fixed with pencil-spacer). Heat sink mounted. **Physical state: under house in final position.**
- **Session 72g/73 NETWORK FAULT — RESOLVED 2026-04-21.** Both possible root causes were actioned during the same trip: (a) Rob reseated the 2× SAS drives in Array B (had come partially unseated during under-house move; P440ar RAID controller can hang POST when unable to enumerate drives), and (b) cable position verified in leftmost port (eno1). **Lesson:** after a physical move, reseat storage *and* verify cable positions before blaming the network stack — symptoms overlap.
- **Hostname:** `g9`
- **OS:** Ubuntu 24.04.4 LTS, kernel 6.8.0-110
- **LAN IP:** `192.168.68.50/22` on `eno1` (DHCP)
- **Tailscale IP:** `100.71.141.89` (device name `g9`, auth user `robpitman1982@`)
- **CPU:** 2× Xeon E5-2650 v4 @ 2.20 GHz = **24 cores / 48 threads** (dual socket, Hyperthreading ON). `nproc` = 48.
- **RAM:** 32 GB + 4 GB swap (Session 72h/73; needs audit — was 16 GB before, mechanism of doubling unclear)
- **Storage — HP Smart Array P440ar:**
  - Array A: logicaldrive 1 (119.21 GB, RAID 0) — SATA SSD `1I:0:1` → `/dev/sda` (boot + `/` on LVM `ubuntu-vg/ubuntu-lv`, 58 GB used / 116 GB VG headroom)
  - Array B: logicaldrive 2 (273.40 GB, RAID 0) — 2× 146 GB SAS HDD `1I:0:2,1I:0:3` striped → `/dev/sdb` → LVM `data-vg/data-lv` → `/data` (269 GB ext4, fstab-persisted, owned by rob, UUID `0661ff58-9086-432e-b70b-51bc8a271cf1`)
- **Credentials:** `rob` / `Ubuntu123`; NOPASSWD sudo via `/etc/sudoers.d/rob-nopasswd`
- **SSH access from Latitude:**
  - Direct LAN SSH from Latitude Wi-Fi fails (client-isolation/ARP quirk) — use `ProxyJump c240` via `ssh g9` alias, or direct over Tailscale via `ssh g9-ts`.
  - `Host g9` in `C:\Users\Rob\.ssh\config` uses `ProxyJump c240`; `Host g9-ts` points at Tailscale IP.
  - Latitude `strategy-engine` pubkey in `~/.ssh/authorized_keys` on g9.
- **SSH services:** `ssh.socket` masked, `ssh.service` enabled + active, `ssh-recover.service` (25s delayed restart) enabled.
- **Always-on posture (per HARD RULE Session 73):** `sleep.target`, `suspend.target`, `hibernate.target`, `hybrid-sleep.target` all **masked**; `systemd-logind.conf.d/no-sleep.conf` sets lid/suspend/idle = ignore.
- **ARP-flush-on-boot:** `@reboot /usr/sbin/ip -s -s neigh flush all` in root crontab.
- **SSH keypair:** `~/.ssh/id_ed25519` (`rob@g9`) — pubkey installed on c240 `authorized_keys` for admin peer access.
- **Toolchain installed (Session 71b):**
  - Docker 29.1.3 (`docker.io` + `docker-compose-v2`, `rob` in `docker` group, daemon enabled)
  - Node.js v24.14.1 + npm 11.11.0
  - Python 3.12.3 + venv at `~/venv`
  - Tailscale 1.96.4
  - ssacli 6.45-8.0 (HP Smart Storage CLI)
  - rclone v1.60.1-DEV (config not done — see Open Issues)
  - Base: build-essential, git, curl, wget, jq, unzip, tmux, htop, iotop, net-tools, nfs-common, cifs-utils, wakeonlan, etherwake, ipmitool, ca-certificates, gnupg, software-properties-common
- **/data layout (Session 75 post-decommission):**
  ```
  /data/                          (269 GB ext4, noatime)
  ├── betfair-historical/         (rob — betfair sweep data, owned by rob)
  ├── backups/
  ├── logs/
  └── lost+found/                 (root:root, expected)
  ```
- **Pending compute-worker setup (Session 75 TODO):** repo clone, market_data sync, sweep scripts, samba membership, post_sweep.sh — not yet in place. g9 was never a backtesting member; the work to make it one is queued.
- **Hermes/OpenClaw decommission audit trail (Session 75 — 2026-04-26):**
  - Users `hermes` (uid 1001) and `openclaw` (uid 1002) deleted via `userdel -r`. Group `agents` (gid 1001) deleted.
  - Removed: `/data/hermes/` (~1.5 GB), `/data/openclaw/`, `/data/shared/` (entire tree), `/etc/cron.d/sync-handover`, `/etc/sudoers.d/agents`, `/usr/local/bin/sync-handover`, `/usr/local/bin/sync-betfair-handover`.
  - Hermes's pubkey `hermes-agent@g9-cluster` (fingerprint ending `JvbVaj`) removed from `rob@authorized_keys` on c240, gen8, r630. Backups taken to `~/.ssh/authorized_keys.bak-pre-hermes-removal-YYYYMMDD` on each host.
  - External retirement also complete (operator, 2026-04-26): GitHub deploy keys revoked on both `python-master-strategy-creator` and `betfair-trader` repos; Telegram bot `@pitmans_heremes_bot` deleted via @BotFather; Hermes Anthropic API key revoked in console. Hermes is fully gone, no remaining state anywhere.

#### Cisco C240 M4 (c240) — ALWAYS-ON DATA HUB + COMPUTE (Gen 9 replacement)
- Ubuntu 24.04.4 LTS, kernel 6.8.0-110, hostname `c240`
- **LAN IP:** 192.168.68.53/22 on eno1 (DHCP)
- **Tailscale IP:** 100.120.11.35 (device name `c240-1` in tailnet — old `c240` at 100.104.66.48 is a stale entry, clean up in admin console)
- **CPU:** 2× Xeon E5-2673 v4 @ 2.3 GHz = **40 cores / 80 threads** (Broadwell, v4) ✅
- **RAM:** 64 GB (2× 32 GB DDR4-2400 RDIMM), 62 GiB usable
- **Storage:** 10.9 TB SAS array on LSI MegaRAID SAS-3 3108 (inherited from Gen 9)
- **LVM layout:**
  - `ubuntu-vg` (11 173 GiB total)
  - `/` → `ubuntu-lv` 100 GB (11 GB used)
  - `/data` → `data-lv` **10 TiB ext4** (UUID `95cd8cf3-d070-447a-bc1f-f18d3800ad18`, fstab-persisted)
  - VG headroom: 834 GiB free for snapshots/growth
- **NICs:** 2× Cisco VIC (10G) + 6× Intel i350 Gigabit
- **Provenance:** ex-corporate machine; BIOS + CIMC factory-reset at start of Session 66 (cleared VLAN 303, hostname `splcbr02-5i-rac.sge.insitec.local`, old subnet 10.254.1.x)
- **CIMC:** management controller reset to factory defaults, set to DHCP/dedicated port; MAC `00:A3:8E:8E:B3:84`, CIMC IP TBD (needs separate setup)
- **Credentials:** `rob` / `Ubuntu123` (system + Samba); NOPASSWD sudo via `/etc/sudoers.d/rob-nopasswd`
- **SSH:** key auth working (Latitude `id_ed25519` in `~/.ssh/authorized_keys`); alias `c240` in `C:\Users\Rob\.ssh\config`
- **Tailscale 1.96.4** installed and authed as `robpitman1982@`
- **Samba:** `smbd`/`nmbd` enabled; shares `[photos]` → `/data/photos`, `[data]` → `/data` (rw, force user rob)
  - Default `/etc/samba/smb.conf` backed up to `/etc/samba/smb.conf.orig`
- **Packages installed (Session 67):** `python3-venv`, `python3.12-venv`, `python3-pip`, `ipmitool`, `rclone`, `wakeonlan`, `etherwake`, `iotop`, `net-tools`, `nfs-common`, `cifs-utils`, `build-essential`, `jq`, `unzip`, `zip`
- **SSH services (Session 67):** `ssh.socket` masked, `ssh.service` enabled + active, `ssh-recover.service` installed (25s delayed restart fallback, matches Gen 8/R630 pattern)
- **ARP-flush-on-boot:** `@reboot /usr/sbin/ip -s -s neigh flush all` in root crontab
- **Repo:** `~/python-master-strategy-creator` cloned via HTTPS, HEAD tracks `origin/main`
- **Python env:** `~/venv` (Python 3.12.3); `requirements.txt` + `dukascopy-python 4.0.1` installed
- **Shell env:** `.bashrc` exports `PSC_VENV`, `PSC_REPO`, alias `psc-activate` (activates venv + cd repo + sets `PYTHONPATH=.`)
- **SSH keypair:** `~/.ssh/id_ed25519` (`rob@c240`) — pubkey authorised on gen8 and r630
- **SSH authorized_keys:** holds keys from Latitude (`strategy-engine`), Gen 8 (`dl380p-deploy`), R630 (`rob@r630`)
- **SSH config:** `~/.ssh/config` aliases for gen8, gen8-ts, r630, r630-ts, x1, latitude
- **WOL scripts:** `/usr/local/bin/wake-gen8.sh`, `/usr/local/bin/wake-r630.sh`, `/usr/local/bin/wake-all.sh` (5-burst pattern, 3 broadcast addresses)
- **post_sweep.sh template:** `/usr/local/bin/post_sweep.sh` (worker-side — rsyncs `$SWEEP_DIR` → `c240:/data/sweep_results/_inbox/`)
- **/data tree (Session 67 restructure):**
  ```
  /data/                          (10 TiB ext4, root owns lost+found)
  ├── backups/                    rclone→gdrive target (empty, needs OAuth)
  ├── configs/
  ├── leaderboards/
  ├── logs/                       (rclone_backup_YYYYMMDD.log lives here)
  ├── photos/                     Samba [photos] share - personal photos, unrelated to project
  ├── portfolio_outputs/
  ├── sweep_results/_inbox/       worker rsync target
  └── market_data/
      ├── futures/                2.2 GB, 87 CSVs (TradeStation: ES, CL, NQ, GC, SI, RTY, YM, HG, AD, BP, EC, JY, BTC, NG, US, TY, W × daily/5m/15m/30m/60m/1m)
      └── cfds/
          ├── ohlc/               2.1 GB, 120 CSVs + 1 .bcf (Dukascopy TDS exports, 24 symbols × D1/H1/M30/M15/M5)
          ├── ticks_dukascopy_tds/   32 GB, 130,238 .bfc files (24 symbol subdirs × YYYY/MM-DD.bfc, TDS proprietary binary)
          ├── ticks_dukascopy_raw/   empty - future dukascopy-python parquet downloads
          ├── ticks_mt5_the5ers/     empty - future MT5 tick exports from The5ers
          └── tds.db              5.2 MB (TDS settings database)
  ```
- **Samba `[data]` share** covers entire `/data/` tree - Latitude can remap Z: to `\\192.168.68.53\data` any time
- **rclone v1.60.1-DEV** installed; `~/.config/rclone/rclone.conf` configured with `gdrive` remote (OAuth done via `rclone authorize` on Latitude, token pasted back into headless config Session 67)
- **Nightly backup:** `/usr/local/bin/backup_to_gdrive.sh` + user cron `30 2 * * *` — syncs `leaderboards/`, `portfolio_outputs/`, `sweep_results/`, `configs/` to `gdrive:c240_backup/`. Deliberately excludes market data + photos (regenerable/personal). **End-to-end verified** — test marker `.backup_test_marker` synced to `gdrive:c240_backup/configs/`.
- **Google Drive mirror for canonical cluster outputs (2026-05-01):** use `python run_cluster_results.py mirror-backup --storage-root <canonical_sweep_results_root> --backup-root "G:\\My Drive\\strategy-data-backup"` from any machine that can see the canonical storage root. This mirrors the active exports (`master_leaderboard.csv`, `master_leaderboard_cfd.csv`, `ultimate_leaderboard_FUTURES.csv`, legacy alias `ultimate_leaderboard.csv`, `ultimate_leaderboard_cfd.csv`) into `strategy-data-backup\\leaderboards\\` and copies the selected or latest canonical run folder into `strategy-data-backup\\sweep_results\\runs\\`. Disaster recovery requires the run folders and manifests, not just the ultimate CSVs. Historical futures strategy pools are preserved separately in Drive as `ultimate_leaderboard_LEGACY_FUTURES_649rows_2026-04-04.csv` and `ultimate_leaderboard_bootcamp.csv`; do not treat the mirrored `ultimate_leaderboard.csv` name as "the old futures corpus" anymore.
- **Physical relocation (Session 67):** moved under house 2026-04-19. Shut down cleanly, auto-booted on power restore, all services + data + rclone config + cron intact. No RAID/disk errors.
- **NOT YET on c240:** Gen 9 data (leaderboards/sweep_results/portfolio_outputs from old disk - blocked until Gen 9 pins fixed, if at all - gdrive backup should be restored from instead once online)

#### Gen 8 (DL380p, dl380p) — COMPUTE WORKER (SLEEPS WHEN IDLE)
- Ubuntu 24.04, IP 192.168.68.71, Tailscale 100.76.227.12, iLO 192.168.68.76
- MAC: ac:16:2d:6e:74:2c
- **Session 72g CPU UPGRADE COMPLETE.** 2× E5-2697 v2 + 2 heat sinks installed successfully. 48 threads expected when back online (currently 12 with the v1 chip). Rob verified both CPUs seat properly; RAM reslotted for dual-socket balance (see RAM layout below).
- **RAM layout (Session 72g, per-socket balanced):**
  - CPU1: 16GB @ 1C + 16GB @ 2G + 8GB @ 7J = **40 GB**
  - CPU2: 16GB @ 12A + 16GB @ 11E + 8GB @ 6L = **40 GB**
  - **Total: 80 GB DDR3 ECC RDIMM.** 16GB sticks in outer slots (farthest from CPU), 8GB on inside. Different channels per letter — no same-channel size mixing.
- **FANS BLOCKER — waiting for 2× replacement fans.** Dual-CPU DL380p Gen 8 requires **6 fans** in bays 1-6. Rob currently has 4 (bays 1, 2, 5, 6 — split 2+2 across both sides for airflow). Bays 3 + 4 empty. Will boot with warnings + non-redundant cooling, WILL throttle under sweep load. **Ordered 2× HP 662520-001 from Interbyte Computers (eBay) AU$4 each + $11 postage. Est. delivery Mon 27 Apr – Mon 4 May 2026.** Seller asked re: combined postage.
- **Gen 8 powered OFF under house** until fans arrive. No access needed meantime.
- **Always-on once fans arrive (Session 72h/73 HARD RULE).** Auto-shutdown cron to be disabled when Gen 8 comes back online.
- BIOS: HP P70 (Feb 2014) — supports E5-2697 v2 ✅, no update needed
- **RAM: DDR3 ECC RDIMM** — NOT DDR4! Cannot share DIMMs with Gen 9 or R630.
- SSH: socket disabled, service enabled, `ssh-recover.service` at 25s, `@reboot sleep 45` root cron fallback
- WOL persistent via netplan, ARP flush on boot (cron), auto-shutdown 30min idle (cron), iLO power policy always-on
- **Session 67 rework:**
  - `~/.ssh/config` rewritten — gen9/gen9-ts removed, c240/c240-ts/r630/r630-ts/latitude/x1 added
  - `/usr/local/bin/post_sweep.sh` retargeted from `gen9:/data/sweep_results/runs/` → `c240:/data/sweep_results/_inbox/`
  - Repo pulled from `e4b4a82` → `6189bd2`
  - Venv created at `~/venv` (was missing); requirements.txt + `dukascopy-python 4.0.1` installed
  - `.bashrc` has `psc-activate` alias
  - c240 pubkey added to `~/.ssh/authorized_keys`; Gen 8's pubkey (`dl380p-deploy`) pushed to c240 and r630
- **KNOWN TIMING QUIRK:** SSH may take 5+ min to come up after reboot — slow HP BIOS POST, not a config issue. See "Server timing notes".

#### Dell R630 — COMPUTE WORKER (SLEEPS WHEN IDLE)
- Ubuntu 24.04.4 LTS, hostname `r630`, IP 192.168.68.78 (+ stale DHCP lease .75 on eno1, clean via netplan when convenient), Tailscale 100.85.102.4
- Credentials: rob / Ubuntu123
- **Threads: 88** (dual E5-2699 v4, 44C/88T)
- **Storage:** 838 GB SSD, LVM expanded to 823 GB root (778 GB free)
- SSH: socket disabled, service enabled, `ssh-recover.service` active, ARP flush + SSH fallback @reboot crons. **Auto-shutdown cron TO BE DISABLED** per Session 72h/73 always-on HARD RULE (pending implementation).
- WOL: MAC **ec:f4:bb:ed:bf:00** (eno1), netplan wakeonlan set, `wake-r630.bat` on Latitude + `wake-r630.sh` on c240
- **Session 67 rework:**
  - `~/.ssh/config` written (was empty) — c240/c240-ts/gen8/gen8-ts/latitude/x1 aliases
  - `/usr/local/bin/post_sweep.sh` retargeted to c240 `_inbox` pattern
  - Repo cloned via HTTPS (HEAD `6189bd2`)
  - `python3.12-venv` + `python3-pip` + `ipmitool` + `rclone` + `wakeonlan` packages installed
  - Venv rebuilt at `~/venv`; requirements.txt + `dukascopy-python 4.0.1` installed
  - `.bashrc` has `psc-activate` alias
  - SSH keypair generated (`rob@r630`); pubkey pushed to c240 + gen8
  - c240 pubkey added to `authorized_keys`
  - Smoke test passes: numpy 2.1.3, pandas 2.2.2, engine modules import cleanly
- **KNOWN TIMING QUIRK:** can fail first WOL attempt (older Dell NIC behaviour). Usually responds on 2nd burst 90s later. See "Server timing notes".

#### Pending Hardware
- **Dell R730 on eBay** (service tag 3TW3T92, Oakleigh VIC, $500 bid / $1000 BIN) — specs unknown, asked seller for CPU/RAM info. Mfg Jan 2016 (v3 Xeon era). NO HARD DRIVES. Don't bid without knowing specs.
- **RAM needed:** DDR4 ECC RDIMM 32GB sticks for Gen 9 (match 2Rx4 DDR4-2400 or faster). DDR3 for Gen 8.
- **Skip:** Anything DDR3 for Gen 9/R630. Only DDR4 ECC RDIMM.

### Network
- **New ISP:** Carbon Comms, 500/50 Mbps NBN, **static IP** (being connected)
- **Router:** XE75 Pro at 192.168.68.1
- Static IP enables: direct SSH from field, dashboard access, Contabo push-to-home
- Recommendation: Keep Tailscale as primary remote access. Use static IP for specific services only.

### Cloud Infrastructure (DELETED — Session 69)
- All GCP cloud code deleted in Session 69 (cloud/, run_spot_resilient.py, run_cloud_sweep.py, Dockerfile, .dockerignore, CI workflow, console scripts)
- ~10,000 LOC removed, 89 files deleted
- GCP project and strategy-console VM can be decommissioned at GCP console level when convenient

### Strategy Engine Status
- **Ultimate leaderboard:** ~454 strategies (414 bootcamp-accepted) across 8 markets (ES, CL, NQ, SI, HG, RTY, YM, GC)
- **Vectorized engine:** 14-23x speedup, zero-tolerance parity confirmed. All configs use `use_vectorized_trades: true`
- **12 strategy families:** 3 long (trend, MR, breakout) + 3 short + 9 subtypes (3 per family)
- **Leaderboard architecture (2026-05-01 naming clarification):** the active pipeline is now neutral across both universes. Futures/generic canonical exports write `family_leaderboard_results.csv`, `master_leaderboard.csv`, and `ultimate_leaderboard_FUTURES.csv`, plus a backward-compatible alias copy at `ultimate_leaderboard.csv`; CFD runs write `family_leaderboard_results.csv`, `master_leaderboard_cfd.csv`, and `ultimate_leaderboard_cfd.csv`. `bootcamp_score` and `*_bootcamp.csv` ranking views are no longer emitted by the active sweep pipeline, but the legacy historical futures files `Outputs/ultimate_leaderboard.csv` and `Outputs/ultimate_leaderboard_bootcamp.csv` remain important archives.
- **Research ranking:** canonical leaderboard order now favors `accepted_final`, stronger `quality_flag`, higher `oos_pf`, higher `recent_12m_pf`, higher `calmar_ratio`, higher `deflated_sharpe_ratio` (where available), higher `leader_pf`, and smaller `leader_max_drawdown`, with net PnL and trade frequency as later tie-breakers.
- **Portfolio selector:** 6-stage pipeline with 3-layer correlation, block bootstrap MC, regime survival gate. Candidate gating no longer uses `bootcamp_score_min`; selector reads the neutral strategy pool and does program-specific ranking inside the selector/MC layer.
- **Prop firm system:** Bootcamp, High Stakes, Pro Growth, Hyper Growth — all with daily DD enforcement
- **CFD sweep infrastructure (Session 65):**
  - `run_local_sweep.py` — single-market local sweep runner (replaces GCP cloud runners)
  - `run_cluster_sweep.py` — batch orchestrator with manifest tracking + resume support
  - `configs/cfd_markets.yaml` — 24 CFD market configs with engine params + cost profiles
  - `configs/local_sweeps/` — 24 generated per-market sweep configs (all 5 timeframes each)
  - `scripts/convert_tds_to_engine.py` — TDS Metatrader CSV -> TradeStation format converter
  - `scripts/generate_sweep_configs.py` — generates sweep configs from market master config
- **CFD swap rates gathered:** CL=$0.70/micro/night (10x Fri!), SI=$4.05, GC=$2.20, indices near-zero, FX $0.10-0.26
- **Session 69 cleanup:** Cloud code deleted, ES config bugs fixed, test suite green (236 pass, 0 fail)
- **Session 70 first CFD sweep:** ES daily Dukascopy on c240, 7m runtime, 13 accepted strategies. Max PnL $1.0M (passed $20M critical threshold). Plausibility validated.

### r630 ES 5m sweep OOM postmortem (Session 72g, 2026-04-21)
- **Launched:** 19/04/26 21:08 UTC on r630 (ES 5m Dukascopy, all 15 strategy families)
- **Expected finish:** ~11 AM 21/04/26 (~62h runtime)
- **Actual end:** **OOM-killer at 20/04/26 06:26:40 UTC — 9h 18m in (~15% through plan)**
- **Auto-shutdown cron** then powered r630 off at 07:00 UTC once system went idle (working as designed)
- **Root cause:** `configs/local_sweeps/ES_5m.yaml` specified `max_workers_sweep: 82` and `max_workers_refinement: 82` (hard override of global `config.yaml` default of 2). r630 has only **62 GiB RAM + 8 GiB swap**. 82 × 5m dataset in parallel exhausted memory during REFINEMENT stage.
- **Progress at OOM** (from `status.json`):
  - Family 1 (mean_reversion): initial sweep ✅ complete (31,008 combos tested)
  - Family 1 refinement: 49.5% (190 / 384 items, 2/5 candidates)
  - Families 2-15: not started
- **Salvageable on disk** at `~/python-master-strategy-creator/Outputs/es_5m_dukascopy_v1/ES_5m/`:
  - `mean_reversion_filter_combination_sweep_results.csv` (21.5 MB, 31,008 rows)
  - `mean_reversion_promoted_candidates.csv` — **14 promoted candidates** with quality flags. Top pick `ComboMR_DownClose_ReversalUpBar_CloseNearLow_InsideBar_ATRExpansionRatio_CumulativeDecline` is ROBUST with IS PF 2.24 → OOS PF 2.59 → recent 12m PF 3.16 (improving OOS).
- **Dataset sizes on disk** (ES CFD Dukascopy, `/data/market_data/cfds/ohlc_engine/`):
  - daily 0.25 MB (1×)
  - 60m 4.3 MB (17×)
  - 30m 8.2 MB (33×)
  - 15m 16.1 MB (65×)
  - **5m 47.6 MB (192×)**
- **Worker review IN PROGRESS (incomplete Session 72g):**
  - ✅ Confirmed `ES_5m.yaml` workers=82 — not 2, not 88
  - ✅ Dataset sizes by TF captured
  - ⏸️ Per-worker memory measurement — `mem_probe.py` staged at `/tmp/mem_probe.py` on r630 (rewritten to use /proc/self/status, no psutil dep). Didn't run due to SSH/venv hiccups.
  - ⏸️ Nested parallelism check (grep engine modules for ProcessPool / Pool() inside workers) — would explain why OOM dump showed "30+" processes when config specified 82.
  - ⏸️ Prior 15m sweep search — Rob believes 15m succeeded; need to locate the output dir and confirm.
  - ⏸️ Concrete RAM + worker recommendation — needs measured per-worker footprint first.

---

## Open Issues (Priority Order)

1. **Delete Latitude's TDS source copy** (~33 GB) now that c240 has a verified full mirror at `/data/market_data/cfds/ticks_dukascopy_tds/` (130,239 files, matching source count). Free up Latitude disk:
   - Verify: `(Get-ChildItem 'C:\Users\Rob\Downloads\Tick Data Suite\Dukascopy' -Recurse -File).Count` should match `find /data/market_data/cfds/ticks_dukascopy_tds -type f \| wc -l` (130,238) + 121 top-level in ohlc/
   - Then: `Remove-Item 'C:\Users\Rob\Downloads\Tick Data Suite' -Recurse -Force`
2. **Clean up stale Tailscale device.** Old `c240` entry (100.104.66.48) still in tailnet. Remove via [Tailscale admin console](https://login.tailscale.com/admin/machines).
3. **CIMC network config for C240.** CIMC on dedicated port via DHCP; IP not captured. Check router ARP for MAC `00:A3:8E:8E:B3:84` or `nmap -sn 192.168.68.0/22`.
4. **Gen 8 CPU install DONE (Session 72g).** 2× E5-2697 v2 + heat sinks installed. RAM re-balanced 40GB per CPU (see Gen 8 section). **Now blocked on 2 missing fans (bays 3-4)** — ordered HP 662520-001 from Interbyte Computers eBay AU$19 total, est. Mon 27 Apr - Mon 4 May 2026. Gen 8 OFF under house until fans arrive. Do NOT power on with 4 fans under sweep load — will throttle.
5. **Disable auto-shutdown crons on gen8 + r630.** Required to implement Session 72h/73 always-on HARD RULE. Remove any cron entry that powers down on idle. Verify by leaving machines idle for 2+ hours and confirming they stay up. R630: action next convenient SSH session. Gen 8: action when it comes back online post-fans.
6. **R630 stale DHCP lease.** `eno1` shows both `192.168.68.78/22` (static) and `192.168.68.75/22` (stale DHCP). Clean via netplan when convenient — `sudo netplan try` to drop the DHCP lease.
7. **X1 Carbon offline** — also need to verify laptop SSH isolation when back online (inspect `C:\ProgramData\ssh\administrators_authorized_keys` AND `C:\Users\rob_p\.ssh\authorized_keys` — no server pubkeys should be present).
8. **CFD cost realism is now PARTIALLY modeled in selector MC, but only when rich trade artifacts exist.** Spread/swap costs from `configs/cfd_markets.yaml` can now flow into Monte Carlo when `strategy_trades.csv` carries fields like `entry_time`, `exit_time`, and `bars_held`. The remaining blocker is reliability: finalized runs still often lack those richer artifacts, so challenge timelines can still fall back to weaker cost-blind paths.
9. **Challenge-vs-funded selector mode is still not explicit.** Program rules (targets, DD, profitable days, funded-stage behavior) are already simulated, but the selector still lacks a first-class `selection_mode` / challenge-specific scoring layer.
10. **Dashboard Live Monitor broken.** Engine log and Promoted Candidates sections don't work during active runs.
11. **g9 not yet a compute-cluster member.** Repo clone, market_data, sweep scripts, samba membership, post_sweep.sh all need to be set up before g9 can take cluster work.
12. **r630 5m sweep OOM'd with 82 workers (Session 72g).** See "r630 ES 5m sweep OOM postmortem" section in Strategy Engine Status. Need: (a) per-worker RAM measurement, (b) nested-pool audit in engine, (c) safe worker count derivation, (d) decide if `configs/local_sweeps/ES_5m.yaml` gets workers dropped from 82 ? e.g. 20, or whether sweep needs to move to c240 (64 GiB same constraint) or r630 RAM gets upgraded. 14 promoted candidates from partial run ARE usable ? don't discard.

---

## Project History (Sessions 0-62)

### Phase 1: Foundation (Sessions 0-5, Mar 16-18 2026)
- **Session 0:** Project review, first ES 60m run analyzed (trend REGIME_DEPENDENT, MR STABLE, breakout BROKEN_IN_OOS), created CLAUDE.md
- **Session 1:** Quality scoring (0-1 continuous), BORDERLINE detection, promotion gate capped at 20, compute budget estimator, candidate dedup
- **Session 2:** Config.yaml (single source of truth), yearly consistency analysis, multi-dataset loop support, OOS split date configurable
- **Session 3:** Cloud deployment prep — Dockerfile, requirements.txt, DigitalOcean run scripts, Sydney region
- **Session 4:** Structured logging (ProgressTracker + status.json), cloud launcher timeout fix
- **Session 5:** 11 smoke tests, master leaderboard aggregator, timeframe-aware refinement grids (hold_bars auto-scales)

### Phase 2: Cloud Infrastructure (Sessions 6-14, Mar 18-21 2026)
- **Session 6:** Hybrid filter parameter scaling (SMA/ATR/momentum scale per timeframe), 48-core cloud config, memory estimation
- **Session 7:** Prop firm challenge simulator — The5ers Bootcamp/HighStakes/HyperGrowth configs, Monte Carlo pass rate
- **Session 8:** CRITICAL BUG FIX — portfolio evaluator now passes timeframe to feature builders. GCP automation scripts created.
- **Session 9:** 10 GCP automation bugs fixed (SCP paths, race conditions, username detection). Streamlit dashboard created.
- **Session 10:** GCP download reliability — dynamic username via `whoami`, tar fallback, safety gate (refuse destroy if 0 files)
- **Session 11:** Windows-first GCP launcher redesign (`cloud/launch_gcp_run.py`) — manifest, bundle, deterministic paths, tarball retrieval
- **Session 13:** Dashboard upgrade — VM cost visibility, dataset progress, best candidates panel, result source grouping
- **Session 14:** One-click `run_cloud_sweep.py` wrapper, `LATEST_RUN.txt` pointer

### Phase 3: Multi-Timeframe & Quality (Sessions 21-34, Mar 23-26 2026)
- **Session 21:** Migrated from Australia to US regions (better SPOT pricing), zone/machine configurable via YAML `cloud:` section
- **Session 22:** Fixed remote Python bootstrap (python3.12 explicit for venv creation)
- **Session 24:** Dashboard overhaul — 3-tab layout (Control Panel, Results Explorer, System), plotly charts
- **Session 33:** Pre-flight validation, vectorized filter status check (not yet implemented)
- **Session 34:** CRITICAL FIX — GCS bundle staging for fire-and-forget mode (43MB SCP was hitting SPOT preemption window)
- **Session 35:** Multi-VM split (VM-A + VM-B), `download_run.py` with merge and ultimate leaderboard

### Phase 4: Strategy Expansion (Sessions 37-45, Mar 26-29 2026)
- **Session 37:** 9 strategy subtypes (3 per family), leaderboard enriched with calmar/win_rate/trades_per_year
- **Session 38:** Cross-dataset portfolio evaluation — all accepted strategies evaluated together, cross-TF correlation matrix
- **Session 39:** Short-side strategies (15 new filters, 3 short families), direction wired through engine
- **Session 40:** Per-timeframe dataset caching, concurrent small-family execution, exit types verified active in refinement
- **Session 41:** Widened exit grids — trend trailing_stop_atr up to 7.0, breakout up to 5.0, MR profit_target up to 3.0
- **Session 42:** 7 universal filters (InsideBar, OutsideBar, GapUp/Down, ATRPercentile, HigherHigh, LowerLow), dropped 5m (zero accepted)
- **Session 43:** Shared ProcessPoolExecutor across families, optional portfolio evaluation, granular status stages
- **Session 44:** Refinement as_completed() (30%→80%+ CPU), task dedup before dispatch
- **Session 45:** CRITICAL BUG FIX — position sizing used current_capital (compounding) instead of initial_capital. All dollar figures were wrong.

### Phase 5: Portfolio Selection (Sessions 47-53, Mar 31 2026)
- **Session 47:** Portfolio selector module — 6-stage pipeline with C(n,k) sweep, Pearson correlation gate, MC pass rate, sizing optimizer
- **Session 48:** Rebuild fix (fallback to filter_class_names), parallelized evaluator, MC step rate bug fix
- **Session 49:** Rebuild 0-trade root cause (min_avg_range misused as filter param), all 20/20 market/TF combos verified
- **Session 50:** Portfolio MC fixes — step rate mixing, daily-resampled trades, correlation dedup, micro contract sizing, time-to-fund
- **Session 51:** Portfolio overhaul — OOS PF threshold lowered, sizing optimizer minimizes time-to-fund, strategy_trades.csv
- **Session 52:** Multi-program prop firm (per-step targets, daily DD enforcement, Pro Growth config, configurable program selector)
- **Session 53:** Parallelized generate_returns.py with ThreadPoolExecutor + data file caching

### Phase 6: Cloud Migration & Advanced MC (Sessions 56-62, Apr 2-4 2026)
- **Session 56:** Migrated to new GCP account (Nikola), new console VM, bucket, SSH keys
- **Session 58:** Portfolio selector upgrades — 3-layer correlation, Expected Conditional Drawdown, block bootstrap MC, regime survival gate
- **Session 59:** Bulletproof SPOT runner (`run_spot_resilient.py`), 9 new market configs (EC, JY, BP, AD, NG, US, TY, W, BTC)
- **Session 60:** Vectorized portfolio MC (numpy 2D arrays), parallel combinatorial sweep, multi-program runner
- **Session 61:** Vectorized trade simulation loop (14-23x speedup, zero-tolerance parity), prop firm config fixes (daily DD pause vs terminate)
- **Session 62:** Repo reorganization for Claude Desktop compatibility, archived 93 session files + 60 temp dirs, fixed .gitignore

### Phase 7: Local Cluster & CFD Pipeline (Sessions 63-67, Apr 14-19 2026)
- **Session 63:** Dukascopy architecture decision, SP500 tick download, The5ers MT5 exports, home lab network setup
- **Session 65:** CFD data pipeline built end-to-end: TDS format converter (24 markets), engine loader "Vol" support, 24 CFD market configs, local sweep runner, batch cluster sweep launcher with resume, config generator (24 sweep YAMLs). Cloud infrastructure deprecated.
- **Session 66 (2026-04-18):** Gen 9 decommissioned. Cisco C240 M4 commissioned at 192.168.68.53. 2× E5-2673 v4 (40C/80T), 64 GB RAM, 10.9 TB SAS (ex-Gen 9 drives). Ubuntu 24.04.4, LVM layout: / 100 GB + /data 10 TiB ext4. SSH key auth, NOPASSWD sudo, Tailscale 100.120.11.35, Samba [photos] share live.
- **Session 67 (2026-04-19):** c240 full buildout + cluster onboarding + tick data migration + restructure + rclone + relocation.
  - c240: all packages installed, ssh-recover.service, ARP-flush cron, repo cloned, venv with dukascopy-python, SSH keypair + config + WOL scripts + post_sweep.sh template, [data] Samba share added.
  - Gen 8 + R630 fix-ups: ssh config rewritten (gen9 refs gone), post_sweep.sh retargeted c240, repos updated, venvs built, full bidirectional SSH mesh c240↔gen8↔r630 verified.
  - Tick data transfer: 33.4 GB / 130,359 files from Latitude TDS cache → c240 via robocopy over Samba (1h 4m, 538 MB/min). 
  - `/data` restructure: `market_data/tradestation/` → `market_data/futures/`; `tick_data/dukascopy_tds/*.csv` → `market_data/cfds/ohlc/`; `tick_data/dukascopy_tds/<SYMBOL>/` → `market_data/cfds/ticks_dukascopy_tds/`; stale empty scaffolding removed.
  - 7.3 GB wrong-path duplicate (`/data/market_data/tick_data/` from earlier crashed chat) deleted after per-file twin verification (zero unique content lost except 7-byte `.writetest` marker).
  - rclone gdrive OAuth completed (headless flow: `rclone authorize` on Latitude, paste token into c240 config). First backup run successful — `gdrive:c240_backup/configs/.backup_test_marker` verified on remote. Nightly cron live at 02:30.
  - Latitude Z: drive remapped from dead `\\192.168.68.69\data` → `\\192.168.68.53\data` (persistent, credentials saved).
  - c240 physically relocated under house. Powered back on cleanly — health check confirms all services, /data mount, rclone config, cron, tailscale intact. No RAID or disk errors.
- **Session 71 (2026-04-19):** Dukascopy conversion scale-out. All 120 TDS CSVs converted to engine format via `scripts/convert_tds_batch.py` on c240. Full CFD OHLC dataset engine-ready at `/data/market_data/cfds/ohlc_engine/`.
- **Session 71b (2026-04-19):** Gen 9 revived as standalone **autonomous business host** (`g9` at 192.168.68.75, Tailscale 100.71.141.89). Fresh Ubuntu 24.04.4 on new 128 GB SATA SSD boot drive. 2× 146 GB SAS drives configured as RAID0 logical drive via ssacli 6.45-8.0 → `/dev/sdb` → LVM `data-vg/data-lv` → `/data` (269 GB ext4). Installed: Docker 29.1.3, Node.js v24.14.1, Tailscale 1.96.4, Python 3.12.3 venv, ssacli, rclone. SSH via ProxyJump c240 (Latitude Wi-Fi ARP quirk) + direct Tailscale. NOPASSWD sudo, ssh-recover.service, ARP-flush cron, sleep/suspend/hibernate masked (always-on). `/data/{hermes,openclaw,backups,logs}/` layout. Backup script + 02:45 cron in place; rclone gdrive OAuth completed end-to-end (verified via test-marker sync). **g9 is NOT a backtesting cluster member** — deliberately isolated from sweep workflow.
- **Session 72 (2026-04-20) — RETIRED:** Hermes + OpenClaw deployed on g9 with full handover sync, deploy keys, Telegram bot, cluster SSH. **Fully decommissioned Session 75 (2026-04-26).** Transition path: Claude Code + Claude Remote Control replaced Hermes for ops; g9 redirected to compute-worker role.

### Key Architectural Decisions Made Along the Way
- **Fixed position sizing** (Session 45): initial_capital only, no compounding — matches prop firm rules
- **Dropped 5m timeframe** (Session 42): zero accepted strategies, ~50% of compute cost
- **Fire-and-forget via GCS** (Session 34): bundle staged to GCS before VM creation, eliminates SCP preemption window
- **Vectorized trades** (Session 61): numpy 2D arrays replace per-bar Python loop, 14-23x faster
- **Block bootstrap MC** (Session 58): preserves crisis clustering vs naive shuffle
- **3-layer correlation** (Session 58): active-day + DD-state + tail co-loss replaces simple Pearson
- **Dukascopy for discovery, The5ers for validation** (Session 63): tick data architecture separates strategy discovery (deep Dukascopy history) from execution validation (The5ers real spreads)
- **Local cluster replaces cloud** (Session 65): `run_local_sweep.py` + `run_cluster_sweep.py` replace GCP SPOT runners. Zero cloud dependencies. ~248 threads available locally once g9 joins (C240: 80, Gen 8: 48 post-CPU-upgrade, R630: 88, g9: 48 — Session 75 decommissioned Hermes and reassigned g9 to compute).
- **Hermes/OpenClaw decommissioned** (Session 75): one-week experiment retired. Claude Code + Claude Remote Control hub on X1 Carbon replaced agent-driven ops. Simpler, no API costs, no security surface from agent SSH access.

---

## Architecture Decision: Compute Cluster

```
Latitude (main control, home + field, SSH via Tailscale)
    │
    ├──► X1 Carbon (always-on, in drawer, Claude + Desktop Commander)
    │        └── SSH relay to all servers
    │
    ├──► C240 M4 (ALWAYS ON — data hub + compute, 80 threads — Gen 9 replacement)
    │     ├── holds master/ultimate leaderboards (local 10 TiB /data)
    │     ├── holds market data — TradeStation, MT5 ticks, Dukascopy ticks
    │     ├── Samba share to X1 Carbon + Latitude (photos live, data shares pending migration)
    │     ├── rclone → Google Drive (pending setup)
    │     ├── receives sweep results from Gen 8 / R630 via rsync (pending)
    │     ├── runs leaderboard updater + portfolio selector
    │     └── wakes Gen 8 / R630 via WOL when compute needed
    │
    ├──► Gen 8 (SLEEPS WHEN IDLE — compute worker, 48 threads after CPU upgrade)
    │     └── woken by Latitude / X1 Carbon / C240 via WOL
    │
    └──► R630 (SLEEPS WHEN IDLE — compute worker, 88 threads)
          └── woken by Latitude / X1 Carbon / C240 via WOL
```

- **Google Drive is backup/remote viewing ONLY — never used for compute reads**
- Market data + leaderboards stay on local SSD/SAS for speed
- Workers crunch sweeps, rsync results to C240 over LAN
- Portfolio selector runs on C240 (or R630), reads from local SAS
- C240 NEVER sleeps. Workers sleep when idle.
- **Session 74 control-plane update:** the X1 now exposes two independent Claude Remote Control entry points from Rob's phone: one for `betfair-trader`, one for `python-master-strategy-creator`. The strategy hub is dispatcher-only and should be treated as a parallel control path, not a shared session.

---

## Compute Rental Side Hustle (Future — Post Trading Stable)

**Concept:** Rent idle cluster compute to retail quants, ML students, researchers.

**Two tiers:**
- Tier 1: Raw CPU rental ($0.04 AUD/thread-hour), fully automated, no support
- Tier 2: Managed QuantSweep Service — customer uploads strategy, gets results in 24hrs, higher margin

**Economics:** 240 threads, $3.20 AUD/day electricity, ~$2K AUD/month net at 30-40% utilisation. Scalable — each $350 server adds ~60 threads, pays for itself in 6 weeks. Tax deductible capex.

**Implementation order:**
1. VLAN isolation — rental network must be completely separate from MT5/trading network (security critical)
2. Docker containerisation — customer code can't break out to host
3. Best-effort SLA (no liability for interruptions)
4. Python job queue + Stripe payments + AI chatbot support
5. Beta: 3 customers at discount, 3 months, then go public

**Positioning:** "Quant Sweep Infrastructure as a Service" — not generic compute rental
**Timeline:** Start after trading stable and generating. ~2 weeks setup, month 3 launch.

---

## Server Timing Notes

**Don't assume "not responding" means broken.** These servers each have quirks that look like failure but are normal:

| Server | Wake/Boot Behaviour | What looks like failure but isn't | Action |
|---|---|---|---|
| **Gen 8** (HP DL380p) | Slow HP BIOS POST — SSH can take **5+ minutes** after power-on | Connection refused / timeout for first 5 min | Wait. Second attempt at T+5min works. |
| **R630** (Dell) | Often ignores **first WOL burst**. Second burst 60-90s later reliably wakes it. | No ARP entry, ping "destination unreachable" | Re-send WOL (`wake-r630.bat` / `wake-r630.sh`), wait 90s, retry SSH |
| **C240** (Cisco) | POST is fast, SSH within ~90s. CIMC takes longer to come up on dedicated port. | Tailscale may show offline for up to 2 min post-boot | Wait 2 min, Tailscale re-registers |
| **All** | `ssh-recover.service` is a **25-second delayed restart** of `ssh.service` after boot | First SSH attempt during window T+0 to T+25s fails | Wait 30s after any reboot before first SSH |
| **All** | `@reboot sleep 45` root cron is a **final fallback** — restarts SSH at T+45s | Only triggers if earlier methods failed | Baseline recovery |

**Robocopy over Samba** to c240 runs ~**538 MB/min** over gigabit LAN with `/MT:16`. A 33 GB tick-data migration = ~1h. Silent during transfer (`/NFL /NDL` flags mean "no file list / no dir list"). Check progress via destination size (`ssh c240 "du -sh /data/..."`), not log file.

**WOL pattern:** 5 bursts × 3 broadcast addresses (`192.168.68.255`, `192.168.71.255`, `255.255.255.255`) × ports 7 + 9 every 1 second. See `/usr/local/bin/wake-gen8.sh`, `wake-r630.sh`, `wake-all.sh` on c240 and `C:\Users\Rob\wake-*.bat` on Latitude.

**If WOL fails, use IPMI:**
```
ssh gen8 "sudo ipmitool -I lanplus -H 192.168.68.76 -U Administrator -P <pw> power on"   # Gen 8 iLO
# R630: iDRAC IP TBD, same pattern
```

---

## On the Horizon

- **Session 73 PRIORITY (still deferred): ES sanity-check sweep across 4 TFs (daily / 60m / 30m / 15m). ES-only, no 5m.** Runs on c240 alone (~30–60 min), no WOL needed. Gated on worker review completion so we don't repeat the r630 OOM mistake at c240 scale. If clean: Session 74 fans out to 23 markets × 4 TFs.
- **Finish the r630 worker review** (carried over from Session 72g). Specifically: run `mem_probe.py` on r630 to get per-TF per-worker footprint, grep engine modules for nested ProcessPool, confirm whether 15m previously succeeded, then decide workers-per-machine (drop ES_5m.yaml workers from 82 to something safe, OR upgrade r630 RAM from 62 GiB → 128 GiB).
- **Bring g9 into the compute cluster** — clone repo, set up venv, sync market_data + configs from c240, install post_sweep.sh, decide on samba role.
- **Delete Latitude TDS source** (`C:\Users\Rob\Downloads\Tick Data Suite\`, ~33 GB) — c240 has verified full mirror at `/data/market_data/cfds/ticks_dukascopy_tds/`.
- **Capture C240 CIMC IP** — check router ARP for MAC `00:A3:8E:8E:B3:84`.
- **Clean up stale Tailscale `c240` device** (100.104.66.48) via admin console.
- **Gen 8 CPU install** — 2× E5-2697 v2 arrived, install under house, verify 48 threads.
- **R630 netplan cleanup** — drop stale `192.168.68.75` DHCP lease from eno1.
- **Full 24-market sweep (Session 74)** — `python run_cluster_sweep.py` (all markets × 4 TFs = 92 sweeps, 5m excluded) on c240 orchestrating gen8 + r630 + g9. Gated on Session 73 ES validation passing.
- Implement CFD swap/overnight cost modeling in MC simulator (cost profiles in `configs/cfd_markets.yaml`).
- **Challenge vs Funded mode** — implement spec in `docs/CHALLENGE_VS_FUNDED_SPEC.md`.
- Static IP port forwarding setup once new ISP connected.
- Strategy templates to reduce search space.

---

## Connection Quick Reference

```
# SSH aliases (from Latitude or X1 Carbon)
ssh c240          # Cisco C240 M4 — LAN 192.168.68.53, Tailscale 100.120.11.35 (device name c240-1)
ssh gen8          # Gen 8 Tailscale (100.76.227.12) — LAN 192.168.68.71
ssh r630          # Dell R630 Tailscale (100.85.102.4) — LAN 192.168.68.78
ssh x1            # X1 Carbon Tailscale (100.86.154.65)
#
# X1 strategy hub control plane (Session 74)
# C:\Users\rob_p\strategy-ops\strategy-hub-watchdog.ps1   # watchdog loop for Claude Remote Control in python-master-strategy-creator
# C:\Users\rob_p\strategy-ops\pull-repo.ps1               # main-only fast-forward pull helper
# C:\Users\rob_p\strategy-ops\pull-repo.bat               # Task Scheduler wrapper for the pull helper
# C:\Users\rob_p\strategy-ops\logs\strategy-hub.log       # watchdog exit log
# StrategyRepoPull                                        # scheduled task, every 5 min, IgnoreNew, battery-safe
# %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StrategyHubWatchdog.vbs   # minimized-but-visible startup launcher
ssh g9            # Gen 9 autonomous business host — LAN 192.168.68.50 via ProxyJump c240 (was .75 pre-72)
ssh g9-ts         # Gen 9 Tailscale direct (100.71.141.89) — works from anywhere

# SSH mesh (c240 ↔ gen8 ↔ r630) — all bidirectional, verified Session 67
# Each box can ssh to any other without password prompt

# Samba shares on c240 (user: rob, password: Ubuntu123)
\\192.168.68.53\photos         # /data/photos — personal photos, separate concern
\\192.168.68.53\data           # /data root — full tree (rw, force_user=rob). Map Z: here.
# \\192.168.68.69\*            # DECOMMISSIONED with Gen 9

# Data layout on c240 (Session 67)
/data/market_data/futures/                      # TradeStation OHLC (87 CSVs, 2.2 GB)
/data/market_data/cfds/ohlc/                    # Dukascopy TDS OHLC (120 CSVs, 2.1 GB)
/data/market_data/cfds/ticks_dukascopy_tds/     # Raw .bfc tick cache (130k files, 32 GB)
/data/market_data/cfds/ticks_dukascopy_raw/     # Future: dukascopy-python parquet
/data/market_data/cfds/ticks_mt5_the5ers/
/data/market_data/cfds/ohlc_engine/             # Engine-ready converted CSVs (120/120 complete, Session 71)
/data/leaderboards/                             # Master leaderboards
/data/sweep_results/_inbox/                     # Worker rsync target
/data/portfolio_outputs/                        # Portfolio selector outputs

# WOL (from Latitude)
C:\Users\Rob\wake-r630.bat      # MAC ec:f4:bb:ed:bf:00 — often needs 2nd burst
C:\Users\Rob\wake-gen8.bat      # MAC ac:16:2d:6e:74:2c — 5 min POST delay normal

# WOL (from c240)
/usr/local/bin/wake-gen8.sh     # MAC ac:16:2d:6e:74:2c
/usr/local/bin/wake-r630.sh     # MAC ec:f4:bb:ed:bf:00
/usr/local/bin/wake-all.sh      # both

# Hermes / OpenClaw — DECOMMISSIONED Session 75 (2026-04-26). All Hermes/OpenClaw users, data, scripts, cron, sudoers, and SSH keys removed from g9 and cluster. Replaced by Claude Code + X1 Carbon Claude Remote Control hub.

# Server creds: rob / Ubuntu123 (all servers)
# C240 sudo: NOPASSWD via /etc/sudoers.d/rob-nopasswd
# GCP SSH: ssh -i C:\Users\Rob\.ssh\google_compute_engine pitman_nikola@35.223.104.173

# Sweep results pipeline (run on worker after sweep):
# /usr/local/bin/post_sweep.sh <sweep_output_dir>
#   -> rsyncs to c240:/data/sweep_results/_inbox/<basename>/
#   -> touches c240:/data/sweep_results/_inbox/.new_result_<basename> as marker

# rclone nightly backup (scheduled, needs one-time OAuth)
# Script: /usr/local/bin/backup_to_gdrive.sh
# Cron:   30 2 * * *
# Targets: leaderboards/ portfolio_outputs/ sweep_results/ configs/ -> gdrive:c240_backup/
# Logs:   /data/logs/rclone_backup_YYYYMMDD.log (14-day retention)

# Quick activate (on any cluster server)
psc-activate        # sources venv + cd to repo + sets PYTHONPATH=.

# iLO / CIMC access
# Gen 9 iLO: https://192.168.68.69   Administrator / PVPT6M5H   (CONFIRMED WORKING Session 72g)
#            ipmitool example (run from c240 where ipmitool is installed):
#            ipmitool -I lanplus -H 192.168.68.69 -U Administrator -P PVPT6M5H chassis status
#            ipmitool -I lanplus -H 192.168.68.69 -U Administrator -P PVPT6M5H sdr type 'Power Supply'
#            ipmitool -I lanplus -H 192.168.68.69 -U Administrator -P PVPT6M5H sel list last 10
Gen 8 iLO: https://192.168.68.76 (old SSL - use Firefox, creds unknown)
R630 iDRAC: IP TBD
C240 CIMC: on dedicated port via DHCP, MAC 00:A3:8E:8E:B3:84, IP TBD — default admin/password
```

## Key Principles
- **ALL SERVERS ALWAYS ON — DO NOT SHUT DOWN ANY SERVER UNDER ANY CIRCUMSTANCES.** c240, g9, gen8, r630 run 24/7 permanently. No WOL cycles, no auto-shutdown, no suspend/hibernate, no "just this once". Power cycles only for planned hardware installs or unplanned outages. Solar + off-peak rates make idle cost irrelevant; reliability of the cluster is the binding constraint. (Session 72h/73 HARD RULE.)
- Always use Desktop Commander before Windows MCP (Windows MCP hangs)
- **Server timing:** see "Server Timing Notes" — Gen 8 needs 5 min post-boot, R630 often needs 2 WOL bursts, give all SSH 30s after reboot
- Full fixes only — no patches
- Drawdown is the binding constraint on The5ers
- Skip DDR3 servers (R710, R610) — only R630/R730 and above
- Gen 8 uses DDR3 RAM, Gen 9 and R630 use DDR4 — do NOT mix
- **Windows↔c240 transfers:** use robocopy over Samba UNC path `\\192.168.68.53\data\` — 538 MB/min, resumable via `/XC /XN /XO` skip flags
- **Large transfers:** robocopy is silent with `/NFL /NDL`. Check progress from dest side (`du -sh`), not logs.
- SPOT zone: us-central1-f; on-demand fallback: us-central1-c (legacy cloud only)
- Dukascopy for strategy discovery, The5ers tick data for execution cost validation
