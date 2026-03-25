# EasyLanguage Filter Map

> Translation guide for converting Python filters to TradeStation EasyLanguage.
> Each filter is rendered as a standalone EasyLanguage condition that can be composed into
> a complete strategy signal.

## Translation Rules

| Python concept | EasyLanguage equivalent |
|---|---|
| `sma_N` / `Average(Close, N)` | `Average(Close, N)` |
| `atr_N` / `AvgTrueRange(N)` | `AvgTrueRange(N)` |
| `bar_range` | `High - Low` |
| `true_range` | `TrueRange` |
| `prev_close` / `Close[1]` | `Close[1]` |
| Rolling max (lookback N) | `Highest(High, N)` |
| Rolling min (lookback N) | `Lowest(Low, N)` |
| Rolling max of close | `Highest(Close, N)` |
| `momentum` (close - close[N]) | `Close - Close[N]` |
| Current open | `Open` |
| Current close | `Close` |
| Current high | `High` |
| Current low | `Low` |

---

## Trend-Family Filters

### 1. TrendDirectionFilter
**Parameters**: `fast_length=50, slow_length=200`
**Logic**: Fast SMA > slow SMA (uptrend confirmed)
**Features**: `sma_50`, `sma_200`

```easylanguage
Condition1 = Average(Close, 50) > Average(Close, 200);
```

---

### 2. PullbackFilter
**Parameters**: `fast_length=50`
**Logic**: Previous close <= fast SMA (price pulled back to or below SMA)
**Features**: `sma_50`, `prev_close`

```easylanguage
Condition2 = Close[1] <= Average(Close, 50);
```

---

### 3. RecoveryTriggerFilter
**Parameters**: `fast_length=50`
**Logic**: Current close > fast SMA (price recovered above SMA)
**Features**: `sma_50`

```easylanguage
Condition3 = Close > Average(Close, 50);
```

---

### 4. VolatilityFilter
**Parameters**: `lookback=20, min_atr_mult=1.0`
**Logic**: Current ATR >= long-term ATR × multiplier (elevated volatility regime)
**Features**: `atr_20`

```easylanguage
Vars: ATRCur(0), ATRLong(0);
ATRCur = AvgTrueRange(20);
ATRLong = AvgTrueRange(100);  { proxy for long-term ATR }
Condition4 = ATRCur >= ATRLong * 1.0;
```

---

### 5. MomentumFilter
**Parameters**: `lookback=10`
**Logic**: Current close > close N bars ago (positive momentum)
**Features**: `close` shifted by `lookback`

```easylanguage
Condition5 = Close > Close[10];
```

---

### 6. UpCloseFilter
**Parameters**: *(none)*
**Logic**: Current close > previous close (single up bar)
**Features**: `close`

```easylanguage
Condition6 = Close > Close[1];
```

---

### 7. TwoBarUpFilter
**Parameters**: *(none)*
**Logic**: Close > Close[1] AND Close[1] > Close[2] (two consecutive up closes)
**Features**: `close`

```easylanguage
Condition7 = Close > Close[1] and Close[1] > Close[2];
```

---

### 8. TrendSlopeFilter
**Parameters**: `fast_length=50, slope_bars=5`
**Logic**: Fast SMA now > fast SMA N bars ago (SMA trending upward)
**Features**: `sma_50`

```easylanguage
Condition8 = Average(Close, 50) > Average(Close, 50)[5];
```

---

### 9. CloseAboveFastSMAFilter
**Parameters**: `fast_length=50`
**Logic**: Current close > fast SMA
**Features**: `sma_50`

```easylanguage
Condition9 = Close > Average(Close, 50);
```

---

### 10. HigherLowFilter
**Parameters**: *(none)*
**Logic**: Current low > previous low (higher low structure)
**Features**: `low`

```easylanguage
Condition10 = Low > Low[1];
```

---

## Breakout-Family Filters

### 11. CompressionFilter
**Parameters**: `lookback=20, max_atr_mult=0.75`
**Logic**: Current ATR <= long-term ATR × multiplier (low-volatility compression before breakout)
**Features**: `atr_20`

```easylanguage
Vars: ATRCur(0), ATRLong(0);
ATRCur = AvgTrueRange(20);
ATRLong = AvgTrueRange(100);
Condition11 = ATRCur <= ATRLong * 0.75;
```

---

### 12. RangeBreakoutFilter
**Parameters**: `lookback=20`
**Logic**: Close > highest close of previous N bars (range breakout)
**Features**: `close`, `high` rolling window

```easylanguage
Condition12 = Close > Highest(Close, 20)[1];
```

---

### 13. ExpansionBarFilter
**Parameters**: `lookback=20, expansion_multiplier=1.50`
**Logic**: Current true range >= ATR × multiplier (expansion/breakout bar)
**Features**: `atr_20`, `true_range`

```easylanguage
Condition13 = TrueRange >= AvgTrueRange(20) * 1.50;
```

---

### 14. BreakoutRetestFilter
**Parameters**: `lookback=20, atr_buffer_mult=0.0`
**Logic**: Close > (prior N-bar high + ATR buffer) (confirmed breakout with buffer)
**Features**: `high`, `atr_20`

```easylanguage
Vars: PriorHigh(0), ATR(0);
PriorHigh = Highest(High, 20)[1];
ATR = AvgTrueRange(20);
Condition14 = Close > PriorHigh + ATR * 0.0;
```

---

### 15. BreakoutTrendFilter
**Parameters**: `fast_length=50, slow_length=200`
**Logic**: Fast SMA > slow SMA (trend context for breakout entries)
**Features**: `sma_50`, `sma_200`

```easylanguage
Condition15 = Average(Close, 50) > Average(Close, 200);
```

---

### 16. BreakoutCloseStrengthFilter
**Parameters**: `close_position_threshold=0.60`
**Logic**: (Close - Low) / (High - Low) >= threshold (bar closed in upper portion)
**Features**: `high`, `low`, `close`

```easylanguage
Vars: BarRange(0), ClosePos(0);
BarRange = High - Low;
If BarRange > 0 Then
  ClosePos = (Close - Low) / BarRange
Else
  ClosePos = 0.5;
Condition16 = ClosePos >= 0.60;
```

---

### 17. PriorRangePositionFilter
**Parameters**: `lookback=20, min_position_in_range=0.50`
**Logic**: Prior close's position within the N-bar range >= threshold
**Features**: `low` rolling min, `high` rolling max, `prev_close`

```easylanguage
Vars: RangeLow(0), RangeHigh(0), RangeSpan(0), PriorPos(0);
RangeLow  = Lowest(Low, 20)[1];
RangeHigh = Highest(High, 20)[1];
RangeSpan = RangeHigh - RangeLow;
If RangeSpan > 0 Then
  PriorPos = (Close[1] - RangeLow) / RangeSpan
Else
  PriorPos = 0.5;
Condition17 = PriorPos >= 0.50;
```

---

### 18. BreakoutDistanceFilter
**Parameters**: `lookback=20, min_breakout_atr=0.10`
**Logic**: (Close - prior N-bar high) >= ATR × min_breakout_atr
**Features**: `high`, `atr_20`, `close`

```easylanguage
Vars: PriorHigh(0), ATR(0);
PriorHigh = Highest(High, 20)[1];
ATR = AvgTrueRange(20);
Condition18 = Close - PriorHigh >= ATR * 0.10;
```

---

### 19. RisingBaseFilter
**Parameters**: `lookback=5`
**Logic**: Second-half minimum low >= first-half minimum low (rising base pattern)
**Features**: `low`

```easylanguage
Vars: HalfLen(0), FirstHalfLow(0), SecondHalfLow(0);
HalfLen = 3;  { half of lookback=5, rounded }
FirstHalfLow  = Lowest(Low, HalfLen)[HalfLen];
SecondHalfLow = Lowest(Low, HalfLen);
Condition19 = SecondHalfLow >= FirstHalfLow;
```

---

### 20. TightRangeFilter
**Parameters**: `lookback=20, max_bar_range_mult=0.85`
**Logic**: Current bar range <= average bar range × multiplier (tight/compressed bar)
**Features**: `bar_range`, `avg_range_20`

```easylanguage
Vars: AvgRange(0);
AvgRange = Average(High - Low, 20);
Condition20 = (High - Low) <= AvgRange * 0.85;
```

---

## Mean-Reversion-Family Filters

### 21. BelowFastSMAFilter
**Parameters**: `fast_length=20`
**Logic**: Close < fast SMA (price below moving average, eligible for mean reversion)
**Features**: `sma_20`

```easylanguage
Condition21 = Close < Average(Close, 20);
```

---

### 22. DistanceBelowSMAFilter
**Parameters**: `fast_length=20, min_distance_atr=0.3`
**Logic**: (SMA - Close) >= ATR × min_distance_atr (price sufficiently below SMA)
**Features**: `sma_20`, `atr_20`

```easylanguage
Vars: ATR(0), SMA(0);
ATR = AvgTrueRange(20);
SMA = Average(Close, 20);
Condition22 = SMA - Close >= ATR * 0.3;
```

---

### 23. DownCloseFilter
**Parameters**: *(none)*
**Logic**: Close < Close[1] (single down bar)
**Features**: `close`

```easylanguage
Condition23 = Close < Close[1];
```

---

### 24. TwoBarDownFilter
**Parameters**: *(none)*
**Logic**: Close < Close[1] AND Close[1] < Close[2] (two consecutive down closes)
**Features**: `close`

```easylanguage
Condition24 = Close < Close[1] and Close[1] < Close[2];
```

---

### 25. ReversalUpBarFilter
**Parameters**: *(none)*
**Logic**: Close > Open (bullish close bar — green candle)
**Features**: `close`, `open`

```easylanguage
Condition25 = Close > Open;
```

---

### 26. LowVolatilityRegimeFilter
**Parameters**: `lookback=20, max_atr_mult=1.0`
**Logic**: Current ATR <= long-term ATR × multiplier (low-volatility environment)
**Features**: `atr_20`

```easylanguage
Vars: ATRCur(0), ATRLong(0);
ATRCur = AvgTrueRange(20);
ATRLong = AvgTrueRange(100);
Condition26 = ATRCur <= ATRLong * 1.0;
```

---

### 27. AboveLongTermSMAFilter
**Parameters**: `slow_length=200`
**Logic**: Close > slow SMA (long-term uptrend context for mean reversion)
**Features**: `sma_200`

```easylanguage
Condition27 = Close > Average(Close, 200);
```

---

### 28. ThreeBarDownFilter
**Parameters**: *(none)*
**Logic**: Three consecutive down closes (strong pullback for reversion entry)
**Features**: `close`

```easylanguage
Condition28 = Close < Close[1] and Close[1] < Close[2] and Close[2] < Close[3];
```

---

### 29. CloseNearLowFilter
**Parameters**: `max_close_position=0.35`
**Logic**: (Close - Low) / (High - Low) <= threshold (bar closed near its low)
**Features**: `high`, `low`, `close`

```easylanguage
Vars: BarRange(0), ClosePos(0);
BarRange = High - Low;
If BarRange > 0 Then
  ClosePos = (Close - Low) / BarRange
Else
  ClosePos = 0.5;
Condition29 = ClosePos <= 0.35;
```

---

### 30. StretchFromLongTermSMAFilter
**Parameters**: `slow_length=200, min_distance_atr=0.5`
**Logic**: (slow SMA - Close) >= ATR × min_distance_atr (price overextended below long-term SMA)
**Features**: `sma_200`, `atr_20`

```easylanguage
Vars: ATR(0), SlowSMA(0);
ATR = AvgTrueRange(20);
SlowSMA = Average(Close, 200);
Condition30 = SlowSMA - Close >= ATR * 0.5;
```

---

## Exit Logic Mapping

### Time Stop (default for all families)
```easylanguage
{ Exit after N bars }
If BarsSinceEntry >= HoldBars Then ExitLong("TimeStop") Next Bar at Market;
```

### ATR Stop Loss
```easylanguage
{ On entry bar, compute stop level }
Vars: EntryPrice(0), StopLevel(0), ATRStop(0);
If MarketPosition = 0 and EntryConditions Then Begin
  Buy Next Bar at Market;
  ATRStop = AvgTrueRange(20);
  StopLevel = EntryPrice - ATRStop * StopDistATR;
End;
ExitLong Next Bar at StopLevel Stop;
```

### Trailing ATR Stop
```easylanguage
Vars: TrailStop(0), ATR(0), HighestSinceEntry(0);
ATR = AvgTrueRange(20);
If MarketPosition > 0 Then Begin
  HighestSinceEntry = Highest(High, BarsSinceEntry + 1);
  TrailStop = HighestSinceEntry - ATR * TrailATR;
  If Close < TrailStop Then ExitLong("TrailStop") Next Bar at Market;
End;
```

### Profit Target
```easylanguage
Vars: TargetPrice(0);
If MarketPosition > 0 Then Begin
  TargetPrice = EntryPrice + AvgTrueRange(20) * ProfitTargetATR;
  ExitLong("ProfitTarget") Next Bar at TargetPrice Limit;
End;
```

### Signal Exit (mean reversion — exit when price returns to SMA)
```easylanguage
If MarketPosition > 0 and Close >= Average(Close, 20) Then
  ExitLong("SignalExit") Next Bar at Market;
```

---

## Complete MR Strategy Template

Top mean-reversion winner: **DistanceBelowSMA + TwoBarDown + ReversalUpBar**
Parameters: Hold bars = 12, ATR stop = 0.5, Distance = 1.2 ATR below SMA-20
(Based on local Session 29 validation results)

```easylanguage
{ ================================================================
  Mean Reversion Strategy — ES Futures
  Filters: DistanceBelowSMA + TwoBarDown + ReversalUpBar
  Exit: Time stop (12 bars) with ATR stop loss
  Timeframe: 60m bars
  ================================================================ }

Inputs:
  SMALength(20),         { fast SMA lookback }
  ATRLength(20),         { ATR lookback }
  MinDistATR(1.2),       { minimum distance below SMA in ATR units }
  HoldBars(12),          { maximum bars to hold }
  StopDistATR(0.5);      { stop loss in ATR units }

Vars:
  SMA(0),
  ATR(0),
  EntryBar(0),
  StopLevel(0),
  BarRange(0),
  ClosePos(0);

SMA = Average(Close, SMALength);
ATR = AvgTrueRange(ATRLength);

{ --- Filter conditions --- }

{ F1: DistanceBelowSMAFilter — price >= 1.2 ATR below SMA }
Condition1 = (SMA - Close) >= ATR * MinDistATR;

{ F2: TwoBarDownFilter — two consecutive down closes }
Condition2 = Close < Close[1] and Close[1] < Close[2];

{ F3: ReversalUpBarFilter — current bar is a bullish close }
Condition3 = Close > Open;

{ --- Entry --- }
If MarketPosition = 0
  and Condition1
  and Condition2
  and Condition3
Then Begin
  Buy("MR_Entry") Next Bar at Market;
  EntryBar = CurrentBar;
  StopLevel = EntryPrice - ATR * StopDistATR;
End;

{ --- Exits --- }
{ ATR stop loss }
If MarketPosition > 0 Then
  ExitLong("ATR_Stop") Next Bar at StopLevel Stop;

{ Time stop }
If MarketPosition > 0 and (CurrentBar - EntryBar) >= HoldBars Then
  ExitLong("TimeStop") Next Bar at Market;
```

---

## Notes for TradeStation Deployment

1. **EntryPrice** — in EasyLanguage, `EntryPrice` is a built-in that returns the price at which the last entry order was filled. Use it to compute stop levels in the bar after entry.
2. **BarsSinceEntry** — use `CurrentBar - EntryBar` or the `BarsSinceEntry` reserved word (EL 9.5+).
3. **ATR values** — `AvgTrueRange(N)` computes ATR using Wilder smoothing (same as `AvgTrueRange` in Python via `pandas_ta`). Use the same `N` as in `config.yaml`.
4. **SMA lookbacks** — `Average(Close, N)` is a simple moving average matching the Python `sma_N` feature columns exactly.
5. **Parameter scaling** — the Python engine scales lookback values by timeframe multiplier. For 60m bars, no scaling is needed (multiplier = 1.0). For daily bars, SMA lengths are multiplied by ~0.154.
6. **Commission/slippage** — the Python engine uses `$2.50/contract` commission and `0.25 points` slippage. Set equivalent values in TradeStation Format > Strategy Properties.
7. **Tick value** — for MES micro futures: 1 tick = 0.25 points = $1.25. For ES mini: 1 tick = 0.25 points = $12.50.
