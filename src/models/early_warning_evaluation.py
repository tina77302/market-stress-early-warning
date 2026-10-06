import logging
import numpy as np
import pandas as pd

from src.config import DATA_PROCESSED_DIR, DATA_FEATURES_DIR


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class EarlyWarningEvaluator:
    def __init__(
        self,
        prediction_filename="oos_predictions.csv",
        target_filename="targets.csv",
        threshold=0.5,
        lookback_days=10,
    ):
        self.prediction_path = DATA_PROCESSED_DIR / prediction_filename
        self.target_path = DATA_FEATURES_DIR / target_filename

        self.threshold = threshold
        self.lookback_days = lookback_days

    def load_data(self):
        """
        Merge strictly OOS model probabilities with the
        independently generated stress-event labels.
        """

        pred = pd.read_csv(
            self.prediction_path,
            index_col="Date",
            parse_dates=True
        ).sort_index()

        targets = pd.read_csv(
            self.target_path,
            index_col="Date",
            parse_dates=True
        ).sort_index()

        required_pred = [
            "Actual_Target",
            "Prob_Logistic",
            "Prob_XGBoost",
        ]

        required_target = [
            "Is_Stress_Event",
        ]

        missing_pred = [
            c for c in required_pred
            if c not in pred.columns
        ]

        missing_target = [
            c for c in required_target
            if c not in targets.columns
        ]

        if missing_pred:
            raise ValueError(
                f"Missing prediction columns: {missing_pred}"
            )

        if missing_target:
            raise ValueError(
                f"Missing target columns: {missing_target}"
            )

        # Only OOS dates are retained.
        df = pred.join(
            targets[["Is_Stress_Event"]],
            how="left"
        )

        if df["Is_Stress_Event"].isna().any():
            raise ValueError(
                "Some OOS dates do not have Is_Stress_Event labels."
            )

        df["Is_Stress_Event"] = (
            df["Is_Stress_Event"].astype(int)
        )

        return df

    @staticmethod
    def identify_event_onsets(df):
        """
        Stress onset = first trading day of each contiguous
        Is_Stress_Event == 1 episode.

        This avoids manually choosing crisis dates.
        """

        previous = df["Is_Stress_Event"].shift(1).fillna(0)

        onset_mask = (
            (df["Is_Stress_Event"] == 1)
            & (previous == 0)
        )

        return df.index[onset_mask].tolist()

    @staticmethod
    def identify_event_ends(df):
        """
        Find the final trading day of each contiguous
        stress episode.
        """

        next_value = df["Is_Stress_Event"].shift(-1).fillna(0)

        end_mask = (
            (df["Is_Stress_Event"] == 1)
            & (next_value == 0)
        )

        return df.index[end_mask].tolist()

    def build_event_table(self, df):
        """
        Pair each algorithmically identified stress onset
        with its corresponding contiguous episode end.
        """

        onsets = self.identify_event_onsets(df)
        ends = self.identify_event_ends(df)

        events = []

        end_pointer = 0

        for event_id, onset in enumerate(onsets, start=1):

            while (
                end_pointer < len(ends)
                and ends[end_pointer] < onset
            ):
                end_pointer += 1

            if end_pointer >= len(ends):
                event_end = df.index[-1]
            else:
                event_end = ends[end_pointer]
                end_pointer += 1

            events.append({
                "Event_ID": event_id,
                "Onset": onset,
                "End": event_end,
            })

        return pd.DataFrame(events)

    def evaluate_model_on_events(
        self,
        df,
        event_table,
        probability_column,
        model_name,
    ):
        """
        For each stress episode:

        1. Look only at the N trading observations immediately
           BEFORE the stress onset.
        2. Determine whether the model crossed the fixed
           threshold before the event.
        3. Report first warning and lead time.

        Lead time is measured in trading observations.

        No future information is used to generate the model
        probabilities themselves; all probabilities come from
        the existing walk-forward OOS predictions.
        """

        rows = []

        for _, event in event_table.iterrows():

            onset = event["Onset"]
            event_end = event["End"]

            onset_position = df.index.get_loc(onset)

            lookback_start = max(
                0,
                onset_position - self.lookback_days
            )

            pre_event = df.iloc[
                lookback_start:onset_position
            ].copy()

            alerts = pre_event[
                pre_event[probability_column]
                >= self.threshold
            ]

            detected = len(alerts) > 0

            first_warning = pd.NaT
            last_warning = pd.NaT
            first_warning_lead = np.nan
            last_warning_lead = np.nan
            max_pre_event_prob = np.nan

            if len(pre_event) > 0:
                max_pre_event_prob = (
                    pre_event[probability_column].max()
                )

            if detected:
                first_warning = alerts.index[0]
                last_warning = alerts.index[-1]

                # Number of trading observations from
                # warning date to onset.
                first_pos = df.index.get_loc(first_warning)
                last_pos = df.index.get_loc(last_warning)

                first_warning_lead = (
                    onset_position - first_pos
                )

                last_warning_lead = (
                    onset_position - last_pos
                )

            rows.append({
                "Model": model_name,
                "Event_ID": event["Event_ID"],
                "Stress_Onset": onset,
                "Stress_End": event_end,
                "Event_Length":
                    df.loc[onset:event_end].shape[0],
                "Detected_Pre_Event": detected,
                "First_Warning": first_warning,
                "First_Warning_Lead_Days":
                    first_warning_lead,
                "Last_Warning": last_warning,
                "Last_Warning_Lead_Days":
                    last_warning_lead,
                "Max_Pre_Event_Prob":
                    max_pre_event_prob,
            })

        return pd.DataFrame(rows)

    def evaluate(self):
        df = self.load_data()

        event_table = self.build_event_table(df)

        logger.info(
            f"OOS stress episodes found: {len(event_table)}"
        )

        logistic = self.evaluate_model_on_events(
            df=df,
            event_table=event_table,
            probability_column="Prob_Logistic",
            model_name="Logistic Regression",
        )

        xgboost = self.evaluate_model_on_events(
            df=df,
            event_table=event_table,
            probability_column="Prob_XGBoost",
            model_name="XGBoost",
        )

        results = pd.concat(
            [logistic, xgboost],
            ignore_index=True
        )

        summary_rows = []

        for model_name, sub in results.groupby("Model"):

            detected = sub["Detected_Pre_Event"]

            detected_sub = sub[detected]

            detection_rate = (
                detected.mean()
                if len(sub) > 0
                else np.nan
            )

            median_first_lead = (
                detected_sub[
                    "First_Warning_Lead_Days"
                ].median()
                if len(detected_sub) > 0
                else np.nan
            )

            mean_first_lead = (
                detected_sub[
                    "First_Warning_Lead_Days"
                ].mean()
                if len(detected_sub) > 0
                else np.nan
            )

            summary_rows.append({
                "Model": model_name,
                "Stress Episodes": len(sub),
                "Detected Episodes":
                    int(detected.sum()),
                "Detection Rate":
                    detection_rate,
                "Median First Warning Lead":
                    median_first_lead,
                "Mean First Warning Lead":
                    mean_first_lead,
            })

        summary = pd.DataFrame(summary_rows)

        logger.info(
            "\nEARLY WARNING SUMMARY "
            f"(Threshold={self.threshold}, "
            f"Lookback={self.lookback_days} trading days)\n"
            + summary.round(4).to_string(index=False)
        )

        logger.info(
            "\nFIRST 20 EVENT-LEVEL RESULTS\n"
            + results.head(20).round(4).to_string(index=False)
        )

        return summary, results


if __name__ == "__main__":

    evaluator = EarlyWarningEvaluator(
        threshold=0.5,
        lookback_days=10,
    )

    evaluator.evaluate()
    
    if __name__ == "__main__":

    validator = MultiHorizonValidator()

    df = pd.read_csv(
        validator.input_path,
        index_col="Date",
        parse_dates=True
    )

    df.sort_index(inplace=True)

    os.makedirs(
        DATA_PROCESSED_DIR,
        exist_ok=True
    )

    all_metrics = []

    for horizon in HORIZONS:

        logger.info(
            f"========== {horizon}D VALIDATION =========="
        )

        oos_results = validator.run_horizon(
            df,
            horizon
        )

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
            f"{horizon}D OOS predictions saved to: "
            f"{output_path}"
        )

    metrics_df = pd.concat(
        all_metrics,
        ignore_index=True
    )

    metrics_path = (
        DATA_PROCESSED_DIR
        / "multi_horizon_metrics.csv"
    )

    metrics_df.to_csv(
        metrics_path,
        index=False
    )

    print("\n")
    print("=" * 100)
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