from __future__ import annotations

import pandas as pd


class OptimizationHeatmap:
    """
    Generates pivot-table heatmaps from optimizer results.
    Used to visualize parameter plateaus.
    """

    def __init__(self, optimization_df: pd.DataFrame):
        if optimization_df is None or optimization_df.empty:
            raise ValueError("Optimization dataframe is empty.")

        self.df = optimization_df.copy()

    def create_heatmap(
        self,
        metric: str,
        index_param: str = "hold_bars",
        column_param: str = "stop_distance_points",
    ) -> pd.DataFrame:
        """
        Creates pivot heatmap for chosen metric.
        """

        if metric not in self.df.columns:
            raise ValueError(f"Metric '{metric}' not found in optimization results.")

        heatmap = self.df.pivot_table(
            values=metric,
            index=index_param,
            columns=column_param,
            aggfunc="mean"
        )

        return heatmap.round(3)

    def print_heatmap(
        self,
        metric: str,
        title: str,
        index_param: str = "hold_bars",
        column_param: str = "stop_distance_points",
    ):
        """
        Prints formatted heatmap to terminal.
        """

        heatmap = self.create_heatmap(metric, index_param, column_param)

        print(f"\n📊 {title}")
        print(heatmap)