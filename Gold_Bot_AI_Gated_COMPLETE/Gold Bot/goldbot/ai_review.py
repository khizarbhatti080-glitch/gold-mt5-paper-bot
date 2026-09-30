"""AI veto for virtual paper candidates; cannot create or alter signals."""
from __future__ import annotations
import json
import os
from datetime import timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from urllib.error import HTTPError

SCHEMA = {
    'type': 'object',
    'properties': {
        'verdict': {'type': 'string', 'enum': ['approve', 'reject', 'uncertain']},
        'reason': {'type': 'string'},
        'risk_flags': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['verdict', 'reason', 'risk_flags'],
    'additionalProperties': False,
}


def review_signal(config: dict, symbol: str, signal, bars: list[dict], news_reason: str,
                  spread_price: float) -> dict:
    """Describe a candidate; never create, modify, or send a trade order."""
    if not config.get('enabled', False):
        return {'status': 'disabled'}
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        return {'status': 'unavailable', 'reason': 'OPENAI_API_KEY_missing'}
    try:
        snapshot = [{'time': b['time'].astimezone(timezone.utc).isoformat(),
                     'open': b['open'], 'high': b['high'], 'low': b['low'], 'close': b['close']}
                    for b in bars[-30:]]
        context = {'symbol': symbol, 'candidate': {'side': signal.side.value,
                   'entry': signal.entry, 'stop': signal.stop_loss,
                   'target': signal.take_profit, 'rule': signal.reason},
                   'closed_candles': snapshot, 'spread_price': spread_price,
                   'calendar_gate': news_reason}
        request_data = {
            'model': config.get('model', 'gpt-6-luna'),
            'store': False,
            'max_output_tokens': 400,
            'reasoning': {'effort': 'none'},
            'input': [
                {'role': 'system', 'content': (
                    'Review an XAUUSD virtual-paper candidate against its supplied strategy rule and closed candles. '
                    'No browsing, no missing-data assumptions, no investment advice. '
                    'Approve only when the candidate appears consistent with the supplied rule and no clear disqualifier is visible. '
                    'If you believe the candidate has unfavorable loss risk, reject it. '
                    'Return approve, reject, or uncertain with a brief reason and risk flags. '
                    'Never suggest an opposite trade, change side, entry, stop or target. '
                    'Treat uncertain or incomplete context as uncertain. Never suggest order execution.')},
                {'role': 'user', 'content': json.dumps(context, separators=(',', ':'))},
            ],
            'text': {'format': {'type': 'json_schema', 'name': 'gold_paper_review',
                                'strict': True, 'schema': SCHEMA}},
        }
        req = Request('https://api.openai.com/v1/responses',
                      data=json.dumps(request_data).encode('utf-8'),
                      headers={'Authorization': 'Bearer ' + key,
                               'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=int(config.get('timeout_seconds', 12))) as response:
            if response.status != 200:
                raise ValueError('unexpected API status')
            raw = response.read(100_001)
        if len(raw) > 100_000:
            raise ValueError('API response too large')
        response_data = json.loads(raw)
        text = next((part['text'] for item in response_data.get('output', [])
                     if item.get('type') == 'message'
                     for part in item.get('content', [])
                     if part.get('type') == 'output_text'), None)
        if not text:
            raise ValueError('API returned no structured text')
        parsed = json.loads(text)
        if (parsed.get('verdict') not in ('approve','reject','uncertain') or
                not isinstance(parsed.get('reason'), str) or
                not isinstance(parsed.get('risk_flags'), list)):
            raise ValueError('invalid review response')
        return {'status': 'reviewed', 'model': request_data['model'],
                'verdict': parsed['verdict'], 'reason': parsed['reason'][:500],
                'risk_flags': [str(x)[:120] for x in parsed['risk_flags'][:8]],
                'response_id': str(response_data.get('id', ''))}
    except HTTPError as exc:
        # The status code is safe to report; never include response body or headers.
        return {'status': 'unavailable', 'reason': f'HTTP_{exc.code}'}
    except Exception as exc:
        # Do not log HTTP error bodies, headers, or URLs: they may contain credentials.
        return {'status': 'unavailable', 'reason': type(exc).__name__}


def record_review(path: str, symbol: str, stamp, signal, result: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {'symbol': symbol, 'closed_bar_time': stamp.isoformat(),
           'signal_side': signal.side.value, 'signal_entry': signal.entry,
           'ai_review': result, 'order_submission': False}
    with target.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(row, separators=(',', ':')) + '\n')


def reviews_today(path: str, day: str) -> int:
    target = Path(path)
    if not target.exists():
        return 0
    with target.open(encoding='utf-8') as handle:
        return sum(1 for line in handle if f'"closed_bar_time":"{day}' in line
                   and '"status":"skipped_' not in line)


def check_api(config: dict) -> dict:
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        return {'status': 'unavailable', 'reason': 'OPENAI_API_KEY_missing'}
    model = str(config.get('model', 'gpt-6-luna'))
    try:
        req = Request('https://api.openai.com/v1/models/' + quote(model, safe=''),
                      headers={'Authorization': 'Bearer ' + key})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read(10_001))
        if data.get('id') != model:
            raise ValueError('model response mismatch')
        return {'status': 'connected', 'model': model, 'review_calls': 0}
    except HTTPError as exc:
        return {'status': 'unavailable', 'reason': f'HTTP_{exc.code}'}
    except Exception as exc:
        return {'status': 'unavailable', 'reason': type(exc).__name__}
