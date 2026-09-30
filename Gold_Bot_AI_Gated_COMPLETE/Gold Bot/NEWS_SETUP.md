# Gold USD calendar gate (paper mode)

The v0.8 `portfolio-observe` bot now checks a UTC economic calendar immediately before each new XAUUSD virtual entry. High-impact USD events block new entries 30 minutes before and after. CPI, NFP, FOMC/rate decisions, and Powell/Fed press conferences block 60 minutes before and after. A missing, invalid, or stale feed blocks new gold entries. Open virtual positions still process stops, targets, and exits. GBPUSD entries retain their original behavior.

The default `news.source: forexfactory` reads Forex Factory's public weekly JSON export over HTTPS. It does not require an API key. The weekly export supplies event times with UTC offsets, impact labels, and USD currency codes; the gate converts timestamps to UTC and blocks entries around high-impact USD events. If the feed is unavailable, malformed, or from a different week, new XAUUSD entries remain blocked. The bot checks once at startup and then once per newly closed bar; it prints `waiting_for_next_closed_m15_bar` while idle. Calendar data is provided by a third party, so check the event times against the calendar page.

`source: tradingeconomics` is still supported for users with their own API access, using `TRADING_ECONOMICS_API_KEY` in the shell. It is optional. No key is needed for the default Forex Factory source.

If you have a different calendar provider, configure `news.source` in `config.paper.v08.yaml` as a local JSON file or HTTPS JSON endpoint. An external importer must update the local file at least every 360 minutes (or set a justified `max_age_minutes`). Example:

```json
{
  "generated_at": "2026-09-24T12:00:00Z",
  "events": [
    {"time": "2026-09-24T13:30:00Z", "currency": "USD", "impact": "high", "title": "US CPI"}
  ]
}
```

All timestamps require explicit UTC offsets. The endpoint must provide the entire current event calendar in that schema. No provider/API credentials are bundled. Check the provider's event times and impact classification before using it. The calendar only vetoes entries; headlines, sentiment, and surprise values do not generate directional trades.

From the project root on Windows:

The supplied `config.paper.v08.yaml` points to `C:\Program Files\MetaTrader 5\terminal64.exe`. Confirm this executable exists on your PC. If your installation uses `terminal.exe` or a different folder, update `mt5_terminal_path` accordingly. Open MT5 and log in before running the bot.

```powershell
python -m goldbot.cli portfolio-observe --config config.paper.v08.yaml --once
```

Inspect the `news_gate` field and `VIRTUAL_ENTRY_REJECTED` events. `news_calendar_unavailable`, `news_calendar_stale`, or `news_gate_not_enabled` mean no new XAUUSD entries. The current paper configuration selects `unified_gold_confluence_v1` for XAUUSD only. It requires completed H1/H4 context, H4 FVG/BOS, H1 invalidation check, M15 sweep/structure shift/FVG, 1.5R structural target, and UTC sessions. The optional order-block fallback and COMEX order-flow variant are not implemented. Historical USD news is not replayed by the backtester; demo eligibility remains false. Trade execution is still locked. Do not interpret a clear calendar as a buy/sell recommendation.
