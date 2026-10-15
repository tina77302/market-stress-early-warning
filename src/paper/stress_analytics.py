"""Read-only conditional history, separate from model inference and trade execution."""
import hashlib
import json
import math
from io import BytesIO
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import exchange_calendars as xcals
from fastapi import HTTPException
from src.config import DATA_DIR

VERSION = 'conditional-history-v1'
HORIZON = 10
MIN_SAMPLE = 20
MIN_DOWNSIDE = 100


def regime(market, score):
    """Existing UI regimes only; these are not new model thresholds."""
    if not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError('Invalid score')
    if market == 'us':
        return 'HIGH' if score >= 70 else 'ELEVATED' if score >= 50 else 'WATCH' if score >= 30 else 'LOW'
    if market == 'korea':
        return 'WARNING' if score >= 50 else 'BELOW WARNING'
    raise ValueError('Unknown market')


def distribution(events):
    values = np.asarray([e['return_pct'] for e in events], dtype=float)
    n = len(values)
    if not np.isfinite(values).all():
        raise ValueError('Nonfinite return')
    result = {'status': 'AVAILABLE' if n >= MIN_SAMPLE else 'INSUFFICIENT_SAMPLE', 'n': n,
              'minimum_sample': MIN_SAMPLE, 'median_pct': None, 'q25_pct': None, 'q75_pct': None,
              'negative_frequency': None, 'downside_q10_pct': None, 'dispersion_iqr_pct': None,
              'sample_std_pct': None, 'downside_minimum_sample': MIN_DOWNSIDE, 'events': events}
    if n >= MIN_SAMPLE:
        q25, median, q75 = np.quantile(values, [.25, .5, .75], method='linear')
        result.update(median_pct=float(median), q25_pct=float(q25), q75_pct=float(q75),
                      negative_frequency=float(np.mean(values < 0)), dispersion_iqr_pct=float(q75-q25),
                      sample_std_pct=float(np.std(values, ddof=1)))
    if n >= MIN_DOWNSIDE:
        result['downside_q10_pct'] = float(np.quantile(values, .1, method='linear'))
    return result


def _series(frame, column, *, allow_missing=False):
    dates = pd.to_datetime(frame['Date'], errors='raise')
    if dates.dt.tz is not None or dates.duplicated().any() or not dates.is_monotonic_increasing or any(d != d.normalize() for d in dates):
        raise ValueError('Duplicate, unordered or non-daily dates')
    values = pd.to_numeric(frame[column], errors='raise').astype(float)
    checked = values.dropna() if allow_missing else values
    if not np.isfinite(checked).all() or (checked <= 0).any():
        raise ValueError('Invalid price history')
    return pd.Series(values.to_numpy(), index=dates)


def load_market(market):
    if market not in ('us', 'korea'):
        raise ValueError('Unknown market')
    processed = DATA_DIR/'processed'
    prediction = processed/'oos_predictions.csv' if market == 'us' else processed/'korea/korea_oos_predictions_10d.csv'
    prediction_bytes = prediction.read_bytes()
    oos = pd.read_csv(BytesIO(prediction_bytes))
    dates = pd.to_datetime(oos['Date'], errors='raise')
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError('Invalid OOS dates')
    scores = pd.to_numeric(oos['Prob_XGBoost'], errors='raise') * 100
    if not np.isfinite(scores).all() or ((scores < 0) | (scores > 100)).any():
        raise ValueError('Invalid OOS scores')
    if market == 'us':
        raw_path = DATA_DIR/'raw/raw_market_data.csv'
        raw_bytes = raw_path.read_bytes()
        raw = pd.read_csv(BytesIO(raw_bytes))
        benchmark = _series(raw, 'SPY', allow_missing=True)
        label = 'SPY'
    else:
        raw_path = DATA_DIR/'raw/korea/krx_indices.csv'
        raw_bytes = raw_path.read_bytes()
        raw = pd.read_csv(BytesIO(raw_bytes))
        benchmark = _series(raw.loc[raw['Index'] == 'KOSPI200'], 'Close')
        label = 'KOSPI200'
    calendar = xcals.get_calendar('XNYS' if market == 'us' else 'XKRX',
                                  start=benchmark.index.min(), end=benchmark.index.max()).sessions
    if calendar.tz is not None:
        calendar = calendar.tz_localize(None)
    # Retain missing exchange-session marks as missing; never shorten the horizon.
    benchmark = benchmark.reindex(calendar)
    return {'scores': pd.Series(scores.to_numpy(), index=dates), 'benchmark': benchmark, 'calendar': calendar, 'label': label,
            'sources': {str(prediction.relative_to(DATA_DIR)): hashlib.sha256(prediction_bytes).hexdigest(),
                        str(raw_path.relative_to(DATA_DIR)): hashlib.sha256(raw_bytes).hexdigest()},
            'calendar_sha256': hashlib.sha256(calendar.asi8.tobytes()).hexdigest()}


def load_evidence(market):
    """Operator-reviewed, atomic JSON bundle. Never infer classifications from names."""
    path = DATA_DIR/'paper/stress-evidence'/f'{market}.json'
    if not path.exists():
        return {}, None
    raw = path.read_bytes()
    return parse_evidence(raw, market)


def parse_evidence(raw, market):
    bundle = json.loads(raw)
    if not isinstance(bundle, dict) or bundle.get('market') != market or bundle.get('schema_version') != 1:
        raise ValueError('Evidence market/schema mismatch')
    records = {}
    if not isinstance(bundle.get('instruments'), list) or not 0 < len(bundle['instruments']) <= 200:
        raise ValueError('Invalid evidence universe size')
    for item in bundle['instruments']:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in ('symbol', 'currency', 'kind', 'source', 'reviewed_at', 'return_basis')):
            raise ValueError('Invalid evidence field types')
        if any(item.get(k) is not None and (not isinstance(item[k], str) or not item[k].strip()) for k in ('sector', 'industry', 'sector_proxy')):
            raise ValueError('Invalid classification field types')
        if not isinstance(item.get('prices'), list):
            raise ValueError('Invalid historical rows')
        if item.get('identity_verified') is not True or not item.get('source', '').startswith('https://') or not item.get('reviewed_at') or item['currency'] != ('USD' if market == 'us' else 'KRW'):
            raise ValueError('Missing reviewed provenance/currency')
        reviewed = datetime.fromisoformat(item['reviewed_at'])
        if reviewed.tzinfo is None or reviewed > datetime.now(timezone.utc):
            raise ValueError('Invalid evidence review timestamp')
        if not isinstance(item['symbol'], str) or not 1 <= len(item['symbol']) <= 16:
            raise ValueError('Invalid canonical identity')
        if item['kind'] not in ('security', 'sector', 'industry') or item['symbol'] in records:
            raise ValueError('Invalid evidence identity')
        if item['kind'] in ('sector', 'industry') and not item.get(item['kind']):
            raise ValueError('Missing verified classification')
        if item.get('return_basis') != 'split_and_dividend_adjusted_close':
            raise ValueError('Adjusted price evidence required')
        if len(item['prices']) > 30000:
            raise ValueError('History exceeds bounded input size')
        prices = _series(pd.DataFrame(item['prices']), 'Close') if item['prices'] else pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        if item.get('provenance') is not None:
            from .evidence_pipeline import verify_receipts
            verify_receipts(item,market)
        records[item['symbol']] = {**{k: v for k, v in item.items() if k != 'prices'}, 'prices': prices}
    for item in records.values():
        proxy = item.get('sector_proxy')
        if proxy and (item['kind'] != 'security' or proxy not in records or records[proxy]['kind'] != 'sector' or not item.get('sector') or records[proxy].get('sector') != item['sector']):
            raise ValueError('Invalid reviewed sector mapping')
    return records, hashlib.sha256(raw).hexdigest()


def selected_events(scores, calendar, as_of, market, current_regime):
    """First matching observation, then embargo its next ten market sessions."""
    calendar = calendar[calendar <= pd.Timestamp(as_of)]
    positions = {day: i for i, day in enumerate(calendar)}
    events = []
    next_allowed = 0
    for day, score in scores.items():
        i = positions.get(day)
        if i is None or i < next_allowed or i+HORIZON >= len(calendar):
            continue
        # The public current score and history use one-decimal displayed risk scores.
        if regime(market, round(float(score), 1) if market == 'us' else float(score)) != current_regime:
            continue
        events.append((day, calendar[i+HORIZON], calendar[i:i+HORIZON+1]))
        next_allowed = i+HORIZON
    return events


def instrument_events(prices, windows):
    output = []
    for start, end, sessions in windows:
        # Require every market session. Never compress missing rows into a ten-day return.
        rows = prices.reindex(sessions)
        if len(rows) != 11 or rows.isna().any() or not np.isfinite(rows).all() or (rows <= 0).any():
            continue
        output.append({'date': start.date().isoformat(), 'end_date': end.date().isoformat(),
                       'return_pct': float((rows.iloc[-1]/rows.iloc[0]-1)*100)})
    return output


def market_analysis(market, latest):
    records, evidence_hash = load_evidence(market)
    state = {'market': market, 'status': 'UNAVAILABLE', 'sectors': [], 'instruments': {}, 'regime': None}
    if not latest or not latest.get('data_health', {}).get('is_current') or latest.get('data_health', {}).get('model_available') is False:
        return {**state, 'reason': 'CURRENT_STRESS_UNAVAILABLE'}, records
    state.update(regime=regime(market, latest.get('risk_score_10d')), observation_date=latest['last_updated'],
                 risk_score=latest['risk_score_10d'], model_sha256=latest.get('model_sha256'),
                 snapshot_id=latest.get('data_health', {}).get('snapshot_id'))
    if market == 'korea' and isinstance(latest.get('warning_active'), bool):
        state['regime'] = 'WARNING' if latest['warning_active'] else 'BELOW WARNING'
    history = load_market(market)
    windows = selected_events(history['scores'], history.get('calendar', history['benchmark'].index), latest['last_updated'], market, state['regime'])
    state.update(status='AVAILABLE', eligible_events=len(windows), sources=history['sources'], calendar_sha256=history.get('calendar_sha256'), evidence_sha256=evidence_hash,
                 benchmark={'label': history['label'], 'evidence_level': 'market_context_only', 'return_basis': 'existing_price_series_not_total_return',
                            **distribution(instrument_events(history['benchmark'], windows))})
    for symbol, item in records.items():
        stats = distribution(instrument_events(item['prices'], windows))
        state['instruments'][symbol] = {**{k: v for k, v in item.items() if k != 'prices'}, **stats}
        if item['kind'] in ('sector', 'industry'):
            state['sectors'].append({'symbol': symbol, **state['instruments'][symbol]})
    state['sector_status'] = 'AVAILABLE' if state['sectors'] else 'VERIFIED_SECTOR_HISTORY_UNAVAILABLE'
    return state, records


def exposures(investment, records):
    total = investment.get('portfolio_value')
    complete = investment.get('valuation_complete') and isinstance(total, (float, int)) and total > 0
    rate = (investment.get('fx') or {}).get('rate')
    rows = []
    for market in ('us', 'korea'):
        for position in investment['books'][market]['positions']:
            metadata = records[market].get(position['symbol'], {})
            native = position.get('market_value')
            usd = native if market == 'us' else native/rate if native is not None and rate else None
            rows.append({'market': market, 'symbol': position['symbol'], 'currency': 'USD' if market == 'us' else 'KRW',
                         'sector': metadata.get('sector'), 'industry': metadata.get('industry'),
                         'metadata_source': metadata.get('source'), 'metadata_reviewed_at': metadata.get('reviewed_at'),
                         'metadata_retrieved_at': metadata.get('provenance', {}).get('retrieved_at'),
                         'classification_basis': metadata.get('classification_basis'),
                         'exposure_basis': 'fund_mandate_not_lookthrough' if metadata.get('kind') in ('sector','industry') else 'direct_security_classification' if metadata else 'unavailable',
                         'value_usd': usd, 'weight': usd/total if complete and usd is not None else None})
    groups = {}
    for dimension in ('market', 'sector', 'industry', 'currency', 'symbol'):
        buckets = {}
        for row in rows:
            label = row[dimension] or 'UNKNOWN'
            # Sector/industry names remain market-specific even when their text matches.
            key = f"{row['market']}:{label}" if dimension in ('sector', 'industry', 'symbol') else label
            buckets[key] = buckets.get(key, 0)+(row['weight'] or 0)
        if dimension == 'currency' and complete:
            for currency, cash in investment['cash_balances'].items():
                cash_usd = cash if currency == 'USD' else cash/rate if cash and rate else 0
                buckets[currency] = buckets.get(currency, 0)+cash_usd/total
        groups[dimension] = [{'label': k, 'weight': v if complete else None} for k, v in sorted(buckets.items())]
    return {'status': 'AVAILABLE' if complete else 'VALUATION_INCOMPLETE', 'holdings': rows, 'groups': groups,
            'cash_weight': investment.get('cash')/total if complete and investment.get('cash') is not None else None,
            'largest_security_weight': max((r['weight'] or 0 for r in rows), default=0) if complete else None}


def sensitivity(market, exposure, analysis, records):
    holdings = [r for r in exposure['holdings'] if r['market'] == market]
    evidence = []
    maps = []
    for holding in holdings:
        symbol = holding['symbol']
        candidate = analysis.get('instruments', {}).get(symbol)
        security_n = candidate['n'] if candidate else 0
        level = 'security'
        if not candidate or candidate['status'] != 'AVAILABLE':
            proxy = records.get(symbol, {}).get('sector_proxy')
            candidate = analysis.get('instruments', {}).get(proxy)
            level = 'sector_proxy'
            # Require explicitly reviewed mapping and exact sector agreement, never choose by return.
            if not candidate or candidate['kind'] != 'sector' or not holding['sector'] or candidate.get('sector') != holding['sector'] or candidate['status'] != 'AVAILABLE':
                candidate = None
        evidence.append({'symbol': symbol, 'weight': holding['weight'], 'level': level if candidate else 'unavailable',
                         'instrument': candidate['symbol'] if candidate else None, 'n': candidate['n'] if candidate else security_n})
        if candidate and holding['weight'] is not None:
            maps.append({(e['date'], e['end_date']): e['return_pct']*holding['weight'] for e in candidate['events']})
    result = {'market': market, 'evidence': evidence, 'weight': sum(r['weight'] or 0 for r in holdings),
              'status': 'NO_HOLDINGS' if not holdings else 'INSUFFICIENT_EVIDENCE', 'distribution': None}
    if holdings and len(maps) == len(holdings) and exposure['status'] == 'AVAILABLE':
        common = set(maps[0]).intersection(*(set(m) for m in maps[1:]))
        events = [{'date': d, 'end_date': end, 'return_pct': sum(m[(d, end)] for m in maps)} for d, end in sorted(common)]
        result['distribution'] = distribution(events)
        result['status'] = result['distribution']['status']
    return result


def report(investment, latest_by_market):
    markets, records = {}, {}
    for market in ('us', 'korea'):
        try:
            markets[market], records[market] = market_analysis(market, latest_by_market.get(market))
        except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError):
            try:
                records[market], _ = load_evidence(market)
            except (OSError, ValueError, KeyError, TypeError):
                records[market] = {}
            markets[market] = {'market': market, 'status': 'UNAVAILABLE', 'reason': 'INVALID_OR_MISSING_HISTORY', 'sectors': [], 'instruments': {}}
    exposure = exposures(investment, records)
    sensitivities = [sensitivity(m, exposure, markets[m], records[m]) for m in ('us', 'korea')]
    active = [s for s in sensitivities if s['evidence']]
    # Never add independent market quantiles or pair unrelated U.S./Korea events.
    outlook = {'status': 'NO_HOLDINGS' if not active else 'SEPARATE_MARKET_EVIDENCE_REQUIRED', 'distribution': None}
    if len(active) == 1:
        outlook = {'status': active[0]['status'], 'distribution': active[0]['distribution'], 'market': active[0]['market']}
    return {'methodology_version': VERSION, 'horizon_sessions': HORIZON, 'valuation_at': investment.get('observed_at'),
            'markets': markets, 'exposure': exposure, 'sensitivity': sensitivities, 'outlook': outlook,
            'assumptions': {'fx': 'held_constant_at_current_validated_rate', 'weights': 'current_usd_equity_weights_buy_and_hold',
                            'cash_return': 0, 'future_trades_fees_dividends': 'no_future_trades_or_additional_costs; adjusted_history_includes_distributions',
                            'interpretation': 'Historical conditional scenarios, not a forecast or causal effect.'}}


def current_report(user_id):
    from src.operations.service import current_payload
    from .investment import summary
    latest = {}
    for market in ('us', 'korea'):
        try:
            latest[market] = current_payload(market)
        except HTTPException:
            latest[market] = None
    return report(summary(user_id), latest)
