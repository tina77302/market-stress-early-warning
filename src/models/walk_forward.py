import os
import pandas as pd
import numpy as np
import joblib
import logging

from src.config import (
    DATA_FEATURES_DIR,
    DATA_PROCESSED_DIR,
    MODELS_DIR
)

from src.models.logistic import build_logistic_model
from src.models.xgboost_model import build_xgboost_model


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WalkForwardValidator:

    def __init__(
        self,
        input_filename="feature_matrix.csv",
        initial_train_years=5,
        step_months=1,
        embargo_days=10
    ):
        self.input_path = DATA_FEATURES_DIR / input_filename
        self.output_path = DATA_PROCESSED_DIR / "oos_predictions.csv"

        # 약 252 거래일 = 1년
        self.min_train_size = initial_train_years * 252

        # 약 21 거래일 = 1개월
        self.step_size = step_months * 21

        # Target_10D의 forward horizon과 동일한 embargo
        self.embargo_days = embargo_days

    def run_validation(self):

        logger.info(
            f"Reading feature matrix from {self.input_path}"
        )

        df = pd.read_csv(
            self.input_path,
            index_col="Date",
            parse_dates=True
        )

        df.sort_index(inplace=True)

        target_col = "Target_10D"

        # --------------------------------------------------
        # 1. ML Feature Whitelist
        # --------------------------------------------------

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

        missing_features = [
            col for col in feature_cols
            if col not in df.columns
        ]

        if missing_features:
            raise ValueError(
                f"Missing required features: {missing_features}"
            )

        X = df[feature_cols]
        y = df[target_col]

        n_samples = len(df)

        logger.info(
            f"Total samples: {n_samples}"
        )

        logger.info(
            f"Initial train size: {self.min_train_size}"
        )

        logger.info(
            f"Step size: {self.step_size}"
        )

        logger.info(
            f"Embargo: {self.embargo_days} trading days"
        )

        logger.info(
            f"Number of ML features: {len(feature_cols)}"
        )

        # --------------------------------------------------
        # 2. OOS Result Container
        # --------------------------------------------------

        results = pd.DataFrame(
            index=df.index
        )

        results["Actual_Target"] = y
        results["MSI"] = df["MSI"]
        results["SPY"] = df["SPY"]
        results["VIX"] = df["VIX"]

        results["BAA_Treasury_Spread"] = (
            df["BAA_Treasury_Spread"]
        )

        results["Prob_Logistic"] = np.nan
        results["Prob_XGBoost"] = np.nan

        current_test_start = self.min_train_size
        fold_count = 0

        # --------------------------------------------------
        # 3. Expanding Walk-Forward Validation
        # --------------------------------------------------

        while current_test_start < n_samples:

            test_end = min(
                current_test_start + self.step_size,
                n_samples
            )

            # ----------------------------------------------
            # Embargo
            #
            # Target_10D(t)는 t+1 ~ t+10 정보를 사용하므로
            # test 시작 직전 10개 observation을 train에서 제외.
            # ----------------------------------------------

            train_end = (
                current_test_start
                - self.embargo_days
            )

            if train_end <= 0:
                raise ValueError(
                    "Training window is empty after embargo."
                )

            X_train = X.iloc[:train_end]
            y_train = y.iloc[:train_end]

            X_test = X.iloc[
                current_test_start:test_end
            ]

            y_test = y.iloc[
                current_test_start:test_end
            ]

            if len(X_test) == 0:
                break

            # ----------------------------------------------
            # QA
            # ----------------------------------------------

            if y_train.nunique() < 2:
                raise ValueError(
                    f"Fold {fold_count + 1}: "
                    "training data contains only one class."
                )

            neg_count = (y_train == 0).sum()
            pos_count = (y_train == 1).sum()

            scale_pos_weight = (
                neg_count / (pos_count + 1e-8)
            )

            logger.info(
                f"Fold {fold_count + 1}: "
                f"Train={len(X_train)}, "
                f"Embargo={self.embargo_days}, "
                f"Test={len(X_test)}, "
                f"Train End={X_train.index[-1].date()}, "
                f"Test Start={X_test.index[0].date()}, "
                f"Test End={X_test.index[-1].date()}, "
                f"Positive Rate={y_train.mean():.2%}"
            )

            # ----------------------------------------------
            # Logistic Regression
            # ----------------------------------------------

            model_log = build_logistic_model()

            model_log.fit(
                X_train,
                y_train
            )

            prob_log = model_log.predict_proba(
                X_test
            )[:, 1]

            # ----------------------------------------------
            # XGBoost
            # ----------------------------------------------

            model_xgb = build_xgboost_model(
                scale_pos_weight=scale_pos_weight
            )

            model_xgb.fit(
                X_train,
                y_train
            )

            prob_xgb = model_xgb.predict_proba(
                X_test
            )[:, 1]

            # ----------------------------------------------
            # Store strictly OOS predictions
            # ----------------------------------------------

            results.loc[
                X_test.index,
                "Prob_Logistic"
            ] = prob_log

            results.loc[
                X_test.index,
                "Prob_XGBoost"
            ] = prob_xgb

            current_test_start = test_end
            fold_count += 1

        logger.info(
            f"Completed {fold_count} "
            "Walk-Forward folds."
        )

        # --------------------------------------------------
        # 4. OOS Results
        # --------------------------------------------------

        oos_results = results.dropna(
            subset=[
                "Prob_Logistic",
                "Prob_XGBoost"
            ]
        ).copy()

        if oos_results.empty:
            raise ValueError(
                "No OOS predictions were generated."
            )

        logger.info(
            f"OOS Start Date: "
            f"{oos_results.index.min()}"
        )

        logger.info(
            f"OOS End Date: "
            f"{oos_results.index.max()}"
        )

        logger.info(
            f"OOS Dataset Shape: "
            f"{oos_results.shape}"
        )

        # --------------------------------------------------
        # 5. Save OOS Predictions
        # --------------------------------------------------

        os.makedirs(
            DATA_PROCESSED_DIR,
            exist_ok=True
        )

        os.makedirs(
            MODELS_DIR,
            exist_ok=True
        )

        oos_results.to_csv(
            self.output_path
        )

        logger.info(
            f"OOS predictions saved to: "
            f"{self.output_path}"
        )

        # --------------------------------------------------
        # 6. Final Deployment Models
        #
        # Walk-forward evaluation이 끝난 뒤,
        # 현재 사용 가능한 모든 labeled data로 별도 재학습.
        # 이 모델은 실시간/웹 추론용이며
        # OOS 성능 평가에는 사용하지 않음.
        # --------------------------------------------------

        final_neg = (y == 0).sum()
        final_pos = (y == 1).sum()

        final_scale_pos_weight = (
            final_neg / (final_pos + 1e-8)
        )

        final_log = build_logistic_model()

        final_log.fit(
            X,
            y
        )

        final_xgb = build_xgboost_model(
            scale_pos_weight=final_scale_pos_weight
        )

        final_xgb.fit(
            X,
            y
        )

        joblib.dump(
            final_log,
            MODELS_DIR / "logistic_latest.joblib"
        )

        joblib.dump(
            final_xgb,
            MODELS_DIR / "xgboost_latest.joblib"
        )

        logger.info(
            "Final deployment models trained "
            "on all currently labeled observations."
        )

        logger.info(
            f"Latest models saved in: {MODELS_DIR}"
        )

        return oos_results


if __name__ == "__main__":
    validator = WalkForwardValidator()
    validator.run_validation()