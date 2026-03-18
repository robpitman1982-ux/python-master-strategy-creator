# TradeStation Data Export Guide

## Required exports for ES multi-timeframe sweep

Export these 4 datasets from TradeStation:

| File name | Symbol | Interval | Date range |
|-----------|--------|----------|------------|
| ES_daily_2008_2026_tradestation.csv | @ES (continuous) | Daily | 01/01/2008 — today |
| ES_60m_2008_2026_tradestation.csv | @ES (continuous) | 60 min | 01/01/2008 — today |
| ES_30m_2008_2026_tradestation.csv | @ES (continuous) | 30 min | 01/01/2008 — today |
| ES_15m_2008_2026_tradestation.csv | @ES (continuous) | 15 min | 01/01/2008 — today |

## Export steps (TradeStation)

1. Open a chart for @ES with the desired interval
2. Set the date range to start from 01/01/2008
3. File → Save As → select "Text/CSV" format
4. Ensure columns include: Date, Time, Open, High, Low, Close, Volume
5. Save to your local `Data/` folder with the naming convention below

## Naming convention

`{MARKET}_{TIMEFRAME}_{START_YEAR}_{END_YEAR}_tradestation.csv`

Examples:
- `ES_daily_2008_2026_tradestation.csv`
- `ES_15m_2008_2026_tradestation.csv`
- `NQ_60m_2008_2026_tradestation.csv`
- `CL_daily_2008_2026_tradestation.csv`

## Expected file sizes (approximate)

| Timeframe | Bars (18 years) | File size |
|-----------|----------------|-----------|
| Daily | ~4,500 | ~300 KB |
| 60m | ~107,000 | ~7 MB |
| 30m | ~214,000 | ~14 MB |
| 15m | ~428,000 | ~28 MB |
| 5m | ~1,300,000 | ~85 MB |

## Verification

After export, verify each file loads correctly:

```bash
python -c "from modules.data_loader import load_tradestation_csv; df = load_tradestation_csv('Data/ES_daily_2008_2026_tradestation.csv'); print(f'{len(df):,} bars, {df.index.min()} to {df.index.max()}')"
python -c "from modules.data_loader import load_tradestation_csv; df = load_tradestation_csv('Data/ES_30m_2008_2026_tradestation.csv'); print(f'{len(df):,} bars, {df.index.min()} to {df.index.max()}')"
python -c "from modules.data_loader import load_tradestation_csv; df = load_tradestation_csv('Data/ES_15m_2008_2026_tradestation.csv'); print(f'{len(df):,} bars, {df.index.min()} to {df.index.max()}')"
```

## Notes

- The data loader auto-detects date format (day-first vs month-first)
- Volume column is optional (falls back to Up+Down or zeros)
- Make sure TradeStation exports the continuous contract (@ES), not individual months
- ES 60m already exists — only need to export daily, 30m, and 15m
