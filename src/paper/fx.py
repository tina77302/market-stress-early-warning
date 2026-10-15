"""Dated FRED DEXKOUS observations; never advertised as real-time FX."""
import os
import json
import time
from threading import Lock
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

import requests
from fastapi import HTTPException
from .store import database
from .fx_primary import SOURCE as PRIMARY_SOURCE
from . import fx_exchange_rate as exchange

SOURCE='FRED / Federal Reserve H.10 / DEXKOUS'
MAX_OBSERVATION_AGE_DAYS=10  # H.10 publication lag plus weekends/holidays; not a live quote.
_primary_lock=Lock()
_primary_retry_after=0
MAX_RETRIEVAL_AGE_SECONDS=21600
TIMESTAMPED_SOURCES=(PRIMARY_SOURCE,exchange.SOURCE)
EXCHANGE_CONTEXT=('provider_stale','provider_source','market_session','response_timestamp','data_updated_at','feed_delay_seconds')


def preferred_provider():
    # Explicit empty value retains the FRED-only rollback option. No key is copied.
    return os.getenv('PAPER_FX_PRIMARY_PROVIDER','exchangerate_dev')


def validate(row):
    try:
        rate=Decimal(row['rate'])
        observed=date.fromisoformat(row['observation_date'])
        retrieved=datetime.fromisoformat(row['retrieved_at'])
        now=datetime.now(timezone.utc)
        if (not rate.is_finite() or not 0<rate<1000000 or row['source'] not in (SOURCE,*TIMESTAMPED_SOURCES) or
                not 0<=(now.date()-observed).days<=MAX_OBSERVATION_AGE_DAYS or retrieved.tzinfo is None or
                not 0<=(now-retrieved).total_seconds()<=MAX_RETRIEVAL_AGE_SECONDS):
            raise ValueError()
        if row['source']==PRIMARY_SOURCE:
            timestamp=datetime.fromisoformat(row['observation_timestamp'])
            if timestamp.tzinfo is None or timestamp.date()!=observed or not 0<=(now-timestamp).total_seconds()<=300 or not 0<=(now-retrieved).total_seconds()<=300:raise ValueError()
        if row['source']==exchange.SOURCE:
            timestamp=exchange.timestamp(row['observation_timestamp'])
            served=exchange.timestamp(row['response_timestamp'])
            updated=exchange.timestamp(row['data_updated_at'])
            if (timestamp.date()!=observed or row['provider_stale'] is not False or row['provider_source']!='live' or
                    row['market_session'] not in ('open','weekend','interbank_closed') or row['feed_delay_seconds']!=exchange.DELAY_SECONDS or
                    not timestamp<=updated<=served<=retrieved or
                    not 0<=(now-timestamp).total_seconds()<=exchange.MAX_OBSERVATION_AGE_SECONDS or
                    not 0<=(now-retrieved).total_seconds()<=exchange.MAX_RETRIEVAL_AGE_SECONDS or
                    (retrieved-served).total_seconds()>exchange.MAX_RETRIEVAL_AGE_SECONDS):raise ValueError()
        return rate
    except (ValueError,TypeError,KeyError,InvalidOperation,OverflowError):
        raise HTTPException(503,'Validated USD/KRW FX is stale or unusable. No currency conversion can be executed.')


def public(row):
    validate(row)
    delayed=row['source']==exchange.SOURCE
    timed=row['source'] in TIMESTAMPED_SOURCES
    return {**dict(row),'rate_exact':str(row['rate']),'rate':float(Decimal(row['rate'])),
            'status':'AVAILABLE','kind':'delayed_observation' if delayed else 'higher_frequency_observation' if timed else 'latest_available_daily_observation',
            'selection_role':'primary' if timed else ('fallback' if preferred_provider() else 'reference'),
            'observation_timestamp':dict(row).get('observation_timestamp'),'observation_time_precision':'timestamp' if timed else 'date',
            'freshness_status':'DELAYED' if delayed else 'TIMESTAMPED' if timed else 'DAILY_REFERENCE',
            'feed_delay_seconds':exchange.DELAY_SECONDS if delayed else None,
            'max_observation_age_seconds':exchange.MAX_OBSERVATION_AGE_SECONDS if delayed else 300 if timed else MAX_OBSERVATION_AGE_DAYS*86400,
            'max_retrieval_age_seconds':exchange.MAX_RETRIEVAL_AGE_SECONDS if delayed else 300 if timed else MAX_RETRIEVAL_AGE_SECONDS,
            'max_observation_age_days':MAX_OBSERVATION_AGE_DAYS if not timed else None}


def fetch_observation():
    key=os.getenv('FRED_API_KEY','')
    if not key:
        raise HTTPException(503,'USD/KRW FX provider is not configured.')
    try:
        response=requests.get('https://api.stlouisfed.org/fred/series/observations',params={
            'series_id':'DEXKOUS','api_key':key,'file_type':'json','sort_order':'desc','limit':30,
            'observation_end':datetime.now(timezone.utc).date().isoformat()},timeout=8)
        response.raise_for_status()
        rows=response.json()['observations']
        # Skip provider missing-value markers only; never rename an observation date.
        item=next(item for item in rows if item['value']!='.')
        row={'id':str(uuid4()),'rate':str(item['value']),'observation_date':item['date'],
             'retrieved_at':datetime.now(timezone.utc).isoformat(),'source':SOURCE}
        validate(row)
        return row
    except HTTPException:
        raise
    except Exception:
        # Exceptions from requests may contain the API key in the URL. Never expose/log them.
        raise HTTPException(503,'USD/KRW FX provider unavailable. Currency conversion requires a validated rate.') from None


def _fred_latest():
    with database() as db:
        cached=db.execute('SELECT * FROM paper_fx_rates WHERE source=? ORDER BY retrieved_at DESC LIMIT 1',(SOURCE,)).fetchone()
    if cached:
        try:
            validate(cached)
            if (datetime.now(timezone.utc)-datetime.fromisoformat(cached['retrieved_at'])).total_seconds()<3600:
                return dict(cached)
        except HTTPException:
            pass
    try:
        row=fetch_observation()
        validate(row)
        with database() as db:
            db.execute('INSERT INTO paper_fx_rates VALUES (?,?,?,?,?)',tuple(row[key] for key in ['id','rate','observation_date','retrieved_at','source']))
            db.commit()
        return row
    except HTTPException:
        if cached:
            validate(cached)  # LKG is usable only within both observation and retrieval limits.
            return dict(cached)
        raise


def enrich(db,row):
    if not row:return row
    row=dict(row)
    if row['source'] in TIMESTAMPED_SOURCES:
        metadata=db.execute('SELECT observation_timestamp FROM paper_fx_metadata WHERE rate_id=?',(row['id'],)).fetchone()
        if metadata:row['observation_timestamp']=metadata['observation_timestamp']
    if row['source']==exchange.SOURCE:
        context=db.execute('SELECT detail_json FROM paper_fx_provider_context WHERE rate_id=?',(row['id'],)).fetchone()
        if context:
            try:
                values=json.loads(context['detail_json'])
                row.update({key:values[key] for key in EXCHANGE_CONTEXT if key in values})
            except (ValueError,TypeError):pass
    return row


def _latest():
    global _primary_retry_after
    provider=preferred_provider()
    if not provider:
        return _fred_latest()
    enabled=provider=='exchangerate_dev' or (provider=='twelve_data' and os.getenv('PAPER_FX_PRIMARY_LICENSE_CONFIRMED','false').lower()=='true')
    if not enabled or time.monotonic()<_primary_retry_after:
        return {**_fred_latest(),'fallback_reason':'Preferred FX unavailable; validated daily reference in use.'}
    source=exchange.SOURCE if provider=='exchangerate_dev' else PRIMARY_SOURCE
    cache_seconds=exchange.CACHE_SECONDS if provider=='exchangerate_dev' else 120
    with database() as db:
        cached=enrich(db,db.execute('SELECT * FROM paper_fx_rates WHERE source=? ORDER BY retrieved_at DESC LIMIT 1',(source,)).fetchone())
    if cached:
        try:
            validate(cached)
            if (datetime.now(timezone.utc)-datetime.fromisoformat(cached['retrieved_at'])).total_seconds()<cache_seconds:return cached
        except HTTPException:
            if provider=='exchangerate_dev':
                try:
                    age=(datetime.now(timezone.utc)-datetime.fromisoformat(cached['retrieved_at'])).total_seconds()
                    if 0<=age<cache_seconds:
                        # An observation aging out must not turn user traffic into quota bursts.
                        return {**_fred_latest(),'fallback_reason':'Delayed observation exceeded its safety limit; preferred refresh remains paced.'}
                except (ValueError,TypeError,OverflowError):pass
    try:
        if provider=='exchangerate_dev':
            fetch_primary=exchange.fetch_observation
        else:
            from .fx_primary import fetch_observation as fetch_primary
        row=fetch_primary()
        if row['source']!=source:raise HTTPException(503,'FX provider identity mismatch.')
        validate(row)
        with database() as db:
            db.execute('INSERT INTO paper_fx_rates VALUES (?,?,?,?,?)',tuple(row[key] for key in ['id','rate','observation_date','retrieved_at','source']))
            db.execute('INSERT INTO paper_fx_metadata VALUES (?,?)',(row['id'],row['observation_timestamp']))
            if source==exchange.SOURCE:
                db.execute('INSERT INTO paper_fx_provider_context VALUES (?,?)',(row['id'],json.dumps({key:row[key] for key in EXCHANGE_CONTEXT},sort_keys=True)))
            db.commit()
        return row
    except HTTPException as error:
        retry=exchange.CACHE_SECONDS if provider=='exchangerate_dev' else 120
        try:retry=max(retry,int((error.headers or {}).get('Retry-After',retry)))
        except (ValueError,TypeError):pass
        _primary_retry_after=time.monotonic()+retry
        # A fallback is always independently validated and visibly identified.
        return {**_fred_latest(),'fallback_reason':'Preferred FX unavailable; validated daily reference in use.'}


def latest():
    # Serialize fetch/cache selection within this API worker to avoid quota bursts.
    with _primary_lock:
        return _latest()
