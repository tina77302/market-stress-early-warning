"""All tests use isolated, deterministic listing metadata, never live directories."""
import pytest
from src.paper import symbol_master
from src.paper.security_sources import entry


@pytest.fixture(autouse=True)
def security_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_FX_PRIMARY_PROVIDER','')
    monkeypatch.setenv('PAPER_SYMBOL_MASTER_PATH',str(tmp_path/'security-master.sqlite3'))
    # Provider boundary only: no test ever calls live FRED for Paper Trading FX.
    from src.paper import fx
    from datetime import datetime,timezone,timedelta
    from uuid import uuid4
    monkeypatch.setattr(fx,'fetch_observation',lambda:{'id':str(uuid4()),'rate':'1000','observation_date':(datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat(),'retrieved_at':datetime.now(timezone.utc).isoformat(),'source':fx.SOURCE})
    rows = [
        entry('us','SPY','SPDR S&P 500 ETF','NYSE Arca','ETF'),
        entry('us','QQQ','Invesco QQQ ETF','Nasdaq','ETF'),
        entry('us','VOO','Vanguard S&P 500 ETF','NYSE Arca','ETF'),
        entry('us','AAPL','Apple Inc. Common Stock','Nasdaq','Stock'),
        entry('us','MSFT','Microsoft Corporation Common Stock','Nasdaq','Stock'),
        entry('us','NVDA','NVIDIA Corporation Common Stock','Nasdaq','Stock'),
        entry('us','NVDS','Fixture NVDA Name ETF','Nasdaq','ETF'),
        entry('us','PLTR','Palantir Technologies Inc. Common Stock','Nasdaq','Stock'),
        entry('korea','005930','삼성전자','KOSPI','Stock'),
        entry('korea','000660','SK하이닉스','KOSPI','Stock'),
        entry('korea','035420','NAVER','KOSPI','Stock'),
        entry('korea','035720','카카오','KOSPI','Stock'),
        entry('korea','028260','삼성물산','KOSPI','Stock'),
        entry('korea','009150','삼성전기','KOSPI','Stock'),
        entry('korea','035900','JYP Ent.','KOSDAQ','Stock'),
        entry('korea','069500','KODEX 200','KOSPI','ETF'),
    ]
    for market in ['us','korea']:
        symbol_master.publish(market,[r for r in rows if r['market']==market],[{'source':'isolated-test-fixture'}],minimum=1)
    monkeypatch.setattr(symbol_master,'yahoo_candidates',lambda query:[])
    return rows


@pytest.fixture
def zero_cost_policy(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from src.paper import costs
    profile=json.loads(Path(costs.__file__).with_name('cost_rules.json').read_text())
    profile['fx_spread_bps']='0'
    for market in profile['commission_bps'].values():
        for kind in market.values():
            for side in kind:kind[side]='0'
    for row in profile['us_sec']:row['rate']='0'
    for row in profile['us_taf']:row['per_share_usd']='0';row['max_usd']='0'
    for row in profile['korea_stock_sell_taxes'].values():
        for key in row:row[key]='0'
    path=tmp_path/'zero-cost-native-fixture.json';path.write_text(json.dumps(profile))
    monkeypatch.setenv('PAPER_COST_CONFIG_PATH',str(path))
    return profile
