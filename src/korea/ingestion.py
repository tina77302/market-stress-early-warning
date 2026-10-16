"""Runtime bounds and receipt-preserving helpers for the instructor CLI."""
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import uuid
import pandas as pd
import exchange_calendars as xcals


def sessions(start, end):
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if end < start:
        return pd.DatetimeIndex([])
    cal = xcals.get_calendar('XKRX', start=start - pd.Timedelta(days=10), end=end + pd.Timedelta(days=10))
    result = cal.sessions_in_range(start, end)
    return result.tz_localize(None) if result.tz is not None else result


def runtime_end(value=None, now=None):
    now = now or datetime.now(ZoneInfo('Asia/Seoul'))
    if now.tzinfo is None:
        raise ValueError('now must have a timezone')
    local = now.astimezone(ZoneInfo('Asia/Seoul'))
    bound = pd.Timestamp(local.date())
    candidates = sessions(bound - pd.Timedelta(days=20), bound)
    cal = xcals.get_calendar('XKRX', start=bound-pd.Timedelta(days=30), end=bound+pd.Timedelta(days=10))
    closed = [day for day in candidates if cal.session_close(day) <= pd.Timestamp(now).tz_convert('UTC')]
    latest = closed[-1]
    chosen = pd.Timestamp(value).normalize() if value else latest
    if chosen > latest:
        raise ValueError('end-date exceeds the latest completed Korean session')
    return chosen.to_pydatetime()


def configure(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--end-date', default=os.getenv('KOREA_END_DATE'))
    parser.add_argument('--start-date', default=os.getenv('KOREA_START_DATE', '2010-01-04'))
    parser.add_argument('--data-root', default=os.getenv('MARKET_DATA_ROOT', 'data'))
    args = parser.parse_args(argv)
    args.end = runtime_end(args.end_date)
    args.start = pd.Timestamp(args.start_date).to_pydatetime()
    if args.start > args.end:
        parser.error('start-date must not exceed end-date')
    args.raw = Path(args.data_root).resolve() / 'raw' / 'korea'
    args.raw.mkdir(parents=True, exist_ok=True)
    return args


def resume_date(dates, start, end):
    """Retry holes as well as the tail; a later success cannot hide failed dates."""
    missing = sessions(start, end).difference(pd.DatetimeIndex(pd.to_datetime(dates)).normalize())
    return missing[0].to_pydatetime() if len(missing) else end + timedelta(days=1)


def atomic_csv(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        frame.to_csv(temporary, index=False, encoding='utf-8-sig')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def receipt(output, series, frame, origin="PROVIDER_RESPONSE"):
    """Provider publication time is unknown; retrieval proves possession only now."""
    directory = Path(output).parent / 'receipts'
    directory.mkdir(parents=True, exist_ok=True)
    payload = {'receipt_id': uuid.uuid4().hex, 'series': series, 'evidence_origin': origin,
               'retrieved_at': datetime.now(ZoneInfo('UTC')).isoformat(),
               'source_available_at': None,
               'rows': json.loads(frame.to_json(orient='records', date_format='iso'))}
    with (directory / (payload['receipt_id'] + '.json')).open('x') as stream:
        json.dump(payload, stream, allow_nan=False)
