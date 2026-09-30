# Gold confluence research bot: current status

## Ready for use

- Windows MT5 connection at the configured terminal executable; `check` is read-only.
- XAUUSD M15 paper observer with closed H1/H4 context, sweep/shift/FVG confluence, 4-bar pending limits, risk caps, daily stop/target, and a fail-closed USD calendar blackout. The paper config disables GBPUSD and uses a fresh `state/gold_confluence_paper_v1.json` ledger to avoid mixing results from the previous v0.8 strategy.
- The default Forex Factory public weekly calendar adapter needs no key; unavailable or stale data block new gold entries. Trading Economics remains optional with `TRADING_ECONOMICS_API_KEY`. The calendar veto does not create directional trade signals.
- Existing MT5 demo runner and live CLI remain separate; `goldbot.cli run` remains locked. No order submission occurs in `portfolio-observe`.

## Validation still required before demo/live

- Historical USD economic event snapshots and news-window replay in the backtest. The present backtest reports `historical_usd_news_replayed: false` and cannot approve the strategy.
- Confirm the user-supplied order-block alternative, exact H1 POI overlap, session rollover exit, target invalidation, and spread/slippage assumptions against broker data. Current strategy uses only the FVG branch and an approximate H1 invalidation rule.
- Minimum 100 out-of-sample trades, profit factor >= 1.20, positive net return, drawdown <= 10%, then 30 forward paper trades. A two-trade legacy paper result does not qualify.
- The original research backtest is bar-based. OHLC cannot establish the order of entry/stop/target within a single candle. Spread and slippage are modeled, not broker executions.

## Windows PowerShell from project root

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m goldbot.cli check --config config.yaml
.\.venv\Scripts\python.exe -m goldbot.cli portfolio-observe --config config.paper.v08.yaml --once
.\.venv\Scripts\python.exe -m goldbot.cli paper-report --config config.paper.v08.yaml
```

For a historical comparison with the included CSV, run:

```powershell
.\.venv\Scripts\python.exe -m goldbot.cli backtest --config config.paper.v08.yaml --csv gold_mt5_bot\data\portfolio\xauusd_m15.csv --strategy unified_gold_confluence_v1
```

This command provides research statistics only. Never treat the output as approval for order submission.

## Historical check on the supplied 50,000 XAUUSD M15 bars

The dataset spans 2024-07-30 through 2026-09-18. With 70/30 chronological split,
0.25% risk, $0.30 fallback spread, $0.05 slippage, and the pending-limit model:

- In sample: 2 closed trades, $51.99 net loss.
- Out of sample: 1 closed trade, $61.40 net profit.
- Approval: **failed** (fewer than 100 out-of-sample trades; historical USD news not replayed).

One out-of-sample win is not evidence of a dependable edge. The supplied legacy
paper ledger's $60.23 came from the old strategy and is deliberately excluded.
The optional order-block branch and futures order-flow confirmation are future
research work. The bot is a paper research build, not a completed live system.
