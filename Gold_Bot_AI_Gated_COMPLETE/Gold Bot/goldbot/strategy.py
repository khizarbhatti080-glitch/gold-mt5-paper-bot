from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from .models import Side, Signal
from .confluence import UnifiedGoldConfluenceV1


class PendingUserStrategy:
    name = "pending_user_strategy"
    version = "0.0.0-hold"

    def required_timeframes(self) -> list[str]:
        return []

    def on_bar(self, bar, history) -> Signal:
        return Signal(Side.HOLD, bar["time"], reason="No approved strategy loaded")


class CandleBreakReversalStrategy:
    """User's red/green candle break-and-reverse rules."""

    name = "candle_break_reversal"
    version = "1.0.0"

    def required_timeframes(self) -> list[str]:
        return ["configured"]

    def reset(self) -> None:
        pass

    def on_bar(self, bar, history) -> Signal:
        if not history:
            return Signal(Side.HOLD, bar["time"], reason="need_prior_candle")
        previous = history[-1]
        if previous["close"] < previous["open"] and bar["low"] < previous["low"]:
            return Signal(Side.SELL, bar["time"], previous["low"], previous["high"], None,
                          "red_candle_next_bar_breaks_low")
        if previous["close"] > previous["open"] and bar["high"] > previous["high"]:
            return Signal(Side.BUY, bar["time"], previous["high"], previous["low"], None,
                          "green_candle_next_bar_breaks_high")
        return Signal(Side.HOLD, bar["time"], reason="no_candle_break")


@dataclass
class _Gap:
    kind: str
    lower: float
    upper: float
    inverted: bool = False
    inversion_body_edge: float | None = None
    inversion_index: int | None = None


class LondonFVGInversionStrategy:
    """First London-session FVG inversion/retest strategy from the supplied video."""

    name = "london_first_fvg_inversion"
    version = "1.0.0"

    def __init__(self, reward_risk: float = 2.0, trend_filter: bool = False,
                 entry_end_hour: int = 24, one_trade_per_day: bool = False):
        self.reward_risk = reward_risk
        self.trend_filter = trend_filter
        self.entry_end_hour = entry_end_hour
        self.one_trade_per_day = one_trade_per_day
        self.tz = ZoneInfo("America/New_York")
        self.reset()

    def required_timeframes(self) -> list[str]:
        return ["M15"]

    def reset(self) -> None:
        self.session_date = None
        self.gap: _Gap | None = None
        self.index = -1
        self.traded_dates = set()

    def on_bar(self, bar, history) -> Signal:
        self.index += 1
        local = bar["time"].astimezone(self.tz)
        if self.session_date != local.date():
            self.session_date = local.date()
            self.gap = None

        in_london = time(3, 0) <= local.time().replace(tzinfo=None) < time(7, 0)
        if self.gap is None and in_london and len(history) >= 2:
            first, middle = history[-2], history[-1]
            middle_local = middle["time"].astimezone(self.tz)
            middle_time = middle_local.time().replace(tzinfo=None)
            if middle_local.date() == local.date() and time(3, 0) <= middle_time < time(7, 0):
                if bar["low"] > first["high"]:
                    self.gap = _Gap("bullish", first["high"], bar["low"])
                elif bar["high"] < first["low"]:
                    self.gap = _Gap("bearish", bar["high"], first["low"])

        gap = self.gap
        if gap is None:
            return Signal(Side.HOLD, bar["time"], reason="no_first_london_fvg")
        if not gap.inverted:
            if gap.kind == "bullish" and bar["close"] < gap.lower:
                gap.inverted = True
                gap.inversion_body_edge = max(bar["open"], bar["close"])
                gap.inversion_index = self.index
            elif gap.kind == "bearish" and bar["close"] > gap.upper:
                gap.inverted = True
                gap.inversion_body_edge = min(bar["open"], bar["close"])
                gap.inversion_index = self.index
            return Signal(Side.HOLD, bar["time"], reason="waiting_for_inversion_or_retest")

        if self.index == gap.inversion_index:
            return Signal(Side.HOLD, bar["time"], reason="retest_must_be_later_bar")
        if local.hour >= self.entry_end_hour:
            return Signal(Side.HOLD, bar["time"], reason="entry_window_closed")
        if self.one_trade_per_day and local.date() in self.traded_dates:
            return Signal(Side.HOLD, bar["time"], reason="daily_trade_already_taken")
        closes = [value["close"] for value in history[-49:]] + [bar["close"]]
        ema = closes[0]
        alpha = 2.0 / 51.0
        for close in closes[1:]:
            ema = alpha * close + (1.0 - alpha) * ema
        if gap.kind == "bullish" and bar["high"] >= gap.lower:
            entry, stop = gap.lower, max(gap.upper, gap.inversion_body_edge or gap.upper)
            if stop > entry and (not self.trend_filter or bar["close"] < ema):
                target = entry - self.reward_risk * (stop - entry)
                self.gap = None
                self.traded_dates.add(local.date())
                return Signal(Side.SELL, bar["time"], entry, stop, target,
                              "bullish_fvg_inverted_and_retested")
        if gap.kind == "bearish" and bar["low"] <= gap.upper:
            entry, stop = gap.upper, min(gap.lower, gap.inversion_body_edge or gap.lower)
            if stop < entry and (not self.trend_filter or bar["close"] > ema):
                target = entry + self.reward_risk * (entry - stop)
                self.gap = None
                self.traded_dates.add(local.date())
                return Signal(Side.BUY, bar["time"], entry, stop, target,
                              "bearish_fvg_inverted_and_retested")
        return Signal(Side.HOLD, bar["time"], reason="waiting_for_retest")


class LondonFVGTrendV04(LondonFVGInversionStrategy):
    name = "london_fvg_trend_v04"
    version = "0.4.0-experimental"

    def __init__(self):
        super().__init__(reward_risk=2.5, trend_filter=True,
                         entry_end_hour=13, one_trade_per_day=True)


STRATEGIES = {
    "unified_gold_confluence_v1": UnifiedGoldConfluenceV1,
    "candle_break_reversal": CandleBreakReversalStrategy,
    "london_fvg_inversion": LondonFVGInversionStrategy,
    "london_fvg_trend_v04": LondonFVGTrendV04,
}


def build_strategy(name: str):
    try:
        return STRATEGIES[name]()
    except KeyError as exc:
        raise ValueError(f"unknown strategy: {name}; choose {', '.join(STRATEGIES)}") from exc
