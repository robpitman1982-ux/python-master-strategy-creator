from pathlib import Path

from modules.portfolio_evaluator import evaluate_portfolio

# Input paths
LEADERBOARD_PATH = Path("Outputs") / "family_leaderboard_results.csv"
DATA_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"

# Output paths
REVIEW_TABLE_PATH = Path("Outputs") / "portfolio_review_table.csv"
RETURNS_PATH = Path("Outputs") / "strategy_returns.csv"
CORRELATION_PATH = Path("Outputs") / "correlation_matrix.csv"
YEARLY_STATS_PATH = Path("Outputs") / "yearly_stats_breakdown.csv"


if __name__ == "__main__":
    print("Starting Portfolio Evaluation Phase...")

    Path("Outputs").mkdir(parents=True, exist_ok=True)

    filename_parts = DATA_PATH.stem.split("_")
    market_symbol = filename_parts[0] if len(filename_parts) > 0 else "UNKNOWN"
    timeframe = filename_parts[1] if len(filename_parts) > 1 else "UNKNOWN"

    print(f"Detecting target: Market={market_symbol}, Timeframe={timeframe}")

    review_table, returns_df, corr_matrix, yearly_df = evaluate_portfolio(
        leaderboard_csv=LEADERBOARD_PATH,
        data_csv=DATA_PATH,
        market_name=market_symbol,
        timeframe=timeframe,
    )

    if not review_table.empty:
        review_table.to_csv(REVIEW_TABLE_PATH, index=False)
        returns_df.to_csv(RETURNS_PATH, index=True)
        corr_matrix.to_csv(CORRELATION_PATH, index=True)

        if not yearly_df.empty:
            yearly_df.to_csv(YEARLY_STATS_PATH, index=False)

        print("\n" + "=" * 60)
        print("✅ EVALUATION COMPLETE - FILES GENERATED:")
        print("=" * 60)
        print(f"1. Master Review Table:    {REVIEW_TABLE_PATH}")
        print(f"2. Daily Returns Log:      {RETURNS_PATH}")
        print(f"3. Correlation Matrix:     {CORRELATION_PATH}")
        print(f"4. Yearly Stats Breakdown: {YEARLY_STATS_PATH}")

        print("\n[Preview of Portfolio Review Table]")
        preview_cols = [
            "strategy_family",
            "strategy_name",
            "quality_flag",
            "is_trades",
            "oos_trades",
            "is_pf_pre_2019",
            "oos_pf_post_2019",
            "mc_max_dd_99",
            "shock_drop_10pct_pnl",
        ]
        preview_df = review_table[[c for c in preview_cols if c in review_table.columns]]
        print(preview_df.to_string(index=False))
    else:
        print("\n❌ No valid strategies found to evaluate.")
        print("This usually means either:")
        print("- the leaderboard is empty, or")
        print("- no rows passed accepted_final=True.")
