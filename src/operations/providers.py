"""Independent provider adapters with bounded HTTP and recorded retries."""
import os
import time
from io import StringIO
from datetime import timedelta
import pandas as pd
import requests
import yfinance as yf
from .store import record_attempt, utcnow
from .validation import ValidationFailure, TransientProviderError, validate_series
from .calendar import calendar

PROVIDERS = {'SPY':'Yahoo Finance', 'VIX':'Yahoo Finance', 'DBAA':'FRED', 'DGS10':'FRED',
             'KOSPI200':'KRX', 'VKOSPI':'KRX', 'Korea_Treasury_3Y':'BOK ECOS', 'Korea_Corporate_AAminus_3Y':'BOK ECOS'}
UNITS = {'SPY':'USD adjusted close', 'VIX':'index points', 'DBAA':'percent per annum', 'DGS10':'percent per annum',
         'KOSPI200':'index points', 'VKOSPI':'index points', 'Korea_Treasury_3Y':'percent per annum', 'Korea_Corporate_AAminus_3Y':'percent per annum'}


class Providers:
    def __init__(self, job_id, attempts=3, sleep=time.sleep):
        self.job_id, self.max_attempts, self.sleep = job_id, attempts, sleep
        self.counts = {}

    def call(self, series, fetch):
        for attempt in range(1, self.max_attempts + 1):
            self.counts[series] = self.counts.get(series, 0) + 1
            started = utcnow()
            try:
                result = fetch()
                latest = result.index.max().strftime('%Y-%m-%d') if not result.empty else None
                retrieved = record_attempt(self.job_id, PROVIDERS[series], series, self.counts[series], started, 'SUCCESS', latest)
                return result, retrieved
            except Exception as error:
                # Never persist request URLs (ECOS embeds its API key in the URL).
                if isinstance(error, requests.RequestException):
                    error = TransientProviderError('Provider connection/timeout failed.')
                if not isinstance(error, (ValidationFailure, TransientProviderError)):
                    error = ValidationFailure(f'Provider response could not be parsed ({type(error).__name__}).')
                record_attempt(self.job_id, PROVIDERS[series], series, self.counts[series], started, 'ERROR', error=error)
                if not isinstance(error, TransientProviderError) or attempt == self.max_attempts:
                    raise error from None
                self.sleep(min(2 ** (attempt - 1), 8))
        raise AssertionError('Unreachable')

    @staticmethod
    def http(url, **kwargs):
        response = requests.get(url, timeout=(10, 25), **kwargs)
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientProviderError(f'Provider HTTP {response.status_code}.')
        if response.status_code != 200:
            raise ValidationFailure(f'Provider HTTP {response.status_code} (not retryable).')
        if not response.content.strip():
            raise TransientProviderError('Provider returned an empty response.')
        return response

    def yahoo(self, series, end):
        def fetch():
            # Explicitly retain existing pipeline's auto-adjusted Close semantics.
            frame = yf.download('SPY' if series == 'SPY' else '^VIX', start='2000-01-01',
                                end=(pd.Timestamp(end)+timedelta(days=1)).strftime('%Y-%m-%d'),
                                auto_adjust=True, progress=False, threads=False, timeout=25)
            if frame.empty:
                raise TransientProviderError('Yahoo Finance returned no observations (unavailable/rate limited).')
            if 'Close' not in frame:
                raise ValidationFailure('Yahoo Finance missing Close column.')
            close = frame['Close']
            if isinstance(close, pd.DataFrame):
                if len(close.columns) != 1:
                    raise ValidationFailure('Yahoo Finance returned unexpected ticker columns.')
                close = close.iloc[:,0]
            result = close.rename(series).to_frame()
            result.index = pd.to_datetime(result.index).tz_localize(None)
            validate_series(result, series, positive=True, allow_missing=True, today=end)
            return result
        return self.call(series, fetch)

    def fred(self, series, end):
        def fetch():
            response = self.http('https://fred.stlouisfed.org/graph/fredgraph.csv', params={'id':series,'cosd':'2000-01-01','coed':end})
            result = pd.read_csv(StringIO(response.text), na_values='.')
            if set(['observation_date',series]) - set(result.columns):
                raise ValidationFailure(f'FRED missing observation_date/{series}.')
            result['observation_date'] = pd.to_datetime(result['observation_date'], errors='raise')
            result = result.set_index('observation_date')[[series]]
            validate_series(result,series,allow_missing=True,today=end)
            return result
        return self.call(series,fetch)

    def krx(self, series, end, history):
        key = os.getenv('KRX_API_KEY')
        if not key:
            return self.call(series,lambda: (_ for _ in ()).throw(ValidationFailure('KRX_API_KEY is not configured.')))
        if history.empty:
            return self.call(series,lambda: (_ for _ in ()).throw(ValidationFailure('KRX validated historical seed is required before incremental refresh.')))
        start = history.index.max() - timedelta(days=14)
        if (pd.Timestamp(end)-start).days > 90:
            return self.call(series,lambda: (_ for _ in ()).throw(ValidationFailure('KRX history gap exceeds bounded 90-day refresh; explicit historical backfill required.')))
        cal = calendar('korea',pd.Timestamp(end).year)
        dates = cal.sessions_in_range(start,pd.Timestamp(end))
        rows, retrieved = [], None
        for date in dates:
            def fetch(date=date):
                path = 'kospi_dd_trd' if series == 'KOSPI200' else 'drvprod_dd_trd'
                data = self.http(f'https://data-dbg.krx.co.kr/svc/apis/idx/{path}',headers={'AUTH_KEY':key},params={'basDd':date.strftime('%Y%m%d')}).json()
                if 'OutBlock_1' not in data or not isinstance(data['OutBlock_1'],list):
                    raise ValidationFailure('KRX missing OutBlock_1 (authorization/schema failure).')
                target = '코스피 200' if series == 'KOSPI200' else '코스피 200 변동성지수'
                matched = [r for r in data['OutBlock_1'] if r.get('IDX_NM')==target]
                if not matched:
                    raise TransientProviderError(f'KRX {series} has no observation for expected session {date:%Y-%m-%d}.')
                if len(matched)!=1 or matched[0].get('BAS_DD') != date.strftime('%Y%m%d'):
                    raise ValidationFailure('KRX duplicate index or mismatched observation date.')
                result = pd.DataFrame({series:[float(str(matched[0]['CLSPRC_IDX']).replace(',',''))]},index=pd.DatetimeIndex([date.tz_localize(None) if date.tzinfo else date]))
                validate_series(result,series,positive=True,today=end)
                return result
            result,retrieved = self.call(series,fetch)
            rows.append(result)
        if not rows:
            raise ValidationFailure('No KRX sessions available in incremental window.')
        return pd.concat(rows),retrieved

    def ecos(self, series, end):
        def fetch():
            key = os.getenv('ECOS_API_KEY')
            if not key:
                raise ValidationFailure('ECOS_API_KEY is not configured.')
            item = '010200000' if series == 'Korea_Treasury_3Y' else '010310000'
            data = self.http(f'https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/10000/817Y002/D/20100104/{end.replace("-","")}/{item}').json()
            if 'RESULT' in data:
                code = str(data['RESULT'].get('CODE','unknown'))
                if code in ['ERROR-500','ERROR-600']:
                    raise TransientProviderError(f'ECOS temporarily unavailable ({code}).')
                raise ValidationFailure(f'ECOS rejected request ({code}).')
            search = data.get('StatisticSearch',{})
            rows = search.get('row')
            if not isinstance(rows,list) or not rows:
                raise TransientProviderError('ECOS returned no observations.')
            if int(search.get('list_total_count',0)) > len(rows):
                raise ValidationFailure('ECOS response truncated; pagination required.')
            if any(r.get('UNIT_NAME') not in ['연%','%','연 %'] or r.get('ITEM_CODE1') != item or r.get('STAT_CODE') != '817Y002' for r in rows):
                raise ValidationFailure('ECOS unexpected units or series identity.')
            result = pd.DataFrame({series:[float(str(r['DATA_VALUE']).replace(',','')) for r in rows]},index=pd.to_datetime([r['TIME'] for r in rows],format='%Y%m%d'))
            # ECOS contract returns chronological observations; reject deviations.
            validate_series(result,series,today=end)
            return result
        return self.call(series,fetch)
