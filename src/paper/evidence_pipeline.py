"""Bounded reviewed-universe ingestion; never imports accounts or model code."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4

import numpy as np
import pandas as pd
from src.config import DATA_DIR
from .symbol_master import path as master_path

CATALOG = Path(__file__).with_name('stress_coverage.json')
EXCHANGES = {'Nasdaq':{'NMS','NGM','NCM'},'NYSE Arca':{'PCX'},'KOSPI':{'KSC'}}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(market, symbol):
    with sqlite3.connect(master_path().resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT * FROM securities WHERE market=? AND symbol=? AND active=1',(market,symbol)).fetchone()
    if not row or row['currency']!=('USD' if market=='us' else 'KRW'):
        raise ValueError('Reviewed security is absent from the existing Symbol Master')
    return {key:row[key] for key in ('market','symbol','ticker','provider_symbol','exchange','currency','security_type')}


def check_identity(item, metadata, info=None):
    if (metadata.get('symbol')!=item['provider_symbol'] or metadata.get('currency')!=item['currency'] or
            metadata.get('exchangeName') not in EXCHANGES.get(item['exchange'],set()) or
            metadata.get('instrumentType')!=('ETF' if item['security_type']=='ETF' else 'EQUITY') or
            metadata.get('exchangeTimezoneName')!=('America/New_York' if item['market']=='us' else 'Asia/Seoul')):
        raise ValueError('History identity mismatch')
    if info is not None and (info.get('symbol')!=item['provider_symbol'] or info.get('currency')!=item['currency'] or
            info.get('exchange') not in EXCHANGES.get(item['exchange'],set()) or info.get('quoteType')!='EQUITY'):
        raise ValueError('Classification identity mismatch')


def normalize(raw, market, cutoff, known_action=None):
    """Use provider Adj Close only. Never repair, reconstruct, or fill prices."""
    frame=pd.read_csv(BytesIO(raw))
    required={'Date','Close','Adj Close','Dividends','Stock Splits'}
    if not required.issubset(frame.columns):
        raise ValueError('Explicit adjusted-close and corporate-action columns required')
    zone='America/New_York' if market=='us' else 'Asia/Seoul'
    days=pd.to_datetime(frame['Date'],utc=True,errors='raise').dt.tz_convert(zone).dt.tz_localize(None)
    if days.duplicated().any() or not days.is_monotonic_increasing or (days!=days.dt.normalize()).any():
        raise ValueError('Invalid daily session dates')
    frame.index=pd.DatetimeIndex(days)
    excluded_open=int((frame.index>=pd.Timestamp(cutoff)).sum())
    frame=frame.loc[frame.index<pd.Timestamp(cutoff)].copy()
    for column in required-{'Date'}:
        frame[column]=pd.to_numeric(frame[column],errors='raise')
    close,adjusted=frame['Close'],frame['Adj Close']
    valid=close.notna() & adjusted.notna()
    if (not np.isfinite(close[valid]).all() or not np.isfinite(adjusted[valid]).all() or
            (close[valid]<=0).any() or (adjusted[valid]<=0).any() or valid.sum()<252):
        raise ValueError('Invalid or insufficient adjusted history')
    for col in ['Dividends','Stock Splits']:
        if not np.isfinite(frame[col]).all() or (frame[col]<0).any():
            raise ValueError('Invalid corporate actions')
    dividends=frame['Dividends']
    if not (dividends>0).any():
        raise ValueError('Initial reviewed universe requires observable dividend evidence')
    factor=adjusted/close
    cash=dividends+frame.get('Capital Gains',0)
    cash_days=(cash>0) & valid & valid.shift(fill_value=False)
    expected=1-cash/close.shift()
    errors=abs(factor.shift()/factor-expected)
    if (errors[cash_days]>0.0002).any():
        raise ValueError('Dividend adjustment factors inconsistent with reported cash actions')
    if known_action:
        day=pd.Timestamp(known_action['date']);col=known_action['column']
        if day not in frame.index or not np.isclose(frame.loc[day,col],known_action['value'],rtol=0,atol=1e-8):
            raise ValueError('Issuer-reviewed corporate action is missing or inconsistent')
    prices=[{'Date':day.date().isoformat(),'Close':float(value)} for day,value in adjusted[valid].items()]
    coverage={'start':prices[0]['Date'],'end':prices[-1]['Date'],'rows':len(prices),
              'missing_price_rows':int((~valid).sum()),'excluded_current_or_future_rows':excluded_open}
    audit={'status':'validated_provider_adjusted_history','dividend_events':int((dividends>0).sum()),
           'split_events':int((frame['Stock Splits']>0).sum()),'checked_cash_adjustments':int(cash_days.sum()),
           'adjusted_vs_close_different_rows':int((abs(adjusted[valid]-close[valid])>1e-6).sum()),
           'known_action_verified':bool(known_action),'repair':False,'forward_fill':False}
    return prices,coverage,audit


def fetch(item, spec):
    import yfinance as yf
    ticker=yf.Ticker(item['provider_symbol'])
    frame=ticker.history(start='2006-01-01',interval='1d',auto_adjust=False,repair=False,actions=True,keepna=True,timeout=20)
    if frame.empty:raise ValueError('History unavailable')
    metadata={key:ticker.history_metadata.get(key) for key in ('symbol','currency','exchangeName','instrumentType','exchangeTimezoneName')}
    info=None
    if spec['kind']=='security':
        data=ticker.get_info()
        info={key:data.get(key) for key in ('symbol','currency','exchange','quoteType','sector','industry')}
        if any(info.get(key)!=spec.get(key) for key in ('sector','industry')):
            raise ValueError('Provider classification differs from reviewed coverage')
    check_identity(item,metadata,info)
    return frame.to_csv(index_label='Date').encode(),{'history_metadata':metadata,'classification':info,'yfinance_version':yf.__version__}


def root():
    return DATA_DIR/'paper/stress-evidence'


def verify_receipts(item, market):
    """Importer verification binds labels/prices to retained, hashed source receipts."""
    provenance=item.get('provenance')
    if provenance is None:return  # Existing reviewed manual bundle contract remains supported.
    if not isinstance(provenance,dict) or not isinstance(provenance.get('identity'),dict) or not isinstance(provenance.get('receipts'),dict):
        raise ValueError('Malformed provenance')
    if set(provenance['receipts'])!={'history','metadata','catalog'}:
        raise ValueError('History, metadata and reviewed catalog receipts required')
    retrieved=datetime.fromisoformat(provenance['retrieved_at'])
    reviewed=datetime.fromisoformat(provenance['reviewed_at'])
    if retrieved.tzinfo is None or reviewed.tzinfo is None or not reviewed<=retrieved<=datetime.now(timezone.utc):
        raise ValueError('Invalid source retrieval/review timestamps')
    if provenance['version']!=1 or provenance['identity']['market']!=market or provenance['identity']['symbol']!=item['symbol']:
        raise ValueError('Evidence provenance identity mismatch')
    if provenance['review_status']!='source_documents_reviewed' or provenance['usage_scope']!='local_noncommercial_research_demo':
        raise ValueError('Missing explicit review scope')
    receipts={}
    for name,ref in provenance['receipts'].items():
        if not isinstance(ref,dict) or not isinstance(ref.get('path'),str) or not isinstance(ref.get('sha256'),str):
            raise ValueError('Malformed receipt reference')
        target=(root()/ref['path']).resolve()
        if not target.is_relative_to((root()/'receipts').resolve()):
            raise ValueError('Receipt path outside evidence root')
        raw=target.read_bytes()
        if digest(raw)!=ref['sha256']:raise ValueError('Evidence receipt checksum mismatch')
        receipts[name]=raw
    catalog=json.loads(receipts['catalog'])
    if digest(receipts['catalog'])!=provenance['catalog_sha256'] or catalog['reviewed_at']!=item['reviewed_at'] or catalog['reviewed_at']!=provenance['reviewed_at']:
        raise ValueError('Classification review receipt mismatch')
    spec=next((s for s in catalog['markets'][market] if s['symbol']==item['symbol']),None)
    if not spec or any(item.get(key)!=value for key,value in spec.items()):
        raise ValueError('Instrument does not match reviewed classification/proxy catalog')
    snapshot=json.loads(receipts['metadata'])
    check_identity(provenance['identity'],snapshot['history_metadata'],snapshot['classification'])
    if item['kind']=='security' and (not isinstance(snapshot.get('classification'),dict) or any(snapshot['classification'].get(k)!=item.get(k) for k in ('sector','industry'))):
        raise ValueError('Classification not supported by provider receipt')
    prices,coverage,audit=normalize(receipts['history'],market,provenance['cutoff_exclusive'],provenance.get('known_action'))
    if prices!=item['prices'] or coverage!=provenance['coverage'] or audit!=provenance['adjustment_review']:
        raise ValueError('Imported prices or coverage differ from adjusted provider evidence')


def collect(market):
    if market not in ('us','korea'):raise ValueError('Unknown market')
    catalog_raw=CATALOG.read_bytes();catalog=json.loads(catalog_raw)
    if catalog['review_status']!='source_documents_reviewed':raise ValueError('Coverage must be reviewed')
    now=datetime.now(timezone.utc)
    if datetime.fromisoformat(catalog['reviewed_at'])>now:raise ValueError('Future review date')
    run=f'{market}/{now.strftime("%Y%m%dT%H%M%S")}-{uuid4().hex[:10]}'
    directory=root()/'receipts'/run;directory.mkdir(parents=True,mode=0o700)
    catalog_path=f'receipts/{run}/catalog.json'
    (root()/catalog_path).write_bytes(catalog_raw)
    items=[]
    for spec in catalog['markets'][market]:
        ident=identity(market,spec['symbol'])
        if spec['kind'] in ('sector','industry') and ident['security_type']!='ETF':raise ValueError('Benchmark must be an ETF')
        raw,metadata=fetch(ident,spec)
        retrieved=datetime.now(timezone.utc).isoformat()
        cutoff=now.astimezone(ZoneInfo('America/New_York' if market=='us' else 'Asia/Seoul')).date().isoformat()
        prices,coverage,audit=normalize(raw,market,cutoff,spec.get('known_action'))
        metadata_raw=json.dumps(metadata,sort_keys=True,allow_nan=False).encode()
        references={'catalog':{'path':catalog_path,'sha256':digest(catalog_raw)}}
        for name,content,suffix in [('history',raw,'csv'),('metadata',metadata_raw,'json')]:
            relative=f'receipts/{run}/{spec["symbol"]}.{name}.{suffix}'
            (root()/relative).write_bytes(content)
            references[name]={'path':relative,'sha256':digest(content)}
        provenance={'version':1,'identity':ident,'retrieved_at':retrieved,'reviewed_at':catalog['reviewed_at'],
                    'review_status':catalog['review_status'],'usage_scope':catalog['usage_scope'],
                    'public_display_rights':catalog['public_display_rights'],'classification_basis':spec['classification_basis'],
                    'review_sources':spec['review_sources'],'catalog_sha256':digest(catalog_raw),'receipts':references,
                    'history_source':f'https://finance.yahoo.com/quote/{ident["provider_symbol"]}/history/',
                    'price_column':'Adj Close','coverage':coverage,'adjustment_review':audit,
                    'cutoff_exclusive':cutoff,'known_action':spec.get('known_action')}
        item={**spec,'currency':ident['currency'],'identity_verified':True,'reviewed_at':catalog['reviewed_at'],
              'return_basis':'split_and_dividend_adjusted_close','prices':prices,'provenance':provenance}
        items.append(item)
    bundle={'schema_version':1,'market':market,'instruments':items}
    staged=directory/'bundle.json';staged.write_text(json.dumps(bundle,allow_nan=False,sort_keys=True))
    from src.admin.import_stress_evidence import publish
    result=publish(staged,market)
    return {**result,'bundle_sha256':digest(staged.read_bytes()),'coverage':[
        {'symbol':i['symbol'],'kind':i['kind'],**i['provenance']['coverage'],'adjustment_review':i['provenance']['adjustment_review']} for i in items]}
