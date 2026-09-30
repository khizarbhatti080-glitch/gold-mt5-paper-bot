# Strategy specification — v0.3

## 1. Candle-break reversal

- Evaluate completed OHLC candles only.
- A bearish reference candle has close below open.
- Enter short when the immediately following candle trades strictly below the
  reference low. Entry is the reference low; stop is the reference high.
- A bullish reference candle has close above open.
- Enter long when the immediately following candle trades strictly above the
  reference high. Entry is the reference high; stop is the reference low.
- A doji creates no setup.
- An opposing valid signal exits and reverses the open position.
- If the stop is touched before an opposing signal, the trade exits at the stop.
- There is no fixed take-profit.

## 2. London first-FVG inversion

- Use 15-minute candles and America/New_York time.
- Session window: 03:00 inclusive to 07:00 exclusive.
- The middle candle of the three-candle FVG must start inside that window.
- Bullish FVG: candle 3 low is strictly above candle 1 high.
- Bearish FVG: candle 3 high is strictly below candle 1 low.
- Only the first FVG of each session is tracked.
- Inversion requires a candle-body close through the far FVG boundary.
- Entry requires a later candle to retest the inverted boundary.
- Stop is beyond both the FVG and the inversion candle body.
- Target is fixed at 2R.
- No FVG, inversion, or retest means no trade.

## Conservative backtest rules

- CSV spread is interpreted as broker points and multiplied by point_size.
- Slippage and half-spread are adverse on entry and exit.
- If stop and target are both touched in one OHLC candle, stop is assumed first.
- Trades still open at the end of the dataset are closed at the final close.
- Data is split chronologically: 70% in-sample and 30% out-of-sample.
- Demo eligibility requires at least 100 combined trades, out-of-sample profit
  factor of 1.20 or higher, out-of-sample drawdown no more than 10%, and positive
  out-of-sample net profit.

## Sources not encoded

- The 14-second MambaFX YouTube short has no captions and supplies no complete,
  objective entry, stop, exit, timeframe, or session rules.
- The general beginner/macro video is not a single deterministic setup.
- The Instagram reel must be transcribed or summarized before it can be coded.

No source-reported win rate is treated as verified performance.
