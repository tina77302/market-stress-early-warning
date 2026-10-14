import argparse
import json
import time
from .refresh import refresh
from .service import health
from .store import history
from .scheduler import tick, SchedulerLease

parser=argparse.ArgumentParser(description='Validated market-data operations; never trains models.')
parser.add_argument('command',choices=['refresh','adopt-local','health','history','schedule'])
parser.add_argument('--market',choices=['us','korea','both'],default='both')
parser.add_argument('--once',action='store_true',help='Run one scheduler catch-up tick and exit.')
args=parser.parse_args()
markets=['us','korea'] if args.market=='both' else [args.market]
if args.command=='schedule':
    with SchedulerLease():
        while True:
            print(json.dumps(tick(),indent=2,ensure_ascii=False),flush=True)
            if args.once:break
            time.sleep(60)
else:
    reports=[]
    for market in markets:
        if args.command in ['refresh','adopt-local']:
            reports.append(refresh(market,adopt_local=args.command=='adopt-local'))
        elif args.command=='health':reports.append(health(market))
        else:reports.extend(history(market))
    print(json.dumps(reports,indent=2,ensure_ascii=False))
    if args.command in ['refresh','adopt-local'] and any(r['status']=='ERROR' for r in reports):
        raise SystemExit(1)
