"""Read-only provider probe security and observation-time semantics, offline."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import json
import pytest
import requests
from src.admin import validate_exchange_rate as probe


def response(age=0):
    now=datetime.now(timezone.utc)-timedelta(seconds=1)
    result=Mock(status_code=200,headers={})
    result.json.return_value={'result':'success','base':'USD','rates':{'KRW':'1350.123456789'},
        'effective_at':{'KRW':(now-timedelta(seconds=age)).isoformat()},
        'timestamp':now.isoformat(),'data_updated_at':now.isoformat(),
        'sources':{'KRW':'live'},'market_session':'open','stale':{'KRW':False}}
    return result


@pytest.mark.parametrize('age,fresh',[(0,True),(900,False)])
def test_observation_not_served_time_drives_freshness(monkeypatch,age,fresh):
    monkeypatch.setattr(probe.requests,'get',lambda *a,**k:response(age))
    result=probe.probe('fixture-key')
    assert result['status']=='VALIDATED_RESPONSE'
    assert result['passes_existing_300_second_age_limit'] is fresh
    assert result['rate_exact']=='1350.123456789'
    assert result['provider_enabled'] is False


@pytest.mark.parametrize('status',[401,429,503])
def test_http_errors_do_not_dump_bodies(monkeypatch,status):
    result=Mock(status_code=status,headers={'Retry-After':'60'})
    result.json.side_effect=AssertionError('Error bodies must not be parsed or printed')
    monkeypatch.setattr(probe.requests,'get',lambda *a,**k:result)
    data=probe.probe('fixture-key')
    assert data['status']=='HTTP_ERROR' and data['quota']['Retry-After']=='60'


def test_non_json_and_bad_quote_are_safe(monkeypatch):
    item=response();item.json.side_effect=ValueError('sensitive response')
    monkeypatch.setattr(probe.requests,'get',lambda *a,**k:item)
    assert probe.probe('fixture-key')['status']=='NON_JSON_RESPONSE'
    item.json.side_effect=None;item.json.return_value={'result':'success','base':'EUR'}
    assert probe.probe('fixture-key')['status']=='INVALID_QUOTE_OR_METADATA'


def test_key_only_in_header_and_output_redacted(monkeypatch,capsys):
    key='fixture-secret-value';monkeypatch.setenv('EXCHANGERATE_API_KEY',key)
    monkeypatch.setattr(probe,'load_dotenv',lambda *a,**k:None)
    def fetch(url,**options):
        assert key not in url and key not in str(options['params'])
        assert options['headers']['Authorization']=='Bearer '+key
        assert options['allow_redirects'] is False
        result=response();result.headers={'X-RateLimit-Remaining':key};return result
    monkeypatch.setattr(probe.requests,'get',fetch)
    assert probe.main()==0
    output=capsys.readouterr().out;assert key not in output
    assert json.loads(output)['quota']['X-RateLimit-Remaining']=='[REDACTED]'


def test_missing_key_and_network_exception_not_exposed(monkeypatch,capsys):
    monkeypatch.setattr(probe,'load_dotenv',lambda *a,**k:None)
    monkeypatch.delenv('EXCHANGERATE_API_KEY',raising=False)
    assert probe.main()==1
    monkeypatch.setenv('EXCHANGERATE_API_KEY','fixture-secret-value')
    def failure(*a,**k):raise requests.RequestException('fixture-secret-value')
    monkeypatch.setattr(probe.requests,'get',failure)
    assert probe.main()==1
    output=capsys.readouterr().out
    assert 'fixture-secret-value' not in output and 'REQUEST_FAILED' in output
