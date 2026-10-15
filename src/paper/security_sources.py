"""Structured public listing metadata; no prices or account data.

Nasdaq field definitions: https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs
KIS layouts: https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
"""
import csv
import hashlib
import io
import re
import zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

URLS = {
    'nasdaq': 'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt',
    'other': 'https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt',
    'kospi': 'https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip',
    'kosdaq': 'https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip',
}
US_EXCHANGES = {'N': 'NYSE', 'A': 'NYSE American', 'P': 'NYSE Arca', 'Z': 'Cboe BZX'}
UNSUPPORTED = re.compile(r'\b(?:warrants?|rights?|units?|preferred|depositary|notes?|leveraged|inverse|ultrapro|ultrashort|ultra)\b|\b[2-9]x\b|레버리지|인버스', re.I)


def normalize_name(value):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def entry(market, ticker, name, exchange, kind, active=True):
    provider = ticker.replace('.', '-') if market == 'us' else ticker + ('.KS' if exchange == 'KOSPI' else '.KQ')
    # Preserve existing Korean execution/storage keys and portfolios. The
    # exchange ticker is separate and shown without Yahoo suffixes in the UI.
    return {'market': market, 'symbol': ticker if market == 'us' else provider,
            'ticker': ticker, 'provider_symbol': provider, 'name': name.strip(),
            'exchange': exchange, 'currency': 'USD' if market == 'us' else 'KRW',
            'security_type': kind, 'active': bool(active)}


def parse_nasdaq(content, source):
    text = content.decode('utf-8-sig')
    lines = text.splitlines()
    footer = next((line.split('|')[0].split(': ',1)[1].strip() for line in lines if line.startswith('File Creation Time: ')), None)
    if not footer:
        raise ValueError('Nasdaq directory timestamp is missing.')
    stamp = datetime.strptime(footer, '%m%d%Y%H:%M').replace(tzinfo=ZoneInfo('America/New_York'))
    if not -86400 <= (datetime.now(timezone.utc)-stamp).total_seconds() <= 7*86400:
        raise ValueError('Nasdaq directory timestamp is not usable.')
    reader = csv.DictReader(io.StringIO('\n'.join(line for line in lines if not line.startswith('File Creation Time:'))), delimiter='|')
    required = {'Security Name','ETF','Test Issue'} | ({'Symbol','Financial Status','Market Category','NextShares'} if source=='nasdaq' else {'ACT Symbol','CQS Symbol','Exchange'})
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('Unexpected Nasdaq directory schema.')
    rows = []
    for row in reader:
        name = row['Security Name'].strip()
        ticker = (row.get('Symbol') if source=='nasdaq' else row.get('CQS Symbol')).strip()
        exchange = 'Nasdaq' if source=='nasdaq' else US_EXCHANGES.get(row['Exchange'])
        kind = 'ETF' if row['ETF']=='Y' else 'Stock'
        common = bool(re.search(r'\b(common stock|common shares|ordinary shares|ordinary share|capital stock)\b', name, re.I))
        if not exchange or row['Test Issue']!='N' or row['ETF'] not in ('Y','N') or UNSUPPORTED.search(name):
            continue
        if not re.fullmatch(r'[A-Z]{1,6}(?:\.[A-Z])?', ticker) or (kind=='Stock' and not common):
            continue
        active = row.get('Financial Status','N')=='N' and row.get('NextShares','N')=='N'
        rows.append(entry('us',ticker,name,exchange,kind,active))
    return rows, stamp.isoformat()


def parse_kis(content, board):
    # Offsets are the fixed-width trailing fields documented by KIS, after
    # decoding CP949. Newlines are excluded (official scripts count them).
    tail_size, halt, liquidation, preferred = (227,60,61,158) if board=='kospi' else (221,55,56,153)
    filename = board+'_code.mst'
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        info = archive.getinfo(filename)
        if info.file_size > 8*1024*1024:
            raise ValueError('Korean master exceeds size limit.')
        text = archive.read(filename).decode('cp949')
    rows = []
    for line in text.splitlines():
        if len(line) < tail_size+22:
            raise ValueError('Unexpected Korean master record length.')
        prefix, tail = line[:-tail_size], line[-tail_size:]
        ticker, isin, name = prefix[:9].strip(), prefix[9:21].strip(), prefix[21:].strip()
        if not re.fullmatch(r'\d{6}',ticker) or not re.fullmatch(r'KR[A-Z0-9]{10}',isin) or not name:
            continue
        group = tail[:2]
        if group not in ('ST','EF') or tail[preferred]!='0' or UNSUPPORTED.search(name):
            continue
        if tail[halt] not in ('Y','N') or tail[liquidation] not in ('Y','N'):
            raise ValueError('Unrecognized Korean trading-status flags.')
        rows.append(entry('korea',ticker,name,'KOSPI' if board=='kospi' else 'KOSDAQ',
                          'ETF' if group=='EF' else 'Stock',tail[halt]=='N' and tail[liquidation]=='N'))
    return rows


def download(url):
    data = bytearray()
    with requests.get(url, timeout=(4,12), stream=True) as response:
        response.raise_for_status()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data)>8*1024*1024:
                raise ValueError('Listing source exceeds size limit.')
        return bytes(data), response.headers.get('Last-Modified')


def fetch_market(market):
    result, provenance = [], []
    for source in (('nasdaq','other') if market=='us' else ('kospi','kosdaq')):
        content, modified = download(URLS[source])
        if market=='us':
            rows, source_date = parse_nasdaq(content,source)
        else:
            rows, source_date = parse_kis(content,source), None
            if modified:
                stamp = parsedate_to_datetime(modified)
                if not -86400 <= (datetime.now(timezone.utc)-stamp).total_seconds() <= 7*86400:
                    raise ValueError('Korean master source is stale.')
                source_date = stamp.isoformat()
        if not rows:
            raise ValueError('Listing source contains no supported securities.')
        result.extend(rows)
        provenance.append({'source':source,'url':URLS[source], 'sha256':hashlib.sha256(content).hexdigest(),
                           'source_timestamp':source_date})
    # Duplicate exchange listings cannot silently resolve to another security.
    unique = {}
    for row in result:
        key = row['symbol']
        if key in unique and unique[key] != row:
            raise ValueError('Conflicting duplicate listing identity.')
        unique[key] = row
    return list(unique.values()), provenance
