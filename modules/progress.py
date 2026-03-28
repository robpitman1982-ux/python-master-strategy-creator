from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProgressTracker:
    """Structured progress tracking for cloud monitoring."""

    def __init__(self, output_dir: str | Path, dataset_label: str = ""):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_label = dataset_label
        self.status_path = self.output_dir / "status.json"
        self.start_time = time.perf_counter()
        self.families_completed: list[str] = []
        self.families_remaining: list[str] = []
        self._current_family = ""
        self._current_stage = ""
        self._stage_start = time.perf_counter()
        self._current_candidate: int = 0
        self._total_candidates: int = 0
        self._candidate_name: str = ""

    def _ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _elapsed(self) -> float:
        return time.perf_counter() - self.start_time

    def log(self, family: str, stage: str, msg: str) -> None:
        prefix = f"[{self._ts()}]"
        if family:
            prefix += f" [{family.upper()[:3]}]"  # e.g. TRE, MEA, BRE
        if stage:
            prefix += f" [{stage}]"
        print(f"{prefix} {msg}", flush=True)

    def set_families(self, all_families: list[str]) -> None:
        self.families_remaining = list(all_families)

    def start_family(self, family_name: str) -> None:
        self._current_family = family_name
        if family_name in self.families_remaining:
            self.families_remaining.remove(family_name)
        self.log(family_name, "START", f"Beginning {family_name} family")
        self._write_status("STARTING", 0, 0, 0)

    def end_family(self, family_name: str) -> None:
        self.families_completed.append(family_name)
        self.log(family_name, "DONE", f"Completed {family_name} family")
        self._write_status("FAMILY_DONE", 100, 0, 0)

    def update_sweep(self, done: int, total: int) -> None:
        pct = (done / total * 100) if total > 0 else 0
        elapsed_stage = time.perf_counter() - self._stage_start
        eta = (elapsed_stage / done * (total - done)) if done > 0 else 0
        # Log every 10% or at completion — also on combo 1 so dashboard updates immediately
        step = max(1, total // 10)
        if done == 1 or done % step == 0 or done == total:
            self.log(self._current_family, "SWEEP",
                     f"{done}/{total} ({pct:.1f}%) — ETA {eta/60:.1f} min")
            self._write_status("SWEEP", pct, done, total, eta)

    def update_refinement(self, done: int, total: int) -> None:
        pct = (done / total * 100) if total > 0 else 0
        elapsed_stage = time.perf_counter() - self._stage_start
        eta = (elapsed_stage / done * (total - done)) if done > 0 else 0
        step = max(1, total // 10)
        if done == 1 or done % step == 0 or done == total:
            self.log(self._current_family, "REFINEMENT",
                     f"{done}/{total} ({pct:.1f}%) — ETA {eta/60:.1f} min")
            self._write_status("REFINEMENT", pct, done, total, eta)

    def log_promotion(self, count: int, cap: int) -> None:
        self.log(self._current_family, "PROMOTION",
                 f"{count} candidates promoted (cap={cap})")
        self._write_status("PROMOTION", 100, count, cap)

    def log_leaderboard(self, leader_name: str, pf: float, oos_pf: float) -> None:
        self.log(self._current_family, "LEADERBOARD",
                 f"Leader: {leader_name} PF={pf:.2f} OOS_PF={oos_pf:.2f}")
        self._write_status("LEADERBOARD", 100, 0, 0)

    def log_portfolio(self, n_strategies: int) -> None:
        self.log("", "PORTFOLIO", f"Evaluating {n_strategies} strategies...")
        self._write_status("PORTFOLIO", 0, 0, n_strategies)

    def log_load_data(self, dataset_label: str) -> None:
        self.log("", "LOAD_DATA", f"Loading CSV for {dataset_label}")
        self._write_status("LOAD_DATA", 0, 0, 0)

    def log_precompute_features(self, n_families: int) -> None:
        self.log("", "PRECOMPUTE_FEATURES", f"Computing features for {n_families} families")
        self._write_status("PRECOMPUTE_FEATURES", 0, 0, n_families)

    def log_dedup(self, family: str) -> None:
        self.log(family, "DEDUP", "Deduplicating promoted candidates")
        self._write_status("DEDUP", 0, 0, 0)

    def log_write_csv(self, family: str, filename: str) -> None:
        self.log(family, "WRITE_CSV", f"Writing {filename}")
        self._write_status("WRITE_CSV", 0, 0, 0)

    def log_build_leaderboard(self) -> None:
        self.log("", "BUILD_LEADERBOARD", "Building family leaderboard")
        self._write_status("BUILD_LEADERBOARD", 0, 0, 0)

    def log_portfolio_rebuild(self, n_strategies: int) -> None:
        self.log("", "PORTFOLIO_REBUILD", f"Rebuilding {n_strategies} strategies for portfolio evaluation")
        self._write_status("PORTFOLIO_REBUILD", 0, 0, n_strategies)

    def log_done(self) -> None:
        total = self._elapsed()
        self.log("", "DONE", f"Total runtime: {total:.1f}s")
        self._write_status("DONE", 100, 0, 0)

    def log_refinement_candidate(self, candidate_num: int, total_candidates: int,
                                  candidate_name: str) -> None:
        self._current_candidate = candidate_num
        self._total_candidates = total_candidates
        self._candidate_name = candidate_name
        self.log(self._current_family, "REFINEMENT",
                 f"Candidate {candidate_num}/{total_candidates}: {candidate_name}")
        self._write_status("REFINEMENT", 0, 0, 0)

    def reset_stage_timer(self) -> None:
        self._stage_start = time.perf_counter()

    def _write_status(self, stage: str, pct: float, done: int, total: int,
                      eta: float = 0) -> None:
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dataset": self.dataset_label,
            "current_family": self._current_family,
            "current_stage": stage,
            "progress_pct": round(pct, 1),
            "items_done": done,
            "items_total": total,
            "elapsed_seconds": round(self._elapsed(), 1),
            "eta_seconds": round(eta, 1),
            "families_completed": self.families_completed,
            "families_remaining": self.families_remaining,
            "last_event": f"{stage} {done}/{total}" if total > 0 else stage,
            "current_candidate": self._current_candidate,
            "total_candidates": self._total_candidates,
            "candidate_name": self._candidate_name,
        }
        try:
            self.status_path.write_text(json.dumps(status, indent=2))
        except Exception:
            pass  # never crash the pipeline for a status write failure
