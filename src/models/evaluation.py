import pandas as pd
import numpy as np
import logging

from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    brier_score_loss,
)

from src.config import DATA_PROCESSED_DIR


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ModelEvaluator:
    def __init__(
        self,
        input_filename="oos_predictions.csv",
        default_threshold=0.5
    ):
        self.input_path = DATA_PROCESSED_DIR / input_filename
        self.default_threshold = default_threshold

    def load_data(self):
        logger.info(f"Reading OOS predictions from {self.input_path}")

        df = pd.read_csv(
            self.input_path,
            index_col="Date",
            parse_dates=True
        ).sort_index()

        required_cols = [
            "Actual_Target",
            "Prob_Logistic",
            "Prob_XGBoost",
            "MSI",
            "SPY",
            "VIX",
            "BAA_Treasury_Spread",
        ]

        missing = [c for c in required_cols if c not in df.columns]

        if missing:
            raise ValueError(
                f"Missing required columns in OOS predictions: {missing}"
            )

        return df

    @staticmethod
    def calculate_binary_metrics(y_true, y_prob, threshold):
        y_pred = (y_prob >= threshold).astype(int)

        tn, fp, fn, tp = confusion_matrix(
            y_true,
            y_pred,
            labels=[0, 1]
        ).ravel()

        precision = precision_score(
            y_true,
            y_pred,
            zero_division=0
        )

        recall = recall_score(
            y_true,
            y_pred,
            zero_division=0
        )

        f1 = f1_score(
            y_true,
            y_pred,
            zero_division=0
        )

        false_alarm_rate = (
            fp / (fp + tn)
            if (fp + tn) > 0
            else np.nan
        )

        missed_event_rate = (
            fn / (fn + tp)
            if (fn + tp) > 0
            else np.nan
        )

        return {
            "Threshold": threshold,
            "TP": tp,
            "FP": fp,
            "TN": tn,
            "FN": fn,
            "Precision": precision,
            "Recall": recall,
            "F1": f1,
            "False Alarm Rate": false_alarm_rate,
            "Missed Event Rate": missed_event_rate,
        }

    def evaluate_overall(self):
        """
        Evaluate strictly OOS predictions.

        ROC-AUC and PR-AUC are threshold-independent.

        Precision / Recall / F1 / False Alarm Rate are reported
        at the fixed baseline operating threshold of 0.50.

        Brier Score is included as a first diagnostic of
        probability calibration.
        """

        df = self.load_data()

        y_true = df["Actual_Target"].astype(int)

        prevalence = y_true.mean()

        logger.info(
            f"OOS Period: {df.index.min().date()} ~ "
            f"{df.index.max().date()}"
        )
        logger.info(f"OOS Observations: {len(df)}")
        logger.info(
            f"Positive Target Prevalence: {prevalence:.2%}"
        )

        models = {
            "Logistic Regression": df["Prob_Logistic"],
            "XGBoost": df["Prob_XGBoost"],
        }

        results = []

        for model_name, y_prob in models.items():

            roc_auc = roc_auc_score(y_true, y_prob)

            # Average Precision is used as the primary
            # summary metric for the precision-recall curve.
            pr_auc = average_precision_score(
                y_true,
                y_prob
            )

            brier = brier_score_loss(
                y_true,
                y_prob
            )

            binary = self.calculate_binary_metrics(
                y_true,
                y_prob,
                self.default_threshold
            )

            results.append({
                "Model": model_name,
                "ROC-AUC": roc_auc,
                "PR-AUC (AP)": pr_auc,
                "Brier Score": brier,
                **binary,
            })

        result_df = pd.DataFrame(results)

        logger.info(
            "\nOVERALL OOS PERFORMANCE\n" +
            result_df.round(4).to_string(index=False)
        )

        return result_df

    def evaluate_threshold_grid(self):
        """
        Diagnostic threshold table only.

        IMPORTANT:
        This table is NOT used to select the final threshold
        from the OOS test set.

        It only illustrates the operating trade-off between
        recall, precision, false alarms, and missed events.
        """

        df = self.load_data()

        y_true = df["Actual_Target"].astype(int)

        models = {
            "Logistic Regression": df["Prob_Logistic"],
            "XGBoost": df["Prob_XGBoost"],
        }

        thresholds = [
            0.30,
            0.40,
            0.50,
            0.60,
            0.70,
        ]

        rows = []

        for model_name, y_prob in models.items():
            for threshold in thresholds:

                metrics = self.calculate_binary_metrics(
                    y_true,
                    y_prob,
                    threshold
                )

                rows.append({
                    "Model": model_name,
                    **metrics,
                })

        threshold_df = pd.DataFrame(rows)

        logger.info(
            "\nTHRESHOLD SENSITIVITY "
            "(DIAGNOSTIC ONLY — NOT FOR OOS TUNING)\n" +
            threshold_df.round(4).to_string(index=False)
        )

        return threshold_df

    def evaluate_historical_events(self):
        """
        Descriptive analysis of OOS probabilities during
        major historical stress episodes.

        This is NOT yet an early-warning lead-time test.
        """

        df = self.load_data()

        events = {
            "2008 Financial Crisis":
                ("2007-10-01", "2009-03-31"),

            "2011 Eurozone / US Debt":
                ("2011-07-01", "2011-12-31"),

            "2015-2016 China / Oil Shock":
                ("2015-08-01", "2016-02-28"),

            "2018 Volatility Shock":
                ("2018-01-15", "2018-03-31"),

            "2020 COVID-19 Crash":
                ("2020-02-01", "2020-04-30"),

            "2022 Inflation / Rate Shock":
                ("2022-01-01", "2022-10-31"),

            "2023 US Banking Stress":
                ("2023-03-01", "2023-04-30"),
        }

        rows = []

        for event_name, (start_date, end_date) in events.items():

            sub = df.loc[start_date:end_date]

            if sub.empty:
                continue

            rows.append({
                "Event": event_name,
                "Start": start_date,
                "End": end_date,
                "Days": len(sub),

                "Actual Stress Days":
                    int(sub["Actual_Target"].sum()),

                "Logistic Avg Prob":
                    sub["Prob_Logistic"].mean(),

                "Logistic Max Prob":
                    sub["Prob_Logistic"].max(),

                "Logistic >= 0.5 Days":
                    int(
                        (sub["Prob_Logistic"] >= 0.5).sum()
                    ),

                "XGB Avg Prob":
                    sub["Prob_XGBoost"].mean(),

                "XGB Max Prob":
                    sub["Prob_XGBoost"].max(),

                "XGB >= 0.5 Days":
                    int(
                        (sub["Prob_XGBoost"] >= 0.5).sum()
                    ),
            })

        event_df = pd.DataFrame(rows)

        logger.info(
            "\nHISTORICAL EVENT DESCRIPTIVE ANALYSIS\n" +
            event_df.round(4).to_string(index=False)
        )

        return event_df


if __name__ == "__main__":

    evaluator = ModelEvaluator(
        default_threshold=0.5
    )

    evaluator.evaluate_overall()

    evaluator.evaluate_threshold_grid()

    evaluator.evaluate_historical_events()