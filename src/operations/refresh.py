"""FETCH → STAGE → VALIDATE → unchanged inference → atomic publication."""
import fcntl
import hashlib
import json
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
import pandas as pd
from src.config import PROJECT_ROOT, DATA_RAW_DIR
from . import alerts
from .calendar import expected, calendar, series_expected
from .providers import Providers, PROVIDERS, UNITS
from .store import database, root, utcnow, snapshot, publish, history, artifact_path
from .validation import ValidationFailure, validate_series

logger = logging.getLogger(__name__)


def redact_diagnostic(text):
    # Workers run local calculations, but exception text can contain environment
    # values. Redact configured credentials before persisting any diagnostics.
    credentials = {value for key, value in os.environ.items() if value and
                   any(part in key.upper() for part in ('KEY', 'SECRET', 'PASSWORD', 'TOKEN', 'CREDENTIAL'))}
    for value in sorted(credentials, key=len, reverse=True):
        text = text.replace(value, '[REDACTED]')
    return text

SERIES = {'us':['SPY','VIX','DBAA','DGS10'],
          'korea':['KOSPI200','VKOSPI','Korea_Treasury_3Y','Korea_Corporate_AAminus_3Y']}


def legacy(market):
    if market=='us':
        frame=pd.read_csv(DATA_RAW_DIR/'raw_market_data.csv',index_col='Date',parse_dates=True)
        # Existing US cache contains only the spread, not independent FRED inputs.
        # Its retrieval time and component provenance cannot be reconstructed.
        return {col:frame[[col]] for col in ['SPY','VIX','BAA_Treasury_Spread']}
    krx=pd.read_csv(DATA_RAW_DIR/'korea/krx_indices.csv',parse_dates=['Date'])
    equity=krx.loc[krx['Index']=='KOSPI200',['Date','Close']].set_index('Date').rename(columns={'Close':'KOSPI200'})
    vol=pd.read_csv(DATA_RAW_DIR/'korea/vkospi.csv',index_col='Date',parse_dates=True)
    credit=pd.read_csv(DATA_RAW_DIR/'korea/ecos_credit.csv',index_col='Date',parse_dates=True)
    return {'KOSPI200':equity,'VKOSPI':vol[['Close']].rename(columns={'Close':'VKOSPI'}),**{name:credit[[name]] for name in SERIES['korea'][2:]}}


def seeds(market):
    current=snapshot(market)
    if current:
        path=artifact_path(current['payload'].get('artifact_directory', 'missing'))/'source_history.csv'
        if path.exists():
            digest=current['payload'].get('source_history_sha256')
            if digest and hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValidationFailure('Snapshot source history integrity check failed.')
            frame=pd.read_csv(path,index_col='Date',parse_dates=True)
            return {col:frame[[col]] for col in frame.columns}
    return legacy(market)


def stage_inputs(market, stage, frames, metadata, provenance, today):
    for name,frame in frames.items():
        validate_series(frame,name,positive=name in ['SPY','VIX','KOSPI200','VKOSPI'],allow_missing=True,today=today)
    merged=pd.concat([f for f in frames.values()],axis=1).sort_index()
    merged.index.name='Date'
    # Save original source dates, including late/unmatched inputs, for future revision-aware refreshes.
    merged.to_csv(stage/'source_history.csv')
    complete=merged.dropna(subset=list(frames))
    if complete.empty or len(complete)<400:
        raise ValidationFailure('At least 400 real common observations required for rolling MSI and expanding threshold warm-up.')
    common=complete.index[-1]
    raw=merged.loc[:common].copy()
    if market=='us':
        if 'BAA_Treasury_Spread' not in raw:
            raw['BAA_Treasury_Spread']=raw['DBAA']-raw['DGS10']
        raw[['SPY','VIX','BAA_Treasury_Spread']].to_csv(stage/'raw_market_data.csv')
    else:
        # No new imputation: Korea existing builders require common observed rows.
        # Preserve equity calendar rows; missing required observations fail closed,
        # rather than dropping them and silently changing rolling-feature windows.
        raw=raw.loc[raw['KOSPI200'].notna()].copy()
        if raw[list(frames)].isna().any().any():
            raise ValidationFailure('Missing Korea input on an equity observation date; no forward fill permitted.')
        raw['Korea_Credit_Spread']=raw['Korea_Corporate_AAminus_3Y']-raw['Korea_Treasury_3Y']
        raw['Korea_Credit_Spread_bp']=raw['Korea_Credit_Spread']*100
        raw[['KOSPI200']].rename(columns={'KOSPI200':'Close'}).assign(Index='KOSPI200').to_csv(stage/'krx_indices.csv')
        raw[['VKOSPI']].rename(columns={'VKOSPI':'Close'}).to_csv(stage/'vkospi.csv')
        raw[['Korea_Treasury_3Y','Korea_Corporate_AAminus_3Y','Korea_Credit_Spread','Korea_Credit_Spread_bp']].to_csv(stage/'ecos_credit.csv')
    anomalies=[]
    for name in ['SPY','VIX','KOSPI200','VKOSPI']:
        if name in frames:
            changes=frames[name][name].dropna().pct_change()
            if len(changes)>1 and abs(float(changes.iloc[-1]))>=.3:
                anomalies.append({'series':name,'type':'large_move_review','change':float(changes.iloc[-1]),'rejected':False})
    for item in metadata:
        item['used_observation_date']=common.strftime('%Y-%m-%d')
    spec={'common_date':common.strftime('%Y-%m-%d'),'series':metadata,'provenance':provenance,'anomalies':anomalies}
    (stage/'inputs.json').write_text(json.dumps(spec,allow_nan=False))
    return spec


def refresh(market, trigger='manual', adopt_local=False, providers_factory=Providers):
    if market not in SERIES:
        raise ValueError('Unknown market.')
    root().mkdir(parents=True,exist_ok=True)
    with open(root()/f'{market}.lock','a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return {'market':market,'status':'ALREADY_RUNNING','snapshot_published':False}
        job_id=uuid.uuid4().hex
        started=utcnow()
        try:
            date,deadline=expected(market)
        except Exception:
            date,deadline=None,None
        with database() as db:
            # Any RUNNING job under the now-exclusive lock was interrupted.
            db.execute("UPDATE jobs SET status='ERROR',finished_at=?,error_type='InterruptedJob',error_message='Previous worker exited before completing refresh.' WHERE market=? AND status='RUNNING'",(started,market))
            db.execute('INSERT INTO jobs (job_id,market,trigger,expected_date,started_at,status) VALUES (?,?,?,?,?,?)',(job_id,market,'adopt-local' if adopt_local else trigger,date,started,'RUNNING'))
            if date:
                db.execute('INSERT INTO scheduler (market,heartbeat_at,expected_date,expected_run_at,last_run_at,last_run_expected_date) VALUES (?,?,?,?,?,?) ON CONFLICT(market) DO UPDATE SET last_run_at=excluded.last_run_at,last_run_expected_date=excluded.last_run_expected_date', (market,'1970-01-01T00:00:00+00:00',date,deadline,started,None if adopt_local else date))
        committed=False
        report={'job_id':job_id,'market':market,'expected_date':date,'series':[]}
        try:
            if not date:
                raise ValidationFailure('Cannot prove expected exchange session; calendar unavailable.')
            # Provider adapters require sessions through this cutoff. A close
            # alone does not make end-of-day inputs due: use the same market
            # publication deadline as freshness/scheduling, sampled above.
            fetch_end=date
            report['fetch_through_date']=fetch_end
            base=seeds(market)
            frames={}
            if adopt_local:
                frames=base
                for name,frame in frames.items():
                    latest=validate_series(frame,name,positive=name in ['SPY','VIX','KOSPI200','VKOSPI'],allow_missing=True,today=date)
                    report['series'].append({'series':name,'provider':PROVIDERS.get(name,'FRED cached spread'),'unit':UNITS.get(name,'percentage points'),
                        'latest_observation_date':latest,'retrieved_at':None,'status':'STALE','attempt_count':0,'provenance':'legacy cache; retrieval time unknown'})
            else:
                providers=providers_factory(job_id)
                # Attempt every independent critical channel even if one fails.
                for name in SERIES[market]:
                    info={'series':name,'provider':PROVIDERS[name],'unit':UNITS[name]}
                    try:
                        if market=='us':
                            frame,retrieved=providers.yahoo(name,fetch_end) if name in ['SPY','VIX'] else providers.fred(name,fetch_end)
                        else:
                            frame,retrieved=providers.krx(name,fetch_end,base.get(name,pd.DataFrame())) if name in ['KOSPI200','VKOSPI'] else providers.ecos(name,fetch_end)
                        latest=validate_series(frame,name,positive=name in ['SPY','VIX','KOSPI200','VKOSPI'],allow_missing=True,today=fetch_end)
                        if name in ['KOSPI200','VKOSPI']:
                            prior=base.get(name,pd.DataFrame())
                            frame=pd.concat([prior,frame]);frame=frame[~frame.index.duplicated(keep='last')].sort_index()
                        series_date=series_expected(market,name,date)
                        info['expected_observation_date']=series_date
                        sessions=calendar(market,pd.Timestamp(date).year).sessions_in_range(pd.Timestamp(latest),pd.Timestamp(series_date)) if latest<series_date else []
                        if len(sessions)>6:
                            raise ValidationFailure(f'{name}: required input is more than five due exchange sessions stale.')
                        frames[name]=frame
                        info.update(value=float(frame.loc[pd.Timestamp(latest),name]),observation_date=latest,source=PROVIDERS[name],latest_observation_date=latest,retrieved_at=retrieved,status='CURRENT' if latest>=series_date else 'DELAYED')
                    except Exception as exc:
                        info.update(latest_observation_date=None,retrieved_at=None,status='ERROR',error_type=type(exc).__name__,error_message=str(exc)[:500])
                    info['attempt_count']=providers.counts.get(name,0)
                    report['series'].append(info)
                failed=[s for s in report['series'] if s['status']=='ERROR']
                if failed:
                    raise ValidationFailure('Required provider series failed: '+', '.join(s['series'] for s in failed))
            stage=root()/'staging'/job_id
            stage.mkdir(parents=True)
            spec=stage_inputs(market,stage,frames,report['series'],'legacy-cache' if adopt_local else 'provider-validated',fetch_end)
            # This process redirects paths only in its own memory. Live files are never changed.
            result=subprocess.run([sys.executable,'-m','src.operations.worker',market,str(stage.resolve())],cwd=PROJECT_ROOT,timeout=180,capture_output=True,text=True)
            if result.returncode:
                # The uncaught traceback reaches subprocess stderr after the
                # worker's redirect context exits. Preserve it, not just stdout.
                stderr = redact_diagnostic(getattr(result, 'stderr', '') or '')
                stdout = redact_diagnostic(getattr(result, 'stdout', '') or '')
                (stage/'worker.stderr.log').write_text(stderr)
                (stage/'worker.stdout.log').write_text(stdout)
                calculation = stage/'calculation.log'
                calculation_tail = redact_diagnostic(calculation.read_text()[-1500:] if calculation.exists() else '')
                (stage/'worker.diagnostic.log').write_text(
                    f'exit_code={result.returncode}\nSTDERR\n{stderr[-6000:]}\nCALCULATION\n{calculation_tail}\nSTDOUT\n{stdout[-1500:]}')
                logger.error('Staged worker failed: market=%s job=%s exit_code=%s\nSTDERR\n%s\nCALCULATION\n%s',
                             market, job_id, result.returncode, stderr[-6000:], calculation_tail)
                # Ledger/API/UI carry only a safe summary, never a traceback.
                raise ValidationFailure(f'Staged calculation failed (exit_code={result.returncode}). See worker diagnostic logs.')
            payload=json.loads((stage/'snapshot.json').read_text())
            payload['expected_date_at_refresh']=date
            payload['refresh_job_id']=job_id
            report.update(common_feature_date=spec['common_date'],snapshot=payload)
            previous=snapshot(market)
            if previous and payload['last_updated']<previous['observation_date']:
                raise ValidationFailure('Provider response would regress the last-known-good date.')
            report.update(status='SUCCESS',snapshot_published=True)
            publish(job_id,market,payload,report)
            committed=True
            if payload['last_updated']<date or adopt_local:
                alerts.emit(market,'required_series_stale',report,job_id)
            if payload['anomalies']:
                alerts.emit(market,'large_market_move_review',{'anomalies':payload['anomalies']},job_id)
            report.update(status='SUCCESS',snapshot_published=True)
        except Exception as exc:
            if committed:
                report['alert_error_type']=type(exc).__name__
                with database() as db:
                    db.execute('UPDATE jobs SET report=? WHERE job_id=?',(json.dumps(report,allow_nan=False),job_id))
                return report
            report.update(status='ERROR',error_type=type(exc).__name__,error_message=str(exc)[:2000],snapshot_published=False)
            with database() as db:
                db.execute("UPDATE jobs SET status='ERROR',finished_at=?,error_type=?,error_message=?,report=? WHERE job_id=?",(utcnow(),type(exc).__name__,report['error_message'],json.dumps(report,allow_nan=False),job_id))
            alerts.emit(market,'refresh_failed',report,job_id)
            if not snapshot(market):
                alerts.emit(market,'no_valid_snapshot',{'error':report['error_message']},job_id)
        return report
