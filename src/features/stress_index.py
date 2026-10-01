import os
import pandas as pd
import logging
from src.config import DATA_PROCESSED_DIR, DATA_FEATURES_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StressIndexCalculator:
    def __init__(
        self,
        input_filename="cleaned_market_data.csv",
        output_filename="market_stress_index.csv",
        rolling_window=252
    ):
        self.input_path = DATA_PROCESSED_DIR / input_filename
        self.output_path = DATA_FEATURES_DIR / output_filename
        self.rolling_window = rolling_window

    def calculate_msi(self):
        """
        SPY, VIX, BAA-Treasury Spread를 이용해
        Market Stress Index(MSI)를 생성합니다.

        각 날짜 t의 Z-score 기준 평균/표준편차는
        t-1까지의 과거 데이터만 사용합니다.

        구성:
        1. Equity Stress
        2. Volatility Stress
        3. Credit Stress

        세 구성요소의 rolling Z-score를 동일 가중치로 결합합니다.
        """

        logger.info(
            f"Calculating Market Stress Index "
            f"(Rolling Window: {self.rolling_window} days)"
        )

        df = pd.read_csv(
            self.input_path,
            index_col="Date",
            parse_dates=True
        )

        df.sort_index(inplace=True)

        # --------------------------------------------------
        # 1. Equity Stress
        # --------------------------------------------------
        # 최근 21거래일 SPY 수익률의 부호를 반전
        # 주가가 하락할수록 높은 stress 값
        df["SPY_Stress"] = -df["SPY"].pct_change(periods=21)

        # --------------------------------------------------
        # 2. Volatility Stress
        # --------------------------------------------------
        # VIX가 높을수록 stress 증가
        df["VIX_Stress"] = df["VIX"]

        # --------------------------------------------------
        # 3. Credit Stress
        # --------------------------------------------------
        # Baa-Treasury spread가 확대될수록 stress 증가
        df["Credit_Stress"] = df["BAA_Treasury_Spread"]

        # --------------------------------------------------
        # 4. Past-only Rolling Z-score
        # --------------------------------------------------
        def rolling_zscore(series, window):
            """
            날짜 t의 값은 t-1까지의 과거 분포와 비교합니다.

            shift(1)을 적용하여 현재 관측치가
            자신의 기준 평균/표준편차 계산에 포함되지 않도록 합니다.
            """

            historical = series.shift(1)

            rolling_mean = historical.rolling(
                window=window,
                min_periods=window // 2
            ).mean()

            rolling_std = historical.rolling(
                window=window,
                min_periods=window // 2
            ).std()

            return (
                (series - rolling_mean)
                / (rolling_std + 1e-8)
            )

        logger.info(
            "Applying past-only rolling standardization..."
        )

        df["Z_SPY"] = rolling_zscore(
            df["SPY_Stress"],
            self.rolling_window
        )

        df["Z_VIX"] = rolling_zscore(
            df["VIX_Stress"],
            self.rolling_window
        )

        df["Z_Credit"] = rolling_zscore(
            df["Credit_Stress"],
            self.rolling_window
        )

        # --------------------------------------------------
        # 5. Market Stress Index
        # --------------------------------------------------
        # 임의의 가중치를 두지 않고 동일 가중치 사용
        df["MSI"] = (
            df["Z_SPY"]
            + df["Z_VIX"]
            + df["Z_Credit"]
        ) / 3.0

        # 세 구성요소가 모두 계산 가능한 날짜만 사용
        df.dropna(
            subset=[
                "Z_SPY",
                "Z_VIX",
                "Z_Credit",
                "MSI"
            ],
            inplace=True
        )

        # --------------------------------------------------
        # 6. 저장
        # --------------------------------------------------
        os.makedirs(
            DATA_FEATURES_DIR,
            exist_ok=True
        )

        output_df = df[
            [
                "SPY",
                "VIX",
                "BAA_Treasury_Spread",
                "MSI"
            ]
        ].copy()

        output_df.to_csv(self.output_path)

        logger.info(
            f"Market Stress Index successfully saved to: "
            f"{self.output_path}"
        )

        logger.info(
            f"MSI Dataset Shape: {output_df.shape}"
        )

        logger.info(
            f"MSI Start Date: {output_df.index.min()}"
        )

        logger.info(
            f"MSI End Date: {output_df.index.max()}"
        )

        return output_df


if __name__ == "__main__":
    calc = StressIndexCalculator()
    calc.calculate_msi()