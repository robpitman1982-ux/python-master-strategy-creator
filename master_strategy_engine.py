"""
Master Strategy Engine
Project: Python Master Strategy Creator
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Adjust import path if your data_loader is in a different folder
from modules.data_loader import load_tradestation_csv


@dataclass
class EngineConfig:
    # Global Presets from Master Prompt
    initial_capital: float = 250_000.0
    risk_per_trade: float = 0.01  # ~1% equity
    symbol: str = "ES"
    
    # Friction Assumptions
    commission_per_contract: float = 2.00
    slippage_ticks: int = 4  # 2 in, 2 out
    tick_value: float = 12.50 # ES specific
    
class MasterStrategyEngine:
    def __init__(self, data: pd.DataFrame, config: Optional[EngineConfig] = None):
        if data is None or data.empty:
            raise ValueError("Data is empty. Cannot initialize engine.")

        self.data = data
        self.config = config or EngineConfig()

        self.initial_capital = float(self.config.initial_capital)
        self.current_capital = float(self.config.initial_capital)
        self.risk_per_trade = float(self.config.risk_per_trade)

        self.positions = []
        self.trades = []

    def calculate_position_size_contracts(self, stop_distance_points: float, dollars_per_point: float = 50.0) -> int:
        """
        Calculates position size based on the 1% risk rule from the Master Prompt.
        """
        if stop_distance_points <= 0 or dollars_per_point <= 0:
            return 0
            
        risk_amount = self.current_capital * self.risk_per_trade
        contracts_float = risk_amount / (stop_distance_points * dollars_per_point)
        contracts = int(np.floor(contracts_float))
        
        # Default minimum 1 contract as per Master Prompt
        return max(1, contracts) if contracts > 0 else 0

    def run(self):
        # We will build the backtest loop here in Step 4
        pass

    def results(self) -> dict:
        return {
            "Symbol": self.config.symbol,
            "Initial Capital": f"${self.initial_capital:,.2f}",
            "Current Capital": f"${self.current_capital:,.2f}",
            "Total Trades": len(self.trades),
        }

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
    # Ensure this path matches your folder structure
    CSV_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"

    print("Loading data from:", CSV_PATH)
    data = load_tradestation_csv(CSV_PATH, debug=True)
    print("Data loaded successfully.")

    print_data_summary(data, name="ES Data (2008+)")

    cfg = EngineConfig(initial_capital=250_000.0, risk_per_trade=0.01, symbol="ES")
    engine = MasterStrategyEngine(data=data, config=cfg)

    print("\n🚀 Master Strategy Engine Initialized.")
    print("Engine Results Snapshot:", engine.results())