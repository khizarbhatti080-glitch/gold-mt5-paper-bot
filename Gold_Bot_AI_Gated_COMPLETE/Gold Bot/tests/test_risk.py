from datetime import date, datetime, timedelta, timezone

import pytest

from goldbot.config import RiskConfig
from goldbot.journal import TradeJournal
from goldbot.kill_switch import KillSwitch
from goldbot.market_data import validate_bars
from goldbot.models import AccountSnapshot, DataQuality, Mode, RejectReason, Side, Signal, SymbolSpec, TradeProposal
from goldbot.risk import RiskManager


@pytest.fixture
def manager(tmp_path):
    cfg = RiskConfig(0.5, 2.0, 1.5, 3, 1, 60, 100, 1000, 0.10, 2, 5.0, 0.10)
    return RiskManager(cfg, str(tmp_path / "state.json"))


@pytest.fixture
def proposal():
    signal = Signal(Side.BUY, datetime.now(timezone.utc), 2000.0, 1999.0, 2002.0, "test")
    return TradeProposal(signal, "XAUUSD", "test", "1.0", "test rule")


@pytest.fixture
def spec():
    return SymbolSpec(0.01, 1.0, 0.01, 100.0, 0.01, 50, 0.01)


def evaluate(manager, proposal, spec, equity=1000, mode=Mode.LIVE, **changes):
    state = changes.pop("state", manager.load_or_start(1000, date(2026, 9, 18)))
    args = dict(state=state, account=AccountSnapshot(equity, 1000, 0, 10), proposal=proposal,
                spec=spec, mode=mode, kill_switch_engaged=False, connection_healthy=True,
                data_quality=DataQuality.OK, market_open=True, in_session=True)
    args.update(changes)
    return state, manager.evaluate(**args)


def test_profit_target_locks_live_but_not_paper(manager, proposal, spec):
    state, live = evaluate(manager, proposal, spec, equity=1020, mode=Mode.LIVE)
    assert not live.approved and live.reason == RejectReason.DAILY_PROFIT and state.locked
    manager.path.unlink()
    state, paper = evaluate(manager, proposal, spec, equity=1020, mode=Mode.PAPER)
    assert paper.approved and state.target_would_have_hit and not state.locked


def test_loss_limit_survives_restart(manager, proposal, spec):
    state, result = evaluate(manager, proposal, spec, equity=985)
    assert not result.approved and result.reason == RejectReason.DAILY_LOSS
    reloaded = manager.load_or_start(1000, date(2026, 9, 18))
    assert reloaded.locked and "loss limit" in reloaded.lock_reason


@pytest.mark.parametrize("change,reason", [
    ({"kill_switch_engaged": True}, RejectReason.KILL_SWITCH),
    ({"connection_healthy": False}, RejectReason.CONNECTION_UNHEALTHY),
    ({"data_quality": DataQuality.DEGRADED}, RejectReason.DATA_QUALITY),
    ({"market_open": False}, RejectReason.MARKET_CLOSED),
    ({"in_session": False}, RejectReason.OUT_OF_SESSION),
])
def test_integrity_and_session_gates(manager, proposal, spec, change, reason):
    _, result = evaluate(manager, proposal, spec, **change)
    assert not result.approved and result.reason == reason


def test_missing_stop_rejected(manager, proposal, spec):
    bad = TradeProposal(Signal(Side.BUY, proposal.signal.timestamp, 2000, None, None, "bad"),
                        "XAUUSD", "test", "1")
    _, result = evaluate(manager, bad, spec)
    assert result.reason == RejectReason.MISSING_STOP


def test_spread_and_consecutive_loss_locks(manager, proposal, spec):
    _, spread = evaluate(manager, proposal, spec, account=AccountSnapshot(1000, 1000, 0, 61))
    assert spread.reason == RejectReason.SPREAD
    manager.path.unlink()
    state = manager.load_or_start(1000, date(2026, 9, 18))
    state.consecutive_losses = 2
    manager.save(state)
    _, streak = evaluate(manager, proposal, spec, state=state)
    assert streak.reason == RejectReason.CONSECUTIVE_LOSSES and state.locked


def test_position_size_and_multiplier(manager, spec):
    lots, risk = manager.position_size(10000, 2000, 1999, spec)
    assert lots == 0.10 and risk == 50
    for drawdown in (-10, 0, 5, 100):
        for volatility in (0, 1, 2, 100):
            assert 0 <= manager.size_multiplier(drawdown, volatility, 5) <= 1


def test_below_minimum_lot_rejected(manager):
    tiny_value = SymbolSpec(0.01, 1000.0, 0.1, 100, 0.1, 0, 0.01)
    with pytest.raises(ValueError, match="below broker minimum"):
        manager.position_size(1000, 2000, 1999, tiny_value)


def test_kill_switch_persists(tmp_path):
    switch = KillSwitch(str(tmp_path / "kill.json"))
    switch.engage("test emergency", close_all=True)
    assert KillSwitch(str(tmp_path / "kill.json")).read().engaged
    assert not switch.resume("test complete").engaged


def test_journal_records_rejected_decision(tmp_path):
    journal = TradeJournal(str(tmp_path / "journal.sqlite3"))
    row_id = journal.record_decision({"mode": "paper", "symbol": "XAUUSD", "action": "BUY",
                                      "decision": "REJECTED", "reject_reason_code": "SPREAD"})
    assert row_id == 1


def test_data_quality_detects_duplicate_and_stale():
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    bars = [{"time": old, "open": 1, "high": 2, "low": 0, "close": 1},
            {"time": old, "open": 1, "high": 2, "low": 0, "close": 1}]
    report = validate_bars(bars, 300)
    assert report.quality == DataQuality.DEGRADED
    assert "duplicate_timestamps" in report.reasons and "stale_feed" in report.reasons
