"""Validated completed-close prices for securities in the listing master."""
import os
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .store import factor

_price_cache = OrderedDict()
_price_cache_lock = threading.Lock()


def security(market, symbol):
    from .symbol_master import resolve
    return resolve(market, symbol)


@dataclass(frozen=True)
class Price:
    minor: int
    previous_minor: int | None
    observed_at: str
    fetched_at: int
    source: str = 'Yahoo Finance / yfinance · completed daily close'


def ensure_fresh(price):
    try:
        observed = datetime.fromisoformat(price.observed_at)
        if observed.tzinfo is None:
            raise ValueError('Timezone required')
        age = datetime.now(timezone.utc) - observed.astimezone(timezone.utc)
        limit = int(os.getenv('PAPER_MAX_PRICE_AGE_DAYS', '5'))
        if price.minor <= 0 or age < timedelta(0) or age > timedelta(days=limit):
            raise ValueError('Stale or invalid close')
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(503, 'A sufficiently recent valid completed close is unavailable. Trading is disabled for this security.')


def fetch_price(market, symbol):
    item = security(market, symbol)
    import yfinance as yf
    local_zone = ZoneInfo('America/New_York' if market == 'us' else 'Asia/Seoul')
    today = datetime.now(local_zone).date()
    from .symbol_master import path as directory_path
    key = (str(directory_path()), market,
           item['provider_symbol'], item['exchange'], item['currency'], item['security_type'],item['name'],today)
    with _price_cache_lock:
        cached = _price_cache.get(key)
        if cached and time.monotonic()-cached[0]<15:
            ensure_fresh(cached[1])
            _price_cache.move_to_end(key)
            return cached[1]
    try:
        ticker = yf.Ticker(item['provider_symbol'])
        history = ticker.history(period='1mo', interval='1d', auto_adjust=False, timeout=8)
        metadata = ticker.history_metadata
        exchanges = {'Nasdaq': {'NMS','NGM','NCM'}, 'NYSE': {'NYQ'},
                     'NYSE American': {'ASE'}, 'NYSE Arca': {'PCX'}, 'Cboe BZX': {'BTS','BATS'},
                     'KOSPI': {'KSC'}, 'KOSDAQ': {'KOE'}}
        if (metadata.get('currency') != item['currency'] or
                metadata.get('symbol','').upper() != item['provider_symbol'] or
                metadata.get('exchangeName') not in exchanges.get(item['exchange'], set()) or
                metadata.get('instrumentType') != ('ETF' if item['security_type']=='ETF' else 'EQUITY')):
            raise ValueError('Quote identity, exchange, type or currency mismatch')
        rows = [(index.date(), row['Close']) for index, row in history.iterrows() if index.date() < today]
        if not rows:
            raise ValueError('No completed close')
        def minor(value):
            amount = Decimal(str(value)) * factor(market)
            if not amount.is_finite() or amount <= 0 or amount > 10**12:
                raise ValueError('Invalid price')
            return int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        day, value = rows[-1]
        observed = datetime(day.year, day.month, day.day, 16 if market == 'us' else 15, 0 if market == 'us' else 30, tzinfo=local_zone)
        price = Price(minor(value), minor(rows[-2][1]) if len(rows) > 1 else None, observed.isoformat(), int(time.time()))
        ensure_fresh(price)
        with _price_cache_lock:
            _price_cache[key] = (time.monotonic(),price)
            _price_cache.move_to_end(key)
            while len(_price_cache)>256:
                _price_cache.popitem(last=False)
        return price
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Price source unavailable. No simulated trade can be executed without a valid price.')
