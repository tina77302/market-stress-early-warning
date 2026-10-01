import os
import pandas as pd
import yfinance as yf
import requests
from io import StringIO
import logging
from src.config import START_DATE, DATA_RAW_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketDataFetcher:
    def __init__(self, start_date=START_DATE, end_date=None):
        self.start_date = start_date
        self.end_date = end_date

    def fetch_yahoo_data(self):
        """
        SPY와 VIX 데이터를 Yahoo Finance에서 수집합니다.
        """
        logger.info(
            f"Fetching SPY and ^VIX from {self.start_date}..."
        )

        tickers = ["SPY", "^VIX"]

        df_yf = yf.download(
            tickers,
            start=self.start_date,
            end=self.end_date,
            progress=False
        )

        # yfinance 다중 티커 결과 처리
        if isinstance(df_yf.columns, pd.MultiIndex):
            df_close = df_yf["Close"]
        else:
            df_close = df_yf

        # 컬럼 순서 명확하게 지정
        df_close = df_close[["SPY", "^VIX"]].copy()
        df_close.columns = ["SPY", "VIX"]

        # timezone 제거
        df_close.index = (
            pd.to_datetime(df_close.index)
            .tz_localize(None)
        )

        logger.info(
            f"Yahoo Finance data fetched successfully. "
            f"Shape: {df_close.shape}"
        )

        return df_close


    def fetch_fred_credit_spread(self):
        """
        FRED에서 신용시장 스트레스 proxy를 수집합니다.

        Credit Spread Proxy:
        Moody's Seasoned Baa Corporate Bond Yield (DBAA)
        - 10-Year Treasury Constant Maturity Rate (DGS10)

        Raw 단계에서는 결측치를 임의로 forward-fill하지 않습니다.
        결측치 처리는 cleaner 단계에서 수행합니다.
        """

        logger.info(
            "Fetching BAA-Treasury Credit Spread "
            "(DBAA - DGS10) from FRED..."
        )

        def download_fred_csv(series_id):

            url = (
                "https://fred.stlouisfed.org/graph/"
                f"fredgraph.csv?id={series_id}"
                f"&cosd={self.start_date}"
            )

            if self.end_date:
                url += f"&coed={self.end_date}"

            resp = requests.get(url)
            resp.raise_for_status()

            df = pd.read_csv(
                StringIO(resp.text),
                parse_dates=["observation_date"],
                na_values="."
            )

            df.rename(
                columns={
                    "observation_date": "Date",
                    series_id: series_id
                },
                inplace=True
            )

            df.set_index("Date", inplace=True)

            return df

        # FRED 원자료
        df_dbaa = download_fred_csv("DBAA")
        df_dgs10 = download_fred_csv("DGS10")

        # 날짜 기준 병합
        df_spread = df_dbaa.join(
            df_dgs10,
            how="outer"
        )

        # 같은 날짜에 두 금리가 모두 존재하는 경우에만 계산
        # 결측치는 그대로 보존
        df_spread["BAA_Treasury_Spread"] = (
            df_spread["DBAA"]
            - df_spread["DGS10"]
        )

        df_credit = df_spread[
            ["BAA_Treasury_Spread"]
        ].copy()

        # 시작일 필터링
        df_credit = df_credit[
            df_credit.index >= pd.to_datetime(self.start_date)
        ]

        logger.info(
            "Credit Spread (DBAA - DGS10) "
            f"fetched successfully. Shape: {df_credit.shape}"
        )

        return df_credit


    def run_pipeline(
        self,
        output_filename="raw_market_data.csv"
    ):
        """
        전체 원천 데이터를 수집하고 병합하여
        raw_market_data.csv로 저장합니다.
        """

        # 1. 시장 데이터 수집
        df_yf = self.fetch_yahoo_data()

        # 2. Credit 데이터 수집
        df_credit = self.fetch_fred_credit_spread()

        # 3. Raw 단계에서는 모든 원본 날짜를 보존
        logger.info(
            "Merging datasets (Outer Join)..."
        )

        df_merged = df_yf.join(
            df_credit,
            how="outer"
        )

        # 날짜 정리
        df_merged.index.name = "Date"
        df_merged.sort_index(inplace=True)

        # 4. Raw CSV 저장
        os.makedirs(
            DATA_RAW_DIR,
            exist_ok=True
        )

        output_path = (
            DATA_RAW_DIR / output_filename
        )

        df_merged.to_csv(output_path)

        logger.info(
            f"Raw data successfully saved to: "
            f"{output_path}"
        )

        logger.info(
            f"Final Dataset Shape: "
            f"{df_merged.shape}"
        )

        return df_merged


if __name__ == "__main__":
    fetcher = MarketDataFetcher()
    fetcher.run_pipeline()