import os
import pandas as pd
import logging
from src.config import DATA_RAW_DIR, DATA_PROCESSED_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketDataCleaner:
    def __init__(
        self,
        input_filename="raw_market_data.csv",
        output_filename="cleaned_market_data.csv"
    ):
        self.input_path = DATA_RAW_DIR / input_filename
        self.output_path = DATA_PROCESSED_DIR / output_filename

    def clean(self):
        """
        원본 데이터를 SPY 실제 거래일 기준으로 정렬하고,
        시장별 휴장일 차이로 발생한 결측치를 과거 데이터만 사용해 처리합니다.

        SPY:
            실제 거래일(master calendar)로 사용하며 forward-fill하지 않습니다.

        VIX:
            SPY 거래일 중 결측치가 있을 경우 과거 관측값으로 최대 5일 보정합니다.

        BAA_Treasury_Spread:
            채권시장 휴장일/발표일 차이로 인한 결측치를
            과거 관측값으로 최대 5일 보정합니다.
        """

        logger.info(f"Reading raw data from {self.input_path}")

        if not self.input_path.exists():
            raise FileNotFoundError(
                f"{self.input_path} 가 존재하지 않습니다. 먼저 fetcher를 실행하세요."
            )

        # --------------------------------------------------
        # 1. Raw data 불러오기
        # --------------------------------------------------
        df = pd.read_csv(
            self.input_path,
            index_col="Date",
            parse_dates=True
        )

        # 날짜 순서 정렬
        df.sort_index(inplace=True)

        # 혹시 존재할 수 있는 중복 날짜 제거
        duplicate_count = df.index.duplicated().sum()

        if duplicate_count > 0:
            logger.warning(
                f"Found {duplicate_count} duplicated dates. Removing duplicates."
            )
            df = df[~df.index.duplicated(keep="first")]

        logger.info(f"Raw Dataset Shape: {df.shape}")

        # --------------------------------------------------
        # 2. SPY 실제 거래일을 Master Calendar로 사용
        # --------------------------------------------------
        # Outer join으로 들어온 채권시장-only 날짜나
        # 미국 주식시장 비거래일 제거
        before_calendar_filter = len(df)

        df = df[df["SPY"].notna()].copy()

        removed_non_trading_days = before_calendar_filter - len(df)

        logger.info(
            f"Removed {removed_non_trading_days} non-SPY trading dates."
        )

        # --------------------------------------------------
        # 3. VIX 결측치 처리
        # --------------------------------------------------
        vix_missing_before = df["VIX"].isna().sum()

        df["VIX"] = df["VIX"].ffill(limit=5)

        vix_missing_after = df["VIX"].isna().sum()

        logger.info(
            f"VIX missing values: "
            f"{vix_missing_before} -> {vix_missing_after}"
        )

        # --------------------------------------------------
        # 4. Credit Spread 결측치 처리
        # --------------------------------------------------
        credit_missing_before = df["BAA_Treasury_Spread"].isna().sum()

        df["BAA_Treasury_Spread"] = df["BAA_Treasury_Spread"].ffill(limit=5)

        credit_missing_after = df["BAA_Treasury_Spread"].isna().sum()

        logger.info(
            f"BAA_Treasury_Spread missing values: "
            f"{credit_missing_before} -> {credit_missing_after}"
        )

        # --------------------------------------------------
        # 5. 해결되지 않은 결측치 제거
        # --------------------------------------------------
        before_dropna = len(df)

        df.dropna(
            subset=["SPY", "VIX", "BAA_Treasury_Spread"],
            inplace=True
        )

        dropped_rows = before_dropna - len(df)

        if dropped_rows > 0:
            logger.info(
                f"Dropped {dropped_rows} rows with unresolved missing values."
            )

        # --------------------------------------------------
        # 6. 기본 데이터 품질 검증
        # --------------------------------------------------
        if (df["SPY"] <= 0).any():
            raise ValueError(
                "SPY contains zero or negative values."
            )

        if (df["VIX"] <= 0).any():
            raise ValueError(
                "VIX contains zero or negative values."
            )

        # 날짜가 오름차순인지 확인
        if not df.index.is_monotonic_increasing:
            raise ValueError(
                "Date index is not monotonically increasing."
            )

        # 중복 날짜 최종 확인
        if df.index.duplicated().any():
            raise ValueError(
                "Duplicate dates remain after cleaning."
            )

        # --------------------------------------------------
        # 7. 저장
        # --------------------------------------------------
        os.makedirs(DATA_PROCESSED_DIR, exist_ok=True)

        df.to_csv(self.output_path)

        # --------------------------------------------------
        # 8. QA 결과 출력
        # --------------------------------------------------
        logger.info(
            f"Cleaned data successfully saved to: {self.output_path}"
        )

        logger.info(f"Cleaned Dataset Shape: {df.shape}")
        logger.info(f"Start Date: {df.index.min()}")
        logger.info(f"End Date: {df.index.max()}")
        logger.info(f"Duplicate Dates: {df.index.duplicated().sum()}")

        logger.info(
            "Remaining Missing Values:\n"
            f"{df[['SPY', 'VIX', 'BAA_Treasury_Spread']].isna().sum()}"
        )

        return df


if __name__ == "__main__":
    cleaner = MarketDataCleaner()
    cleaner.clean()