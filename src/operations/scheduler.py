"""Catch-up on every startup/poll, not dependent on a single cron instant."""
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from .calendar import expected, series_expected
from .refresh import refresh, SERIES
from .store import database, snapshot, history, utcnow
from . import alerts

logger=logging.getLogger(__name__)


def tick():
    reports=[]
    for market in ['us','korea']:
        now=datetime.now(timezone.utc)
        try:
            date,deadline=expected(market,now)
            with database() as db:
                db.execute('INSERT INTO scheduler (market,heartbeat_at,expected_date,expected_run_at) VALUES (?,?,?,?) ON CONFLICT(market) DO UPDATE SET heartbeat_at=excluded.heartbeat_at,expected_date=excluded.expected_date,expected_run_at=excluded.expected_run_at',(market,utcnow(),date,deadline))
            current=snapshot(market)
            jobs=history(market,1)
            latest=jobs[0] if jobs else None
            ran=bool(latest and latest['expected_date']==date and latest['trigger']!='adopt-local')
            inputs={s['series']:s for s in current['payload'].get('input_series',[])} if current else {}
            source_due=any(name not in inputs or not inputs[name].get('retrieved_at') or
                           inputs[name].get('latest_observation_date','')<series_expected(market,name,date)
                           for name in SERIES[market])
            common_due=min(series_expected(market,name,date) for name in SERIES[market])
            needs=(not current or current['observation_date']<common_due or source_due or
                   current['payload'].get('source_provenance')!='provider-validated' or not ran or
                   bool(latest and latest['status'] in ['ERROR','RUNNING']))
            recently=bool(latest and latest['trigger']!='adopt-local' and now-datetime.fromisoformat(latest['started_at'])<timedelta(minutes=30))
            if needs and not recently:
                reports.append(refresh(market,trigger='startup-catch-up' if not ran else 'scheduled-retry'))
                if len(history(market,3))>=3 and all(j['status']=='ERROR' for j in history(market,3)):
                    alerts.emit(market,'provider_repeatedly_failing',{'expected_date':date})
        except Exception:
            logger.exception('Market refresh scheduler failed for %s',market)
    return reports


def start():
    lease=SchedulerLease()
    stop=threading.Event()
    def run():
        try:
            while not stop.is_set():
                tick()
                stop.wait(60)
        finally:
            lease.close()
    thread=threading.Thread(target=run,name='market-refresh',daemon=True)
    thread.start()
    return stop


class SchedulerLease:
    """Host-wide ownership on the same persistent volume as market locks."""
    def __init__(self):
        import fcntl
        from .store import root
        root().mkdir(parents=True, exist_ok=True)
        self.handle = open(root() / 'scheduler.lock', 'a')
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            raise RuntimeError('A market scheduler already owns this operations volume.') from None

    def close(self):
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
