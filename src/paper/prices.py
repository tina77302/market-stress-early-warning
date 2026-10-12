"""Reuse Yahoo/yfinance with a deliberately limited, non-leveraged security catalog."""
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .store import factor

SECURITIES = [
    {'market': 'us', 'symbol': 'SPY', 'name': 'SPDR S&P 500 ETF', 'currency': 'USD'},
    {'market': 'us', 'symbol': 'QQQ', 'name': 'Invesco QQQ ETF', 'currency': 'USD'},
    {'market': 'us', 'symbol': 'AAPL', 'name': 'Apple', 'currency': 'USD'},
    {'market': 'us', 'symbol': 'MSFT', 'name': 'Microsoft', 'currency': 'USD'},
    {'market': 'korea', 'symbol': '005930.KS', 'name': 'Samsung Electronics', 'currency': 'KRW'},
    {'market': 'korea', 'symbol': '000660.KS', 'name': 'SK Hynix', 'currency': 'KRW'},
    {'market': 'korea', 'symbol': '069500.KS', 'name': 'KODEX 200 ETF', 'currency': 'KRW'},
]


def security(market, symbol):
    item = next((item for item in SECURITIES if item['market'] == market and item['symbol'] == symbol), None)
    if not item:
        raise HTTPException(422, 'Unsupported symbol for this market.')
    return item


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
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period='1mo', interval='1d', auto_adjust=False, timeout=8)
        if ticker.history_metadata.get('currency') != item['currency']:
            raise ValueError('Price currency mismatch')
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
        return price
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Price source unavailable. No simulated trade can be executed without a valid price.')
