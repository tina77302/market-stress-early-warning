"""Collect the bounded reviewed research universe; no accounts, model or AWS writes."""
import argparse
import json
from src.paper.evidence_pipeline import collect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--market',choices=['us','korea','both'],required=True)
    args=parser.parse_args()
    failed=False
    for market in (['us','korea'] if args.market=='both' else [args.market]):
        try:
            print(json.dumps(collect(market),ensure_ascii=False),flush=True)
        except Exception as error:
            failed=True
            # Provider exceptions may include URLs/cookies. Never emit their bodies.
            print(json.dumps({'market':market,'status':'REJECTED','error_type':type(error).__name__,
                              'message':'Evidence unavailable or failed review; last installed evidence preserved.'}),flush=True)
    return int(failed)


if __name__=='__main__':
    raise SystemExit(main())
