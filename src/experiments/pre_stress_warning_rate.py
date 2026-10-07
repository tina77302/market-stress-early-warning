from pathlib import Path
import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

OOS_PATH = Path("data/processed/oos_predictions_10d.csv")
TARGETS_PATH = Path("data/features/targets.csv")

OUTPUT_DIR = Path("data/processed/pre_stress_warning_rate")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

THRESHOLD = 0.50
COOLDOWN_DAYS = 10

WINDOWS = {
    "20_11D": (-20, -11),
    "10_6D": (-10, -6),
    "5_1D": (-5, -1),
}

MODELS = {
    "Logistic": "Prob_Logistic",
    "XGBoost": "Prob_XGBoost",
}


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

    oos = oos.sort_index()
    targets = targets.sort_index()

    required_oos = list(MODELS.values())

    missing = [
        col for col in required_oos
        if col not in oos.columns
    ]

    if missing:
        raise ValueError(
            f"Missing OOS columns: {missing}"
        )

    if "Is_Stress_Event" not in targets.columns:
        raise ValueError(
            "Is_Stress_Event missing from targets.csv"
        )

    print(
        f"OOS: {oos.index.min().date()} "
        f"→ {oos.index.max().date()} | N={len(oos):,}"
    )

    print(
        f"Targets: {targets.index.min().date()} "
        f"→ {targets.index.max().date()} | N={len(targets):,}"
    )

    return oos, targets


# ============================================================
# IDENTIFY ACTUAL STRESS EPISODES
# ============================================================

def identify_episodes(targets):

    stress = (
        targets["Is_Stress_Event"]
        .fillna(0)
        .astype(int)
    )

    positions = np.flatnonzero(
        stress.values == 1
    )

    if len(positions) == 0:
        return []

    episodes = []

    start = positions[0]
    previous = positions[0]

    for pos in positions[1:]:

        gap = pos - previous - 1

        if gap > COOLDOWN_DAYS:

            episodes.append(
                {
                    "start_pos": start,
                    "end_pos": previous,
                    "onset_date": targets.index[start],
                }
            )

            start = pos

        previous = pos

    episodes.append(
        {
            "start_pos": start,
            "end_pos": previous,
            "onset_date": targets.index[start],
        }
    )

    return episodes


# ============================================================
# ANALYZE WARNING WINDOWS
# ============================================================

def analyze_warning_windows(oos, targets, episodes):

    rows = []

    for episode_id, episode in enumerate(
        episodes,
        start=1,
    ):

        onset_date = episode["onset_date"]

        # Only evaluate episodes whose onset is inside
        # the OOS prediction period.
        if onset_date < oos.index.min():
            continue

        if onset_date > oos.index.max():
            continue

        # Position in target trading-day calendar.
        onset_pos = targets.index.get_loc(
            onset_date
        )

        # Need full 20 trading days before onset.
        if onset_pos < 20:
            continue

        for window_name, (
            relative_start,
            relative_end,
        ) in WINDOWS.items():

            start_pos = (
                onset_pos + relative_start
            )

            end_pos = (
                onset_pos + relative_end
            )

            dates = targets.index[
                start_pos:end_pos + 1
            ]

            # Restrict to actual OOS dates.
            window_oos = oos.reindex(
                dates
            )

            for model_name, prob_col in MODELS.items():

                scores = (
                    window_oos[prob_col]
                    .dropna()
                )

                if len(scores) == 0:
                    continue

                warning_mask = (
                    scores >= THRESHOLD
                )

                warning_days = int(
                    warning_mask.sum()
                )

                detected = (
                    warning_days > 0
                )

                # Earliest warning in this window.
                if detected:

                    first_warning_date = (
                        scores[
                            warning_mask
                        ].index[0]
                    )

                    first_warning_pos = (
                        targets.index.get_loc(
                            first_warning_date
                        )
                    )

                    lead_days = (
                        onset_pos
                        - first_warning_pos
                    )

                else:
                    first_warning_date = pd.NaT
                    lead_days = np.nan

                rows.append(
                    {
                        "Episode_ID":
                            episode_id,

                        "Stress_Onset":
                            onset_date,

                        "Window":
                            window_name,

                        "Model":
                            model_name,

                        "Available_Days":
                            len(scores),

                        "Warning_Days":
                            warning_days,

                        "Warning_Rate":
                            warning_days
                            / len(scores),

                        "Detected":
                            int(detected),

                        "Max_Risk_Score":
                            scores.max(),

                        "Mean_Risk_Score":
                            scores.mean(),

                        "First_Warning_Date":
                            first_warning_date,

                        "Lead_Days":
                            lead_days,
                    }
                )

    return pd.DataFrame(rows)


# ============================================================
# SUMMARY
# ============================================================

def build_summary(results):

    rows = []

    for (
        model,
        window,
    ), group in results.groupby(
        ["Model", "Window"]
    ):

        episodes = len(group)

        detected = int(
            group["Detected"].sum()
        )

        detection_rate = (
            detected / episodes
            if episodes > 0
            else np.nan
        )

        detected_group = group[
            group["Detected"] == 1
        ]

        rows.append(
            {
                "Model":
                    model,

                "Window":
                    window,

                "Episodes":
                    episodes,

                "Detected_Episodes":
                    detected,

                "Episode_Detection_Rate":
                    detection_rate,

                "Median_Max_Risk":
                    group[
                        "Max_Risk_Score"
                    ].median(),

                "Median_Mean_Risk":
                    group[
                        "Mean_Risk_Score"
                    ].median(),

                "Median_Warning_Rate":
                    group[
                        "Warning_Rate"
                    ].median(),

                "Median_Lead_Days":
                    (
                        detected_group[
                            "Lead_Days"
                        ].median()
                        if len(detected_group) > 0
                        else np.nan
                    ),
            }
        )

    summary = pd.DataFrame(rows)

    window_order = {
        "20_11D": 1,
        "10_6D": 2,
        "5_1D": 3,
    }

    model_order = {
        "Logistic": 1,
        "XGBoost": 2,
    }

    summary["_window_order"] = (
        summary["Window"]
        .map(window_order)
    )

    summary["_model_order"] = (
        summary["Model"]
        .map(model_order)
    )

    summary = (
        summary
        .sort_values(
            [
                "_model_order",
                "_window_order",
            ]
        )
        .drop(
            columns=[
                "_window_order",
                "_model_order",
            ]
        )
    )

    return summary


# ============================================================
# PERSISTENT WARNING CHECK
# ============================================================

def build_persistence_summary(results):

    rows = []

    for (
        model,
        window,
    ), group in results.groupby(
        ["Model", "Window"]
    ):

        episodes = len(group)

        for required_days in [1, 2, 3]:

            detected = (
                group["Warning_Days"]
                >= required_days
            )

            rows.append(
                {
                    "Model":
                        model,

                    "Window":
                        window,

                    "Required_Warning_Days":
                        required_days,

                    "Episodes":
                        episodes,

                    "Detected_Episodes":
                        int(detected.sum()),

                    "Detection_Rate":
                        detected.mean(),
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
        " PRE-STRESS OOS WARNING RATE ANALYSIS\n"
        " Did the model warn BEFORE stress onset?\n"
        "============================================"
    )

    oos, targets = load_data()

    episodes = identify_episodes(
        targets
    )

    print(
        f"\nTotal stress episodes: "
        f"{len(episodes)}"
    )

    results = analyze_warning_windows(
        oos,
        targets,
        episodes,
    )

    summary = build_summary(
        results
    )

    persistence = build_persistence_summary(
        results
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    results.to_csv(
        OUTPUT_DIR
        / "episode_warning_windows.csv",
        index=False,
    )

    summary.to_csv(
        OUTPUT_DIR
        / "warning_window_summary.csv",
        index=False,
    )

    persistence.to_csv(
        OUTPUT_DIR
        / "warning_persistence_summary.csv",
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
        240,
    )

    print(
        "\n========== WARNING WINDOW SUMMARY =========="
    )

    display_summary = summary.copy()

    display_summary[
        "Episode_Detection_Rate"
    ] *= 100

    display_summary[
        "Median_Warning_Rate"
    ] *= 100

    print(
        display_summary
        .round(4)
        .to_string(index=False)
    )

    print(
        "\n========== WARNING PERSISTENCE =========="
    )

    display_persistence = (
        persistence.copy()
    )

    display_persistence[
        "Detection_Rate"
    ] *= 100

    print(
        display_persistence
        .round(4)
        .to_string(index=False)
    )

    print(
        "\n========== INTERPRETATION =========="
    )

    print(
        """
Episode_Detection_Rate:
    Percentage of actual stress episodes for which
    Risk Score >= 0.50 at least once in that
    pre-stress window.

Median_Warning_Rate:
    Within each pre-stress window, how frequently
    the model remained above 0.50.

Persistence:
    1 day = at least one warning day
    2 days = at least two warning days
    3 days = at least three warning days

IMPORTANT:
    This is based on genuine OOS predictions.

    Stress onset is defined using Is_Stress_Event,
    NOT Target_10D.

    A single threshold crossing does not necessarily
    represent a reliable early warning.

    Persistent warnings are therefore reported
    separately.

    Threshold 0.50 is a fixed reference threshold,
    not an OOS-optimized threshold.
"""
    )

    print(
        "\n========== SAVED =========="
    )

    for filename in [
        "episode_warning_windows.csv",
        "warning_window_summary.csv",
        "warning_persistence_summary.csv",
    ]:
        print(
            OUTPUT_DIR / filename
        )

    print(
        "\nPRE-STRESS WARNING ANALYSIS COMPLETE"
    )


if __name__ == "__main__":
    main()