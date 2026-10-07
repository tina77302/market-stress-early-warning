from pathlib import Path
import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

OOS_PATH = Path("data/processed/oos_predictions_10d.csv")
TARGETS_PATH = Path("data/features/targets.csv")

OUTPUT_DIR = Path("data/processed/false_warning_analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

THRESHOLD = 0.50

MODELS = {
    "Logistic": "Prob_Logistic",
    "XGBoost": "Prob_XGBoost",
}

FOLLOW_WINDOWS = [10, 20]

# Consecutive warning days are treated as one warning episode.
# A break below threshold starts a new warning episode.
WARNING_GAP = 0


# ============================================================
# LOAD
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

    required = list(MODELS.values())

    missing = [
        col for col in required
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

    # Use only dates for which genuine OOS predictions exist.
    common_dates = (
        oos.index
        .intersection(targets.index)
    )

    oos = oos.loc[common_dates]
    targets = targets.loc[common_dates]

    print(
        f"OOS evaluation period: "
        f"{common_dates.min().date()} "
        f"→ {common_dates.max().date()}"
    )

    print(
        f"Observations: {len(common_dates):,}"
    )

    return oos, targets


# ============================================================
# BUILD WARNING EPISODES
# ============================================================

def identify_warning_episodes(scores):

    warning = (
        scores >= THRESHOLD
    ).astype(int)

    positions = np.flatnonzero(
        warning.values == 1
    )

    if len(positions) == 0:
        return []

    episodes = []

    start = positions[0]
    previous = positions[0]

    for pos in positions[1:]:

        gap = pos - previous - 1

        if gap > WARNING_GAP:

            episodes.append(
                {
                    "start_pos": start,
                    "end_pos": previous,
                }
            )

            start = pos

        previous = pos

    episodes.append(
        {
            "start_pos": start,
            "end_pos": previous,
        }
    )

    return episodes


# ============================================================
# ANALYZE WARNING EPISODES
# ============================================================

def analyze_model(
    model_name,
    prob_col,
    oos,
    targets,
):

    scores = oos[prob_col].dropna()

    stress = (
        targets["Is_Stress_Event"]
        .fillna(0)
        .astype(int)
    )

    # Reindex stress exactly to model score dates.
    stress = stress.reindex(
        scores.index
    ).fillna(0).astype(int)

    episodes = identify_warning_episodes(
        scores
    )

    rows = []

    for episode_id, episode in enumerate(
        episodes,
        start=1,
    ):

        start_pos = episode["start_pos"]
        end_pos = episode["end_pos"]

        start_date = scores.index[start_pos]
        end_date = scores.index[end_pos]

        episode_scores = scores.iloc[
            start_pos:end_pos + 1
        ]

        row = {
            "Model": model_name,
            "Warning_Episode_ID": episode_id,
            "Warning_Start": start_date,
            "Warning_End": end_date,
            "Warning_Days": len(
                episode_scores
            ),
            "Max_Risk_Score":
                episode_scores.max(),
            "Mean_Risk_Score":
                episode_scores.mean(),
        }

        # ----------------------------------------------------
        # Does ACTUAL stress occur AFTER warning begins?
        #
        # We check forward trading observations from the
        # first warning day.
        # ----------------------------------------------------

        for horizon in FOLLOW_WINDOWS:

            forward_start = start_pos + 1

            forward_end = min(
                start_pos + horizon,
                len(stress) - 1,
            )

            # Episodes too close to end of OOS sample
            # cannot receive a complete forward evaluation.
            full_window_available = (
                start_pos + horizon
                < len(stress)
            )

            row[
                f"Full_{horizon}D_Window"
            ] = int(
                full_window_available
            )

            if not full_window_available:

                row[
                    f"Stress_Within_{horizon}D"
                ] = np.nan

                row[
                    f"Lead_To_Stress_{horizon}D"
                ] = np.nan

                continue

            forward = stress.iloc[
                forward_start:
                forward_end + 1
            ]

            stress_positions = (
                np.flatnonzero(
                    forward.values == 1
                )
            )

            hit = (
                len(stress_positions) > 0
            )

            row[
                f"Stress_Within_{horizon}D"
            ] = int(hit)

            if hit:

                first_relative_pos = (
                    stress_positions[0] + 1
                )

                row[
                    f"Lead_To_Stress_{horizon}D"
                ] = first_relative_pos

            else:

                row[
                    f"Lead_To_Stress_{horizon}D"
                ] = np.nan

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# SUMMARY
# ============================================================

def build_summary(results):

    rows = []

    for model, group in results.groupby(
        "Model"
    ):

        for horizon in FOLLOW_WINDOWS:

            full_col = (
                f"Full_{horizon}D_Window"
            )

            hit_col = (
                f"Stress_Within_{horizon}D"
            )

            lead_col = (
                f"Lead_To_Stress_{horizon}D"
            )

            valid = group[
                group[full_col] == 1
            ].copy()

            total = len(valid)

            hits = int(
                valid[hit_col].sum()
            )

            false_warnings = (
                total - hits
            )

            hit_rate = (
                hits / total
                if total > 0
                else np.nan
            )

            false_rate = (
                false_warnings / total
                if total > 0
                else np.nan
            )

            hit_rows = valid[
                valid[hit_col] == 1
            ]

            rows.append(
                {
                    "Model":
                        model,

                    "Follow_Window":
                        f"{horizon}D",

                    "Warning_Episodes":
                        total,

                    "Followed_By_Stress":
                        hits,

                    "False_Warning_Episodes":
                        false_warnings,

                    "Warning_Precision":
                        hit_rate,

                    "False_Warning_Rate":
                        false_rate,

                    "Median_Days_To_Stress":
                        (
                            hit_rows[
                                lead_col
                            ].median()
                            if len(hit_rows) > 0
                            else np.nan
                        ),

                    "Median_Warning_Duration":
                        valid[
                            "Warning_Days"
                        ].median(),

                    "Median_Max_Risk":
                        valid[
                            "Max_Risk_Score"
                        ].median(),
                }
            )

    return pd.DataFrame(rows)


# ============================================================
# PERSISTENCE SENSITIVITY
# ============================================================

def build_persistence_summary(results):

    rows = []

    for model, group in results.groupby(
        "Model"
    ):

        for horizon in FOLLOW_WINDOWS:

            full_col = (
                f"Full_{horizon}D_Window"
            )

            hit_col = (
                f"Stress_Within_{horizon}D"
            )

            for required_days in [1, 2, 3]:

                valid = group[
                    (group[full_col] == 1)
                    &
                    (
                        group["Warning_Days"]
                        >= required_days
                    )
                ].copy()

                total = len(valid)

                if total == 0:
                    continue

                hits = int(
                    valid[hit_col].sum()
                )

                false_warnings = (
                    total - hits
                )

                rows.append(
                    {
                        "Model":
                            model,

                        "Follow_Window":
                            f"{horizon}D",

                        "Minimum_Warning_Days":
                            required_days,

                        "Warning_Episodes":
                            total,

                        "Followed_By_Stress":
                            hits,

                        "False_Warnings":
                            false_warnings,

                        "Warning_Precision":
                            hits / total,

                        "False_Warning_Rate":
                            false_warnings / total,
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
        " FALSE WARNING EPISODE ANALYSIS\n"
        " Does a warning lead to actual stress?\n"
        "============================================"
    )

    oos, targets = load_data()

    all_results = []

    for model_name, prob_col in MODELS.items():

        model_results = analyze_model(
            model_name,
            prob_col,
            oos,
            targets,
        )

        all_results.append(
            model_results
        )

    results = pd.concat(
        all_results,
        ignore_index=True,
    )

    summary = build_summary(
        results
    )

    persistence = (
        build_persistence_summary(
            results
        )
    )

    # ========================================================
    # SAVE
    # ========================================================

    results.to_csv(
        OUTPUT_DIR
        / "warning_episodes.csv",
        index=False,
    )

    summary.to_csv(
        OUTPUT_DIR
        / "false_warning_summary.csv",
        index=False,
    )

    persistence.to_csv(
        OUTPUT_DIR
        / "false_warning_persistence.csv",
        index=False,
    )

    # ========================================================
    # PRINT
    # ========================================================

    pd.set_option(
        "display.max_columns",
        None,
    )

    pd.set_option(
        "display.width",
        240,
    )

    print(
        "\n========== FALSE WARNING SUMMARY =========="
    )

    display_summary = summary.copy()

    display_summary[
        "Warning_Precision"
    ] *= 100

    display_summary[
        "False_Warning_Rate"
    ] *= 100

    print(
        display_summary
        .round(4)
        .to_string(index=False)
    )

    print(
        "\n========== PERSISTENCE SENSITIVITY =========="
    )

    display_persistence = (
        persistence.copy()
    )

    display_persistence[
        "Warning_Precision"
    ] *= 100

    display_persistence[
        "False_Warning_Rate"
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
Warning_Precision:
    Of warning episodes, percentage followed by
    an actual Is_Stress_Event within the stated
    forward trading-day window.

False_Warning_Rate:
    Of warning episodes, percentage NOT followed
    by actual stress within that window.

Persistence sensitivity:
    Tests whether requiring >=2 or >=3 consecutive
    warning days improves warning reliability.

IMPORTANT:
    - Uses genuine OOS risk scores.
    - Uses actual Is_Stress_Event, not Target_10D.
    - 0.50 is a fixed reference threshold.
    - 10D and 20D results answer different questions.
    - This is episode-level warning reliability,
      not classification accuracy.
"""
    )

    print(
        "\n========== SAVED =========="
    )

    for filename in [
        "warning_episodes.csv",
        "false_warning_summary.csv",
        "false_warning_persistence.csv",
    ]:
        print(
            OUTPUT_DIR / filename
        )

    print(
        "\nFALSE WARNING ANALYSIS COMPLETE"
    )


if __name__ == "__main__":
    main()