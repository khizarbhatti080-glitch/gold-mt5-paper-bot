from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import DataQuality


@dataclass(frozen=True)
class QualityReport:
    quality: DataQuality
    reasons: tuple[str, ...]


def validate_bars(bars: list[dict], timeframe_seconds: int,
                  now: datetime | None = None, stale_after_bars: int = 2) -> QualityReport:
    reasons: list[str] = []
    if len(bars) < 2:
        return QualityReport(DataQuality.DEGRADED, ("insufficient_bars",))
    times = [bar["time"] for bar in bars]
    if len(set(times)) != len(times):
        reasons.append("duplicate_timestamps")
    if times != sorted(times):
        reasons.append("out_of_order")
    allowed_gap = timedelta(seconds=timeframe_seconds * 3)
    if any(b - a > allowed_gap for a, b in zip(times, times[1:])):
        reasons.append("data_gap")
    for bar in bars:
        if bar["low"] > min(bar["open"], bar["close"]) or bar["high"] < max(bar["open"], bar["close"]):
            reasons.append("invalid_ohlc")
            break
    current = now or datetime.now(timezone.utc)
    last = times[-1]
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if current - last > timedelta(seconds=timeframe_seconds * stale_after_bars):
        reasons.append("stale_feed")
    return QualityReport(DataQuality.DEGRADED if reasons else DataQuality.OK, tuple(reasons))
