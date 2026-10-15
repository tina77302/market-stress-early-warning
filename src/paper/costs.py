"""Versioned simulation assumptions and verified, dated transaction-level pass-throughs."""
import hashlib
import json
import os
from datetime import datetime,date
from decimal import Decimal,ROUND_CEILING,ROUND_FLOOR,InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import HTTPException


def trade_date(market):
    return datetime.now(ZoneInfo('America/New_York' if market=='us' else 'Asia/Seoul')).date().isoformat()


def validate(policy):
    try:
        if date.fromisoformat(policy['valid_from'])>date.fromisoformat(policy['valid_through']):raise ValueError
        if not isinstance(policy['version'],str) or not policy['version'].strip():raise ValueError
        if not isinstance(policy['sources'],dict) or not policy['sources'] or not all(isinstance(v,str) and v.startswith('https://') for v in policy['sources'].values()):raise ValueError
        def rate(value,max_value):
            d=Decimal(str(value))
            if not d.is_finite() or not 0<=d<=max_value:raise ValueError
        rate(policy['fx_spread_bps'],1000)
        for market in ['us','korea']:
            minimum=policy['commission_min_minor'][market]
            if type(minimum) is not int or not 0<=minimum<=1000000:raise ValueError
            for kind in ['Stock','ETF']:
                for side in ['BUY','SELL']:rate(policy['commission_bps'][market][kind][side],1000)
        for key in ['us_sec','us_taf']:
            previous=None
            for row in policy[key]:
                start=date.fromisoformat(row['from']);end=date.fromisoformat(row['through'])
                if start>end or (previous is not None and start<=previous):raise ValueError
                previous=end
                if key=='us_sec':rate(row['rate'],Decimal('0.1'))
                else:rate(row['per_share_usd'],1);rate(row['max_usd'],1000)
        for exchange in ['KOSPI','KOSDAQ']:
            taxes=policy['korea_stock_sell_taxes'][exchange]
            if set(taxes)!={'securities_transaction_tax','agricultural_special_tax'}:raise ValueError
            for value in taxes.values():rate(value,Decimal('0.1'))
        return policy
    except (KeyError,ValueError,TypeError,InvalidOperation):
        raise HTTPException(503,'Simulated cost policy is invalid. Trading requires a valid cost schedule.') from None


def load():
    try:
        policy=json.loads(Path(os.getenv('PAPER_COST_CONFIG_PATH',str(Path(__file__).with_name('cost_rules.json')))).read_text())
        return validate(policy)
    except HTTPException:raise
    except Exception:raise HTTPException(503,'Simulated cost policy is unavailable.') from None


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def snapshot(db,quote_id,item):
    policy=load();day=trade_date(item['market'])
    breakdown(policy,item['market'],item['security_type'],item['exchange'],'BUY',1,1,day)
    db.execute('INSERT INTO paper_quote_costs VALUES (?,?,?,?,?,?)',(quote_id,canonical(policy),item['security_type'],item['exchange'],day,digest(policy)))


def quote_policy(db,quote):
    row=db.execute('SELECT * FROM paper_quote_costs WHERE quote_id=?',(quote['id'],)).fetchone()
    if not row or row['trade_date']!=trade_date(quote['market']):
        raise HTTPException(409,'Refresh the quote to obtain the current dated cost schedule.')
    try:policy=validate(json.loads(row['policy_json']))
    except (ValueError,TypeError):raise HTTPException(503,'Cost policy integrity check failed.') from None
    if digest(policy)!=row['policy_hash']:raise HTTPException(503,'Cost policy integrity check failed.')
    return row,policy


def breakdown(policy,market,kind,exchange,side,price_minor,quantity,day):
    if not policy['valid_from']<=day<=policy['valid_through']:
        raise HTTPException(503,'The dated cost schedule requires review before further trading.')
    if market not in ('us','korea') or kind not in ('Stock','ETF') or side not in ('BUY','SELL'):
        raise HTTPException(503,'Unsupported transaction cost classification.')
    gross=price_minor*quantity
    rounding=ROUND_CEILING if market=='us' else ROUND_FLOOR
    commission=max(policy['commission_min_minor'][market],int((Decimal(gross)*Decimal(policy['commission_bps'][market][kind][side])/10000).to_integral_value(rounding=rounding)))
    lines=[]
    if side=='SELL' and market=='korea' and kind=='Stock':
        if exchange not in policy['korea_stock_sell_taxes']:raise HTTPException(503,'Unsupported Korean tax classification.')
        for label,rate in policy['korea_stock_sell_taxes'][exchange].items():
            lines.append({'name':label,'category':'transaction_tax','rate':rate,'minor':int((Decimal(gross)*Decimal(rate)).to_integral_value(rounding=ROUND_FLOOR))})
    if side=='SELL' and market=='us':
        def dated(key):
            selected=[r for r in policy[key] if r['from']<=day<=r['through']]
            if len(selected)!=1:raise HTTPException(503,'The dated regulatory fee schedule requires review.')
            return selected[0]
        sec=dated('us_sec');taf=dated('us_taf')
        lines.append({'name':'SEC_section_31','category':'regulatory_fee','rate':sec['rate'],'minor':int((Decimal(gross)*Decimal(sec['rate'])).to_integral_value(rounding=ROUND_CEILING))})
        lines.append({'name':'FINRA_TAF','category':'regulatory_fee','rate':taf['per_share_usd'],'minor':int((min(Decimal(quantity)*Decimal(taf['per_share_usd']),Decimal(taf['max_usd']))*100).to_integral_value(rounding=ROUND_CEILING))})
    tax=sum(row['minor'] for row in lines if row['category']=='transaction_tax')
    regulatory=sum(row['minor'] for row in lines if row['category']=='regulatory_fee')
    fees=commission+tax+regulatory
    net=gross+fees if side=='BUY' else gross-fees
    if net<0:raise HTTPException(409,'Trade proceeds cannot cover the simulated transaction costs.')
    return {'commission_bps':policy['commission_bps'][market][kind][side],'commission_min_minor':policy['commission_min_minor'][market],'sources':policy['sources'],'gross_minor':gross,'commission_minor':commission,'transaction_tax_minor':tax,'regulatory_fee_minor':regulatory,
            'total_fees_minor':fees,'net_minor':net,'components':lines,'security_type':kind,'exchange':exchange,
            'trade_date':day,'policy_version':policy['version'],'policy_hash':digest(policy),'simulated_assumptions':True,
            'unmodeled':'Personal capital gains/dividend/ETF income withholding, ADR fees and venue-specific liquidity fees/rebates are not modeled. These are not universal broker charges.'}
