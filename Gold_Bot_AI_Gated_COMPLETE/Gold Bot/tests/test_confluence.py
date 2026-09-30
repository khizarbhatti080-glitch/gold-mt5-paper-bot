from datetime import datetime, timedelta, timezone
from goldbot.confluence import UnifiedGoldConfluenceV1, aggregate
from goldbot.models import Side


def candle(time, o=100, h=101, l=99, c=100):
    return {'time':time,'open':o,'high':h,'low':l,'close':c,'spread':30}


def test_higher_timeframe_aggregation_requires_completed_bucket():
    t = datetime(2026, 9, 24, 8, tzinfo=timezone.utc)
    bars = [candle(t + timedelta(minutes=15*i)) for i in range(3)]
    assert aggregate(bars,1) == []
    bars.append(candle(t + timedelta(minutes=45)))
    assert len(aggregate(bars,1)) == 1
    assert aggregate(bars,4) == []


def test_confluence_holds_when_context_missing():
    t = datetime(2026, 9, 24, 8, tzinfo=timezone.utc)
    signal = UnifiedGoldConfluenceV1().on_bar(candle(t), [])
    assert signal.side == Side.HOLD and signal.reason == 'insufficient_history'
