import json
import os
import re
import sqlite3
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from . import auth, prices
from .service import execute_order, money, now_iso, portfolio_summary, serialize_order
from .store import database

router = APIRouter(prefix='/api', tags=['Simulated workspace'])
Market = Literal['us', 'korea']


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator('email')
    @classmethod
    def email_address(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address.')
        return value


class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Preserve the email/password request contract; username is an optional alias.
    email: str = Field(min_length=3, max_length=254, validation_alias=AliasChoices('email', 'username'))
    password: str = Field(min_length=8, max_length=128)

    @field_validator('email')
    @classmethod
    def identity(cls, value):
        return value.strip().lower()


class Order(BaseModel):
    model_config = ConfigDict(extra='forbid')
    market: Market
    symbol: str = Field(min_length=1, max_length=16)
    side: Literal['BUY', 'SELL']
    quantity: int = Field(strict=True, gt=0, le=1000000)
    quote_id: UUID
    request_key: UUID
    fx_usd_cents: int | None = Field(default=None, strict=True, ge=0)
    settlement_id: UUID | None = None
    fx_krw: int | None = Field(default=None, strict=True, ge=0)


@router.post('/auth/register', status_code=201)
def register(body: Credentials, request: Request, response: Response):
    auth.check_origin(request)
    auth.secret()
    auth.throttle(request, body.email)
    encoded = auth.password_hash(body.password)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            cursor = db.execute('INSERT INTO users (email,password_hash,created_at) VALUES (?,?,?)', (body.email, encoded, now_iso()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'An account with this email already exists.')
        user_id = cursor.lastrowid
        created = now_iso()
        from .accounts import initialize_portfolio
        initialize_portfolio(db,user_id,created)
        auth.set_session(db, user_id, request, response)
        db.commit()
    return {'user': {'id': user_id, 'email': body.email, 'role': 'user'}, 'simulated': True}


@router.post('/auth/login')
def login(body: LoginCredentials, request: Request, response: Response):
    auth.check_origin(request)
    auth.throttle(request, body.email)
    with database() as db:
        user = db.execute('SELECT * FROM users WHERE email=? OR username=? COLLATE NOCASE', (body.email, body.email)).fetchone()
        # Spend comparable hashing work for unknown users too.
        encoded = user['password_hash'] if user else auth.password_hash('unregistered-user-placeholder')
        valid = auth.password_matches(body.password, encoded)
        if not user or not valid:
            raise HTTPException(401, 'Invalid email, user ID or password.')
        auth.set_session(db, user['id'], request, response)
        db.commit()
    return {'user': {'id': user['id'], 'email': user['email'], 'username': user['username'], 'role': user['role']}}


@router.get('/auth/me')
def me(request: Request, response: Response, user=Depends(auth.current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return {'user': user, 'csrf_token': auth.csrf_token(request)}


@router.post('/auth/logout')
def logout(request: Request, response: Response, user=Depends(auth.protected_write)):
    with database() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (auth.digest(request.cookies[auth.COOKIE]),))
        db.commit()
    response.delete_cookie(auth.COOKIE, path='/', secure=auth.secure_cookie(), httponly=True, samesite='lax')
    return {'logged_out': True}


@router.get('/paper/securities')
def securities(market: Market, q: str = Query('', max_length=100), limit: int = Query(20, ge=1, le=30), user=Depends(auth.current_user)):
    from .symbol_master import search
    return search(market,q,limit)


@router.get('/paper/quote')
def quote(market: Market, symbol: str = Query(max_length=16), user=Depends(auth.current_user)):
    symbol = symbol.strip().upper()
    item = prices.security(market,symbol)
    symbol = item['symbol']
    price = prices.fetch_price(market, symbol)
    prices.ensure_fresh(price)
    quote_id = str(uuid4())
    expires = int(time.time()) + 120
    fx_row=None
    try:
        from . import fx
        fx_row=fx.latest()
    except HTTPException:
        pass
    with database() as db:
        db.execute('DELETE FROM quotes WHERE expires_at<?', (int(time.time()) - 86400,))
        db.execute('INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)', (quote_id, user['id'], market, symbol, price.minor, price.previous_minor, price.observed_at, price.fetched_at, expires, price.source))
        from .costs import snapshot
        snapshot(db,quote_id,item)
        if fx_row:
            db.execute('INSERT INTO paper_quote_fx VALUES (?,?)',(quote_id,fx_row['id']))
        db.commit()
    return {'fx':fx.public(fx_row) if fx_row else None,'id': quote_id, 'market': market, 'symbol': symbol, 'price': money(price.minor, market), 'currency': 'USD' if market == 'us' else 'KRW', 'observed_at': price.observed_at, 'source': price.source, 'expires_at': expires, 'price_kind': 'completed_daily_close', 'simulated': True}


@router.get('/paper/portfolio')
def portfolio(market: Market, response: Response, user=Depends(auth.current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return portfolio_summary(user['id'], market)


@router.get('/paper/positions')
def positions(market: Market, response: Response, user=Depends(auth.current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return {'data': portfolio_summary(user['id'], market)['positions']}


@router.get('/paper/orders')
def orders(market: Market, response: Response, user=Depends(auth.current_user)):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        rows = db.execute('SELECT o.*,c.detail_json FROM orders o LEFT JOIN paper_order_costs c ON c.order_id=o.id WHERE o.user_id=? AND o.market=? ORDER BY o.id DESC LIMIT 200', (user['id'], market)).fetchall()
    return {'data': [serialize_order(row,json.loads(row['detail_json']) if row['detail_json'] else None) for row in rows]}


@router.post('/paper/orders', status_code=201)
def submit(body: Order, user=Depends(auth.protected_write)):
    symbol = prices.security(body.market, body.symbol)['symbol']
    return execute_order(user['id'], body.model_copy(update={'symbol': symbol}))


@router.get('/paper/performance')
def performance(market: Market, response: Response, user=Depends(auth.current_user)):
    response.headers['Cache-Control'] = 'no-store'
    with database() as db:
        rows = db.execute('SELECT s.observed_at,s.value,s.cash FROM snapshots s JOIN portfolios p ON p.id=s.portfolio_id WHERE p.user_id=? AND p.market=? ORDER BY s.observed_at DESC LIMIT 500', (user['id'], market)).fetchall()
    return {'data': [{'observed_at': row['observed_at'], 'value': money(row['value'], market), 'cash': money(row['cash'], market)} for row in reversed(rows)], 'currency': 'USD' if market == 'us' else 'KRW', 'note': 'Actual recorded valuations since account creation; no backfilled performance.'}


@router.get('/paper/investment')
def investment_summary(response:Response,user=Depends(auth.current_user)):
    response.headers['Cache-Control']='no-store'
    from .investment import summary
    return summary(user['id'])


@router.get('/paper/settlement')
def settlement(quote_id:UUID,side:Literal['BUY','SELL'],quantity:int=Query(ge=1,le=1000000),user=Depends(auth.current_user)):
    from .investment import preview
    return preview(user['id'],str(quote_id),side,quantity)


@router.get('/paper/fx-ledger')
def fx_ledger(user=Depends(auth.current_user)):
    with database() as db:
        rows=db.execute('SELECT l.*,r.rate,r.source,r.observation_date,r.retrieved_at FROM paper_fx_ledger l JOIN paper_fx_rates r ON r.id=l.rate_id WHERE l.user_id=? ORDER BY l.order_id DESC LIMIT 200',(user['id'],)).fetchall()
        return {'data':[dict(row) for row in rows]}


@router.get('/paper/fx')
def latest_fx(user=Depends(auth.current_user)):
    from . import fx
    return {'fx':fx.public(fx.latest())}


@router.get('/paper/stress-analytics')
def stress_analytics(response: Response, user=Depends(auth.current_user)):
    response.headers['Cache-Control'] = 'no-store'
    from .stress_analytics import current_report
    return current_report(user['id'])
