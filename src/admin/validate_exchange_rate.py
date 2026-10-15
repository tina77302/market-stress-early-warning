"""Read-only exchangerate.dev USD/KRW probe; never enables a provider or writes a DB."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path

from src.paper import fx_exchange_rate
from dotenv import load_dotenv
import requests

KEY_VARIABLE = 'EXCHANGERATE_API_KEY'
URL = 'https://api.exchangerate.dev/v1/latest/USD'
QUOTA_HEADERS = ('X-RateLimit-Limit', 'X-RateLimit-Remaining', 'X-RateLimit-Reset',
                 'X-RateLimit-Scope', 'Retry-After', 'X-Price-Delay-Seconds')


def utc_timestamp(value):
    if not isinstance(value, str):
        raise ValueError()
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError()
    return result.astimezone(timezone.utc)


def probe(key):
    try:
        response = requests.get(URL, params={'symbols': 'KRW'}, headers={
            'Authorization': 'Bearer ' + key,
            'User-Agent': 'market-stress-early-warning/fx-evaluation'}, timeout=15,
            allow_redirects=False)
    except requests.RequestException:
        return {'status': 'REQUEST_FAILED', 'provider_enabled': False}
    now = datetime.now(timezone.utc)
    report = {'http_status': response.status_code, 'retrieved_at': now.isoformat(),
              'quota': {name: response.headers.get(name) for name in QUOTA_HEADERS},
              'provider_enabled': False}
    if response.status_code != 200:
        return {**report, 'status': 'HTTP_ERROR'}
    try:
        data = response.json(parse_float=Decimal)
    except ValueError:
        return {**report, 'status': 'NON_JSON_RESPONSE'}
    try:
        if not isinstance(data, dict) or data.get('result') != 'success' or data.get('base') != 'USD':
            raise ValueError()
        rate = Decimal(str(data['rates']['KRW']))
        if not rate.is_finite() or not 0 < rate < 1000000:
            raise ValueError()
        observed = utc_timestamp(data['effective_at']['KRW'])
        served = utc_timestamp(data['timestamp'])
        updated = utc_timestamp(data['data_updated_at'])
        age = (now - observed).total_seconds()
        stale = data['stale']['KRW']
        if type(stale) is not bool or age < 0 or served > now or updated > now:
            raise ValueError()
        source = data['sources']['KRW']
        session = data['market_session']
        if source not in ('live', 'ecb_daily', 'market_daily') or session not in ('open', 'weekend', 'interbank_closed'):
            raise ValueError()
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        return {**report, 'status': 'INVALID_QUOTE_OR_METADATA'}
    try:
        fx_exchange_rate.parse(data, now)
        accepted = report['quota'].get('X-Price-Delay-Seconds') == str(fx_exchange_rate.DELAY_SECONDS)
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        accepted = False
    return {**report, 'status': 'VALIDATED_RESPONSE', 'base': 'USD', 'quote': 'KRW',
            'rate_exact': str(rate), 'source': source, 'market_session': session,
            'observation_timestamp': observed.isoformat(), 'response_timestamp': served.isoformat(),
            'data_updated_at': updated.isoformat(), 'observation_age_seconds': round(age, 3),
            'provider_stale': stale, 'passes_existing_300_second_age_limit': not stale and age <= 300,
            'passes_exchangerate_delayed_policy': accepted,
            'feed_delay_seconds': fx_exchange_rate.DELAY_SECONDS,
            'max_observation_age_seconds': fx_exchange_rate.MAX_OBSERVATION_AGE_SECONDS,
            'rights_confirmed': False}


def main():
    # Existing local environment convention; no key is copied to another file.
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    key = os.environ.get(KEY_VARIABLE, '').strip()
    if not key:
        print(json.dumps({'status': 'KEY_NOT_CONFIGURED', 'variable': KEY_VARIABLE, 'provider_enabled': False}))
        return 1
    result = probe(key)
    # Only selected data/headers are serialized. Never print raw bodies,
    # request headers, exception strings or credential-bearing configuration.
    print(json.dumps(result, ensure_ascii=False).replace(key, '[REDACTED]'))
    return 0 if result['status'] == 'VALIDATED_RESPONSE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
