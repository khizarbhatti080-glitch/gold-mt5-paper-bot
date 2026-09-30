# Solana research extension

This extension applies the unchanged `london_fvg_trend_v04` mechanical rules to
the broker's Solana CFD/crypto symbol. It does not assume that performance on
XAUUSD transfers to SOL and it never enables order submission.

## Workflow

1. Find the exact broker symbol:

   `python -m goldbot.cli find-symbol --config config.yaml --query SOL`

2. Copy `config.solana.example.yaml` to `config.solana.yaml`, set the exact
   symbol name and confirm `point_size` from the discovery output.

3. Export M15 history:

   `python -m goldbot.cli export-history --config config.solana.yaml --timeframe M15 --bars 50000 --output data/sol_m15.csv`

4. Run a chronological 70/30 walk-forward backtest:

   `python -m goldbot.cli backtest --config config.solana.yaml --csv data/sol_m15.csv --strategy london_fvg_trend_v04 > sol_backtest.json`

The strategy is rejected for demo use unless every out-of-sample validation
gate passes. Crypto trading costs and broker history availability can differ
substantially from gold, so the exported spread and symbol point size must be
checked before interpreting results.
