from pathlib import Path
from modules.portfolio_evaluator import evaluate_portfolio

# Input paths
LEADERBOARD_PATH = Path("Outputs") / "family_leaderboard_results.csv"
DATA_PATH = Path("Data") / "ES_60m_2008_2026_tradestation.csv"

# The 3 core output paths
REVIEW_TABLE_PATH = Path("Outputs") / "portfolio_review_table.csv"
RETURNS_PATH = Path("Outputs") / "strategy_returns.csv"
CORRELATION_PATH = Path("Outputs") / "correlation_matrix.csv"

if __name__ == "__main__":
    print("Starting Portfolio Evaluation Phase...")
    
    # Ensure the Outputs directory exists
    Path("Outputs").mkdir(parents=True, exist_ok=True)
    
    # Run the evaluator
    review_table, returns_df, corr_matrix = evaluate_portfolio(
        leaderboard_csv=LEADERBOARD_PATH,
        data_csv=DATA_PATH,
        market_name="ES",
        timeframe="60m"
    )

    if not review_table.empty:
        # Save all three files
        review_table.to_csv(REVIEW_TABLE_PATH, index=False)
        returns_df.to_csv(RETURNS_PATH, index=True)  # Index is dates, so keep it True
        corr_matrix.to_csv(CORRELATION_PATH, index=True)
        
        print("\n" + "="*60)
        print("✅ EVALUATION COMPLETE - FILES GENERATED:")
        print("="*60)
        print(f"1. Master Review Table: {REVIEW_TABLE_PATH}")
        print(f"2. Daily Returns Log:   {RETURNS_PATH}")
        print(f"3. Correlation Matrix:  {CORRELATION_PATH}")
        
        print("\n[Preview of Portfolio Review Table]")
        # Display a clean, abbreviated version in the terminal
        preview_cols = ["strategy_family", "profit_factor", "recent_12m_pf", "weighted_pf_score", "mc_max_dd_99"]
        preview_df = review_table[[c for c in preview_cols if c in review_table.columns]]
        print(preview_df.to_string())
        
    else:
        print("\n❌ No valid strategies found to evaluate. Ensure your leaderboard has promoted candidates.")