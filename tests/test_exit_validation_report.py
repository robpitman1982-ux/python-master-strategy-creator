from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd

from modules.exit_validation_report import generate_exit_validation_report


def test_exit_validation_report_summarizes_by_dataset_family_and_exit_type():
    outputs_dir = Path(".tmp_exit_validation_report_test") / str(uuid4()) / "Outputs"
    es60_dir = outputs_dir / "ES_60m"
    es30_dir = outputs_dir / "ES_30m"
    es60_dir.mkdir(parents=True)
    es30_dir.mkdir(parents=True)

    pd.DataFrame(
        [
            {
                "strategy_name": "RefinedTrend_TimeStop",
                "strategy_type": "trend",
                "exit_type": "time_stop",
                "profit_factor": 1.10,
                "net_pnl": 1000.0,
                "total_trades": 120,
                "quality_flag": "STABLE",
            },
            {
                "strategy_name": "RefinedTrend_Trail",
                "strategy_type": "trend",
                "exit_type": "trailing_stop",
                "profit_factor": 1.35,
                "net_pnl": 1800.0,
                "total_trades": 90,
                "quality_flag": "ROBUST",
            },
        ]
    ).to_csv(es60_dir / "trend_top_combo_refinement_results_narrow.csv", index=False)

    pd.DataFrame(
        [
            {
                "strategy_name": "RefinedMR_TimeStop",
                "strategy_type": "mean_reversion",
                "exit_type": "time_stop",
                "profit_factor": 1.40,
                "net_pnl": 2200.0,
                "total_trades": 150,
                "quality_flag": "ROBUST",
            },
            {
                "strategy_name": "RefinedMR_Target",
                "strategy_type": "mean_reversion",
                "exit_type": "profit_target",
                "profit_factor": 1.55,
                "net_pnl": 2600.0,
                "total_trades": 140,
                "quality_flag": "ROBUST",
            },
        ]
    ).to_csv(es30_dir / "mean_reversion_top_combo_refinement_results_narrow.csv", index=False)

    summary_df = generate_exit_validation_report(outputs_dir=outputs_dir)

    assert not summary_df.empty
    assert (outputs_dir / "exit_validation_summary.csv").exists()
    assert {"dataset", "strategy_type", "exit_type", "rows", "best_pf", "median_pf", "best_net_pnl", "best_strategy_name"}.issubset(summary_df.columns)

    trend_trail = summary_df[
        (summary_df["dataset"] == "ES_60m")
        & (summary_df["strategy_type"] == "trend")
        & (summary_df["exit_type"] == "trailing_stop")
    ].iloc[0]
    assert trend_trail["best_pf"] == 1.35
    assert trend_trail["best_strategy_name"] == "RefinedTrend_Trail"

    mr_target = summary_df[
        (summary_df["dataset"] == "ES_30m")
        & (summary_df["strategy_type"] == "mean_reversion")
        & (summary_df["exit_type"] == "profit_target")
    ].iloc[0]
    assert mr_target["best_net_pnl"] == 2600.0
    assert mr_target["best_quality_flag"] == "ROBUST"
