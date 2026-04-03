import pandas as pd

lb = pd.read_csv('Outputs/ultimate_leaderboard_bootcamp.csv')

strats = [
    ('NQ', 'daily', 'mean_reversion'),
    ('YM', 'daily', 'trend'),
    ('GC', 'daily', 'mean_reversion'),
    ('NQ', '15m', 'mean_reversion'),
]

for m, tf, st in strats:
    matches = lb[(lb['market']==m) & (lb['timeframe']==tf) & (lb['strategy_type'].str.startswith(st))]
    if not matches.empty:
        row = matches.sort_values('bootcamp_score', ascending=False).iloc[0]
        tpy = float(row.get('leader_trades_per_year', 0))
        trades = int(row.get('leader_trades', 0))
        avg = float(row.get('leader_avg_trade', 0))
        pf = float(row.get('leader_pf', 0))
        dd = abs(float(row.get('leader_max_drawdown', 0)))
        oos = float(row.get('oos_pf', 0))
        pnl = float(row.get('leader_net_pnl', 0))
        print(f"{m}_{tf} {st}")
        print(f"  PF={pf:.2f} OOS_PF={oos:.2f}")
        print(f"  trades/yr={tpy:.1f} total={trades}")
        print(f"  avg_trade=${avg:,.0f} net_pnl=${pnl:,.0f}")
        print(f"  max_DD=${dd:,.0f}")
        print()

# Combined portfolio stats
total_tpy = 0
for m, tf, st in strats:
    matches = lb[(lb['market']==m) & (lb['timeframe']==tf) & (lb['strategy_type'].str.startswith(st))]
    if not matches.empty:
        row = matches.sort_values('bootcamp_score', ascending=False).iloc[0]
        total_tpy += float(row.get('leader_trades_per_year', 0))

trades_per_month = total_tpy / 12
print(f"=== PORTFOLIO COMBINED ===")
print(f"Total trades/year: {total_tpy:.0f}")
print(f"Trades/month: {trades_per_month:.1f}")
print()

# $100K High Stakes sizing scenarios
account = 100000
step1_target = 0.08  # 8%
step2_target = 0.05  # 5%
max_dd = 0.10  # 10%
target_step1 = account * step1_target  # $8,000
target_step2 = account * step2_target  # $5,000

print(f"=== $100K HIGH STAKES ===")
print(f"Step 1 target: ${target_step1:,.0f} (8%)")
print(f"Step 2 target: ${target_step2:,.0f} (5%)")
print(f"Max DD: ${account * max_dd:,.0f} (10%)")
print()

# Micro contract value by market
# These are CFD but we use futures point values for estimation
# NQ: $2/point per micro, YM: $0.50/point per micro, GC: $1/point per micro (approx CFD)
# On $100K at 1:30 leverage, we have $3.33M buying power

# Sizing scenarios
print("=== SIZING SCENARIOS ===")
print("(Based on avg PnL per trade from backtest, scaled by micro count)")
print()

# Scenario data: [micros_nq_daily, micros_ym_daily, micros_gc_daily, micros_nq_15m]
scenarios = [
    ("Conservative (same as $5K)", [1, 1, 1, 1], "Match $5K test"),
    ("Moderate (2x)", [2, 2, 2, 2], "Double sizing"),
    ("Scaled (proportional)", [3, 2, 2, 3], "Weight to NQ anchors"),
    ("Aggressive", [5, 3, 3, 5], "Max within DD budget"),
    ("Speed run", [7, 4, 4, 7], "Push for 4 months"),
]

for name, micros, note in scenarios:
    # Est monthly PnL (very rough - using trades/month * avg_trade_scaled)
    # With $5K at 1 micro, we got 13.4 month estimate
    # $100K is 20x account size, but micros don't scale linearly with account
    # At 1 micro per strategy, monthly PnL ~= $5K rate * 1 (same absolute return)
    # Need to scale up micros to take advantage of $100K
    total_micros = sum(micros)
    # Rough monthly return estimate based on $5K test producing $400 target in 13.4 months
    # That's ~$30/month per strategy at 1 micro
    # Scale by micro count
    base_monthly = target_step1 / 13.4  # ~$597/month at 1 micro each on $5K
    scale_factor = total_micros / 4  # 4 micros was the $5K baseline
    est_monthly = base_monthly * scale_factor
    months_step1 = target_step1 / est_monthly if est_monthly > 0 else 99
    # After step1, step2 target is smaller
    months_step2 = target_step2 / est_monthly if est_monthly > 0 else 99
    total_months = months_step1 + months_step2
    
    # DD risk (rough: more micros = proportionally more DD)
    base_dd_pct = 6.9  # from the $5K MC simulation
    dd_pct = base_dd_pct * scale_factor
    dd_risk = "OK" if dd_pct < 9 else "TIGHT" if dd_pct < 10 else "DANGER"
    
    print(f"{name}: {micros} = {total_micros} micros total")
    print(f"  Est monthly PnL: ${est_monthly:,.0f}")
    print(f"  Step 1 ({target_step1:,.0f}): ~{months_step1:.1f} months")
    print(f"  Step 2 ({target_step2:,.0f}): ~{months_step2:.1f} months")
    print(f"  Total time: ~{total_months:.1f} months")
    print(f"  Est DD: {dd_pct:.1f}% ({dd_risk})")
    print(f"  Note: {note}")
    print()
