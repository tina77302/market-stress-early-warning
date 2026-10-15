"""Optional timestamped primary adapter; disabled until licensed/configured.

An API key is not evidence of external-display rights. Operators must confirm
those rights before enabling this path. No new service is enabled by default.
"""
import os
from decimal import Decimal
from datetime import datetime,timezone
from uuid import uuid4
import requests
from fastapi import HTTPException

SOURCE='Twelve Data / USD/KRW'


def fetch_observation():
    if (os.getenv('PAPER_FX_PRIMARY_PROVIDER')!='twelve_data' or
            os.getenv('PAPER_FX_PRIMARY_LICENSE_CONFIRMED','false').lower()!='true' or
            not os.getenv('TWELVE_DATA_API_KEY')):
        raise HTTPException(503,'Higher-frequency FX source is not configured with confirmed display rights.')
    try:
        result=requests.get('https://api.twelvedata.com/exchange_rate',params={
            'symbol':'USD/KRW','apikey':os.environ['TWELVE_DATA_API_KEY']},timeout=8)
        result.raise_for_status();data=result.json(parse_float=Decimal)
        if data['symbol']!='USD/KRW' or type(data['timestamp']) is not int:raise ValueError()
        observed=datetime.fromtimestamp(data['timestamp'],timezone.utc)
        return {'id':str(uuid4()),'source':SOURCE,'rate':str(data['rate']),
                'observation_date':observed.date().isoformat(),'observation_timestamp':observed.isoformat(),
                'retrieved_at':datetime.now(timezone.utc).isoformat()}
    except Exception:
        # HTTP exception text can contain API credentials. Never log or expose it.
        raise HTTPException(503,'Higher-frequency USD/KRW source unavailable.') from None
