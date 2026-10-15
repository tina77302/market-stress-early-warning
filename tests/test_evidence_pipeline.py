"""Deterministic ingestion tests. Synthetic fixtures are never installed as real data."""
import copy
from datetime import datetime,timezone
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from src.paper import evidence_pipeline as p, stress_analytics as a, symbol_master
from src.paper.security_sources import entry
from src.admin.import_stress_evidence import publish

FETCH=p.fetch


def raw_history(market='us',missing=False):
    zone='America/New_York' if market=='us' else 'Asia/Seoul'
    days=pd.bdate_range('2010-01-01',periods=400,tz=zone)
    df=pd.DataFrame({'Close':100.,'Adj Close':100.,'Dividends':0.,'Stock Splits':0.},index=days)
    df.loc[days[:100],'Adj Close']=99.
    df.loc[days[100],'Dividends']=1.
    df.loc[days[200],'Stock Splits']=2.
    if missing:df.loc[days[150],['Close','Adj Close']]=np.nan
    return df.to_csv(index_label='Date').encode()


def metadata(ident,spec):
    exchange='NMS' if ident['exchange']=='Nasdaq' else 'PCX' if ident['exchange']=='NYSE Arca' else 'KSC'
    info={'symbol':ident['provider_symbol'],'currency':ident['currency'],'exchange':exchange,'quoteType':'EQUITY',
          'sector':spec['sector'],'industry':spec.get('industry')} if spec['kind']=='security' else None
    return {'history_metadata':{'symbol':ident['provider_symbol'],'currency':ident['currency'],'exchangeName':exchange,
             'instrumentType':'EQUITY' if spec['kind']=='security' else 'ETF',
             'exchangeTimezoneName':'America/New_York' if ident['market']=='us' else 'Asia/Seoul'},
            'classification':info,'yfinance_version':'fixture'}


@pytest.fixture
def pipeline(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_SYMBOL_MASTER_PATH',str(tmp_path/'master.sqlite3'))
    monkeypatch.setattr(p,'DATA_DIR',tmp_path);monkeypatch.setattr(a,'DATA_DIR',tmp_path)
    from src.admin import import_stress_evidence as importer
    monkeypatch.setattr(importer,'DATA_DIR',tmp_path)
    catalog=json.loads(p.CATALOG.read_text());catalog['reviewed_at']='2020-01-01T00:00:00+00:00'
    for market,items in catalog['markets'].items():
        rows=[]
        for item in items:
            item.pop('known_action',None)
            ticker=item['symbol'].split('.')[0]
            rows.append(entry(market,ticker,'Fixture '+ticker,'KOSPI' if market=='korea' else 'NYSE Arca' if ticker=='XLK' else 'Nasdaq','Stock' if item['kind']=='security' else 'ETF'))
        symbol_master.publish(market,rows,[{'source':'fixture'}],minimum=1)
    file=tmp_path/'catalog.json';file.write_text(json.dumps(catalog));monkeypatch.setattr(p,'CATALOG',file)
    monkeypatch.setattr(p,'fetch',lambda ident,spec:(raw_history(ident['market'],missing=True),metadata(ident,spec)))
    return catalog


@pytest.mark.parametrize('market',['us','korea'])
def test_normalization_uses_explicit_adjusted_prices_and_local_dates(market):
    prices,coverage,audit=p.normalize(raw_history(market,missing=True),market,'2026-10-15')
    assert prices[0]=={'Date':'2010-01-01','Close':99.}
    assert coverage['rows']==399 and coverage['missing_price_rows']==1
    assert audit['checked_cash_adjustments']==1 and audit['split_events']==1
    assert not audit['repair'] and not audit['forward_fill']
    limited,_,_=p.normalize(raw_history(market),market,'2011-07-01')
    assert all(row['Date']<'2011-07-01' for row in limited)


@pytest.mark.parametrize('mutation',[
    lambda d:d.drop(columns='Adj Close'),
    lambda d:d.assign(**{'Adj Close':d['Close']}),
    lambda d:d.assign(Dividends=0),
    lambda d:d.assign(**{'Adj Close':-1}),
    lambda d:pd.concat([d,d.iloc[[0]]]),
    lambda d:d.iloc[::-1],
    lambda d:d.iloc[:20]])
def test_wrong_unadjusted_or_incomplete_history_is_rejected(mutation):
    df=pd.read_csv(BytesIO(raw_history()))
    changed=mutation(df)
    with pytest.raises(ValueError):p.normalize(changed.to_csv(index=False).encode(),'us','2026-10-15')


def test_issuer_record_date_is_not_mislabelled_as_ex_date():
    prices,_,_=p.normalize(raw_history(), 'us','2026-10-15')
    date=pd.bdate_range('2010-01-01',periods=400)[100].date().isoformat()
    action={'date':date,'column':'Dividends','value':1,'issuer_record_date':'different date'}
    assert p.normalize(raw_history(),'us','2026-10-15',action)[2]['known_action_verified']
    with pytest.raises(ValueError):p.normalize(raw_history(),'us','2026-10-15',{**action,'value':2})


@pytest.mark.parametrize('market',['us','korea'])
def test_collect_provenance_receipts_archives_and_separate_market(pipeline,market):
    result=p.collect(market);assert result['status']=='PUBLISHED' and result['instruments']==3
    raw=(p.root()/f'{market}.json').read_bytes()
    bundle=json.loads(raw)
    assert p.digest(raw)==result['bundle_sha256']
    assert (p.root()/'archive'/market/(p.digest(raw)+'.json')).read_bytes()==raw
    for item in bundle['instruments']:
        proof=item['provenance'];assert proof['identity']['market']==market
        assert proof['review_status']=='source_documents_reviewed'
        assert proof['coverage']['rows']==399
        assert proof['public_display_rights']=='not_confirmed'
        assert proof['history_source'].startswith('https://finance.yahoo.com/')
        p.verify_receipts(item,market)
    assert not (p.root()/('korea.json' if market=='us' else 'us.json')).exists()


@pytest.mark.parametrize('tamper',['price','classification','receipt','identity','path'])
def test_tampered_evidence_rejected_and_lkg_preserved(pipeline,tamper,tmp_path):
    p.collect('us');target=p.root()/'us.json';before=target.read_bytes();bundle=json.loads(before)
    item=bundle['instruments'][0]
    if tamper=='price':item['prices'][0]['Close']=100.
    if tamper=='classification':item['industry']='Invented from company name'
    if tamper=='identity':item['provenance']['identity']['symbol']='AAPL'
    if tamper=='receipt':
        receipt=p.root()/item['provenance']['receipts']['history']['path'];receipt.write_bytes(receipt.read_bytes()+b'corruption')
    if tamper=='path':item['provenance']['receipts']['history']['path']='../../outside.csv'
    source=tmp_path/'modified.json';source.write_text(json.dumps(bundle))
    with pytest.raises((ValueError,OSError)):publish(source,'us')
    assert target.read_bytes()==before


def test_unreviewed_changed_provider_classification_is_not_inferred(pipeline,monkeypatch):
    ident=p.identity('us','NVDA');spec=pipeline['markets']['us'][0]
    data=metadata(ident,spec);data['classification']['industry']=None
    import yfinance
    class Ticker:
        def __init__(self,*args):self.history_metadata=data['history_metadata']
        def history(self,**kwargs):return pd.read_csv(BytesIO(raw_history())).set_index('Date')
        def get_info(self):return data['classification']
    monkeypatch.setattr(yfinance,'Ticker',Ticker)
    with pytest.raises(ValueError,match='differs'):FETCH(ident,spec)


def test_identity_mismatch_rejected_before_classification_use(pipeline):
    ident=p.identity('korea','000660.KS');spec=pipeline['markets']['korea'][0];data=metadata(ident,spec)
    data['history_metadata']['currency']='USD'
    with pytest.raises(ValueError,match='identity'):p.check_identity(ident,data['history_metadata'],data['classification'])


def test_failed_korea_collection_preserves_both_installed_markets(pipeline,monkeypatch):
    p.collect('us');p.collect('korea')
    before={m:(p.root()/f'{m}.json').read_bytes() for m in ('us','korea')}
    monkeypatch.setattr(p,'fetch',lambda *args:(_ for _ in ()).throw(ValueError('Provider missing')))
    with pytest.raises(ValueError):p.collect('korea')
    assert all((p.root()/f'{m}.json').read_bytes()==raw for m,raw in before.items())


def test_runtime_rejects_corrupt_receipts_and_future_retrieval(pipeline):
    p.collect('us');target=p.root()/'us.json';raw=target.read_bytes();bundle=json.loads(raw)
    assert a.load_evidence('us')[0]['NVDA']['sector']=='Technology'
    malformed=copy.deepcopy(bundle);malformed['instruments'][0]['provenance']['retrieved_at']='2999-01-01T00:00:00+00:00'
    with pytest.raises(ValueError):a.parse_evidence(json.dumps(malformed).encode(),'us')
    reference=bundle['instruments'][0]['provenance']['receipts']['metadata'];(p.root()/reference['path']).write_bytes(b'{}')
    with pytest.raises(ValueError,match='checksum'):a.load_evidence('us')


def test_example_verifier_refuses_production_before_account_changes(monkeypatch,tmp_path):
    from src.admin.verify_stress_evidence import run
    monkeypatch.setenv('APP_ENV','production')
    prior=__import__('os').environ.get('PAPER_DB_PATH')
    with pytest.raises(ValueError,match='Local research'):run(tmp_path)
    assert __import__('os').environ.get('PAPER_DB_PATH')==prior
