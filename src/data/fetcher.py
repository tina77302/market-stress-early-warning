import os
import pandas as pd
import yfinance as yf
import requests
from io import StringIO
import logging
from src.config import FRED_API_KEY, START_DATE, DATA_RAW_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MarketDataFetcher:
    def __init__(self, start_date=START_DATE, end_date=None):
        self.start_date = start_date
        self.end_date = end_date # If None, fetches up to today
        
    def fetch_yahoo_data(self):
        """SPY와 VIX 데이터를 yfinance를 통해 수집합니다."""
        logger.info(f"Fetching SPY and ^VIX from {self.start_date}...")
        
        # SPY, VIX 다운로드
        tickers = ["SPY", "^VIX"]
        df_yf = yf.download(tickers, start=self.start_date, end=self.end_date, progress=False)
        
        # yfinance 다중 티커 결과는 MultiIndex 컬럼이므로 'Close' 가격만 추출
        if isinstance(df_yf.columns, pd.MultiIndex):
            df_close = df_yf['Close']
        else:
            df_close = df_yf
            
        df_close.columns = ['SPY', 'VIX']
        df_close.index = pd.to_datetime(df_close.index).tz_localize(None)
        
        logger.info(f"Yahoo Finance data fetched successfully. Shape: {df_close.shape}")
        return df_close
        
    def fetch_fred_credit_spread(self):
        """
        신용 스프레드(Credit Spread)를 FRED에서 수집합니다.
        (기존 ICE BofA HY Spread는 FRED 계정 약관 동의가 필요하여 제한될 수 있으므로,
        무료로 접근 가능한 Moody's Baa Corporate Bond Yield (DBAA) - 10-Year Treasury (DGS10) 로 대체합니다.)
        """
        logger.info("Fetching Credit Spread (DBAA - DGS10) from FRED...")
        
        def download_fred_csv(series_id):
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={self.start_date}"
            if self.end_date:
                url += f"&coed={self.end_date}"
            resp = requests.get(url)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text), parse_dates=['observation_date'], na_values='.')
            df.rename(columns={'observation_date': 'Date', series_id: series_id}, inplace=True)
            df.set_index('Date', inplace=True)
            return df
            
        df_dbaa = download_fred_csv('DBAA')
        df_dgs10 = download_fred_csv('DGS10')
        
        df_spread = df_dbaa.join(df_dgs10, how='outer')
        # 결측치를 앞선 값으로 채우고 계산
        df_spread.ffill(inplace=True)
        df_spread['HY_Spread'] = df_spread['DBAA'] - df_spread['DGS10']
        
        df_hy = df_spread[['HY_Spread']].dropna()
        
        # 시작일 필터링
        df_hy = df_hy[df_hy.index >= pd.to_datetime(self.start_date)]
        
        logger.info(f"Credit Spread (DBAA - DGS10) fetched successfully. Shape: {df_hy.shape}")
        return df_hy
        
    def run_pipeline(self, output_filename="raw_market_data.csv"):
        """전체 데이터를 수집, 병합한 후 CSV로 저장합니다."""
        # 1. 개별 데이터 수집
        df_yf = self.fetch_yahoo_data()
        df_hy = self.fetch_fred_credit_spread()
        
        # 2. 데이터 병합 (Outer Join)
        logger.info("Merging datasets (Outer Join)...")
        df_merged = df_yf.join(df_hy, how='outer')
        
        # 3. 인덱스 이름 정리 및 정렬
        df_merged.index.name = 'Date'
        df_merged.sort_index(inplace=True)
        
        # 4. CSV 저장
        os.makedirs(DATA_RAW_DIR, exist_ok=True)
        output_path = DATA_RAW_DIR / output_filename
        df_merged.to_csv(output_path)
        logger.info(f"Raw data successfully saved to: {output_path}")
        logger.info(f"Final Dataset Shape: {df_merged.shape}")
        
        return df_merged

if __name__ == "__main__":
    fetcher = MarketDataFetcher()
    fetcher.run_pipeline()
