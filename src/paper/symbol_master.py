"""Durable listing master, atomic per-market replacement and bounded search.

Independent from model data, the account schema, and the market refresh scheduler.
"""
import argparse
import fcntl
import json
import os
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException
from src.config import DATA_DIR
from .security_sources import fetch_market, normalize_name

REFRESH_SECONDS = 86400
SEARCH_MAX_AGE = 3*86400
PUBLIC_FIELDS = ('symbol','ticker','name','exchange','market','currency','security_type')
_fallback_cache = OrderedDict()
_fallback_lock = threading.Lock()
_fallback_slots = threading.BoundedSemaphore(2)


def path():
    return Path(os.getenv('PAPER_SYMBOL_MASTER_PATH', str(DATA_DIR/'paper/security-master.sqlite3')))


@contextmanager
def database():
    target = path()
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    from contextlib import closing
    with closing(sqlite3.connect(target,timeout=15)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS securities (
          market TEXT NOT NULL,symbol TEXT NOT NULL,ticker TEXT NOT NULL,provider_symbol TEXT NOT NULL,
          name TEXT NOT NULL,search_name TEXT NOT NULL,exchange TEXT NOT NULL,currency TEXT NOT NULL,
          security_type TEXT NOT NULL,active INTEGER NOT NULL,PRIMARY KEY(market,symbol));
        CREATE INDEX IF NOT EXISTS security_provider ON securities(market,provider_symbol);
        CREATE INDEX IF NOT EXISTS security_ticker ON securities(market,ticker);
        CREATE TABLE IF NOT EXISTS directory_state (market TEXT PRIMARY KEY,refreshed_at REAL NOT NULL,sources TEXT NOT NULL);
        ''')
        try:
            yield db
        except BaseException:
            db.rollback()
            raise


def state(market):
    with database() as db:
        row = db.execute('SELECT * FROM directory_state WHERE market=?',(market,)).fetchone()
    return dict(row) if row else None


def publish(market, rows, sources, *, minimum=1000):
    if market not in ('us','korea') or len(rows)<minimum:
        raise ValueError('Incomplete listing directory; previous snapshot preserved.')
    symbols = set()
    for row in rows:
        if row['market']!=market or row['currency']!=('USD' if market=='us' else 'KRW') or row['security_type'] not in ('Stock','ETF') or not row['name']:
            raise ValueError('Invalid security metadata.')
        if row['symbol'] in symbols:
            raise ValueError('Duplicate security identity.')
        symbols.add(row['symbol'])
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        count = db.execute('SELECT COUNT(*) FROM securities WHERE market=?',(market,)).fetchone()[0]
        if count and len(rows)<count*.7:
            raise ValueError('Unexpected directory shrink; previous snapshot preserved.')
        db.execute('DELETE FROM securities WHERE market=?',(market,))
        db.executemany('INSERT INTO securities VALUES (?,?,?,?,?,?,?,?,?,?)',
                       [(row['market'],row['symbol'],row['ticker'],row['provider_symbol'],row['name'],normalize_name(row['name']),row['exchange'],row['currency'],row['security_type'],int(row['active'])) for row in rows])
        db.execute('INSERT INTO directory_state VALUES (?,?,?) ON CONFLICT(market) DO UPDATE SET refreshed_at=excluded.refreshed_at,sources=excluded.sources',
                   (market,time.time(),json.dumps(sources,allow_nan=False)))
        db.commit()
    return {'market':market,'count':len(rows),'active':sum(row['active'] for row in rows)}


def refresh(market, *, force=False):
    if market not in ('us','korea'):
        raise ValueError('Unknown listing market.')
    current = state(market)
    if not force and current and time.time()-current['refreshed_at']<REFRESH_SECONDS:
        return current
    lock_path = path().with_name(path().name+'.'+market+'.lock')
    existed = lock_path.exists()
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            if force:
                raise RuntimeError('A directory refresh is already running.') from None
            return state(market)
        current = state(market)
        if not force and current and time.time()-current['refreshed_at']<REFRESH_SECONDS:
            return current
        if not force and existed and time.time()-lock_path.stat().st_mtime<60:
            return current
        lock_path.touch()
        try:
            rows,sources = fetch_market(market)
            publish(market,rows,sources)
        except Exception:
            if force:
                raise
            return current
    return state(market)


def ensure_current(market, *, trading=False):
    try:
        current = refresh(market)
    except (OSError,sqlite3.Error):
        raise HTTPException(503,'Security directory unavailable or too old. Try again after the directory refresh.') from None
    if not current or not 0 <= time.time()-current['refreshed_at'] <= (REFRESH_SECONDS if trading else SEARCH_MAX_AGE):
        raise HTTPException(503,'Security directory unavailable or too old. Try again after the directory refresh.')
    return current


def resolve(market, symbol):
    if market not in ('us','korea') or not isinstance(symbol,str) or not re.fullmatch(r'[A-Za-z0-9.\-]{1,16}',symbol):
        raise HTTPException(422,'Unsupported symbol for this market.')
    ensure_current(market,trading=True)
    with database() as db:
        row = db.execute('SELECT * FROM securities WHERE market=? AND active=1 AND (symbol=? OR ticker=? OR provider_symbol=?)',
                         (market,symbol.upper(),symbol.upper(),symbol.upper())).fetchone()
    if not row:
        raise HTTPException(422,'Unsupported symbol for this market.')
    return dict(row)


def yahoo_candidates(query):
    """Name-lookup aid only; its results must join an existing master entry."""
    now = time.monotonic()
    with _fallback_lock:
        cached = _fallback_cache.get(query)
        if cached and cached[0]>now:
            _fallback_cache.move_to_end(query)
            return cached[1]
    if not _fallback_slots.acquire(blocking=False):
        return []
    try:
        import yfinance as yf
        candidates = yf.Search(query,max_results=8,news_count=0,lists_count=0,include_cb=False,
                               recommended=0,timeout=4).quotes
        result = [(row.get('symbol',''),row.get('quoteType','')) for row in candidates
                  if row.get('quoteType') in ('EQUITY','ETF') and normalize_name(query) in normalize_name(' '.join(str(row.get(k,'')) for k in ('symbol','shortname','longname')))]
    except Exception:
        result = []
    finally:
        _fallback_slots.release()
    with _fallback_lock:
        _fallback_cache[query] = (now+300,result)
        _fallback_cache.move_to_end(query)
        while len(_fallback_cache)>256:
            _fallback_cache.popitem(last=False)
    return result


def search(market, query, limit=20):
    if market not in ('us','korea') or not 1<=limit<=30 or len(query)>100 or any(ord(c)<32 or ord(c)==127 for c in query):
        raise HTTPException(422,'Invalid security search.')
    query = query.strip()
    if not query:
        return {'data':[],'directory_status':'NOT_QUERIED'}
    normalized = normalize_name(query)
    if not normalized:
        return {'data':[],'directory_status':'NOT_QUERIED'}
    current = ensure_current(market)
    ticker = query.upper()
    with database() as db:
        # instr/substr do not interpret SQL LIKE wildcard characters in user input.
        rows = db.execute('''SELECT * FROM securities WHERE market=? AND active=1 AND
          (ticker=? OR symbol=? OR (length(?)>=2 AND (instr(ticker,?)>0 OR instr(search_name,?)>0)))
          ORDER BY CASE WHEN ticker=? OR symbol=? THEN 0 WHEN substr(ticker,1,length(?))=? THEN 1
          WHEN search_name=? THEN 2 WHEN substr(search_name,1,length(?))=? THEN 3 ELSE 4 END,
          length(ticker),ticker LIMIT ?''',
          (market,ticker,ticker,normalized,ticker,normalized,ticker,ticker,ticker,ticker,normalized,normalized,normalized,limit)).fetchall()
        if not rows and len(normalized)>=2:
            fallback = []
            for provider,kind in yahoo_candidates(query.casefold()):
                row = db.execute('SELECT * FROM securities WHERE market=? AND provider_symbol=? AND active=1', (market,provider.upper())).fetchone()
                if row and row['security_type']==('ETF' if kind=='ETF' else 'Stock') and row['symbol'] not in {r['symbol'] for r in fallback}:
                    fallback.append(row)
            rows = fallback[:limit]
    return {'data':[{key:row[key] for key in PUBLIC_FIELDS} for row in rows],
            'directory_status':'CURRENT' if time.time()-current['refreshed_at']<REFRESH_SECONDS else 'STALE',
            'directory_updated_at':current['refreshed_at']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Refresh structured security listings; never changes accounts, prices or models.')
    parser.add_argument('command',choices=['refresh','status'])
    parser.add_argument('--market',choices=['us','korea','both'],default='both')
    args=parser.parse_args()
    failed=False
    for selected in (['us','korea'] if args.market=='both' else [args.market]):
        try:
            if args.command=='refresh':
                refresh(selected,force=True)
            current=state(selected)
            if current:
                current['sources']=json.loads(current['sources'])
            with database() as connection:
                counts=[dict(row) for row in connection.execute('SELECT exchange,security_type,active,COUNT(*) AS count FROM securities WHERE market=? GROUP BY exchange,security_type,active',(selected,))]
            print(json.dumps({'market':selected,'status':'OK','state':current,'coverage':counts},ensure_ascii=False))
        except Exception:
            failed=True
            print(json.dumps({'market':selected,'status':'ERROR','message':'Directory refresh unavailable; previous committed directory preserved.'}))
    raise SystemExit(1 if failed else 0)
