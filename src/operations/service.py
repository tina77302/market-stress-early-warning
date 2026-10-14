"""Shared validated snapshots for every user; no subscription inputs."""
import math
from datetime import datetime, timezone, timedelta
from .calendar import expected, series_expected
from .store import snapshot, history, database


def health(market, now=None, *, current=None):
    now=now or datetime.now(timezone.utc)
    current=current or snapshot(market)
    jobs=history(market,1)
    job=jobs[0] if jobs else None
    try:
        date,deadline=expected(market,now)
    except Exception:
        date,deadline=None,None
    with database() as db:
        row=db.execute('SELECT * FROM scheduler WHERE market=?',(market,)).fetchone()
    scheduler=dict(row) if row else {}
    scheduler.update(expected_date=date,expected_run_at=deadline)
    ran=bool(row and row['last_run_expected_date']==date)
    late=bool(deadline and now>datetime.fromisoformat(deadline)+timedelta(minutes=10))
    scheduler['status']='RAN' if ran else 'MISSED' if late else 'DUE'
    scheduler['heartbeat_fresh']=bool(row and now-datetime.fromisoformat(row['heartbeat_at'])<timedelta(minutes=5))
    payload=current['payload'] if current else {}
    status='ERROR' if not current else 'CURRENT'
    series=[dict(s) for s in payload.get('input_series',[])]
    from .refresh import SERIES
    required=set(SERIES[market])
    available={item['series'] for item in series}
    recent_success=bool(job and job['status']=='SUCCESS' and job['expected_date']==date)
    for item in series:
        item['expected_observation_date']=series_expected(market,item['series'],date)
        item['status']='CURRENT' if date and item['latest_observation_date']>=item['expected_observation_date'] and item['retrieved_at'] else 'DELAYED' if recent_success and item.get('retrieved_at') else 'STALE'
    if current:
        if not required.issubset(available) or not date or payload.get('source_provenance')!='provider-validated' or current['observation_date']<min(series_expected(market,name,date) for name in required) or any(s['status']!='CURRENT' for s in series):
            status='STALE'
        if job and job['status']=='ERROR':
            outcomes=(job.get('report') or {}).get('series',[])
            success=sum(s['status']!='ERROR' for s in outcomes)
            status='PARTIAL' if 0<success<len(outcomes) else 'ERROR'
        elif status=='STALE' and recent_success and required.issubset(available) and payload.get('source_provenance')=='provider-validated':
            status='DELAYED'
    report=job.get('report') if job else None
    attempted=(report or {}).get('series') or (report or {}).get('input_series') or []
    model_available = bool(current and isinstance(payload.get('risk_score_10d'), (int, float)) and
                           math.isfinite(payload['risk_score_10d']) and 0 <= payload['risk_score_10d'] <= 100 and
                           isinstance(payload.get('market_stress_index'), (int, float)) and math.isfinite(payload['market_stress_index']))
    return {'market':market,'status':status,'is_current':status=='CURRENT','model_available':model_available,
            'last_known_good_date':current['observation_date'] if current else None,
            'published_at':current['published_at'] if current else None,
            'snapshot_id':current['snapshot_id'] if current else None,
            'expected_observation_date':date,'input_series':series,'latest_attempt_series':attempted,
            'last_job':{k:job[k] for k in ['job_id','started_at','finished_at','status','error_type','snapshot_published']} if job else None,
            'scheduler':scheduler,'message':'Validated current market snapshot.' if status=='CURRENT' else 'Some indicators are awaiting updates. Showing the last validated observation.' if status=='DELAYED' and model_available else 'Showing the last validated observation; check data freshness.' if model_available else 'Current market risk unavailable. No validated snapshot.'}


def current_payload(market):
    current=snapshot(market)
    if not current:
        from fastapi import HTTPException
        raise HTTPException(503,detail={'message':'Current market risk unavailable. No validated snapshot.','data_health':health(market)})
    payload={key:value for key,value in current['payload'].items() if key!='artifact_directory'}
    payload.setdefault('market_observation_date',payload['last_updated'])
    payload.setdefault('data_retrieved_at',max((s['retrieved_at'] for s in payload.get('input_series',[]) if s.get('retrieved_at')),default=None))
    payload.setdefault('model_inference_at',None)
    return {**payload,'data_health':health(market,current=current)}
