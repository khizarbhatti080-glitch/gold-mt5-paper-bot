# Strategy research notes

Public web search did not identify a unique, authoritative “Mamba Trader” gold
strategy with complete mechanical rules and verified results. Similar names and
short-form social profiles are ambiguous. No strategy has therefore been copied
or represented as profitable.

For any supplied creator/video, extract these rules before coding:

- instrument and broker symbol
- market/session and timezone
- setup timeframe and entry timeframe
- objective buy/sell conditions
- entry timing (bar close, limit, stop, or market)
- initial stop and invalidation
- take profit, break even, partials, and trailing behavior
- news/spread/volatility filters
- daily trade and loss limits

Validation protocol:

1. Freeze the rules before testing.
2. Use broker-quality XAUUSD bid/ask or spread data.
3. Include spread, commission, slippage, swaps, and rejected orders.
4. Split development and out-of-sample periods chronologically.
5. Report expectancy, profit factor, drawdown, loss streak, and trade count—not
   only win rate or ending balance.
6. Run a demo forward test before considering live execution.
7. Reject martingale/grid recovery and any strategy requiring guaranteed daily
   profit.

