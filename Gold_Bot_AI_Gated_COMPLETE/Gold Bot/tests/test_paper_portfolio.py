from datetime import datetime, timedelta, timezone

from goldbot.models import Side, Signal
from goldbot.paper_portfolio import PortfolioPaperLedger


def bar(when, o, h, low, close):
    return {"time": when, "open": o, "high": h, "low": low, "close": close, "spread": 0}


def test_virtual_entry_exit_persists_and_reports(tmp_path):
    state = tmp_path / "paper.json"
    trades = tmp_path / "trades.csv"
    ledger = PortfolioPaperLedger(str(state), str(trades), 10_000)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ledger.initialize_symbol("XAUUSD", start - timedelta(minutes=15))
    buy = Signal(Side.BUY, start, 100, 99, 102.5, "test_entry")
    events = ledger.process_bar(
        "XAUUSD", bar(start, 99.5, 100.5, 99.5, 100), buy,
        risk_pct=1, spread_price=0, slippage_price=0, commission_per_trade=0,
        max_trades_per_day=3, daily_loss_limit_pct=5, daily_profit_target_pct=5)
    assert events[0]["event"] == "VIRTUAL_PENDING"

    later = start + timedelta(minutes=15)
    events = ledger.process_bar(
        "XAUUSD", bar(later, 100, 100.5, 99.5, 100),
        Signal(Side.HOLD, later), risk_pct=1, spread_price=0,
        slippage_price=0, commission_per_trade=0, max_trades_per_day=3,
        daily_loss_limit_pct=5, daily_profit_target_pct=5)
    assert events[0]["event"] == "VIRTUAL_ENTRY"
    later += timedelta(minutes=15)
    events = ledger.process_bar(
        "XAUUSD", bar(later, 100, 103, 100, 102.5),
        Signal(Side.HOLD, later), risk_pct=1, spread_price=0,
        slippage_price=0, commission_per_trade=0, max_trades_per_day=3,
        daily_loss_limit_pct=5, daily_profit_target_pct=5)
    assert events[0]["event"] == "VIRTUAL_EXIT"
    assert events[0]["pnl"] == 250
    report = PortfolioPaperLedger(str(state), str(trades), 10_000).summary()
    assert report["balance"] == 10_250
    assert report["closed_trades"] == 1
    assert report["win_rate_pct"] == 100


def test_two_symbols_can_be_open_together_and_duplicate_bar_is_ignored(tmp_path):
    ledger = PortfolioPaperLedger(str(tmp_path / "state.json"), str(tmp_path / "trades.csv"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for symbol in ("XAUUSD", "GBPUSD"):
        ledger.initialize_symbol(symbol, now - timedelta(minutes=15))
        signal = Signal(Side.SELL, now, 100, 101, 97.5, "entry")
        kwargs = dict(risk_pct=.25, spread_price=0, slippage_price=0,
                      commission_per_trade=0, max_trades_per_day=1,
                      daily_loss_limit_pct=2, daily_profit_target_pct=2)
        assert ledger.process_bar(symbol, bar(now, 100, 100.5, 99, 99.5), signal, **kwargs)
        assert ledger.process_bar(symbol, bar(now, 100, 100.5, 99, 99.5), signal, **kwargs) == []
        later = now + timedelta(minutes=15)
        assert ledger.process_bar(symbol, bar(later, 100, 100.5, 99, 99.5),
                                  Signal(Side.HOLD, later), **kwargs)[0]['event'] == 'VIRTUAL_ENTRY'
    assert set(ledger.state["open_positions"]) == {"XAUUSD", "GBPUSD"}
