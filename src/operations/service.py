"""Shared validated snapshots for every user; no subscription inputs."""
from datetime import datetime, timezone, timedelta
from .calendar import expected
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
    for item in series:
        item['status']='CURRENT' if date and item['latest_observation_date']>=date and item['retrieved_at'] else 'STALE'
    if current:
        if not date or payload.get('source_provenance')!='provider-validated' or current['observation_date']<date or any(s['status']!='CURRENT' for s in series):
            status='STALE'
        if job and job['status']=='ERROR':
            outcomes=(job.get('report') or {}).get('series',[])
            success=sum(s['status']!='ERROR' for s in outcomes)
            status='PARTIAL' if 0<success<len(outcomes) else 'ERROR'
        elif status=='STALE' and job and job['status']=='SUCCESS' and payload.get('source_provenance')=='provider-validated':
            status='DELAYED'
    report=job.get('report') if job else None
    attempted=(report or {}).get('series') or (report or {}).get('input_series') or []
    return {'market':market,'status':status,'is_current':status=='CURRENT',
            'last_known_good_date':current['observation_date'] if current else None,
            'published_at':current['published_at'] if current else None,
            'snapshot_id':current['snapshot_id'] if current else None,
            'expected_observation_date':date,'input_series':series,'latest_attempt_series':attempted,
            'last_job':{k:job[k] for k in ['job_id','started_at','finished_at','status','error_type','error_message','snapshot_published']} if job else None,
            'scheduler':scheduler,'message':'Validated current market snapshot.' if status=='CURRENT' else 'Current market risk unavailable. Showing the last known good observation.' if current else 'Current market risk unavailable. No validated snapshot.'}


def current_payload(market):
    current=snapshot(market)
    if not current:
        from fastapi import HTTPException
        raise HTTPException(503,detail={'message':'Current market risk unavailable. No validated snapshot.','data_health':health(market)})
    payload={key:value for key,value in current['payload'].items() if key!='artifact_directory'}
    return {**payload,'data_health':health(market,current=current)}
