"""Opt-in Korea alignment diagnostics. Never imported by production forecasting.

AS-OF scores are incompatible-vintage experiments, not validated V1 forecasts.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import uuid
import numpy as np
import pandas as pd
from .ingestion import sessions, runtime_end

SERIES = ['KOSPI200', 'VKOSPI', 'Korea_Treasury_3Y', 'Korea_Corporate_AAminus_3Y']


def cutoff_timestamp(value):
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        raise ValueError('information_cutoff must include timezone')
    return result.tz_convert('UTC')


def align_sources(sources, information_cutoff, *, asof=False, max_trading_days=1,
                  max_calendar_days=4, allow_proxy=False):
    """Sources contain Date/value and optional actual retrieval/availability evidence.

    The equity source defines the axis; calendar ages use the exchange calendar,
    not the number of rows supplied. Unknown publication times stay unknown.
    """
    cutoff = cutoff_timestamp(information_cutoff)
    if max_trading_days < 0 or max_calendar_days < 0:
        raise ValueError('staleness limits must be nonnegative')
    eligible = {}
    for name in SERIES:
        f = sources[name].copy()
        f['Date'] = pd.to_datetime(f.Date).dt.normalize()
        f = f.loc[f.Date <= cutoff.tz_convert('Asia/Seoul').tz_localize(None).normalize()]
        for col in ['retrieved_at', 'source_available_at']:
            if col not in f:
                f[col] = pd.NaT
            f[col] = pd.to_datetime(f[col], utc=True)
        f = f.loc[(f.retrieved_at.isna() | f.retrieved_at.le(cutoff)) &
                  (f.source_available_at.isna() | f.source_available_at.le(cutoff))]
        if not allow_proxy:
            # A publisher date alone does not prove system possession.
            f = f.loc[f.retrieved_at.notna()]
        eligible[name] = f.dropna(subset=['value']).sort_values('Date').drop_duplicates('Date', keep='last')
    axis = pd.DatetimeIndex(eligible['KOSPI200'].Date.unique()).sort_values()
    axis = axis[axis <= pd.Timestamp(runtime_end(now=cutoff.to_pydatetime()))]
    first_dates = [f.Date.min() for f in eligible.values() if len(f)]
    calendar = sessions(min(first_dates), axis[-1]) if len(axis) else pd.DatetimeIndex([])
    result = pd.DataFrame(index=axis)
    result.index.name = 'Date'
    metadata = []
    for name in SERIES:
        f = eligible[name]
        latest = f.Date.max() if len(f) else pd.NaT
        if len(f):
            matched = pd.merge_asof(pd.DataFrame({'Date': axis}), f.rename(columns={'Date': 'used_observation_date'}),
                                    left_on='Date', right_on='used_observation_date', direction='backward',
                                    tolerance=None if asof else pd.Timedelta(0))
        else:
            matched = pd.DataFrame({'Date': axis, 'used_observation_date': pd.NaT, 'value': np.nan,
                                    'retrieved_at': pd.NaT, 'source_available_at': pd.NaT})
        ages = [int(calendar.searchsorted(r.Date, side='right') - calendar.searchsorted(r.used_observation_date, side='right'))
                if pd.notna(r.used_observation_date) else None for r in matched.itertuples()]
        matched['staleness_calendar_days'] = (matched.Date - matched.used_observation_date).dt.days
        matched['staleness_trading_days'] = ages
        valid = matched.used_observation_date.notna()
        if asof:
            valid &= matched.staleness_calendar_days.le(max_calendar_days) & matched.staleness_trading_days.le(max_trading_days)
        result[name] = matched.value.where(valid).to_numpy()
        for i, r in matched.iterrows():
            lag = bool(pd.notna(r.used_observation_date) and r.used_observation_date < r.Date)
            metadata.append({'Date': r.Date, 'series': name, 'source_observation_date': r.used_observation_date,
                             'latest_known_source_observation_date': latest,
                             'used_observation_date': r.used_observation_date if valid.iloc[i] else pd.NaT,
                             'retrieved_at': r.retrieved_at, 'source_available_at': r.source_available_at,
                             'staleness_calendar_days': r.staleness_calendar_days,
                             'staleness_trading_days': r.staleness_trading_days,
                             'is_stale': lag, 'accepted': bool(valid.iloc[i]),
                             'fill_method': ('REJECTED_STALE' if pd.notna(r.used_observation_date) else 'MISSING') if not valid.iloc[i] else ('BACKWARD_ASOF' if asof and lag else 'EXACT'),
                             'information_cutoff': cutoff, 'availability_evidence':
                             'RETRIEVAL_VERIFIED' if pd.notna(r.retrieved_at) else 'OBSERVATION_DATE_PROXY'})
    result['Korea_Credit_Spread'] = result.Korea_Corporate_AAminus_3Y - result.Korea_Treasury_3Y
    result['Korea_Credit_Spread_bp'] = result.Korea_Credit_Spread * 100
    return result, pd.DataFrame(metadata, columns=['Date','series','source_observation_date','latest_known_source_observation_date','used_observation_date','retrieved_at','source_available_at','staleness_calendar_days','staleness_trading_days','is_stale','accepted','fill_method','information_cutoff','availability_evidence'])


def common_path(exact):
    complete = exact.dropna(subset=SERIES)
    if complete.empty:
        return exact.iloc[:0], None
    common = complete.index[-1]
    frame = exact.loc[:common]
    # Same fail-closed rule as operations.stage_inputs; don't shorten rolling windows.
    if frame[SERIES].isna().any().any():
        raise ValueError('Interior missing V1 inputs; no imputation or dropped sessions permitted')
    return frame, common


def quality(metadata, origin):
    m = metadata.loc[metadata.Date.eq(origin)]
    if m.empty or m.source_observation_date.isna().any():
        freshness = 'INCOMPLETE'
    elif not m.accepted.all():
        freshness = 'STALE'
    elif m.is_stale.any():
        freshness = 'PARTIALLY_STALE'
    else:
        freshness = 'FRESH'
    return {'freshness': freshness, 'availability': 'UNKNOWN_AVAILABILITY' if m.empty or
            m.retrieved_at.isna().any() else 'RETRIEVAL_VERIFIED'}


def archive_inputs(directory, files):
    """Content-addressed input artifacts; never replace a prior input snapshot."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, content in files.items():
        target = directory / name
        digest = hashlib.sha256(content).hexdigest()
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError('Immutable input artifact conflict: ' + name)
        else:
            with target.open('xb') as stream:
                stream.write(content)
        hashes[name] = digest
    return hashes


def append_forecast(path, record):
    """Append-only ledger. Same cutoff/model/input retry is a separate attempt only."""
    if cutoff_timestamp(record['information_cutoff']) > cutoff_timestamp(record['prediction_timestamp']):
        raise ValueError('prediction timestamp precedes information cutoff')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    key_fields = ['market', 'information_cutoff', 'model_sha256', 'feature_schema_version',
                  'forecast_origin_session', 'input_sha256', 'path']
    key = hashlib.sha256(json.dumps({k: record[k] for k in key_fields}, sort_keys=True).encode()).hexdigest()
    with sqlite3.connect(path, timeout=30) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS forecasts (forecast_id TEXT PRIMARY KEY, retry_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (attempt_id TEXT PRIMARY KEY, forecast_id TEXT NOT NULL, attempted_at TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS forecasts_no_update BEFORE UPDATE ON forecasts BEGIN SELECT RAISE(ABORT,'immutable forecast'); END;
        CREATE TRIGGER IF NOT EXISTS forecasts_no_delete BEFORE DELETE ON forecasts BEGIN SELECT RAISE(ABORT,'immutable forecast'); END;
        CREATE TRIGGER IF NOT EXISTS attempts_no_update BEFORE UPDATE ON attempts BEGIN SELECT RAISE(ABORT,'immutable attempt'); END;
        CREATE TRIGGER IF NOT EXISTS attempts_no_delete BEFORE DELETE ON attempts BEGIN SELECT RAISE(ABORT,'immutable attempt'); END;
        ''')
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT forecast_id,payload FROM forecasts WHERE retry_key=?', (key,)).fetchone()
        if old:
            previous = json.loads(old[1])
            for field in ['v1_risk_score', 'current_stress', 'shadow_outputs', 'warning_state']:
                if previous.get(field) != record.get(field):
                    raise ValueError('Identical cutoff/model/input produced conflicting output')
            forecast_id, created = old[0], False
        else:
            forecast_id, created = uuid.uuid4().hex, True
            payload = dict(record, forecast_id=forecast_id)
            db.execute('INSERT INTO forecasts VALUES (?,?,?)', (forecast_id, key, json.dumps(payload, sort_keys=True, allow_nan=False)))
        db.execute('INSERT INTO attempts VALUES (?,?,?)', (uuid.uuid4().hex, forecast_id, datetime.now(timezone.utc).isoformat()))
    return forecast_id, created


def replay(frame, model_path, output):
    """Original builders, frozen artifact, isolated output; no fitting or model writes."""
    from . import build_korea_features as features, build_korea_stress_index as stress
    import joblib
    output.mkdir(parents=True, exist_ok=True)
    if frame.empty or frame[SERIES].isna().any().any():
        return {'score': None, 'MSI': None, 'reason': 'Incomplete compatible raw history'}
    frame[['KOSPI200']].rename(columns={'KOSPI200': 'Close'}).assign(Index='KOSPI200').to_csv(output/'krx_indices.csv')
    frame[['VKOSPI']].rename(columns={'VKOSPI': 'Close'}).to_csv(output/'vkospi.csv')
    frame[['Korea_Treasury_3Y', 'Korea_Corporate_AAminus_3Y', 'Korea_Credit_Spread', 'Korea_Credit_Spread_bp']].to_csv(output/'ecos_credit.csv')
    f = features.build_features(frame.reset_index()).dropna(subset=features.FEATURE_COLS)
    if f.empty or f.Date.iloc[-1] != frame.index[-1]:
        return {'score': None, 'MSI': None, 'reason': 'Feature warmup/incomplete latest row'}
    f.to_csv(output/'features.csv', index=False)
    old = {k: getattr(stress, k) for k in ['KRX_PATH','VKOSPI_PATH','CREDIT_PATH','OUTPUT_PATH']}
    try:
        stress.KRX_PATH = str(output/'krx_indices.csv'); stress.VKOSPI_PATH = str(output/'vkospi.csv')
        stress.CREDIT_PATH = str(output/'ecos_credit.csv'); stress.OUTPUT_PATH = str(output/'msi.csv')
        with contextlib.redirect_stdout(io.StringIO()):
            stress.main()
    finally:
        for k, v in old.items():
            setattr(stress, k, v)
    msi = pd.read_csv(output/'msi.csv').set_index('Date')
    date = frame.index[-1].strftime('%Y-%m-%d')
    model = joblib.load(model_path)
    score = float(model.predict_proba(f[features.FEATURE_COLS].tail(1))[0,1])*100
    value = float(msi.loc[date,'Korea_MSI'])
    return {'score': score, 'MSI': value, 'reason': None,
            'warning_active': score >= 50, 'warning_version': 'V1-existing-50',
            'feature_observation_date': date}


def load_sources(raw):
    k = pd.read_csv(raw/'krx_indices.csv', parse_dates=['Date'])
    v = pd.read_csv(raw/'vkospi.csv', parse_dates=['Date'])
    e = pd.read_csv(raw/('ecos_credit_unaligned.csv' if (raw/'ecos_credit_unaligned.csv').exists() else 'ecos_credit.csv'), parse_dates=['Date'])
    sources = {'KOSPI200': k.loc[k.Index.eq('KOSPI200'), ['Date','Close']].rename(columns={'Close':'value'}),
               'VKOSPI': v[['Date','Close']].rename(columns={'Close':'value'})}
    for name in SERIES[2:]:
        sources[name] = e[['Date',name]].rename(columns={name:'value'})
    # Receipt evidence is joined only when the value matches, never assigned to old data wholesale.
    evidence = []
    for file in sorted((raw/'receipts').glob('*.json')):
        r = json.loads(file.read_text())
        for row in r['rows']:
            name = r['series']
            if name == 'KRX_indices':
                if row.get('Index') != 'KOSPI200': continue
                name, value = 'KOSPI200', row.get('Close')
            elif name == 'VKOSPI': value = row.get('Close')
            else: value = row.get(name)
            if value is not None:
                evidence.append({'series':name, 'Date':pd.Timestamp(row['Date']), 'value':float(value),
                                 'retrieved_at':r['retrieved_at'], 'source_available_at':r.get('source_available_at')})
    for name, f in sources.items():
        ev = pd.DataFrame([r for r in evidence if r['series']==name])
        if len(ev):
            ev = ev.sort_values('retrieved_at').drop_duplicates(['Date','value'], keep='first')
            sources[name] = f.merge(ev.drop(columns='series'), on=['Date','value'], how='left')
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--information-cutoff', required=True)
    parser.add_argument('--allow-observation-date-proxy', action='store_true')
    parser.add_argument('--max-staleness-trading-days', type=int, default=1)
    parser.add_argument('--max-staleness-calendar-days', type=int, default=4)
    parser.add_argument('--model', type=Path, default=Path('models/korea/xgboost_10d_latest.joblib'))
    args = parser.parse_args()
    if cutoff_timestamp(args.information_cutoff) > pd.Timestamp.now(tz='UTC'):
        parser.error('information-cutoff cannot be in the future')
    args.output.mkdir(parents=True, exist_ok=True)
    sources = load_sources(args.data_root/'raw/korea')
    result = {}
    for path in ['v1_common', 'experimental_asof']:
        frame, meta = align_sources(sources, args.information_cutoff, asof=path=='experimental_asof',
                                    max_trading_days=args.max_staleness_trading_days,
                                    max_calendar_days=args.max_staleness_calendar_days,
                                    allow_proxy=args.allow_observation_date_proxy)
        available_frame = frame.copy()
        latest = frame.index[-1] if len(frame) else None
        if path=='v1_common': frame, origin = common_path(frame)
        else: origin = latest
        meta.to_csv(args.output/(path+'_source_metadata.csv'), index=False)
        frame.to_csv(args.output/(path+'_inputs.csv'))
        score = replay(frame, args.model, args.output/path)
        cutoff = cutoff_timestamp(args.information_cutoff).isoformat()
        used = meta.loc[meta.Date.eq(origin)] if origin is not None else meta.iloc[:0]
        source_rows = json.loads(used.to_json(orient='records',date_format='iso'))
        record = {'market':'korea','prediction_timestamp':datetime.now(timezone.utc).isoformat(),
                  'information_cutoff':cutoff,'model_sha256':hashlib.sha256(args.model.read_bytes()).hexdigest(),
                  'model_version':str(args.model),'feature_schema_version':'frozen-korea-17',
                  'forecast_origin_session':origin.strftime('%Y-%m-%d') if origin is not None else None,
                  'v1_feature_observation_date':origin.strftime('%Y-%m-%d') if path=='v1_common' and origin is not None else None,
                  'path':path,'input_sha256':hashlib.sha256(frame.to_csv().encode()+used.to_json(date_format='iso').encode()).hexdigest(),
                  'source_observation_dates':source_rows,'data_quality':dict(quality(meta,latest), freshness='PARTIALLY_STALE') if path=='v1_common' and origin is not None and origin < latest else quality(meta,latest),
                  'compatible_origin_quality':quality(meta,origin),
                  'v1_risk_score':score['score'],'current_stress':score['MSI'],
                  'trajectory_metadata':{'status':'NOT_EVALUATED','daily_persistence_key':str(origin),'retry_counts_as_observation':False},
                  'shadow_outputs':{'1D':None,'3D':None,'5D':None,'10D':score['score']},
                  'warning_state':'WARNING' if score.get('warning_active') else ('BELOW_V1_WARNING' if score['score'] is not None else 'UNAVAILABLE'),
                  'warning_version':'V1-existing-50; experimental replay is not an operational warning',
                  'compatibility':'V1_COMMON_DATE' if path=='v1_common' else 'UNVALIDATED_MIXED_VINTAGE_REPLAY',
                  'alignment_reason':'Last complete exact-date row; newer observations retained in source metadata' if path=='v1_common' else 'Backward-only, capped staleness; each credit leg dated independently',
                  'excluded_newer_observations':json.loads(meta.loc[meta.Date.gt(origin)].to_json(orient='records',date_format='iso')) if path=='v1_common' and origin is not None else [],
                  'replay':score}
        artifact_directory = args.output/'artifacts'/record['input_sha256']
        artifacts = {'inference_inputs.csv':frame.to_csv().encode(), 'source_axis.csv':available_frame.to_csv().encode(),
                     'source_metadata.csv':meta.to_csv(index=False).encode()}
        if score['reason'] is None:
            for name in ['features.csv','msi.csv']:
                artifacts[name] = (args.output/path/name).read_bytes()
        record['artifact_hashes'] = archive_inputs(artifact_directory,artifacts)
        record['artifact_directory'] = str(artifact_directory.resolve())
        forecast_id, created = append_forecast(args.output/'shadow_history.sqlite3',record)
        with sqlite3.connect(args.output/'shadow_history.sqlite3') as db:
            saved = json.loads(db.execute('SELECT payload FROM forecasts WHERE forecast_id=?',(forecast_id,)).fetchone()[0])
        result[path] = dict(saved,new_forecast=created,attempt_timestamp=record['prediction_timestamp'],
                            latest_market_observation=latest.strftime('%Y-%m-%d') if latest is not None else None)
    (args.output/'comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:{'origin':v['forecast_origin_session'],'score':v['v1_risk_score'],'MSI':v['current_stress'],'quality':v['data_quality']} for k,v in result.items()},indent=2))

if __name__ == '__main__':
    main()
