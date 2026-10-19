"""Read-only publication ledger. Historical OOS endpoints remain separate."""
from typing import Literal
from fastapi import APIRouter, Query
from src.operations import monitoring

router = APIRouter(prefix='/api/monitoring', tags=['monitoring'])
Market = Literal['us', 'korea']
RecordType = Literal['LIVE', 'RETROSPECTIVE']


@router.get('/latest')
def latest(market: Market, record_type: RecordType = 'LIVE'):
    return monitoring.latest(market, record_type=record_type)


@router.get('/history')
def history(market: Market, record_type: Literal['LIVE', 'RETROSPECTIVE', 'ALL'] = 'LIVE',
            limit: int = Query(50, ge=1, le=500), before_sequence: int | None = Query(None, ge=1)):
    return monitoring.history(market, record_type=record_type, limit=limit, before_sequence=before_sequence)
