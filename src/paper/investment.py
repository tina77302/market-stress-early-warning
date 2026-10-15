"""One initial USD contribution, two native-currency subledgers, auditable simulated FX."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
import time
import json
from uuid import uuid4
from fastapi import HTTPException
from . import fx, prices, costs
from .store import database


def require_account(db,user_id):
    account=db.execute('SELECT * FROM investment_accounts WHERE user_id=?',(user_id,)).fetchone()
    if not account:
        raise HTTPException(409,'Unified portfolio is unavailable. Contact support; no balances were changed.')
    return account


def conversion(db,user_id,market,total,side,quote_id,spread_bps='0'):
    rows={r['market']:r for r in db.execute('SELECT * FROM portfolios WHERE user_id=?',(user_id,))}
    if not {'us','korea'}<=rows.keys():
        raise HTTPException(409,'Currency balances unavailable.')
    deficit=max(0,total-rows[market]['cash']) if side=='BUY' else 0
    rate_row=db.execute('SELECT r.* FROM paper_fx_rates r JOIN paper_quote_fx q ON q.rate_id=r.id WHERE q.quote_id=?',(quote_id,)).fetchone()
    rate_row=fx.enrich(db,rate_row)
    rate=None
    if rate_row:
        try:rate=fx.validate(rate_row)
        except HTTPException:
            if deficit or market=='korea':raise
    if (deficit or market=='korea') and rate is None:
        raise HTTPException(503,'Validated USD/KRW FX is required to cover the settlement currency shortfall. Refresh the quote.')
    base_value=float((Decimal(total)/100 if market=='us' else Decimal(total)/rate).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)) if market=='us' or rate else None
    if not deficit:
        return {'fx_usd_cents':0,'fx_krw':0,'from_currency':None,'to_currency':None,'rate_id':None,'fx':fx.public(rate_row) if rate else None,'base_order_value_usd':base_value,'fx_spread_bps':'0','configured_fx_spread_bps':str(spread_bps),'effective_fx_rate':None,'fx_cost_usd_exact':'0'}
    spread=Decimal(str(spread_bps))/10000
    effective=rate*(1-spread) if market=='korea' else rate*(1+spread)
    if market=='korea':
        usd=int((Decimal(deficit)*100/effective).to_integral_value(rounding=ROUND_CEILING))
        krw=int((Decimal(usd)*effective/100).to_integral_value(rounding=ROUND_FLOOR))
        sufficient=usd<=rows['us']['cash']
        source,target='USD','KRW'
    else:
        krw=int((Decimal(deficit)*effective/100).to_integral_value(rounding=ROUND_CEILING))
        usd=int((Decimal(krw)*100/effective).to_integral_value(rounding=ROUND_FLOOR))
        sufficient=krw<=rows['korea']['cash']
        source,target='KRW','USD'
    if not sufficient:
        raise HTTPException(409,'Insufficient virtual cash across USD and KRW balances.')
    fx_cost=Decimal(usd)/100-Decimal(krw)/rate if source=='USD' else Decimal(krw)/rate-Decimal(usd)/100
    return {'fx_spread_bps':str(spread_bps),'effective_fx_rate':str(effective),'fx_cost_usd_exact':str(fx_cost),'fx_usd_cents':usd,'fx_krw':krw,'from_currency':source,'to_currency':target,'rate_id':rate_row['id'],'fx':fx.public(rate_row),'base_order_value_usd':base_value}


def settlement_plan(db,user_id,quote,side,quantity):
    metadata,policy=costs.quote_policy(db,quote)
    detail=costs.breakdown(policy,quote['market'],metadata['security_type'],metadata['exchange'],side,quote['price'],quantity,metadata['trade_date'])
    if side=='SELL':
        position=db.execute('SELECT p.quantity FROM positions p JOIN portfolios b ON b.id=p.portfolio_id WHERE b.user_id=? AND b.market=? AND p.symbol=?',(user_id,quote['market'],quote['symbol'])).fetchone()
        if not position or quantity>position['quantity']:raise HTTPException(409,'Insufficient shares. Short selling is disabled.')
    plan=conversion(db,user_id,quote['market'],detail['net_minor'],side,quote['id'],policy['fx_spread_bps'])
    balances={r['market']:r['cash'] for r in db.execute('SELECT market,cash FROM portfolios WHERE user_id=?',(user_id,))}
    if plan['from_currency']:
        balances['us']+=(-plan['fx_usd_cents'] if plan['from_currency']=='USD' else plan['fx_usd_cents'])
        balances['korea']+=(plan['fx_krw'] if plan['to_currency']=='KRW' else -plan['fx_krw'])
    balances[quote['market']]+= -detail['net_minor'] if side=='BUY' else detail['net_minor']
    if min(balances.values())<0:raise HTTPException(409,'Insufficient virtual cash.')
    scale=100 if quote['market']=='us' else 1
    reference=Decimal(plan['fx']['rate_exact']) if plan['fx'] else None
    usd_equivalent=(Decimal(detail['net_minor'])/100 if quote['market']=='us' else Decimal(detail['net_minor'])/reference) if quote['market']=='us' or reference else None
    estimated_usd=(usd_equivalent+Decimal(plan['fx_cost_usd_exact'])).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) if usd_equivalent is not None else None
    return {**plan,'market':quote['market'],'symbol':quote['symbol'],'quote_id':quote['id'],'quantity':quantity,'side':side,
            'currency':'USD' if quote['market']=='us' else 'KRW','reference_price':quote['price']/scale,
            'estimated_total_usd':float(estimated_usd) if estimated_usd is not None else None,'actual_usd_conversion_debit':plan['fx_usd_cents']/100 if plan['from_currency']=='USD' else 0,
            'native_order_value':detail['gross_minor']/scale,'costs':detail,'total_cash_effect':detail['net_minor']/scale,
            'remaining_cash':{'USD':balances['us']/100,'KRW':balances['korea']},'cash_after_minor':balances,
            'price_semantics':'validated_completed_daily_close','simulated_cost_assumptions':True}


def preview(user_id,quote_id,side,quantity):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_account(db,user_id)
        quote=db.execute('SELECT * FROM quotes WHERE id=? AND user_id=?',(quote_id,user_id)).fetchone()
        if not quote or quote['expires_at']<=int(time.time()):
            raise HTTPException(409,'Quote expired or unavailable. Request a new price and review the order again.')
        prices.ensure_fresh(prices.Price(quote['price'],quote['previous_close'],quote['observed_at'],quote['fetched_at']))
        plan=settlement_plan(db,user_id,quote,side,quantity)
        token=str(uuid4())
        db.execute('INSERT INTO paper_order_previews VALUES (?,?,?,?,?,?,?)',(token,user_id,quote_id,side,quantity,quote['expires_at'],costs.canonical(plan)))
        db.commit()
        return {**plan,'settlement_id':token}


def approved_plan(db,user_id,quote,order):
    saved=db.execute('SELECT * FROM paper_order_previews WHERE id=? AND user_id=? AND quote_id=? AND side=? AND quantity=?',(str(order.settlement_id),user_id,quote['id'],order.side,order.quantity)).fetchone()
    if not saved or saved['expires_at']<=int(time.time()):
        raise HTTPException(409,'Review the complete current order costs before submitting.')
    plan=settlement_plan(db,user_id,quote,order.side,order.quantity)
    if costs.canonical(plan)!=saved['plan_json']:
        raise HTTPException(409,'Order costs or cash balances changed. Review the order again.')
    return plan


def summary(user_id):
    from .service import portfolio_summary, now_iso
    with database() as db:
        account=dict(require_account(db,user_id))
        revisions={r['market']:r['revision'] for r in db.execute('SELECT market,revision FROM portfolios WHERE user_id=?',(user_id,))}
    books={market:portfolio_summary(user_id,market) for market in ['us','korea']}
    rate_row=None;rate=None;fx_error=None
    try:
        rate_row=fx.latest();rate=fx.validate(rate_row)
    except HTTPException as error:
        fx_error=error.detail
    krw=books['korea']['portfolio_value_minor']
    complete=all(b['valuation_complete'] for b in books.values()) and (krw==0 or rate is not None)
    def usd_cents(usd,krw):
        return int((Decimal(usd)+(Decimal(krw)*100/rate if krw else 0)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    value=usd_cents(books['us']['portfolio_value_minor'],krw) if complete else None
    cash=usd_cents(books['us']['cash_minor'],books['korea']['cash_minor']) if not books['korea']['cash'] or rate else None
    invested=(value-cash) if value is not None and cash is not None else None
    timestamp=now_iso()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        current={r['market']:r['revision'] for r in db.execute('SELECT market,revision FROM portfolios WHERE user_id=?',(user_id,))}
        if current!=revisions:
            raise HTTPException(409,'Portfolio changed during valuation. Refresh to obtain a consistent snapshot.')
        if value is not None:
            db.execute('INSERT INTO investment_snapshots (user_id,observed_at,value_cents,cash_cents,rate_id) VALUES (?,?,?,?,?)',(user_id,timestamp,value,cash,rate_row['id'] if rate_row else None))
        from .fx_performance import performance
        attribution=performance(db,user_id,books,rate_row,(value-account['initial_usd_cents'])/100 if value is not None else None)
        history=db.execute('SELECT * FROM investment_snapshots WHERE user_id=? ORDER BY id DESC LIMIT 500',(user_id,)).fetchall()
        charges=db.execute('SELECT * FROM paper_order_costs WHERE user_id=? ORDER BY order_id',(user_id,)).fetchall()
        ledger=db.execute('SELECT l.*,r.rate,r.source,r.observation_date,r.retrieved_at,o.symbol,o.market,o.execution_price,o.executed_at FROM paper_fx_ledger l JOIN paper_fx_rates r ON r.id=l.rate_id JOIN orders o ON o.id=l.order_id WHERE l.user_id=? ORDER BY l.order_id DESC LIMIT 200',(user_id,)).fetchall()
        db.commit()
    accumulated={'USD':{'commission':0,'tax':0,'regulatory':0},'KRW':{'commission':0,'tax':0,'regulatory':0}}
    fx_total=Decimal(0)
    by_order={}
    for charge in charges:
        currency=charge['currency'];parts=accumulated[currency]
        parts['commission']+=charge['commission_minor'];parts['tax']+=charge['transaction_tax_minor'];parts['regulatory']+=charge['regulatory_fee_minor']
        fx_total+=Decimal(charge['fx_cost_usd']);by_order[charge['order_id']]=json.loads(charge['detail_json'])
    totals={'USD':sum(accumulated['USD'].values())/100,'KRW':sum(accumulated['KRW'].values())}
    def translated(usd_minor,krw_minor):
        return usd_cents(usd_minor,krw_minor)/100 if krw_minor==0 or rate else None
    realized=translated(books['us']['realized_pnl_minor'],books['korea']['realized_pnl_minor'])
    unrealized=translated(books['us']['unrealized_pnl_minor'],books['korea']['unrealized_pnl_minor']) if all(b['valuation_complete'] for b in books.values()) else None
    events=[]
    for row in ledger:
        detail=by_order.get(row['order_id'],{})
        events.append({**dict(row),'effective_rate':detail.get('effective_fx_rate'),'spread_bps':detail.get('fx_spread_bps'),'fx_cost_usd':detail.get('fx_cost_usd_exact')})
    return {'fx_attribution':attribution,'realized_pnl_usd_translated':realized,'unrealized_pnl_usd_translated':unrealized,
            'cumulative_fees':totals,'fee_components_minor':accumulated,'fx_conversion_costs_usd':float(fx_total.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
            'cumulative_fees_usd_translated':translated(sum(accumulated['USD'].values()),sum(accumulated['KRW'].values())),
            'cost_ledger':[{'order_id':row['order_id'],**by_order[row['order_id']]} for row in charges[-200:]],'fx_conversions':events,'base_currency':'USD','initial_capital':account['initial_usd_cents']/100,'portfolio_value':value/100 if value is not None else None,
            'cash':cash/100 if cash is not None else None,'invested_value':invested/100 if invested is not None else None,
            'total_pnl':(value-account['initial_usd_cents'])/100 if value is not None else None,
            'total_return_pct':(value-account['initial_usd_cents'])/account['initial_usd_cents']*100 if value is not None else None,
            'valuation_complete':complete,'observed_at':timestamp,'fx':fx.public(rate_row) if rate_row else None,'fx_error':fx_error,
            'cash_balances':{'USD':books['us']['cash'],'KRW':books['korea']['cash']},'books':books,
            'performance':[{'observed_at':r['observed_at'],'value':r['value_cents']/100,'cash':r['cash_cents']/100} for r in reversed(history)],
            'attribution_note':'Average acquisition basis; native investment effect plus FX translation minus historical costs reconciles to total USD P&L when complete execution evidence is available.',
            'costs_are_simulated':True}
