import os
import logging

import numpy as np
import pandas as pd

from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)

from src.config import (
    DATA_FEATURES_DIR,
    DATA_PROCESSED_DIR,
)

from src.models.logistic import build_logistic_model
from src.models.xgboost_model import build_xgboost_model


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


HORIZONS = [1, 5, 10, 20]

FEATURE_COLS = [
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
    "Credit_252D_ZScore",
]

class MultiHorizonValidator:

    def __init__(
        self,
        input_filename="feature_matrix.csv",
        initial_train_years=5,
        step_months=1,
    ):
        self.input_path = DATA_FEATURES_DIR / input_filename

        # 기존 walk-forward와 동일
        self.min_train_size = initial_train_years * 252
        self.step_size = step_months * 21

    def prepare_horizon_data(self, df, horizon):
        target_col = f"Target_{horizon}D"

        if target_col not in df.columns:
            raise ValueError(
                f"Missing target column: {target_col}"
            )

        # 해당 horizon의 미래 label이 실제 존재하는 행만 사용
        hdf = df.dropna(
            subset=[target_col]
        ).copy()

        hdf[target_col] = hdf[target_col].astype(int)

        # Horizon과 동일한 label-overlap purge
        purge_days = horizon

        logger.info(
            f"{horizon}D | "
            f"Samples={len(hdf)} | "
            f"Positive Rate={hdf[target_col].mean():.2%} | "
            f"Purge={purge_days}"
        )

        return hdf, target_col, purge_days
        
    def run_horizon(self, df, horizon):

        hdf, target_col, purge_days = (
            self.prepare_horizon_data(df, horizon)
        )

        X = hdf[FEATURE_COLS]
        y = hdf[target_col]

        n_samples = len(hdf)

        results = pd.DataFrame(index=hdf.index)
        results["Actual_Target"] = y
        results["MSI"] = hdf["MSI"]
        results["SPY"] = hdf["SPY"]
        results["VIX"] = hdf["VIX"]
        results["BAA_Treasury_Spread"] = (
            hdf["BAA_Treasury_Spread"]
        )

        results["Prob_Logistic"] = np.nan
        results["Prob_XGBoost"] = np.nan

        current_test_start = self.min_train_size
        fold_count = 0

        while current_test_start < n_samples:

            test_end = min(
                current_test_start + self.step_size,
                n_samples
            )

            # label-overlap purge
            train_end = current_test_start - purge_days

            if train_end <= 0:
                raise ValueError(
                    f"{horizon}D: training window empty "
                    "after purge."
                )

            X_train = X.iloc[:train_end]
            y_train = y.iloc[:train_end]

            X_test = X.iloc[
                current_test_start:test_end
            ]

            if len(X_test) == 0:
                break

            if y_train.nunique() < 2:
                raise ValueError(
                    f"{horizon}D Fold {fold_count + 1}: "
                    "training data contains only one class."
                )

            neg_count = (y_train == 0).sum()
            pos_count = (y_train == 1).sum()

            scale_pos_weight = (
                neg_count / (pos_count + 1e-8)
            )

            # Logistic Regression
            model_log = build_logistic_model()

            model_log.fit(
                X_train,
                y_train
            )

            prob_log = model_log.predict_proba(
                X_test
            )[:, 1]

            # XGBoost
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

            # strictly OOS predictions
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

        oos_results = results.dropna(
            subset=[
                "Prob_Logistic",
                "Prob_XGBoost"
            ]
        ).copy()

        if oos_results.empty:
            raise ValueError(
                f"{horizon}D: no OOS predictions generated."
            )

        logger.info(
            f"{horizon}D completed | "
            f"Folds={fold_count} | "
            f"OOS={len(oos_results)} | "
            f"Start={oos_results.index.min().date()} | "
            f"End={oos_results.index.max().date()}"
        )

        return oos_results
    def calculate_metrics(self, oos_results, horizon):

        y_true = oos_results["Actual_Target"].astype(int)

        metrics_rows = []

        for model_name, prob_col in [
            ("Logistic", "Prob_Logistic"),
            ("XGBoost", "Prob_XGBoost"),
        ]:
            y_prob = oos_results[prob_col]
            y_pred = (y_prob >= 0.5).astype(int)

            tn, fp, fn, tp = confusion_matrix(
                y_true,
                y_pred,
                labels=[0, 1]
            ).ravel()

            far = fp / (fp + tn) if (fp + tn) > 0 else np.nan
            missed_rate = fn / (fn + tp) if (fn + tp) > 0 else np.nan

            metrics_rows.append({
                "Horizon": f"{horizon}D",
                "Model": model_name,
                "OOS_Observations": len(y_true),
                "Positive_Rate": y_true.mean(),
                "ROC_AUC": roc_auc_score(y_true, y_prob),
                "PR_AUC": average_precision_score(y_true, y_prob),
                "Brier": brier_score_loss(y_true, y_prob),
                "Precision_0.5": precision_score(
                    y_true, y_pred, zero_division=0
                ),
                "Recall_0.5": recall_score(
                    y_true, y_pred, zero_division=0
                ),
                "F1_0.5": f1_score(
                    y_true, y_pred, zero_division=0
                ),
                "FAR_0.5": far,
                "Missed_Rate_0.5": missed_rate,
                "TP": tp,
                "FP": fp,
                "TN": tn,
                "FN": fn,
                "OOS_Start": oos_results.index.min(),
                "OOS_End": oos_results.index.max(),
            })

        return pd.DataFrame(metrics_rows)

if __name__ == "__main__":

    validator = MultiHorizonValidator()

    df = pd.read_csv(
        validator.input_path,
        index_col="Date",
        parse_dates=True
    )
    df.sort_index(inplace=True)

    os.makedirs(DATA_PROCESSED_DIR, exist_ok=True)

    all_metrics = []

    for horizon in HORIZONS:
        logger.info(
            f"========== {horizon}D VALIDATION =========="
        )

        oos_results = validator.run_horizon(df, horizon)

        output_path = (
            DATA_PROCESSED_DIR
            / f"oos_predictions_{horizon}d.csv"
        )
        oos_results.to_csv(output_path)

        metrics = validator.calculate_metrics(
            oos_results,
            horizon
        )
        all_metrics.append(metrics)

        logger.info(
            f"{horizon}D predictions saved to: {output_path}"
        )

    metrics_df = pd.concat(
        all_metrics,
        ignore_index=True
    )

    metrics_path = (
        DATA_PROCESSED_DIR
        / "multi_horizon_metrics.csv"
    )

    metrics_df.to_csv(metrics_path, index=False)

    print("\n" + "=" * 100)
    print("MULTI-HORIZON OOS RESULTS")
    print("=" * 100)

    print(
        metrics_df[
            [
                "Horizon",
                "Model",
                "OOS_Observations",
                "Positive_Rate",
                "ROC_AUC",
                "PR_AUC",
                "Brier",
                "Precision_0.5",
                "Recall_0.5",
                "F1_0.5",
                "FAR_0.5",
                "Missed_Rate_0.5",
            ]
        ].to_string(index=False)
    )

    print("=" * 100)
    print(f"Metrics saved to: {metrics_path}")
