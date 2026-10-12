"""Durable alert outbox; future workers can fan out to all role=admin accounts.

No network notifications or credentials. Delivery workers must mark delivered_at
only after successful delivery and deduplicate by outbox id.
"""
import json
from .store import database, utcnow


def emit(market, action, payload, job_id=None):
    with database() as db:
        db.execute('INSERT INTO alerts (market,job_id,action,created_at,payload) VALUES (?,?,?,?,?)',
                   (market, job_id, action, utcnow(), json.dumps(payload, allow_nan=False)))
