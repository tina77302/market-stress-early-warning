import numpy as np
import pandas as pd
import pytest

from src.models.evaluation import ModelEvaluator
from src.models.early_warning_evaluation import EarlyWarningEvaluator
from tests.conftest import make_oos_predictions


# --------------------------------------------------------------------------
# ModelEvaluator
# --------------------------------------------------------------------------

def test_binary_metrics_against_hand_counted_confusion_matrix():
    y_true = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    y_prob = np.array([0.9, 0.6, 0.4, 0.2, 0.7, 0.3, 0.1, 0.55, 0.05, 0.0])
    #            pred  1    1    0    0    1    0    0    1     0    0
    m = ModelEvaluator.calculate_binary_metrics(y_true, y_prob, threshold=0.5)

    assert (m["TP"], m["FP"], m["TN"], m["FN"]) == (2, 2, 4, 2)
    assert m["Precision"] == pytest.approx(0.5)
    assert m["Recall"] == pytest.approx(0.5)
    assert m["F1"] == pytest.approx(0.5)
    assert m["False Alarm Rate"] == pytest.approx(2 / 6)
    assert m["Missed Event Rate"] == pytest.approx(2 / 4)
    assert m["Threshold"] == 0.5


def test_binary_metrics_threshold_is_inclusive():
    m = ModelEvaluator.calculate_binary_metrics(
        np.array([1, 0]), np.array([0.5, 0.49]), threshold=0.5
    )
    assert (m["TP"], m["FP"], m["TN"], m["FN"]) == (1, 0, 1, 0)


def test_binary_metrics_undefined_rates_are_nan():
    all_negative = ModelEvaluator.calculate_binary_metrics(
        np.zeros(5, dtype=int), np.linspace(0, 1, 5), 0.5
    )
    assert np.isnan(all_negative["Missed Event Rate"])
    assert all_negative["Precision"] == 0  # zero_division guard

    all_positive = ModelEvaluator.calculate_binary_metrics(
        np.ones(5, dtype=int), np.linspace(0, 1, 5), 0.5
    )
    assert np.isnan(all_positive["False Alarm Rate"])


def test_load_data_requires_columns(data_dirs):
    df = make_oos_predictions().drop(columns=["Prob_XGBoost"])
    df.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions.csv")

    with pytest.raises(ValueError, match="Prob_XGBoost"):
        ModelEvaluator().load_data()


def test_evaluate_overall_perfect_scores(data_dirs):
    df = make_oos_predictions()
    df["Prob_Logistic"] = df["Actual_Target"].astype(float)
    df["Prob_XGBoost"] = df["Actual_Target"].astype(float)
    df.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions.csv")

    res = ModelEvaluator().evaluate_overall()

    assert list(res["Model"]) == ["Logistic Regression", "XGBoost"]
    assert (res["ROC-AUC"] == 1.0).all()
    assert (res["PR-AUC (AP)"] == 1.0).all()
    assert (res["Brier Score"] == 0.0).all()
    assert (res["F1"] == 1.0).all()
    assert (res["False Alarm Rate"] == 0.0).all()
    assert (res["Missed Event Rate"] == 0.0).all()


def test_evaluate_overall_informative_scores_beat_chance(data_dirs):
    df = make_oos_predictions()
    df.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions.csv")

    res = ModelEvaluator().evaluate_overall().set_index("Model")
    prevalence = df["Actual_Target"].mean()

    for model in ["Logistic Regression", "XGBoost"]:
        assert res.loc[model, "ROC-AUC"] > 0.8
        assert res.loc[model, "PR-AUC (AP)"] > prevalence
        assert 0 <= res.loc[model, "Brier Score"] <= 0.25


def test_threshold_grid_is_monotone(data_dirs):
    df = make_oos_predictions()
    df.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions.csv")

    grid = ModelEvaluator().evaluate_threshold_grid()

    assert sorted(grid["Threshold"].unique()) == [0.3, 0.4, 0.5, 0.6, 0.7]
    for _, sub in grid.groupby("Model"):
        sub = sub.sort_values("Threshold")
        # Raising the threshold can only lower recall and the false-alarm rate.
        assert sub["Recall"].is_monotonic_decreasing
        assert sub["False Alarm Rate"].is_monotonic_decreasing


def test_historical_events_only_covered_periods(data_dirs):
    # Synthetic data covers 2020-02 .. 2021-04 only.
    df = make_oos_predictions(n=300, start="2020-02-03")
    df.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions.csv")

    events = ModelEvaluator().evaluate_historical_events()

    assert set(events["Event"]) == {"2020 COVID-19 Crash"}
    row = events.iloc[0]
    sub = df.loc["2020-02-01":"2020-04-30"]
    assert row["Days"] == len(sub)
    assert row["Actual Stress Days"] == int(sub["Actual_Target"].sum())
    assert row["XGB >= 0.5 Days"] == int((sub["Prob_XGBoost"] >= 0.5).sum())


# --------------------------------------------------------------------------
# EarlyWarningEvaluator
# --------------------------------------------------------------------------

def _episode_frame(events, prob):
    dates = pd.bdate_range("2021-01-04", periods=len(events))
    return pd.DataFrame(
        {
            "Is_Stress_Event": events,
            "Prob_Logistic": prob,
            "Prob_XGBoost": prob,
            "Actual_Target": events,
        },
        index=pd.Index(dates, name="Date"),
    )


def test_event_onsets_and_ends():
    df = _episode_frame([0, 0, 1, 1, 0, 0, 0, 1, 0, 1], [0.0] * 10)
    ev = EarlyWarningEvaluator()

    onsets = ev.identify_event_onsets(df)
    ends = ev.identify_event_ends(df)

    assert onsets == [df.index[2], df.index[7], df.index[9]]
    # An episode still open on the final row is closed on that row.
    assert ends == [df.index[3], df.index[7], df.index[9]]

    table = ev.build_event_table(df)
    assert list(table["Event_ID"]) == [1, 2, 3]
    assert list(table["Onset"]) == onsets
    assert list(table["End"]) == [df.index[3], df.index[7], df.index[-1]]


def test_event_table_starting_in_stress():
    df = _episode_frame([1, 1, 0, 0], [0.0] * 4)
    table = EarlyWarningEvaluator().build_event_table(df)
    assert len(table) == 1
    assert table.loc[0, "Onset"] == df.index[0]
    assert table.loc[0, "End"] == df.index[1]


def test_pre_event_warning_detection_and_lead_time():
    events = [0, 0, 0, 1, 1, 0, 0, 0, 0, 1]
    prob = [0.1, 0.7, 0.2, 0.9, 0.9, 0.1, 0.1, 0.1, 0.6, 0.9]
    df = _episode_frame(events, prob)

    ev = EarlyWarningEvaluator(threshold=0.5, lookback_days=3)
    table = ev.build_event_table(df)
    res = ev.evaluate_model_on_events(df, table, "Prob_XGBoost", "XGBoost")

    first = res.iloc[0]
    assert first["Detected_Pre_Event"]
    assert first["First_Warning"] == df.index[1]
    assert first["First_Warning_Lead_Days"] == 2
    assert first["Event_Length"] == 2
    assert first["Max_Pre_Event_Prob"] == pytest.approx(0.7)

    second = res.iloc[1]
    assert second["Detected_Pre_Event"]
    assert second["First_Warning_Lead_Days"] == 1
    assert second["Event_Length"] == 1


def test_pre_event_no_warning():
    df = _episode_frame([0, 0, 0, 1], [0.1, 0.2, 0.3, 0.9])
    ev = EarlyWarningEvaluator(threshold=0.5, lookback_days=3)
    res = ev.evaluate_model_on_events(df, ev.build_event_table(df), "Prob_XGBoost", "X")

    assert not res.loc[0, "Detected_Pre_Event"]
    assert pd.isna(res.loc[0, "First_Warning"])
    assert np.isnan(res.loc[0, "First_Warning_Lead_Days"])
    assert res.loc[0, "Max_Pre_Event_Prob"] == pytest.approx(0.3)


def test_evaluate_end_to_end_with_files(data_dirs):
    pred = make_oos_predictions(n=120)
    pred.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions.csv")

    targets = pd.DataFrame(
        {"Is_Stress_Event": pred["Actual_Target"].values}, index=pred.index
    )
    targets.to_csv(data_dirs.DATA_FEATURES_DIR / "targets.csv")

    summary, results = EarlyWarningEvaluator(threshold=0.5, lookback_days=10).evaluate()

    assert set(summary["Model"]) == {"Logistic Regression", "XGBoost"}
    n_episodes = len(EarlyWarningEvaluator().build_event_table(
        pred.assign(Is_Stress_Event=pred["Actual_Target"])
    ))
    assert (summary["Stress Episodes"] == n_episodes).all()
    assert summary["Detection Rate"].between(0, 1).all()
    assert len(results) == 2 * n_episodes


def test_evaluate_requires_labels_for_every_oos_date(data_dirs):
    pred = make_oos_predictions(n=50)
    pred.to_csv(data_dirs.DATA_PROCESSED_DIR / "oos_predictions.csv")
    pd.DataFrame(
        {"Is_Stress_Event": [0] * 40}, index=pred.index[:40]
    ).to_csv(data_dirs.DATA_FEATURES_DIR / "targets.csv")

    with pytest.raises(ValueError, match="Is_Stress_Event"):
        EarlyWarningEvaluator().load_data()
