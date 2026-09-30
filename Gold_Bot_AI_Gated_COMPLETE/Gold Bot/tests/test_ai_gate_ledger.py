from datetime import datetime, timedelta, timezone
from goldbot.models import Side, Signal
from goldbot.paper_portfolio import PortfolioPaperLedger


def test_gate_veto_and_legacy_pending_cannot_fill(tmp_path):
    ledger = PortfolioPaperLedger(str(tmp_path / 's.json'), str(tmp_path / 't.csv'))
    t = datetime(2026, 1, 2, tzinfo=timezone.utc)
    def bar(stamp):
        return {'time': stamp, 'open': 101, 'high': 102, 'low': 99, 'close': 101}
    options = dict(risk_pct=.25, spread_price=0, slippage_price=0,
                   commission_per_trade=0, max_trades_per_day=2,
                   daily_loss_limit_pct=1, daily_profit_target_pct=1,
                   require_ai_approval=True)
    buy = Signal(Side.BUY, t, 100, 98, 104, 'test')
    veto = ledger.process_bar('XAUUSD', bar(t), buy, **options)
    assert veto[0]['event'] == 'VIRTUAL_ENTRY_REJECTED'
    assert not ledger.state['pending_orders']
    later = t + timedelta(minutes=15)
    accepted = ledger.process_bar('XAUUSD', bar(later), buy, ai_approved=True, **options)
    assert any(e['event'] == 'VIRTUAL_PENDING' for e in accepted)
    ledger.state['pending_orders']['XAUUSD'].pop('ai_approved')
    ledger.save()
    ledger = PortfolioPaperLedger(str(tmp_path / 's.json'), str(tmp_path / 't.csv'))
    events = ledger.process_bar('XAUUSD', bar(later + timedelta(minutes=15)),
                                Signal(Side.HOLD, later), **options)
    assert any(e['event'] == 'VIRTUAL_PENDING_CANCELLED' for e in events)
    assert not ledger.state['open_positions']
