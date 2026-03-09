"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.data_loader import load_tradestation_csv
from modules.engine import EngineConfig, MasterStrategyEngine
from modules.optimizer import StrategyOptimizer
from modules.strategies import TestStrategy


def print_data_summary(df: pd.DataFrame, name: str = "DATA") -> None:
    print(f"\n=== {name} SUMMARY ===")
    print(f"Rows: {len(df):,}")
    print(f"Start: {df.index.min()}")
    print(f"End:   {df.index.max()}")
    print("Columns:", list(df.columns))
    print("\nHead:")
    print(df.head(3))
    print("\nTail:")
    print(df.tail(3))


if __name__ == "__main__":
    CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"
    OUTPUTS_DIR = Path("Outputs")
    OPTIMIZATION_CSV_PATH = OUTPUTS_DIR / "test_strategy_optimization_results.csv"

    print("Loading data from:", CSV_PATH)
    data = load_tradestation_csv(CSV_PATH, debug=True)
    print("Data loaded successfully.")

    print_data_summary(data, name="ES Data (2008+)")

    cfg = EngineConfig(
        initial_capital=250_000.0,
        risk_per_trade=0.01,
        symbol="ES",
    )

    # -----------------------------
    # Single test run
    # -----------------------------
    strategy = TestStrategy()
    engine = MasterStrategyEngine(data=data, config=cfg)

    print("\n🚀 Master Strategy Engine Initialized.")
    print("Engine Results Snapshot (Before Run):", engine.results())

    engine.run(strategy=strategy)

    print("\n✅ Backtest run completed.")
    print("Engine Results Snapshot (After Run):", engine.results())

    trades_df = engine.trades_dataframe()
    if not trades_df.empty:
        print("\nFirst 5 Trades:")
        print(trades_df.head())

    # -----------------------------
    # Optimization run
    # -----------------------------
    optimizer = StrategyOptimizer(
        engine_class=MasterStrategyEngine,
        data=data,
        strategy_class=TestStrategy,
        config=cfg,
    )

    optimization_df = optimizer.run_grid_search(
        hold_bars=[2, 3, 4, 5],
        stop_distance_points=[6.0, 8.0, 10.0, 12.0],
        min_trades=150,
        min_trades_per_year=20.0,
    )

    if not optimization_df.empty:
        print("\n📊 Top Optimization Results:")
        print(optimizer.top_results(10))

        saved_path = optimizer.save_results_csv(OPTIMIZATION_CSV_PATH)
        print(f"\n💾 Full optimization results saved to: {saved_path}")
    else:
        print("\nNo optimization results met the filter criteria.")