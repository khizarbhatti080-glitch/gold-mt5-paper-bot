"""Mechanical XAUUSD M15/H1/H4 confluence research strategy.

Only *completed* higher-timeframe buckets are used. A signal is a four-bar
limit proposal; execution and the economic-calendar veto belong to the ledger.
"""
from __future__ import annotations
from datetime import time, timezone
from statistics import mean
from .models import Side, Signal


def aggregate(bars, hours):
    groups = {}
    for b in bars:
        t = b['time'].astimezone(timezone.utc)
        hour = t.hour // hours * hours
        key = t.replace(hour=hour, minute=0, second=0, microsecond=0)
        if key not in groups:
            groups[key] = {'time': key, 'open': b['open'], 'high': b['high'],
                           'low': b['low'], 'close': b['close'], 'count': 0}
        g = groups[key]
        g['high'] = max(g['high'], b['high'])
        g['low'] = min(g['low'], b['low'])
        g['close'] = b['close']
        g['count'] += 1
    return [g for g in groups.values() if g['count'] == hours * 4]


def swings(bars, kind):
    key = 'high' if kind == 'high' else 'low'
    compare = max if kind == 'high' else min
    return [(i, bars[i][key]) for i in range(2, len(bars)-2)
            if bars[i][key] == compare(b[key] for b in bars[i-2:i+3])
            and all(bars[i][key] != bars[j][key] for j in range(i-2,i+3) if i != j)]


class UnifiedGoldConfluenceV1:
    name = 'unified_gold_confluence_v1'
    version = '1.0.0-paper-research'

    def required_timeframes(self):
        return ['M15', 'H1', 'H4']

    def on_bar(self, bar, history):
        stamp = bar['time']
        utc = stamp.astimezone(timezone.utc)
        if utc.weekday() >= 5 or (utc.weekday() == 4 and utc.hour >= 16):
            return Signal(Side.HOLD, stamp, reason='weekend_or_late_friday')
        clock = utc.time()
        if not (time(7) <= clock < time(10) or time(13,30) <= clock < time(16)):
            return Signal(Side.HOLD, stamp, reason='outside_london_new_york_window')
        if len(history) < 160:
            return Signal(Side.HOLD, stamp, reason='insufficient_history')
        # Exclude the current incomplete H1/H4 bucket (bar timestamps are opens).
        h1 = aggregate([b for b in history if b['time'] < utc.replace(minute=0, second=0, microsecond=0)], 1)
        h4_start = utc.replace(hour=utc.hour//4*4, minute=0, second=0, microsecond=0)
        h4 = aggregate([b for b in history if b['time'] < h4_start], 4)
        if len(h4) < 10 or len(h1) < 12:
            return Signal(Side.HOLD, stamp, reason='insufficient_closed_higher_timeframe')
        h4_highs, h4_lows = swings(h4, 'high'), swings(h4, 'low')
        if not h4_highs or not h4_lows:
            return Signal(Side.HOLD, stamp, reason='no_confirmed_h4_swings')
        # Break of confirmed swing with a three-candle displacement gap.
        bias, zone = None, None
        for i in range(max(2,len(h4)-8),len(h4)):
            candle = h4[i]
            past_highs = [p for j,p in h4_highs if j < i]
            past_lows = [p for j,p in h4_lows if j < i]
            if past_highs and candle['close'] > past_highs[-1] and h4[i]['low'] > h4[i-2]['high']:
                bias, zone = Side.BUY, (h4[i-2]['high'],h4[i]['low'])
            elif past_lows and candle['close'] < past_lows[-1] and h4[i]['high'] < h4[i-2]['low']:
                bias, zone = Side.SELL, (h4[i]['high'],h4[i-2]['low'])
        if bias is None:
            return Signal(Side.HOLD, stamp, reason='no_recent_h4_displacement_bos')
        h1_highs, h1_lows = swings(h1, 'high'), swings(h1, 'low')
        if not h1_highs or not h1_lows:
            return Signal(Side.HOLD, stamp, reason='no_h1_structure')
        price = bar['close']
        if not zone[0] <= price <= zone[1]:
            return Signal(Side.HOLD, stamp, reason='outside_h4_fvg_poi')
        if bias == Side.BUY and h1[-1]['close'] < h1_lows[-1][1]:
            return Signal(Side.HOLD, stamp, reason='h1_bullish_invalidation')
        if bias == Side.SELL and h1[-1]['close'] > h1_highs[-1][1]:
            return Signal(Side.HOLD, stamp, reason='h1_bearish_invalidation')
        m15 = history[-35:] + [bar]
        # A confirmed liquidity level must precede the sweep, followed by a
        # subsequent structure close within four candles and a new M15 FVG.
        for offset in range(1,5):
            sweep_idx = len(m15)-1-offset
            earlier = m15[:sweep_idx]
            if len(earlier)<7:
                continue
            levels = swings(earlier, 'low' if bias == Side.BUY else 'high')
            if not levels:
                continue
            level = levels[-1][1]
            sweep = m15[sweep_idx]
            if bias == Side.BUY:
                swept = sweep['low'] < level < sweep['close']
                internal = max(x['high'] for x in earlier[-5:])
                shifted = bar['close'] > internal
                gap = bar['low'] > m15[-3]['high']
                entry = (m15[-3]['high'] + bar['low'])/2
            else:
                swept = sweep['high'] > level > sweep['close']
                internal = min(x['low'] for x in earlier[-5:])
                shifted = bar['close'] < internal
                gap = bar['high'] < m15[-3]['low']
                entry = (m15[-3]['low'] + bar['high'])/2
            if not (swept and shifted and gap):
                continue
            ranges = [x['high']-x['low'] for x in m15[-15:-1]]
            atr = mean(ranges)
            spread = float(bar.get('spread',0) or 0)*0.01
            buffer = max(spread*1.5,atr*.1)
            stop = sweep['low']-buffer if bias == Side.BUY else sweep['high']+buffer
            risk = abs(entry-stop)
            if risk<=0:
                continue
            targets = [p for j,p in swings(m15,'high' if bias == Side.BUY else 'low')
                       if (p > entry if bias == Side.BUY else p < entry)
                       and not any((b['high'] >= p if bias == Side.BUY else b['low'] <= p)
                                   for b in m15[j+1:-1])]
            if not targets:
                continue
            target = min(targets) if bias == Side.BUY else max(targets)
            # Account for both sides of spread plus configured paper slippage.
            estimated_cost = max(spread, 0.30) + 0.10
            if (abs(target-entry)-estimated_cost)/(risk+estimated_cost) < 1.5:
                continue
            return Signal(bias,stamp,entry,stop,target,'h4_fvg_h1_confirmed_m15_sweep_shift_fvg')
        return Signal(Side.HOLD,stamp,reason='no_m15_sweep_shift_fvg')
