"""Replay immutable executions for reconciled USD investment/FX attribution.

Average gross acquisition basis and an average USD basis for the KRW cash pool.
Costs are separate expenses; this never changes native execution accounting.
"""
import json
from decimal import Decimal, localcontext

D = Decimal
ZERO = D(0)


class EvidenceUnavailable(ValueError):
    pass


def amount(value):
    value = D(str(value))
    if not value.is_finite():
        raise EvidenceUnavailable('Nonfinite execution evidence')
    return value


def replay(db, user_id, extra=None):
    root = db.execute('SELECT initial_usd_cents FROM investment_accounts WHERE user_id=?', (user_id,)).fetchone()
    if not root:
        raise EvidenceUnavailable('Unified inception missing')
    entries = [(dict(r), json.loads(r['detail_json']) if r['detail_json'] else None) for r in db.execute(
        'SELECT o.*,c.detail_json FROM orders o LEFT JOIN paper_order_costs c ON c.order_id=o.id WHERE o.user_id=? ORDER BY o.id', (user_id,))]
    if extra:
        entries = [entry for entry in entries if entry[0]['id'] != extra[0]['id']] + [extra]
    state = {'usd_cash': D(root[0])/100, 'krw_cash': ZERO, 'cash_usd_basis': ZERO,
             'local_realized': ZERO, 'fx_realized': ZERO, 'fees': ZERO, 'conversion_costs': ZERO,
             'positions': {}, 'trades': []}
    for order, plan in entries:
        if not plan or not plan.get('costs'):
            raise EvidenceUnavailable('Historical transaction cost/FX evidence missing')
        korean = order['market'] == 'korea'
        snapshot = plan.get('fx')
        reference = amount(snapshot.get('rate_exact', snapshot['rate'])) if snapshot else None
        if korean and (reference is None or reference <= 0):
            raise EvidenceUnavailable('Historical Korean execution FX missing')
        if plan.get('from_currency'):
            if reference is None or reference <= 0:
                raise EvidenceUnavailable('Conversion FX missing')
            usd, krw = D(plan['fx_usd_cents'])/100, D(plan['fx_krw'])
            if plan['from_currency'] == 'USD':
                state['usd_cash'] -= usd
                state['krw_cash'] += krw
                state['cash_usd_basis'] += krw/reference
                conversion_cost = usd-krw/reference
            else:
                if not 0 < krw <= state['krw_cash']:
                    raise EvidenceUnavailable('KRW conversion basis missing')
                removed = state['cash_usd_basis']*krw/state['krw_cash']
                state['cash_usd_basis'] -= removed
                state['krw_cash'] -= krw
                state['fx_realized'] += krw/reference-removed
                state['usd_cash'] += usd
                conversion_cost = krw/reference-usd
            state['conversion_costs'] += conversion_cost
        scale = D(1) if korean else D(100)
        rate = reference if korean else D(1)
        gross = D(plan['costs']['gross_minor'])/scale
        fee = D(plan['costs']['total_fees_minor'])/scale
        fee_usd = fee/rate
        net = gross+fee if order['side']=='BUY' else gross-fee
        key = (order['market'],order['symbol'])
        position = state['positions'].setdefault(key, {'quantity':0,'native_basis':ZERO,'usd_basis':ZERO,'buy_fees_usd':ZERO})
        record = {'order_id':order['id'],'market':order['market'],'symbol':order['symbol'],'side':order['side'],
                  'quantity':order['quantity'],'executed_at':order['executed_at'],
                  'execution_price':str(D(order['execution_price'])/scale), 'gross_native':str(gross),
                  'execution_fx':snapshot,'gross_usd':str(gross/rate),'fees_usd':str(fee_usd),
                  'fx_spread_bps':plan.get('fx_spread_bps','0'),'effective_conversion_rate':plan.get('effective_fx_rate'),
                  'usd_converted':str(D(plan.get('fx_usd_cents',0))/100),'krw_converted':plan.get('fx_krw',0),
                  'krw_used_or_received':str(net) if korean else None,
                  'conversion_cost_usd':plan.get('fx_cost_usd_exact','0'), 'available':True}
        if order['side']=='BUY':
            position['quantity'] += order['quantity']
            position['native_basis'] += gross
            position['usd_basis'] += gross/rate
            position['buy_fees_usd'] += fee_usd
        else:
            if not 0 < order['quantity'] <= position['quantity']:
                raise EvidenceUnavailable('Historical purchase basis missing')
            fraction = D(order['quantity'])/position['quantity']
            native_basis = position['native_basis']*fraction
            usd_basis = position['usd_basis']*fraction
            buy_fees = position['buy_fees_usd']*fraction
            local = (gross-native_basis)/rate
            fx = native_basis/rate-usd_basis
            state['local_realized'] += local
            state['fx_realized'] += fx
            record.update(purchase_native_basis=str(native_basis),purchase_usd_basis=str(usd_basis),
                          purchase_fx_basis=str(native_basis/usd_basis) if usd_basis else None,
                          native_realized_stock_pnl=str(gross-native_basis),native_effect_usd=str(local),
                          fx_effect_usd=str(fx),allocated_purchase_fees_usd=str(buy_fees),
                          net_realized_usd=str(local+fx-buy_fees-fee_usd))
            position['quantity'] -= order['quantity']
            position['native_basis'] -= native_basis
            position['usd_basis'] -= usd_basis
            position['buy_fees_usd'] -= buy_fees
        # Cash translation realizes when KRW leaves its cash pool. Asset FX and
        # cash FX are disjoint, so a sale followed by retained cash is not doubled.
        if korean:
            if order['side']=='BUY':
                if not 0 < net <= state['krw_cash']:
                    raise EvidenceUnavailable('KRW cash acquisition basis missing')
                removed = state['cash_usd_basis']*net/state['krw_cash']
                state['cash_usd_basis'] -= removed
                state['krw_cash'] -= net
                state['fx_realized'] += net/reference-removed
            else:
                state['krw_cash'] += net
                state['cash_usd_basis'] += net/reference
        else:
            state['usd_cash'] += -net if order['side']=='BUY' else net
        state['fees'] += fee_usd
        state['trades'].append(record)
    return state


def execution_record(db, user_id, order, plan):
    with localcontext() as context:
        context.prec=50
        try:
            return replay(db,user_id,(dict(order),plan))['trades'][-1]
        except EvidenceUnavailable as error:
            return {'available':False,'reason':str(error),'execution_fx':plan.get('fx')}


def performance(db,user_id,books,current_fx,total_pnl):
    with localcontext() as context:
        context.prec=50
        try:
            state=replay(db,user_id)
            if state['usd_cash'] != D(books['us']['cash_minor'])/100 or state['krw_cash'] != D(books['korea']['cash_minor']):
                raise EvidenceUnavailable('Cash history does not match the ledger')
            rate=amount(current_fx['rate']) if current_fx else None
            if (state['krw_cash'] or any(k[0]=='korea' and p['quantity'] for k,p in state['positions'].items())) and rate is None:
                raise EvidenceUnavailable('Current validated FX unavailable')
            local=state['local_realized'];fx=state['fx_realized'];positions=[]
            for market in ('us','korea'):
                actual={p['symbol']:p for p in books[market]['positions']}
                expected={key[1] for key,p in state['positions'].items() if key[0]==market and p['quantity']}
                if set(actual)!=expected:raise EvidenceUnavailable('Position history does not match the ledger')
                for symbol,position in actual.items():
                    basis=state['positions'][(market,symbol)]
                    if basis['quantity']!=position['quantity'] or position['market_value'] is None:
                        raise EvidenceUnavailable('Position marks/basis unavailable')
                    r=rate if market=='korea' else D(1)
                    value=D(position['market_value_minor'])/(100 if market=='us' else 1)
                    native_pnl=value-basis['native_basis']
                    native_effect=native_pnl/r
                    translation=basis['native_basis']/r-basis['usd_basis']
                    local+=native_effect;fx+=translation
                    positions.append({'market':market,'symbol':symbol,'quantity':basis['quantity'],
                        'average_purchase_price':float(basis['native_basis']/basis['quantity']),
                        'average_acquisition_fx':float(basis['native_basis']/basis['usd_basis']) if market=='korea' and basis['usd_basis'] else None,
                        'current_fx':float(r) if market=='korea' else None,
                        'fx_change_pct':float((r/(basis['native_basis']/basis['usd_basis'])-1)*100) if market=='korea' and basis['usd_basis'] else None,
                        'native_stock_pnl':float(native_pnl),'native_effect_usd':float(native_effect),
                        'fx_effect_usd':float(translation),'purchase_costs_usd':float(basis['buy_fees_usd']),
                        'total_usd_pnl':float(native_effect+translation-basis['buy_fees_usd'])})
            cash_fx=state['krw_cash']/rate-state['cash_usd_basis'] if state['krw_cash'] else ZERO
            fx+=cash_fx
            exact=local+fx-state['fees']-state['conversion_costs']
            if total_pnl is None:raise EvidenceUnavailable('Portfolio valuation incomplete')
            residual=amount(total_pnl)-exact
            if abs(residual)>D('0.0050000001'):raise EvidenceUnavailable('Attribution does not reconcile to equity')
            krw_value=books['korea']['portfolio_value_minor']
            total=amount(total_pnl)+100000
            return {'available':True,'native_investment_effect_usd':float(local),'fx_translation_effect_usd':float(fx),
                    'trading_costs_usd':float(state['fees']),'fx_conversion_costs_usd':float(state['conversion_costs']),
                    'krw_cash_fx_unrealized_usd':float(cash_fx),'total_usd_pnl':float(exact),
                    'rounding_residual_usd':float(residual),'reconciled_total_usd_pnl':float(exact+residual),
                    'krw_exposure_usd':float(D(krw_value)/rate) if krw_value and rate else 0,
                    'krw_exposure_pct':float(D(krw_value)/rate/total*100) if krw_value and rate and total else 0,
                    'positions':positions,'basis_method':'average_gross_native_and_historical_USD_basis;average_KRW_cash_basis'}
        except EvidenceUnavailable as error:
            return {'available':False,'reason':str(error),'positions':[]}
