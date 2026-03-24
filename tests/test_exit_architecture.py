from __future__ import annotations

import pandas as pd

from modules.engine import EngineConfig, MasterStrategyEngine
from modules.refiner import StrategyParameterRefiner
from modules.strategies import ExitType, build_exit_config


def _make_engine_config() -> EngineConfig:
    return EngineConfig(
        initial_capital=100_000.0,
        risk_per_trade=0.01,
        commission_per_contract=0.0,
        slippage_ticks=0,
        tick_value=12.50,
        dollars_per_point=50.0,
        oos_split_date="2020-01-01",
    )


def _make_exit_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2020-01-01", periods=len(df), freq="h")
    return df


class _SingleEntryStrategy:
    name = "SingleEntryStrategy"
    hold_bars = 2
    stop_distance_atr = 2.0
    filters: list[object] = []

    def __init__(self, exit_config=None, hold_bars: int = 2, stop_distance_atr: float = 2.0, filters=None):
        self.hold_bars = hold_bars
        self.stop_distance_atr = stop_distance_atr
        self.exit_config = exit_config
        self.filters = filters or []

    def generate_signal(self, data: pd.DataFrame, i: int) -> int:
        return 1 if i == 0 else 0


def test_engine_time_stop_remains_backward_compatible():
    df = _make_exit_df(
        [
            {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "atr_20": 1.0},
            {"open": 100.1, "high": 100.6, "low": 99.9, "close": 100.2, "atr_20": 1.0},
            {"open": 100.2, "high": 100.7, "low": 100.0, "close": 100.3, "atr_20": 1.0},
            {"open": 100.3, "high": 100.8, "low": 100.1, "close": 100.4, "atr_20": 1.0},
        ]
    )
    strategy = _SingleEntryStrategy(exit_config=None, hold_bars=2, stop_distance_atr=2.0)

    engine = MasterStrategyEngine(df, _make_engine_config())
    engine.run(strategy)

    assert len(engine.trades) == 1
    assert engine.trades[0].exit_reason == "TIME"


def test_engine_trailing_stop_exit_on_rising_then_falling_trade():
    df = _make_exit_df(
        [
            {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "atr_20": 1.0},
            {"open": 101.0, "high": 103.0, "low": 101.0, "close": 102.5, "atr_20": 1.0},
            {"open": 103.5, "high": 105.0, "low": 104.0, "close": 104.5, "atr_20": 1.0},
            {"open": 104.0, "high": 104.2, "low": 103.8, "close": 104.0, "atr_20": 1.0},
        ]
    )
    strategy = _SingleEntryStrategy(
        exit_config=build_exit_config(
            exit_type=ExitType.TRAILING_STOP,
            hold_bars=10,
            stop_distance_points=2.0,
            trailing_stop_atr=1.0,
        ),
        hold_bars=10,
        stop_distance_atr=2.0,
    )

    engine = MasterStrategyEngine(df, _make_engine_config())
    engine.run(strategy)

    assert len(engine.trades) == 1
    assert engine.trades[0].exit_reason == "TRAILING_STOP"


def test_engine_profit_target_exit_on_winning_trade():
    df = _make_exit_df(
        [
            {"open": 100.0, "high": 100.4, "low": 99.6, "close": 100.0, "atr_20": 1.0},
            {"open": 100.8, "high": 101.2, "low": 100.6, "close": 101.0, "atr_20": 1.0},
            {"open": 101.1, "high": 101.3, "low": 100.9, "close": 101.2, "atr_20": 1.0},
        ]
    )
    strategy = _SingleEntryStrategy(
        exit_config=build_exit_config(
            exit_type=ExitType.PROFIT_TARGET,
            hold_bars=10,
            stop_distance_points=2.0,
            profit_target_atr=1.0,
        ),
        hold_bars=10,
        stop_distance_atr=2.0,
    )

    engine = MasterStrategyEngine(df, _make_engine_config())
    engine.run(strategy)

    assert len(engine.trades) == 1
    assert engine.trades[0].exit_reason == "PROFIT_TARGET"


def test_engine_signal_exit_uses_fast_sma_reversion_rule():
    df = _make_exit_df(
        [
            {"open": 100.0, "high": 100.3, "low": 99.5, "close": 100.0, "atr_20": 1.0, "sma_20": 100.5},
            {"open": 99.8, "high": 100.0, "low": 99.3, "close": 99.7, "atr_20": 1.0, "sma_20": 100.0},
            {"open": 100.5, "high": 101.0, "low": 100.2, "close": 100.8, "atr_20": 1.0, "sma_20": 100.0},
            {"open": 100.8, "high": 101.1, "low": 100.5, "close": 100.9, "atr_20": 1.0, "sma_20": 100.1},
        ]
    )
    strategy = _SingleEntryStrategy(
        exit_config=build_exit_config(
            exit_type=ExitType.SIGNAL_EXIT,
            hold_bars=10,
            stop_distance_points=2.0,
            signal_exit_reference="fast_sma",
        ),
        hold_bars=10,
        stop_distance_atr=2.0,
    )

    engine = MasterStrategyEngine(df, _make_engine_config())
    engine.run(strategy)

    assert len(engine.trades) == 1
    assert engine.trades[0].exit_reason == "SIGNAL_EXIT"


def test_engine_prefers_protective_stop_over_other_exit_types():
    df = _make_exit_df(
        [
            {"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0, "atr_20": 1.0},
            {"open": 100.1, "high": 103.0, "low": 97.5, "close": 102.5, "atr_20": 1.0},
            {"open": 102.0, "high": 102.5, "low": 101.8, "close": 102.1, "atr_20": 1.0},
        ]
    )
    strategy = _SingleEntryStrategy(
        exit_config=build_exit_config(
            exit_type=ExitType.PROFIT_TARGET,
            hold_bars=10,
            stop_distance_points=2.0,
            profit_target_atr=1.0,
        ),
        hold_bars=10,
        stop_distance_atr=2.0,
    )

    engine = MasterStrategyEngine(df, _make_engine_config())
    engine.run(strategy)

    assert len(engine.trades) == 1
    assert engine.trades[0].exit_reason == "STOP"


def test_supported_exit_types_are_declared_per_family():
    from modules.strategy_types import get_strategy_type

    trend = get_strategy_type("trend")
    mean_reversion = get_strategy_type("mean_reversion")
    breakout = get_strategy_type("breakout")

    assert ExitType.TRAILING_STOP in trend.get_supported_exit_types()
    assert ExitType.PROFIT_TARGET in mean_reversion.get_supported_exit_types()
    assert ExitType.SIGNAL_EXIT in mean_reversion.get_supported_exit_types()
    assert ExitType.TRAILING_STOP in breakout.get_supported_exit_types()


def test_candidate_specific_build_accepts_exit_type():
    from modules.filters import DistanceBelowSMAFilter, ReversalUpBarFilter, TwoBarDownFilter
    from modules.strategy_types import get_strategy_type

    mr = get_strategy_type("mean_reversion")
    strategy = mr.build_candidate_specific_strategy(
        [DistanceBelowSMAFilter, TwoBarDownFilter, ReversalUpBarFilter],
        hold_bars=5,
        stop_distance_points=0.75,
        min_avg_range=0.8,
        momentum_lookback=0,
        timeframe="60m",
        exit_type=ExitType.PROFIT_TARGET,
        profit_target_atr=1.25,
    )

    assert strategy.exit_config.exit_type == ExitType.PROFIT_TARGET
    assert strategy.exit_config.profit_target_atr == 1.25


def test_engine_processes_exit_config_without_crashing():
    df = _make_exit_df(
        [
            {"open": 100.0, "high": 100.3, "low": 99.7, "close": 100.0, "atr_20": 1.0, "sma_20": 100.0},
            {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "atr_20": 1.0, "sma_20": 100.0},
            {"open": 100.7, "high": 100.9, "low": 100.5, "close": 100.8, "atr_20": 1.0, "sma_20": 100.0},
        ]
    )
    strategy = _SingleEntryStrategy(
        exit_config=build_exit_config(
            exit_type=ExitType.SIGNAL_EXIT,
            hold_bars=3,
            stop_distance_points=2.0,
            signal_exit_reference="fast_sma",
        ),
        hold_bars=3,
        stop_distance_atr=2.0,
    )

    engine = MasterStrategyEngine(df, _make_engine_config())
    engine.run(strategy)

    assert len(engine.trades) == 1
    assert engine.results()["Total Trades"] == 1


def test_refinement_results_include_exit_metadata():
    df = _make_exit_df(
        [
            {"open": 100.0, "high": 100.3, "low": 99.7, "close": 100.0, "atr_20": 1.0, "sma_20": 100.2},
            {"open": 100.5, "high": 101.4, "low": 100.4, "close": 101.1, "atr_20": 1.0, "sma_20": 100.1},
            {"open": 101.1, "high": 101.2, "low": 100.0, "close": 100.4, "atr_20": 1.0, "sma_20": 100.2},
            {"open": 100.4, "high": 100.6, "low": 100.1, "close": 100.5, "atr_20": 1.0, "sma_20": 100.0},
        ]
    )

    def strategy_factory(
        hold_bars: int,
        stop_distance_points: float,
        min_avg_range: float,
        momentum_lookback: int,
        exit_type=None,
        profit_target_atr=None,
        trailing_stop_atr=None,
        signal_exit_reference=None,
    ):
        return _SingleEntryStrategy(
            exit_config=build_exit_config(
                exit_type=exit_type,
                hold_bars=hold_bars,
                stop_distance_points=stop_distance_points,
                profit_target_atr=profit_target_atr,
                trailing_stop_atr=trailing_stop_atr,
                signal_exit_reference=signal_exit_reference,
            ),
            hold_bars=hold_bars,
            stop_distance_atr=stop_distance_points,
        )

    refiner = StrategyParameterRefiner(
        MasterStrategyEngine,
        df,
        strategy_factory,
        _make_engine_config(),
    )
    result_df = refiner.run_refinement(
        hold_bars=[2],
        stop_distance_points=[2.0],
        min_avg_range=[0.0],
        momentum_lookback=[0],
        exit_type=[
            ExitType.TIME_STOP,
            ExitType.TRAILING_STOP,
            ExitType.PROFIT_TARGET,
            ExitType.SIGNAL_EXIT,
        ],
        trailing_stop_atr=[1.5],
        profit_target_atr=[1.0],
        signal_exit_reference=["fast_sma"],
        min_trades=0,
        min_trades_per_year=0.0,
        parallel=False,
    )

    assert not result_df.empty
    assert {"exit_type", "trailing_stop_atr", "profit_target_atr", "signal_exit_reference"}.issubset(result_df.columns)
    assert set(result_df["exit_type"]) == {"time_stop", "trailing_stop", "profit_target", "signal_exit"}
