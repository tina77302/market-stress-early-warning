import os
import numpy as np
import pandas as pd
import logging

from src.config import (
    DATA_PROCESSED_DIR,
    DATA_FEATURES_DIR
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FeatureEngineer:
    def __init__(
        self,
        input_filename="cleaned_market_data.csv",
        target_filename="targets.csv",
        output_filename="feature_matrix.csv"
    ):
        self.input_path = DATA_PROCESSED_DIR / input_filename
        self.target_path = DATA_FEATURES_DIR / target_filename
        self.output_path = DATA_FEATURES_DIR / output_filename

    def generate_features(self):

        logger.info(
            f"Reading cleaned market data from {self.input_path}"
        )

        # --------------------------------------------------
        # 1. Clean market data에서 X 독립 생성
        # --------------------------------------------------
        df = pd.read_csv(
            self.input_path,
            index_col="Date",
            parse_dates=True
        )

        df.sort_index(inplace=True)

        # ==================================================
        # SPY FEATURES
        # ==================================================

        df["SPY_1D_Return"] = df["SPY"].pct_change(1)
        df["SPY_5D_Return"] = df["SPY"].pct_change(5)
        df["SPY_20D_Return"] = df["SPY"].pct_change(20)

        df["SPY_20D_Vol"] = (
            df["SPY_1D_Return"]
            .rolling(20)
            .std()
            * np.sqrt(252)
        )

        df["SPY_60D_Vol"] = (
            df["SPY_1D_Return"]
            .rolling(60)
            .std()
            * np.sqrt(252)
        )

        # 현재까지 관측된 역사적 고점 대비 drawdown
        historical_peak = df["SPY"].cummax()

        df["SPY_Drawdown"] = (
            (df["SPY"] - historical_peak)
            / historical_peak
        )

        df["SPY_20D_Momentum"] = (
            df["SPY"]
            / df["SPY"].rolling(20).mean()
            - 1.0
        )

        # ==================================================
        # VIX FEATURES
        # ==================================================

        df["VIX_Level"] = df["VIX"]

        df["VIX_1D_Change"] = (
            df["VIX"].diff(1)
        )

        df["VIX_5D_Change"] = (
            df["VIX"].diff(5)
        )

        df["VIX_20D_Momentum"] = (
            df["VIX"]
            / df["VIX"].rolling(20).mean()
            - 1.0
        )

        # t의 VIX를 t-1까지의 과거 분포와 비교
        vix_history = df["VIX"].shift(1)

        vix_mean = (
            vix_history
            .rolling(252, min_periods=60)
            .mean()
        )

        vix_std = (
            vix_history
            .rolling(252, min_periods=60)
            .std()
        )

        df["VIX_252D_ZScore"] = (
            (df["VIX"] - vix_mean)
            / (vix_std + 1e-8)
        )

        # ==================================================
        # CREDIT FEATURES
        # ==================================================

        df["Credit_Level"] = (
            df["BAA_Treasury_Spread"]
        )

        df["Credit_1D_Change"] = (
            df["BAA_Treasury_Spread"].diff(1)
        )

        df["Credit_5D_Change"] = (
            df["BAA_Treasury_Spread"].diff(5)
        )

        df["Credit_20D_Momentum"] = (
            df["BAA_Treasury_Spread"]
            / df["BAA_Treasury_Spread"]
            .rolling(20)
            .mean()
            - 1.0
        )

        # t의 spread를 t-1까지의 과거 분포와 비교
        credit_history = (
            df["BAA_Treasury_Spread"].shift(1)
        )

        credit_mean = (
            credit_history
            .rolling(252, min_periods=60)
            .mean()
        )

        credit_std = (
            credit_history
            .rolling(252, min_periods=60)
            .std()
        )

        df["Credit_252D_ZScore"] = (
            (
                df["BAA_Treasury_Spread"]
                - credit_mean
            )
            / (credit_std + 1e-8)
        )

        # ==================================================
        # 2. Feature 계산 불가능한 초기 구간 제거
        # ==================================================

        feature_cols = [
            "SPY_1D_Return",
            "SPY_5D_Return",
            "SPY_20D_Return",
            "SPY_20D_Vol",
            "SPY_60D_Vol",
            "SPY_Drawdown",
            "SPY_20D_Momentum",
            "VIX_Level",
            "VIX_1D_Change",
            "VIX_5D_Change",
            "VIX_20D_Momentum",
            "VIX_252D_ZScore",
            "Credit_Level",
            "Credit_1D_Change",
            "Credit_5D_Change",
            "Credit_20D_Momentum",
            "Credit_252D_ZScore"
        ]

        before = len(df)

        df.dropna(
            subset=feature_cols,
            inplace=True
        )

        logger.info(
            f"Dropped {before - len(df)} rows "
            "due to feature warm-up."
        )
        # ==================================================
        # 2-1. 최신 inference용 feature 저장
        # ==================================================

        os.makedirs(
            DATA_FEATURES_DIR,
            exist_ok=True
        )

        latest_features_path = (
            DATA_FEATURES_DIR / "latest_features.csv"
        )

        latest_feature_df = df[
            [
                "SPY",
                "VIX",
                "BAA_Treasury_Spread"
            ] + feature_cols
        ].copy()

        latest_feature_df.to_csv(
            latest_features_path
        )

        logger.info(
            f"Latest inference features saved to: "
            f"{latest_features_path}"
        )

        logger.info(
            f"Latest Feature Date: "
            f"{latest_feature_df.index.max()}"
        )

        logger.info(
            f"Latest Feature Shape: "
            f"{latest_feature_df.shape}"
        )

        # ==================================================
        # 3. Target을 별도로 불러와 Date 기준 병합
        # ==================================================

        logger.info(
            f"Reading targets from {self.target_path}"
        )

        targets = pd.read_csv(
            self.target_path,
            index_col="Date",
            parse_dates=True
        )

        target_cols = [
            "MSI",
            "Stress_Threshold",
            "Is_Stress_Event",
            "Target_10D"
        ]

        targets = targets[target_cols]

        # X와 y가 모두 존재하는 날짜만 사용
        final_df = df.join(
            targets,
            how="inner"
        )

        final_df.sort_index(inplace=True)

        # ==================================================
        # 4. QA
        # ==================================================

        if final_df.index.duplicated().any():
            raise ValueError(
                "Duplicate dates found in feature matrix."
            )

        if final_df[
            feature_cols + ["Target_10D"]
        ].isna().any().any():
            raise ValueError(
                "Missing values remain in final feature matrix."
            )

        logger.info(
            f"Final Dataset Start: {final_df.index.min()}"
        )

        logger.info(
            f"Final Dataset End: {final_df.index.max()}"
        )

        logger.info(
            f"Positive Target Rate: "
            f"{final_df['Target_10D'].mean():.2%}"
        )

        # ==================================================
        # 5. 저장
        # ==================================================

        os.makedirs(
            DATA_FEATURES_DIR,
            exist_ok=True
        )

        final_df.to_csv(
            self.output_path
        )

        logger.info(
            f"Feature matrix saved to: "
            f"{self.output_path}"
        )

        logger.info(
            f"Feature Matrix Shape: "
            f"{final_df.shape}"
        )

        logger.info(
            f"Generated {len(feature_cols)} ML Features: "
            f"{feature_cols}"
        )

        return final_df


if __name__ == "__main__":
    engineer = FeatureEngineer()
    engineer.generate_features()