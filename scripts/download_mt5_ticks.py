"""
Download tick data from MT5 for all priority symbols.
Saves to Z:\market_data\mt5_ticks\ (Gen 9 Samba share).
Must be run while MT5 is open and logged in to The5ers.
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import os
import time

OUTPUT_DIR = r"Z:\market_data\mt5_ticks"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# All symbols to download, in priority order
SYMBOLS = [
    # Tier 1 - futures equivalents (SP500 already done)
    "NAS100",   # NQ
    "US30",     # YM
    "XAUUSD",   # GC
    "XAGUSD",   # SI
    "XTIUSD",   # CL
    # Tier 2 - FX pairs
    "EURUSD",   # EC
    "USDJPY",   # JY
    "GBPUSD",   # BP
    "AUDUSD",   # AD
    # Tier 3 - bonus
    "BTCUSD",
    "ETHUSD",
    "DAX40",
    "JPN225",
    "UK100",
]

START_DATE = datetime(2020, 1, 1)  # Ask for as far back as possible
END_DATE = datetime.now()

def download_symbol(symbol):
    """Download all ticks for a symbol and save to CSV."""
    output_file = os.path.join(OUTPUT_DIR, f"{symbol}_ticks.csv")
    
    # Skip if already downloaded
    if os.path.exists(output_file):
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        print(f"  SKIP {symbol} - already exists ({size_mb:.0f} MB)")
        return True
    
    print(f"  Requesting ticks for {symbol}...")
    start = time.time()
    
    # Request all ticks
    ticks = mt5.copy_ticks_range(symbol, START_DATE, END_DATE, mt5.COPY_TICKS_ALL)
    
    if ticks is None or len(ticks) == 0:
        error = mt5.last_error()
        print(f"  FAILED {symbol}: {error}")
        return False
    
    elapsed = time.time() - start
    print(f"  Received {len(ticks):,} ticks in {elapsed:.1f}s")
    
    # Convert to DataFrame
    df = pd.DataFrame(ticks)
    
    # Convert time from epoch to datetime
    df['time'] = pd.to_datetime(df['time'], unit='s')
    if 'time_msc' in df.columns:
        df['time_msc'] = pd.to_datetime(df['time_msc'], unit='ms')
    
    # Save to CSV
    print(f"  Saving to {output_file}...")
    save_start = time.time()
    df.to_csv(output_file, index=False)
    save_elapsed = time.time() - save_start
    
    size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"  DONE {symbol}: {len(ticks):,} ticks, {size_mb:.0f} MB, saved in {save_elapsed:.1f}s")
    return True

def main():
    print("=" * 60)
    print("MT5 TICK DATA DOWNLOADER")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Date range: {START_DATE.date()} to {END_DATE.date()}")
    print("=" * 60)
    
    # Initialize MT5 connection
    if not mt5.initialize():
        print(f"MT5 initialize() failed: {mt5.last_error()}")
        print("Make sure MT5 is running and logged in.")
        return
    
    info = mt5.account_info()
    print(f"Connected to: {info.server} (account {info.login})")
    print(f"Mode: {'Hedge' if info.margin_mode == 2 else 'Netting'}")
    print("-" * 60)
    
    results = {}
    for i, symbol in enumerate(SYMBOLS, 1):
        print(f"\n[{i}/{len(SYMBOLS)}] {symbol}")
        success = download_symbol(symbol)
        results[symbol] = success
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for symbol, success in results.items():
        status = "OK" if success else "FAILED"
        filepath = os.path.join(OUTPUT_DIR, f"{symbol}_ticks.csv")
        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"  {status:6s} {symbol:10s} {size_mb:>8.0f} MB")
        else:
            print(f"  {status:6s} {symbol}")
    
    mt5.shutdown()
    print("\nDone. MT5 connection closed.")

if __name__ == "__main__":
    main()
