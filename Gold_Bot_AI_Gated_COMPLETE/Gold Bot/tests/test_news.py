import json
from datetime import datetime, timedelta, timezone
from goldbot.news import entry_decision
from goldbot.models import Side, Signal
from goldbot.paper_portfolio import PortfolioPaperLedger


def test_calendar_blackout_and_fail_closed(tmp_path):
    now = datetime(2026, 9, 24, 13, 30, tzinfo=timezone.utc)
    path = tmp_path / 'events.json'
    cfg = {'enabled': True, 'source': str(path)}
    assert entry_decision(cfg, now)[0] is False
    payload = {'generated_at': (now - timedelta(minutes=5)).isoformat(), 'events': [
        {'time': (now + timedelta(minutes=45)).isoformat(), 'currency': 'USD', 'impact': 'high', 'title': 'US CPI'},
    ]}
    path.write_text(json.dumps(payload))
    assert entry_decision(cfg, now)[0] is False
    assert entry_decision(cfg, now + timedelta(minutes=110))[0] is True
    payload['generated_at'] = (now - timedelta(hours=7)).isoformat()
    path.write_text(json.dumps(payload))
    assert entry_decision(cfg, now)[1] == 'news_calendar_stale'


def test_news_blocks_entry_but_allows_exit(tmp_path):
    ledger = PortfolioPaperLedger(str(tmp_path/'state.json'), str(tmp_path/'trades.csv'))
    t = datetime(2026, 9, 24, tzinfo=timezone.utc)
    ledger.initialize_symbol('XAUUSD', t-timedelta(minutes=15))
    kwargs = dict(risk_pct=.25, spread_price=0, slippage_price=0,
                  commission_per_trade=0, max_trades_per_day=2,
                  daily_loss_limit_pct=1, daily_profit_target_pct=1)
    buy = Signal(Side.BUY, t, 100, 99, 102, 'test')
    bar = lambda stamp, high: {'time': stamp, 'open': 100, 'high': high, 'low': 100, 'close': 100}
    assert ledger.process_bar('XAUUSD', bar(t, 101), buy, entry_allowed=False,
                              entry_block_reason='news', **kwargs)[0]['event'] == 'VIRTUAL_ENTRY_REJECTED'
    t += timedelta(minutes=15)
    assert ledger.process_bar('XAUUSD', bar(t, 101), Signal(Side.BUY, t, 100, 99, 102, 'test'), **kwargs)[0]['event'] == 'VIRTUAL_PENDING'
    t += timedelta(minutes=15)
    assert ledger.process_bar('XAUUSD', bar(t, 101), Signal(Side.HOLD, t), **kwargs)[0]['event'] == 'VIRTUAL_ENTRY'
    t += timedelta(minutes=15)
    assert ledger.process_bar('XAUUSD', bar(t, 103), Signal(Side.HOLD, t), entry_allowed=False, **kwargs)[0]['event'] == 'VIRTUAL_EXIT'


def test_trading_economics_requires_key_and_parses_utc(monkeypatch):
    from goldbot.news import entry_decision
    now = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)
    monkeypatch.delenv('TRADING_ECONOMICS_API_KEY', raising=False)
    assert entry_decision({'enabled': True, 'source': 'tradingeconomics'}, now)[0] is False
    monkeypatch.setenv('TRADING_ECONOMICS_API_KEY', 'test-key')
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return json.dumps([{'Date': '2026-09-24T13:30:00', 'Event': 'US CPI',
                                'Importance': 3, 'Country': 'United States'}]).encode()
    monkeypatch.setattr('goldbot.news.urlopen', lambda request, timeout: Response())
    permitted, reason = entry_decision({'enabled': True, 'source': 'tradingeconomics'}, now)
    assert not permitted and 'usd_news_blackout' in reason


def test_forex_factory_weekly_feed_no_key_and_timezone(monkeypatch):
    now = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)
    monkeypatch.delenv('TRADING_ECONOMICS_API_KEY', raising=False)
    rows = [
        {'date': '2026-09-20T19:00:00-04:00', 'country': 'GBP', 'impact': 'Low', 'title': 'Example'},
        {'date': '2026-09-24T09:30:00-04:00', 'country': 'USD', 'impact': 'High', 'title': 'US CPI'},
        {'date': '2026-09-26T10:00:00-04:00', 'country': 'EUR', 'impact': 'Medium', 'title': 'Example'},
    ]
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return json.dumps(rows).encode()
    monkeypatch.setattr('goldbot.news.urlopen', lambda request, timeout: Response())
    blocked, reason = entry_decision({'enabled': True, 'source': 'forexfactory'}, now)
    assert not blocked and 'usd_news_blackout' in reason
    allowed, reason = entry_decision({'enabled': True, 'source': 'forexfactory'}, now + timedelta(hours=3))
    assert allowed and reason == 'usd_calendar_clear'
    blocked, reason = entry_decision({'enabled': True, 'source': 'forexfactory'}, now + timedelta(days=10))
    assert not blocked and reason == 'news_calendar_unavailable:ValueError'
