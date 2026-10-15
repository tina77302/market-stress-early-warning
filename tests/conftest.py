"""All tests use isolated, deterministic listing metadata, never live directories."""
import pytest
from src.paper import symbol_master
from src.paper.security_sources import entry


@pytest.fixture(autouse=True)
def security_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_SYMBOL_MASTER_PATH',str(tmp_path/'security-master.sqlite3'))
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
