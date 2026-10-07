from pathlib import Path
import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

OOS_PATH = Path("data/processed/oos_predictions_10d.csv")
TARGETS_PATH = Path("data/features/targets.csv")

OUTPUT_DIR = Path("data/processed/early_warning")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

THRESHOLD = 0.50

# How far BEFORE actual stress onset to search for warnings
LOOKBACK_DAYS = 20

# If stress disappears only briefly, treat it as the same episode.
# This prevents one prolonged crisis from being split into many
# tiny episodes.
COOLDOWN_DAYS = 10


# ============================================================
# LOAD DATA
# ============================================================

def load_data():

    print("\n========== LOAD DATA ==========")

    oos = pd.read_csv(
        OOS_PATH,
        index_col=0,
        parse_dates=True,
    )

    targets = pd.read_csv(
        TARGETS_PATH,
        index_col=0,
        parse_dates=True,
    )

    oos.index = pd.to_datetime(oos.index)
    targets.index = pd.to_datetime(targets.index)

    print(
        f"OOS     : {oos.index.min().date()} "
        f"→ {oos.index.max().date()} "
        f"| N={len(oos):,}"
    )

    print(
        f"Targets : {targets.index.min().date()} "
        f"→ {targets.index.max().date()} "
        f"| N={len(targets):,}"
    )

    # Flexible probability-column detection
    logistic_candidates = [
        "Prob_Logistic",
        "Logistic_Prob",
    ]

    xgb_candidates = [
        "Prob_XGBoost",
        "XGB_Prob",
    ]

    logistic_col = next(
        (
            c for c in logistic_candidates
            if c in oos.columns
        ),
        None,
    )

    xgb_col = next(
        (
            c for c in xgb_candidates
            if c in oos.columns
        ),
        None,
    )

    if logistic_col is None:
        raise ValueError(
            f"Logistic probability column not found. "
            f"Columns: {list(oos.columns)}"
        )

    if xgb_col is None:
        raise ValueError(
            f"XGBoost probability column not found. "
            f"Columns: {list(oos.columns)}"
        )

    if "Is_Stress_Event" not in targets.columns:
        raise ValueError(
            "Is_Stress_Event not found in targets.csv"
        )

    return (
        oos,
        targets,
        logistic_col,
        xgb_col,
    )


# ============================================================
# IDENTIFY ACTUAL STRESS EPISODES
# ============================================================

def identify_stress_episodes(
    stress_series,
    cooldown_days=10,
):

    """
    Identify stress episodes from ACTUAL Is_Stress_Event.

    IMPORTANT:
    We do NOT use Target_10D onset here because Target_10D
    becomes positive before the actual stress event by design.

    cooldown_days:
    If two stress clusters are separated by <= cooldown_days
    trading observations, they are treated as one episode.
    """

    stress = (
        stress_series
        .fillna(0)
        .astype(int)
    )

    stress_positions = np.flatnonzero(
        stress.values == 1
    )

    if len(stress_positions) == 0:
        return []

    episodes = []

    start_pos = stress_positions[0]
    prev_pos = stress_positions[0]

    for pos in stress_positions[1:]:

        gap = pos - prev_pos - 1

        if gap > cooldown_days:

            episodes.append(
                {
                    "start_pos": start_pos,
                    "end_pos": prev_pos,
                }
            )

            start_pos = pos

        prev_pos = pos

    episodes.append(
        {
            "start_pos": start_pos,
            "end_pos": prev_pos,
        }
    )

    return episodes


# ============================================================
# ANALYZE ONE MODEL
# ============================================================

def analyze_model(
    combined,
    episodes,
    prob_col,
    model_name,
):

    rows = []

    for episode_id, episode in enumerate(
        episodes,
        start=1,
    ):

        start_pos = episode["start_pos"]
        end_pos = episode["end_pos"]

        onset_date = combined.index[start_pos]
        end_date = combined.index[end_pos]

        # ----------------------------------------------------
        # Only count episodes whose onset is inside OOS period.
        # ----------------------------------------------------

        if onset_date < combined["OOS_Available"].idxmax():
            continue

        # Need actual OOS probability on/around episode.
        if not combined.loc[
            onset_date:end_date,
            "OOS_Available"
        ].any():
            continue

        # ----------------------------------------------------
        # PRE-STRESS WINDOW
        #
        # Search up to LOOKBACK_DAYS trading observations
        # BEFORE the actual Is_Stress_Event onset.
        # ----------------------------------------------------

        pre_start_pos = max(
            0,
            start_pos - LOOKBACK_DAYS,
        )

        pre_window = combined.iloc[
            pre_start_pos:start_pos
        ].copy()

        # OOS predictions only
        pre_window = pre_window[
            pre_window["OOS_Available"]
        ]

        warning_rows = pre_window[
            pre_window[prob_col] >= THRESHOLD
        ]

        detected_before = (
            len(warning_rows) > 0
        )

        if detected_before:

            # EARLIEST warning in the defined pre-stress window
            first_warning_date = (
                warning_rows.index[0]
            )

            warning_pos = (
                combined.index.get_loc(
                    first_warning_date
                )
            )

            lead_time = (
                start_pos - warning_pos
            )

            max_pre_score = (
                pre_window[prob_col].max()
            )

        else:

            first_warning_date = pd.NaT
            lead_time = np.nan

            max_pre_score = (
                pre_window[prob_col].max()
                if len(pre_window) > 0
                else np.nan
            )

        # Score at actual onset
        onset_score = (
            combined.loc[
                onset_date,
                prob_col,
            ]
            if pd.notna(
                combined.loc[
                    onset_date,
                    prob_col,
                ]
            )
            else np.nan
        )

        rows.append(
            {
                "Episode_ID":
                    episode_id,

                "Model":
                    model_name,

                "Stress_Onset":
                    onset_date,

                "Stress_End":
                    end_date,

                "Episode_Length":
                    end_pos - start_pos + 1,

                "Detected_Before_Onset":
                    detected_before,

                "First_Warning_Date":
                    first_warning_date,

                "Lead_Time_Trading_Days":
                    lead_time,

                "Max_PreStress_Risk_Score":
                    max_pre_score,

                "Risk_Score_At_Onset":
                    onset_score,
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# SUMMARY
# ============================================================

def summarize_episode_results(
    episode_results,
):

    rows = []

    for model in [
        "Logistic",
        "XGBoost",
    ]:

        df = episode_results[
            episode_results["Model"] == model
        ].copy()

        if len(df) == 0:
            continue

        detected = (
            df["Detected_Before_Onset"]
            .astype(bool)
        )

        lead = (
            df.loc[
                detected,
                "Lead_Time_Trading_Days",
            ]
            .dropna()
        )

        rows.append(
            {
                "Model":
                    model,

                "Threshold":
                    THRESHOLD,

                "Lookback_Trading_Days":
                    LOOKBACK_DAYS,

                "Cooldown_Trading_Days":
                    COOLDOWN_DAYS,

                "Episodes":
                    len(df),

                "Episodes_Detected":
                    int(detected.sum()),

                "Episodes_Missed":
                    int((~detected).sum()),

                "Episode_Detection_Rate":
                    detected.mean(),

                "Median_Lead_Time":
                    (
                        lead.median()
                        if len(lead) > 0
                        else np.nan
                    ),

                "Mean_Lead_Time":
                    (
                        lead.mean()
                        if len(lead) > 0
                        else np.nan
                    ),

                "Min_Lead_Time":
                    (
                        lead.min()
                        if len(lead) > 0
                        else np.nan
                    ),

                "Max_Lead_Time":
                    (
                        lead.max()
                        if len(lead) > 0
                        else np.nan
                    ),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# OBSERVATION-LEVEL METRICS
# ============================================================

def observation_metrics(
    oos,
    logistic_col,
    xgb_col,
):

    rows = []

    actual_col = (
        "Actual_Target"
        if "Actual_Target" in oos.columns
        else "Target_10D"
    )

    if actual_col not in oos.columns:
        raise ValueError(
            "No Actual_Target / Target_10D "
            "column found in OOS predictions."
        )

    y = (
        oos[actual_col]
        .astype(int)
    )

    for model, col in [
        ("Logistic", logistic_col),
        ("XGBoost", xgb_col),
    ]:

        pred = (
            oos[col] >= THRESHOLD
        ).astype(int)

        tp = int(
            ((pred == 1) & (y == 1)).sum()
        )

        fp = int(
            ((pred == 1) & (y == 0)).sum()
        )

        tn = int(
            ((pred == 0) & (y == 0)).sum()
        )

        fn = int(
            ((pred == 0) & (y == 1)).sum()
        )

        recall = (
            tp / (tp + fn)
            if (tp + fn)
            else np.nan
        )

        precision = (
            tp / (tp + fp)
            if (tp + fp)
            else np.nan
        )

        far = (
            fp / (fp + tn)
            if (fp + tn)
            else np.nan
        )

        missed = (
            fn / (fn + tp)
            if (fn + tp)
            else np.nan
        )

        rows.append(
            {
                "Model":
                    model,

                "Threshold":
                    THRESHOLD,

                "Stress_Window_Detection_Rate":
                    recall,

                "Precision":
                    precision,

                "False_Alarm_Rate":
                    far,

                "Missed_Stress_Window_Rate":
                    missed,

                "TP":
                    tp,

                "FP":
                    fp,

                "TN":
                    tn,

                "FN":
                    fn,
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        "============================================\n"
        " EARLY-WARNING EFFECTIVENESS ANALYSIS\n"
        " Actual Stress Onset + OOS Risk Scores\n"
        "============================================"
    )

    (
        oos,
        targets,
        logistic_col,
        xgb_col,
    ) = load_data()

    # --------------------------------------------------------
    # Build master trading-date frame from targets.
    # --------------------------------------------------------

    combined = targets[
        ["Is_Stress_Event"]
    ].copy()

    combined = combined.join(
        oos[
            [
                logistic_col,
                xgb_col,
            ]
        ],
        how="left",
    )

    combined["OOS_Available"] = (
        combined[logistic_col].notna()
        &
        combined[xgb_col].notna()
    )

    # --------------------------------------------------------
    # Restrict episode discovery to dates where the model
    # could actually have OOS history, but retain preceding
    # dates for lead-time indexing.
    # --------------------------------------------------------

    episodes = identify_stress_episodes(
        combined["Is_Stress_Event"],
        cooldown_days=COOLDOWN_DAYS,
    )

    print(
        f"\nRaw stress episodes identified: "
        f"{len(episodes)}"
    )

    logistic_results = analyze_model(
        combined,
        episodes,
        logistic_col,
        "Logistic",
    )

    xgb_results = analyze_model(
        combined,
        episodes,
        xgb_col,
        "XGBoost",
    )

    episode_results = pd.concat(
        [
            logistic_results,
            xgb_results,
        ],
        ignore_index=True,
    )

    summary = summarize_episode_results(
        episode_results
    )

    obs_metrics = observation_metrics(
        oos,
        logistic_col,
        xgb_col,
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    episode_results.to_csv(
        OUTPUT_DIR
        / "episode_lead_time.csv",
        index=False,
    )

    summary.to_csv(
        OUTPUT_DIR
        / "early_warning_summary.csv",
        index=False,
    )

    obs_metrics.to_csv(
        OUTPUT_DIR
        / "observation_metrics.csv",
        index=False,
    )

    # --------------------------------------------------------
    # PRINT
    # --------------------------------------------------------

    pd.set_option(
        "display.max_columns",
        None,
    )

    pd.set_option(
        "display.width",
        220,
    )

    print(
        "\n========== EPISODE RESULTS =========="
    )

    print(
        episode_results.to_string(
            index=False
        )
    )

    print(
        "\n========== EARLY-WARNING SUMMARY =========="
    )

    print(
        summary.to_string(
            index=False
        )
    )

    print(
        "\n========== OBSERVATION-LEVEL METRICS =========="
    )

    print(
        obs_metrics.to_string(
            index=False
        )
    )

    print(
        "\n========== SAVED =========="
    )

    print(
        OUTPUT_DIR
        / "episode_lead_time.csv"
    )

    print(
        OUTPUT_DIR
        / "early_warning_summary.csv"
    )

    print(
        OUTPUT_DIR
        / "observation_metrics.csv"
    )

    print(
        "\nEARLY-WARNING ANALYSIS COMPLETE"
    )


if __name__ == "__main__":
    main()