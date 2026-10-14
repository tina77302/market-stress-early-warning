"""Expected completed sessions, respecting exchange holidays/early closes."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import pandas as pd
import exchange_calendars as xcals


@lru_cache(maxsize=4)
def calendar(market, year):
    return xcals.get_calendar('XNYS' if market == 'us' else 'XKRX', start=f'{year-2}-01-01', end=f'{year+1}-12-31')


def expected(market, now=None):
    now = now or datetime.now(timezone.utc)
    if market not in ['us','korea'] or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Known market and timezone-aware current time required.')
    now = now.astimezone(timezone.utc)
    cal = calendar(market, now.year)
    schedule = cal.schedule
    # Operational allowance for end-of-day inputs: US/FRED 12h, Korea 6h.
    # Until this deadline the previous completed due session is expected.
    lag = timedelta(hours=12 if market == 'us' else 6)
    ready = schedule[schedule['close'] + lag <= pd.Timestamp(now)]
    if ready.empty:
        raise ValueError('No expected exchange session in configured calendar.')
    date = ready.index[-1].strftime('%Y-%m-%d')
    deadline = (ready['close'].iloc[-1] + lag).isoformat()
    return date, deadline


def latest_closed(market, now=None):
    """Fetch through the latest actual close, even before its publication deadline."""
    now = now or datetime.now(timezone.utc)
    if market not in ['us','korea'] or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Known market and timezone-aware current time required.')
    now = now.astimezone(timezone.utc)
    schedule = calendar(market, now.year).schedule
    closed = schedule[schedule['close'] <= pd.Timestamp(now)]
    if closed.empty:
        raise ValueError('No closed exchange session in configured calendar.')
    return closed.index[-1].strftime('%Y-%m-%d')


def series_expected(market, series, due_date):
    """H.15 Treasury observations exclude Board holidays, independently of NYSE."""
    if market != 'us' or series != 'DGS10' or not due_date:
        return due_date
    from pandas.tseries.holiday import USFederalHolidayCalendar
    offset = pd.offsets.CustomBusinessDay(calendar=USFederalHolidayCalendar())
    return offset.rollback(pd.Timestamp(due_date)).strftime('%Y-%m-%d')
