# Gold MT5 Auto-Trading Bot

Safety-first framework for automating an **XAUUSD** strategy in MetaTrader 5.

## Current status

- Phase 1 safety framework: implemented; full demo-session validation awaits broker inputs
- Daily profit and loss locks: ready
- Position sizing from stop distance: ready
- MT5 execution adapter: ready, but live execution is locked by default
- Strategies: candle-break reversal and London first-FVG inversion
- Experimental v0.4 strategy: London FVG + EMA50 + one trade/day + 2.5R
- Walk-forward backtester: 70% in-sample / 30% out-of-sample with trading costs
- Append-only SQLite decision journal: ready
- Persisted independent kill switch: ready
- Market-data quality checks: ready
- Paper/live daily-target behavior split: ready

The 25% daily compounding journal shown in the reference image is not used as a
profitability assumption. The target is configurable and stops **new entries**;
it does not guarantee returns.

## Safety defaults

- `mode: backtest` (`paper` is the MT5 demo-account mode)
- `enable_order_submission: false`
- 0.5% risk per trade
- 2% daily profit target
- 1.5% daily loss limit
- maximum 3 trades per day
- one open bot position at a time
- maximum spread filter
- no martingale, grid, or recovery sizing

## Install (Windows)

1. Install Python 3.11 or 3.12 and MetaTrader 5.
2. Open MT5 and log in to a **demo** account.
3. In this folder:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.yaml config.yaml
python -m goldbot.cli check --config config.yaml
```

## Backtest data

Export broker XAUUSD candles to CSV with columns:

```text
time,open,high,low,close,tick_volume,spread
```

Run:

```powershell
python -m goldbot.cli backtest --config config.yaml --csv data\xauusd_m5.csv
```

Run either strategy:

```powershell
python -m goldbot.cli export-history --config config.yaml --timeframe M5 --bars 50000 --output data\\xauusd_m5.csv
python -m goldbot.cli export-history --config config.yaml --timeframe M15 --bars 50000 --output data\\xauusd_m15.csv
python -m goldbot.cli backtest --config config.yaml --csv data\\xauusd_m5.csv --strategy candle_break_reversal
python -m goldbot.cli backtest --config config.yaml --csv data\\xauusd_m15.csv --strategy london_fvg_inversion
python -m goldbot.cli backtest --config config.yaml --csv data\\xauusd_m15.csv --strategy london_fvg_trend_v04
```

The report includes trades, return, win rate, profit factor, maximum drawdown,
average R, per-trade Sharpe, and every simulated trade. It separately reports
in-sample and out-of-sample performance and sets `demo_eligible` only when every
configured validation gate passes.

## Demo runner

Keep the bot in backtest mode until a real broker-history report returns
`demo_eligible: true`. Demo execution remains hard-locked in this version.

## Signal-only demo observation

After all historical gates pass, change only:

```yaml
mode: paper
enable_order_submission: false
timeframe: M15
```

Test one observation cycle:

```powershell
python -m goldbot.cli observe --config config.yaml --strategy london_fvg_trend_v04 --once
```

Then start continuous observation:

```powershell
python -m goldbot.cli observe --config config.yaml --strategy london_fvg_trend_v04
```

Use Ctrl+C to stop. This mode prints and journals signals but never submits an
order.

```powershell
python -m goldbot.cli run --config config.yaml
```

Press `Ctrl+C` to stop. The bot writes audit records to `logs/trades.sqlite3` and
restart-safe daily state to `state/daily_state.json`.

Emergency controls:

```powershell
python -m goldbot.cli kill --config config.yaml
python -m goldbot.cli resume --config config.yaml
```

Live mode additionally requires `enable_order_submission: true` and the exact
confirmation phrase `I UNDERSTAND LIVE TRADING RISK`. These switches do not
replace the validation gates; live mode stays disabled until all gates pass and
human sign-off is recorded.

## Phase 1 inputs still required

- MT5 broker name and exact gold symbol
- account currency, leverage, and intended starting balance
- symbol contract size, minimum/maximum lot, lot step, commission, swap, spread,
  and server timezone (the check command reads most symbol fields for confirmation)
- approved risk and daily-limit settings

The Mamba Trader or user strategy source and rules are requested only after the
Phase 1 skeleton completes a clean MT5 demo session.

## Strategy specification needed

Send the exact Mamba Trader source link plus your strategy rules:

1. Timeframe(s)
2. Buy setup and entry trigger
3. Sell setup and entry trigger
4. Stop-loss rule
5. Take-profit or trailing rule
6. Allowed London/New York times and timezone
7. News filter
8. Maximum trades per day
9. Any break-even or partial-close rule

Claims, screenshots, and win rates will be treated as hypotheses. A strategy is
accepted only after spread/slippage-aware backtesting, out-of-sample testing,
and demo forward testing.
