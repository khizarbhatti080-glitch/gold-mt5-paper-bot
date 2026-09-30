from datetime import datetime, timezone

from goldbot.backtest import run_backtest, run_walk_forward
from goldbot.models import Side
from goldbot.strategy import CandleBreakReversalStrategy, LondonFVGInversionStrategy


def bar(ts, o, h, l, c, spread=0):
    return {"time": datetime.fromisoformat(ts).replace(tzinfo=timezone.utc),
            "open": o, "high": h, "low": l, "close": c, "spread": spread}


def test_candle_break_sell_and_buy_rules():
    strategy = CandleBreakReversalStrategy()
    red = bar("2026-01-01T00:00:00", 10, 11, 8, 9)
    sell_trigger = bar("2026-01-01T00:05:00", 9, 10, 7, 8)
    signal = strategy.on_bar(sell_trigger, [red])
    assert signal.side == Side.SELL and signal.entry == 8 and signal.stop_loss == 11

    green = bar("2026-01-01T00:10:00", 8, 10, 7, 9)
    buy_trigger = bar("2026-01-01T00:15:00", 9, 11, 8, 10)
    signal = strategy.on_bar(buy_trigger, [red, sell_trigger, green])
    assert signal.side == Side.BUY and signal.entry == 10 and signal.stop_loss == 7


def test_backtester_reverses_and_reports_costs():
    bars = [
        bar("2026-01-01T00:00:00", 10, 11, 8, 9),
        bar("2026-01-01T00:05:00", 9, 10, 7, 8),
        bar("2026-01-01T00:10:00", 8, 10, 7, 9),
        bar("2026-01-01T00:15:00", 9, 11, 8, 10),
        bar("2026-01-01T00:20:00", 10, 12, 9, 11),
    ]
    result = run_backtest(CandleBreakReversalStrategy(), bars, spread_price=0.1,
                          slippage_price=0.01)
    assert result["trades"] >= 1
    assert result["assumptions"]["same_bar_priority"] == "stop_before_target"
    assert "max_drawdown_pct" in result and "profit_factor" in result


def test_london_fvg_requires_inversion_then_later_retest():
    # January NY time is UTC-5; middle candle at 03:00 NY is 08:00 UTC.
    bars = [
        bar("2026-01-02T07:45:00", 99, 100, 98, 99),
        bar("2026-01-02T08:00:00", 100, 103, 100, 102),
        bar("2026-01-02T08:15:00", 103, 104, 102, 103),  # bullish FVG [100, 102]
        bar("2026-01-02T08:30:00", 101, 101, 98, 99),    # close below 100
        bar("2026-01-02T08:45:00", 99, 101, 97, 98),     # retest 100
    ]
    strategy = LondonFVGInversionStrategy()
    signals = [strategy.on_bar(value, bars[:i]) for i, value in enumerate(bars)]
    assert signals[-1].side == Side.SELL
    assert signals[-1].entry == 100
    assert signals[-1].take_profit < signals[-1].entry


def test_walk_forward_never_unlocks_without_enough_trades():
    bars = [
        bar("2026-01-01T00:00:00", 10, 11, 8, 9),
        bar("2026-01-01T00:05:00", 9, 10, 7, 8),
        bar("2026-01-01T00:10:00", 8, 10, 7, 9),
        bar("2026-01-01T00:15:00", 9, 11, 8, 10),
    ] * 3
    result = run_walk_forward(CandleBreakReversalStrategy, bars,
                              gates={"minimum_out_of_sample_trades": 100})
    assert result["demo_eligible"] is False
    assert result["validation_checks"]["minimum_out_of_sample_trades"] is False
