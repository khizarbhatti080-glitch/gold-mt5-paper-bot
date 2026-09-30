# Mandatory AI veto for virtual paper portfolio

Use `config.paper.v08.yaml` for the M15 confluence strategy or `config.paper.activity.yaml` for the M5 activity strategy. Both enable `ai_review.mode: gate`. The strategy alone generates BUY/SELL candidates. OpenAI may approve, reject, or return uncertain; only a successful `approve` permits a new virtual pending entry. Missing API key, timeout, stale candidate, daily call limit, disabled gate, malformed response and review errors block the entry. Any old pending order without an explicit approval is cancelled before it can fill. Existing positions may still exit via strategy or stop/target. No real orders are sent by `portfolio-observe`.

This gate reviews the candidate's strategy reason and recent closed candles, not the complete strategy implementation. Approval is an estimate, not a guarantee against loss. `portfolio-backtest` and `backtest` are historical research commands and do not call the AI gate. Keep the bot on a demo account for observation.

## Windows PowerShell (MT5 terminal installed and signed in)

From the extracted `Gold Bot` folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests -q
$secureKey = Read-Host -Prompt 'OpenAI API key' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
Remove-Variable secureKey
.\.venv\Scripts\python.exe -m goldbot.cli ai-check --config config.paper.v08.yaml
.\.venv\Scripts\python.exe -m goldbot.cli portfolio-observe --config config.paper.v08.yaml
```

Stop with Ctrl+C. `ai-check` must report `connected`. Use an API key with billing enabled; a ChatGPT subscription does not cover API calls. Check `ai_review` and `events` in the console and `logs/ai_gate_reviews.jsonl`. If API access is unavailable, candidates are rejected. Never put the API key in YAML or commit it.

## Ubuntu research only

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install PyYAML==6.0.2 pytest==8.3.5 tzdata==2026.4
python -m pytest tests -q
python -m goldbot.cli backtest --config config.paper.v08.yaml --csv gold_mt5_bot/data/portfolio/xauusd_m15.csv --strategy unified_gold_confluence_v1
```

The MetaTrader5 Python binding and the configured terminal path target Windows; the Ubuntu backtest uses the bundled CSV and does not exercise the AI gate.
