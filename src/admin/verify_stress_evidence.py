"""Real local examples in a newly created disposable DB, never existing users."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import secrets
import tempfile
from uuid import uuid4


def run(operations_dir):
    if os.getenv('APP_ENV','development') in ('staging','production'):
        raise ValueError('Local research examples only')
    operations_dir=Path(operations_dir).resolve()
    if not (operations_dir/'refresh.sqlite3').is_file():raise ValueError('Isolated validated snapshots required')
    from src.config import DATA_DIR
    if operations_dir==(DATA_DIR/'operations').resolve():raise ValueError('Use a separate operations directory')
    directory=Path(tempfile.mkdtemp(prefix='stress-evidence-example-'))
    os.environ.update(PAPER_DB_PATH=str(directory/'workspace.sqlite3'),MARKET_OPERATIONS_DIR=str(operations_dir),
                      PAPER_SESSION_SECRET=secrets.token_urlsafe(48),PAPER_COOKIE_SECURE='false',PAPER_ALLOWED_ORIGINS='http://testserver')
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.paper.accounts import provision_username_account
    from src.paper.router import router
    from src.paper.evidence_pipeline import root
    from src.operations.service import current_payload
    for market in ('us','korea'):
        if not current_payload(market)['data_health']['is_current']:
            raise ValueError('Fresh validated market snapshots required; no freshness override')
    app=FastAPI();app.include_router(router)
    output=[]
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8]
    archive=root()/'examples'/run_id;archive.mkdir(parents=True,mode=0o700)
    def checked(response):
        if response.status_code not in (200,201):raise ValueError('Example API rejected request; no fabricated substitute')
        return response.json()
    def stats(data):
        return {key:value for key,value in data.items() if key in ('status','n','median_pct','q25_pct','q75_pct','downside_q10_pct','negative_frequency','dispersion_iqr_pct')}
    for market,symbol in [('us','NVDA'),('korea','000660.KS')]:
        username='evidence_'+market;password=secrets.token_urlsafe(24)
        provision_username_account(username,password)
        client=TestClient(app)
        checked(client.post('/api/auth/login',json={'username':username,'password':password}))
        csrf=checked(client.get('/api/auth/me'))['csrf_token']
        q=checked(client.get('/api/paper/quote',params={'market':market,'symbol':symbol}))
        rate=(q.get('fx') or {}).get('rate')
        if market=='korea' and not rate:raise ValueError('Valid current FX is required for the Korean example')
        quantity=int(10000*(rate if market=='korea' else 1)/q['price'])
        if quantity<1:raise ValueError('Example size cannot buy a share')
        preview=checked(client.get('/api/paper/settlement',params={'quote_id':q['id'],'side':'BUY','quantity':quantity}))
        order=checked(client.post('/api/paper/orders',headers={'x-csrf-token':csrf},json={
            'market':market,'symbol':symbol,'side':'BUY','quantity':quantity,'quote_id':q['id'],'request_key':str(uuid4()),
            **{key:preview[key] for key in ('settlement_id','fx_usd_cents','fx_krw')}}))
        report=checked(client.get('/api/paper/stress-analytics'))
        holding=next(row for row in report['exposure']['holdings'] if row['symbol']==symbol)
        evidence=report['markets'][market];sensitivity=next(row for row in report['sensitivity'] if row['market']==market)
        if not holding['sector'] or not holding['industry'] or report['outlook']['status']!='AVAILABLE':
            raise ValueError('Full evidence chain is unavailable; sample safeguards preserved')
        sector=next(item for item in evidence['sectors'] if item['kind']=='sector')
        industry=next(item for item in evidence['sectors'] if item['kind']=='industry')
        if sector['status']!='AVAILABLE' or industry['status']!='AVAILABLE':raise ValueError('Sector/industry sample is insufficient')
        (archive/f'{market}.json').write_text(json.dumps(report,sort_keys=True,allow_nan=False))
        result={'market':market,'symbol':symbol,'snapshot_date':evidence['observation_date'],'risk_score':evidence['risk_score'],
                'regime':evidence['regime'],'model_sha256':evidence['model_sha256'],'quantity':quantity,
                'execution_price':order['execution_price'],'currency':'USD' if market=='us' else 'KRW','exposure':holding,
                'sector_instrument':sector['symbol'],'sector':stats(sector),'industry_instrument':industry['symbol'],
                'industry':stats(industry),'security':stats(evidence['instruments'][symbol]),
                'evidence_level':sensitivity['evidence'][0]['level'],'outlook':stats(report['outlook']['distribution']),
                'fx':q.get('fx'),'report_archive':str(archive/f'{market}.json')}
        output.append(result)
    result={'status':'VERIFIED_REAL_DATA','scope':'isolated_disposable_accounts','demo_database':str(directory/'workspace.sqlite3'),
            'operations_directory':str(operations_dir),'examples':output}
    (archive/'summary.json').write_text(json.dumps(result,sort_keys=True,allow_nan=False))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operations-dir',required=True,type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(run(args.operations_dir),ensure_ascii=False,allow_nan=False))
    except Exception as error:
        print(json.dumps({'status':'UNAVAILABLE','error_type':type(error).__name__,'message':'Real example incomplete; no model, freshness or sample override applied.'}))
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
