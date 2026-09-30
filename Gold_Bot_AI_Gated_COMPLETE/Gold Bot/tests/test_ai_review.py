import json
from io import BytesIO
from datetime import datetime, timezone
from urllib.error import HTTPError
from goldbot.ai_review import check_api, review_signal, record_review, reviews_today
from goldbot.models import Side, Signal


def test_ai_key_missing_returns_unavailable(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert check_api({'model':'gpt-6-luna'})['reason'] == 'OPENAI_API_KEY_missing'
    t=datetime(2026,9,24,18,0,tzinfo=timezone.utc)
    signal=Signal(Side.BUY,t,100,99,None,'test')
    assert review_signal({'enabled':True},'XAUUSD',signal,[], 'usd_calendar_clear',.3)['status']=='unavailable'


def test_structured_review_shadow_and_daily_count(monkeypatch,tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    t=datetime(2026,9,24,18,0,tzinfo=timezone.utc)
    signal=Signal(Side.BUY,t,100,99,None,'test')
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,n):
            return json.dumps({'id':'resp_test','output':[{'type':'message','content':[
                {'type':'output_text','text':json.dumps({'verdict':'uncertain','reason':'few bars','risk_flags':['no target']})}]}]}).encode()
    monkeypatch.setattr('goldbot.ai_review.urlopen',lambda req,timeout:Response())
    review=review_signal({'enabled':True},'XAUUSD',signal,[{'time':t,'open':100,'high':101,'low':99,'close':100}], 'usd_calendar_clear',.3)
    assert review['status']=='reviewed' and review['verdict']=='uncertain'
    path=str(tmp_path/'ai.jsonl')
    record_review(path,'XAUUSD',t,signal,review)
    assert reviews_today(path,'2026-09-24')==1
    assert 'test-key' not in (tmp_path/'ai.jsonl').read_text()


def test_http_error_exposes_only_status(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    t = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
    signal = Signal(Side.BUY, t, 100, 99, None, 'test')
    def fail(request, timeout):
        raise HTTPError('https://api.openai.com/v1/responses', 429, 'sensitive error',
                        {'Authorization': 'secret'}, BytesIO(b'sensitive body'))
    monkeypatch.setattr('goldbot.ai_review.urlopen', fail)
    result = review_signal({'enabled': True}, 'XAUUSD', signal, [], 'usd_calendar_clear', .3)
    assert result == {'status': 'unavailable', 'reason': 'HTTP_429'}
