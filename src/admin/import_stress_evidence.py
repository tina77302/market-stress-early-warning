"""Validate reviewed analytics evidence against the listing master; publish atomically.

No network calls, portfolio writes, model changes, or inferred classifications.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from datetime import datetime, timezone
from src.config import DATA_DIR
from src.paper import stress_analytics as analytics
from src.paper.symbol_master import path as master_path


def publish(source, market):
    bundle = json.loads(Path(source).read_bytes())
    if bundle.get('market') != market or bundle.get('schema_version') != 1:
        raise ValueError('Evidence market/schema mismatch')
    with sqlite3.connect(master_path().resolve().as_uri()+'?mode=ro', uri=True) as db:
        for item in bundle['instruments']:
            row = db.execute('SELECT currency,active,security_type FROM securities WHERE market=? AND symbol=?', (market,item['symbol'])).fetchone()
            if not row or not row[1] or row[0] != item['currency']:
                raise ValueError('Instrument identity is not in the active listing master')
            if item['kind'] in ('sector', 'industry') and row[2] != 'ETF':
                raise ValueError('Sector/industry proxy must be a reviewed listed ETF')
            if item.get('provenance'):
                from src.paper.evidence_pipeline import identity,verify_receipts
                if item['provenance']['identity']!=identity(market,item['symbol']):
                    raise ValueError('Receipt identity differs from Symbol Master')
                verify_receipts(item,market)
            if not item.get('source','').startswith('https://') or not item.get('reviewed_at'):
                raise ValueError('Official/provider source URL and review date required')
            reviewed = datetime.fromisoformat(item['reviewed_at'])
            if reviewed.tzinfo is None or reviewed > datetime.now(timezone.utc):
                raise ValueError('Invalid review timestamp')
            item['identity_verified'] = True
    # Validate with the same runtime parser before publishing the live bundle.
    target = DATA_DIR/'paper/stress-evidence'/f'{market}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(bundle, allow_nan=False, sort_keys=True).encode()
    # Validate without mutating module globals or touching the live bundle.
    analytics.parse_evidence(encoded, market)
    # Retain content-addressed bundles for exact historical reproduction.
    import hashlib
    archive=target.parent/'archive'/market
    archive.mkdir(parents=True,exist_ok=True,mode=0o700)
    for content in ([target.read_bytes()] if target.exists() else [])+[encoded]:
        saved=archive/(hashlib.sha256(content).hexdigest()+'.json')
        if not saved.exists():
            with saved.open('xb') as handle:
                handle.write(content);handle.flush();os.fsync(handle.fileno())
            saved.chmod(0o600)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.evidence-')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'market': market, 'instruments': len(bundle['instruments']), 'status': 'PUBLISHED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--market', required=True, choices=['us','korea'])
    parser.add_argument('--file', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(publish(args.file, args.market)))
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error):
        parser.exit(1, 'Evidence rejected; previous analytics evidence preserved.\n')


if __name__ == '__main__':
    main()
