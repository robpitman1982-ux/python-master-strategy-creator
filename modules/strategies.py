from __future__ import annotations

import pandas as pd


class TestStrategy:
    """
    Very simple placeholder strategy:
    enter long when current close > previous close.
    """

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        if i < 1:
            return 0

        current_close = data["close"].iloc[i]
        previous_close = data["close"].iloc[i - 1]

        if current_close > previous_close:
            return 1

        return 0