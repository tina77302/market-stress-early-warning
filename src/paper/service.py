"""Portfolio accounting in integer minor currency units; no FX or brokerage integration."""
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException

from . import prices
from .store import database, factor


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def money(value, market):
    return value / factor(market)


def serialize_order(row):
    return {**{key: row[key] for key in ['id', 'market', 'symbol', 'side', 'quantity', 'executed_at', 'price_observed_at', 'request_key']},
            'execution_price': money(row['execution_price'], row['market']), 'realized_pnl': money(row['realized_pnl'], row['market']), 'simulated': True}


def execute_order(user_id, order):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT * FROM orders WHERE user_id=? AND request_key=?', (user_id, str(order.request_key))).fetchone()
        if previous:
            if (previous['market'], previous['symbol'], previous['side'], previous['quantity'], previous['quote_id']) != (order.market, order.symbol, order.side, order.quantity, str(order.quote_id)):
                raise HTTPException(409, 'This request key belongs to a different order.')
            return serialize_order(previous)
        quote = db.execute('SELECT * FROM quotes WHERE id=? AND user_id=? AND market=? AND symbol=?', (str(order.quote_id), user_id, order.market, order.symbol)).fetchone()
        if not quote or quote['expires_at'] <= int(time.time()):
            raise HTTPException(409, 'Quote expired or unavailable. Request a new price and review the order again.')
        prices.ensure_fresh(prices.Price(quote['price'], quote['previous_close'], quote['observed_at'], quote['fetched_at']))
        portfolio = db.execute('SELECT * FROM portfolios WHERE user_id=? AND market=?', (user_id, order.market)).fetchone()
        if not portfolio:
            raise HTTPException(404, 'Portfolio unavailable.')
        position = db.execute('SELECT * FROM positions WHERE portfolio_id=? AND symbol=?', (portfolio['id'], order.symbol)).fetchone()
        quantity = position['quantity'] if position else 0
        basis = position['cost_basis'] if position else 0
        total = quote['price'] * order.quantity
        realized = 0
        if order.side == 'BUY':
            if total > portfolio['cash']:
                raise HTTPException(409, 'Insufficient virtual cash.')
            cash = portfolio['cash'] - total
            quantity += order.quantity
            basis += total
        else:
            if order.quantity > quantity:
                raise HTTPException(409, 'Insufficient shares. Short selling is disabled.')
            allocated = basis if order.quantity == quantity else int((Decimal(basis) * order.quantity / quantity).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            realized = total - allocated
            cash = portfolio['cash'] + total
            quantity -= order.quantity
            basis -= allocated
        db.execute('UPDATE portfolios SET revision=revision+1,cash=?,realized_pnl=realized_pnl+? WHERE id=? AND user_id=?', (cash, realized, portfolio['id'], user_id))
        if quantity:
            db.execute('INSERT INTO positions VALUES (?,?,?,?) ON CONFLICT(portfolio_id,symbol) DO UPDATE SET quantity=excluded.quantity,cost_basis=excluded.cost_basis', (portfolio['id'], order.symbol, quantity, basis))
        else:
            db.execute('DELETE FROM positions WHERE portfolio_id=? AND symbol=?', (portfolio['id'], order.symbol))
        db.execute('INSERT INTO orders (portfolio_id,user_id,request_key,market,symbol,side,quantity,execution_price,realized_pnl,quote_id,price_observed_at,executed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (portfolio['id'], user_id, str(order.request_key), order.market, order.symbol, order.side, order.quantity, quote['price'], realized, str(order.quote_id), quote['observed_at'], now_iso()))
        result = db.execute('SELECT * FROM orders WHERE user_id=? AND request_key=?', (user_id, str(order.request_key))).fetchone()
        db.commit()
        return serialize_order(result)


def portfolio_summary(user_id, market):
    with database() as db:
        db.execute('BEGIN')
        portfolio = db.execute('SELECT * FROM portfolios WHERE user_id=? AND market=?', (user_id, market)).fetchone()
        if not portfolio:
            raise HTTPException(404, 'Portfolio unavailable.')
        rows = db.execute('SELECT * FROM positions WHERE portfolio_id=?', (portfolio['id'],)).fetchall()
        today = datetime.now(timezone.utc).date().isoformat()
        baseline = db.execute('SELECT value FROM snapshots WHERE portfolio_id=? AND observed_at<? ORDER BY observed_at DESC LIMIT 1', (portfolio['id'], today)).fetchone()
    positions = []
    complete = True
    total = portfolio['cash']
    unrealized = 0
    for row in rows:
        try:
            price = prices.fetch_price(market, row['symbol'])
            prices.ensure_fresh(price)
            value = price.minor * row['quantity']
            pnl = value - row['cost_basis']
            total += value
            unrealized += pnl
            quote_info = {'latest_price': money(price.minor, market), 'price_observed_at': price.observed_at, 'market_value': money(value, market), 'unrealized_pnl': money(pnl, market), 'return_pct': pnl / row['cost_basis'] * 100 if row['cost_basis'] else None, 'price_source': price.source}
        except HTTPException:
            complete = False
            quote_info = {'latest_price': None, 'price_observed_at': None, 'market_value': None, 'unrealized_pnl': None, 'return_pct': None, 'price_source': 'Unavailable or stale; valuation incomplete'}
        positions.append({'symbol': row['symbol'], 'market': market, 'quantity': row['quantity'], 'average_cost': money(row['cost_basis'], market) / row['quantity'], 'cost_basis': money(row['cost_basis'], market), **quote_info})
    result = {'market': market, 'currency': portfolio['currency'], 'starting_cash': money(portfolio['starting_cash'], market), 'cash': money(portfolio['cash'], market), 'portfolio_value': money(total, market) if complete else None, 'realized_pnl': money(portfolio['realized_pnl'], market), 'unrealized_pnl': money(unrealized, market) if complete else None, 'total_return_pct': (total - portfolio['starting_cash']) / portfolio['starting_cash'] * 100 if complete else None, 'today_pnl': money(total - baseline['value'], market) if complete and baseline else None, 'today_pnl_note': 'Change since the last recorded valuation before today (UTC), using completed daily-close marks; unavailable until a prior-day observation exists.', 'valuation_complete': complete, 'positions': positions, 'allocation': {'market': market, 'cash': money(portfolio['cash'], market), 'securities': money(total - portfolio['cash'], market) if complete else None}, 'simulated': True}
    if complete:
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT revision FROM portfolios WHERE id=? AND user_id=?', (portfolio['id'], user_id)).fetchone()
            if current['revision'] != portfolio['revision']:
                raise HTTPException(409, 'Portfolio changed during valuation. Refresh to obtain a consistent snapshot.')
            # Only actual observed valuations are recorded, never backfilled or interpolated.
            db.execute('INSERT OR IGNORE INTO snapshots (portfolio_id,observed_at,value,cash) VALUES (?,?,?,?)', (portfolio['id'], now_iso(), total, portfolio['cash']))
            db.commit()
    return result
