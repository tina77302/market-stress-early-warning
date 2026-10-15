"""exchangerate.dev Free: indicative, 15-minute-delayed USD/KRW observations."""
import os
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from uuid import uuid4

import requests
from fastapi import HTTPException

SOURCE = 'exchangerate.dev Free / USD/KRW (15-minute delayed)'
URL = 'https://api.exchangerate.dev/v1/latest/USD'
DELAY_SECONDS = 900
MAX_OBSERVATION_AGE_SECONDS = 1800
MAX_RETRIEVAL_AGE_SECONDS = 900
CACHE_SECONDS = 600


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Missing observation timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result.astimezone(timezone.utc)


def parse(data, retrieved_at):
    if data.get('result') != 'success' or data.get('base') != 'USD':
        raise ValueError('Wrong pair')
    observed = timestamp(data['effective_at']['KRW'])
    served = timestamp(data['timestamp'])
    updated = timestamp(data['data_updated_at'])
    rate = Decimal(str(data['rates']['KRW']))
    if (not rate.is_finite() or not 0 < rate < 1000000 or data['stale']['KRW'] is not False or
            data['sources']['KRW'] != 'live' or data['market_session'] not in ('open', 'weekend', 'interbank_closed') or
            not 0 <= (retrieved_at-observed).total_seconds() <= MAX_OBSERVATION_AGE_SECONDS or
            not observed <= updated <= served <= retrieved_at or
            (retrieved_at-served).total_seconds() > MAX_RETRIEVAL_AGE_SECONDS):
        raise ValueError('Invalid or old delayed observation')
    return {'id':str(uuid4()), 'rate':str(rate), 'source':SOURCE,
            'observation_date':observed.date().isoformat(), 'observation_timestamp':observed.isoformat(),
            'retrieved_at':retrieved_at.isoformat(), 'provider_stale':False, 'provider_source':'live',
            'market_session':data['market_session'], 'response_timestamp':served.isoformat(),
            'data_updated_at':updated.isoformat(), 'feed_delay_seconds':DELAY_SECONDS}


def retry_seconds(response):
    # Respect both delta-seconds and HTTP-date Retry-After without exposing headers.
    value = response.headers.get('Retry-After', '')
    try:
        seconds = int(value)
    except (ValueError, TypeError):
        try:
            seconds = int((parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            seconds = CACHE_SECONDS
    return max(CACHE_SECONDS, min(31*86400, seconds))


def fetch_observation():
    key = os.getenv('EXCHANGERATE_API_KEY', '').strip()
    if not key:
        raise HTTPException(503, 'Preferred delayed FX source is not configured.')
    try:
        response = requests.get(URL, params={'symbols':'KRW'}, headers={'Authorization':'Bearer '+key},
                                timeout=8, allow_redirects=False)
        if response.status_code == 429:
            raise HTTPException(503, 'Preferred delayed FX quota unavailable.', headers={'Retry-After':str(retry_seconds(response))})
        if response.status_code != 200:
            raise ValueError('Provider response unavailable')
        if response.headers.get('X-Price-Delay-Seconds') != str(DELAY_SECONDS):
            raise ValueError('Unconfirmed free delayed feed')
        return parse(response.json(parse_float=Decimal), datetime.now(timezone.utc))
    except HTTPException:
        raise
    except Exception:
        # No raw body, response header, URL, exception, or API credential is emitted.
        raise HTTPException(503, 'Preferred delayed USD/KRW FX unavailable.') from None
