//+------------------------------------------------------------------+
//| ftmo_symbol_spec_export.mq5                                      |
//|                                                                  |
//| Dumps every visible MT5 Market Watch symbol's specification to a |
//| CSV at MQL5/Files/ftmo_symbol_specs.csv. Run once on the FTMO    |
//| Free Trial demo account to populate configs/ftmo_mt5_specs.yaml. |
//|                                                                  |
//| Usage:                                                           |
//|   1. Save this file to <MT5 data folder>/MQL5/Scripts/           |
//|      Open MT5 → File → Open Data Folder → MQL5/Scripts           |
//|   2. In MT5: Right-click any chart → Script → Compile, then Run  |
//|   3. After it finishes, the CSV lives at:                        |
//|      <MT5 data folder>/MQL5/Files/ftmo_symbol_specs.csv          |
//|   4. Send that CSV back; we'll wire it into the YAML overlay.    |
//+------------------------------------------------------------------+
#property copyright "MSC research"
#property script_show_inputs

input bool VisibleOnly = true;  // false = export ALL FTMO symbols (slow)

void OnStart()
{
    string filename = "ftmo_symbol_specs.csv";
    int handle = FileOpen(filename, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if (handle == INVALID_HANDLE)
    {
        Print("Failed to open ", filename, " err=", GetLastError());
        return;
    }

    // Header row — matches the fields we need for ftmo_mt5_specs.yaml
    FileWrite(handle,
        "symbol",
        "description",
        "currency_base",
        "currency_profit",
        "contract_size",
        "digits",
        "point",
        "tick_size",
        "tick_value",
        "min_lot",
        "lot_step",
        "max_lot",
        "spread_typical_pts",
        "spread_floating",
        "stops_level_pts",
        "swap_mode",
        "swap_long",
        "swap_short",
        "swap_3days_weekday",  // 0=Sun..6=Sat (when triple swap is charged)
        "trade_mode",
        "execution_mode",
        "margin_initial_pct",
        "session_quote",
        "session_trade"
    );

    int total = SymbolsTotal(VisibleOnly);
    Print("Exporting ", total, " symbols (visible_only=", VisibleOnly, ")...");

    for (int i = 0; i < total; i++)
    {
        string sym = SymbolName(i, VisibleOnly);
        if (sym == "") continue;

        // Force-select so SymbolInfo* returns live data
        if (!SymbolSelect(sym, true)) continue;

        string desc            = SymbolInfoString(sym, SYMBOL_DESCRIPTION);
        string base_curr       = SymbolInfoString(sym, SYMBOL_CURRENCY_BASE);
        string profit_curr     = SymbolInfoString(sym, SYMBOL_CURRENCY_PROFIT);
        double contract_size   = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
        long   digits          = SymbolInfoInteger(sym, SYMBOL_DIGITS);
        double point           = SymbolInfoDouble(sym, SYMBOL_POINT);
        double tick_size       = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
        double tick_value      = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
        double min_lot         = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
        double lot_step        = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
        double max_lot         = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
        long   spread          = SymbolInfoInteger(sym, SYMBOL_SPREAD);
        bool   spread_floating = (bool)SymbolInfoInteger(sym, SYMBOL_SPREAD_FLOAT);
        long   stops_level     = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
        long   swap_mode       = SymbolInfoInteger(sym, SYMBOL_SWAP_MODE);
        double swap_long       = SymbolInfoDouble(sym, SYMBOL_SWAP_LONG);
        double swap_short      = SymbolInfoDouble(sym, SYMBOL_SWAP_SHORT);
        long   swap_3days      = SymbolInfoInteger(sym, SYMBOL_SWAP_ROLLOVER3DAYS);
        long   trade_mode      = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
        long   exec_mode       = SymbolInfoInteger(sym, SYMBOL_TRADE_EXEMODE);
        double margin_init     = SymbolInfoDouble(sym, SYMBOL_MARGIN_INITIAL);
        string sess_quote      = SymbolInfoString(sym, SYMBOL_PATH);
        string sess_trade      = "";  // Sessions API needs more code; can be added if needed

        FileWrite(handle,
            sym,
            desc,
            base_curr,
            profit_curr,
            DoubleToString(contract_size, 4),
            (string)digits,
            DoubleToString(point, 8),
            DoubleToString(tick_size, 8),
            DoubleToString(tick_value, 4),
            DoubleToString(min_lot, 3),
            DoubleToString(lot_step, 3),
            DoubleToString(max_lot, 3),
            (string)spread,
            spread_floating ? "true" : "false",
            (string)stops_level,
            (string)swap_mode,
            DoubleToString(swap_long, 4),
            DoubleToString(swap_short, 4),
            (string)swap_3days,
            (string)trade_mode,
            (string)exec_mode,
            DoubleToString(margin_init, 4),
            sess_quote,
            sess_trade
        );
    }

    FileClose(handle);
    Print("DONE: wrote ", total, " symbols to MQL5/Files/", filename);
    Print("Send that CSV file back; we'll auto-merge into ftmo_mt5_specs.yaml.");
}
