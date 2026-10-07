from pathlib import Path
import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

OOS_PATH = Path("data/processed/oos_predictions_10d.csv")
TARGETS_PATH = Path("data/features/targets.csv")

OUTPUT_DIR = Path("data/processed/pre_stress_trajectory")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

THRESHOLD = 0.50

# 20D cap 제거.
# Stress onset 전 최대 120 trading days를 관찰.
LOOKBACK = 120

# Nearby stress clusters are treated as one episode.
COOLDOWN_DAYS = 10

# Risk build-up를 보기 위한 구간
BINS = [
    (-120, -91),
    (-90, -61),
    (-60, -41),
    (-40, -21),
    (-20, -11),
    (-10, -6),
    (-5, -1),
]


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

    logistic_col = next(
        (
            c for c in ["Prob_Logistic", "Logistic_Prob"]
            if c in oos.columns
        ),
        None,
    )

    xgb_col = next(
        (
            c for c in ["Prob_XGBoost", "XGB_Prob"]
            if c in oos.columns
        ),
        None,
    )

    if logistic_col is None:
        raise ValueError(
            f"Logistic probability column not found: "
            f"{list(oos.columns)}"
        )

    if xgb_col is None:
        raise ValueError(
            f"XGBoost probability column not found: "
            f"{list(oos.columns)}"
        )

    if "Is_Stress_Event" not in targets.columns:
        raise ValueError(
            "Is_Stress_Event not found in targets.csv"
        )

    print(
        f"OOS     : {oos.index.min().date()} "
        f"→ {oos.index.max().date()} | N={len(oos):,}"
    )

    print(
        f"Targets : {targets.index.min().date()} "
        f"→ {targets.index.max().date()} | N={len(targets):,}"
    )

    return oos, targets, logistic_col, xgb_col


# ============================================================
# IDENTIFY ACTUAL STRESS EPISODES
# ============================================================

def identify_episodes(stress_series):

    stress = stress_series.fillna(0).astype(int)

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

        if gap > COOLDOWN_DAYS:

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
# BUILD PRE-STRESS TRAJECTORY
# ============================================================

def build_trajectory(
    combined,
    episodes,
    logistic_col,
    xgb_col,
):

    rows = []

    oos_start = combined.loc[
        combined["OOS_Available"]
    ].index.min()

    for episode_id, episode in enumerate(
        episodes,
        start=1,
    ):

        start_pos = episode["start_pos"]
        end_pos = episode["end_pos"]

        onset = combined.index[start_pos]
        end = combined.index[end_pos]

        # Only evaluate episodes whose actual onset
        # occurs in the OOS period.
        if onset < oos_start:
            continue

        pre_start = max(
            0,
            start_pos - LOOKBACK,
        )

        # Include onset itself (relative day = 0)
        window = combined.iloc[
            pre_start:start_pos + 1
        ].copy()

        window = window[
            window["OOS_Available"]
        ].copy()

        for date, row in window.iterrows():

            current_pos = combined.index.get_loc(date)

            relative_day = (
                current_pos - start_pos
            )

            rows.append(
                {
                    "Episode_ID": episode_id,
                    "Stress_Onset": onset,
                    "Stress_End": end,
                    "Date": date,
                    "Relative_Trading_Day":
                        relative_day,
                    "Logistic_Risk":
                        row[logistic_col],
                    "XGBoost_Risk":
                        row[xgb_col],
                    "Is_Stress_Event":
                        row["Is_Stress_Event"],
                }
            )

    return pd.DataFrame(rows)


# ============================================================
# AGGREGATE ACROSS EPISODES
# ============================================================

def aggregate_trajectory(trajectory):

    rows = []

    for relative_day in range(
        -LOOKBACK,
        1,
    ):

        day = trajectory[
            trajectory["Relative_Trading_Day"]
            == relative_day
        ]

        if len(day) == 0:
            continue

        rows.append(
            {
                "Relative_Trading_Day":
                    relative_day,

                "Episode_Count":
                    len(day),

                "Logistic_Median":
                    day["Logistic_Risk"].median(),

                "Logistic_Mean":
                    day["Logistic_Risk"].mean(),

                "Logistic_P25":
                    day["Logistic_Risk"].quantile(0.25),

                "Logistic_P75":
                    day["Logistic_Risk"].quantile(0.75),

                "XGBoost_Median":
                    day["XGBoost_Risk"].median(),

                "XGBoost_Mean":
                    day["XGBoost_Risk"].mean(),

                "XGBoost_P25":
                    day["XGBoost_Risk"].quantile(0.25),

                "XGBoost_P75":
                    day["XGBoost_Risk"].quantile(0.75),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# BIN ANALYSIS
# ============================================================

def build_bin_summary(trajectory):

    rows = []

    for start, end in BINS:

        section = trajectory[
            (
                trajectory["Relative_Trading_Day"]
                >= start
            )
            &
            (
                trajectory["Relative_Trading_Day"]
                <= end
            )
        ]

        if len(section) == 0:
            continue

        rows.append(
            {
                "Window":
                    f"{start}D to {end}D",

                "Observations":
                    len(section),

                "Episodes":
                    section[
                        "Episode_ID"
                    ].nunique(),

                "Logistic_Median_Risk":
                    section[
                        "Logistic_Risk"
                    ].median(),

                "Logistic_Mean_Risk":
                    section[
                        "Logistic_Risk"
                    ].mean(),

                "Logistic_Above_0.5":
                    (
                        section["Logistic_Risk"]
                        >= THRESHOLD
                    ).mean(),

                "XGBoost_Median_Risk":
                    section[
                        "XGBoost_Risk"
                    ].median(),

                "XGBoost_Mean_Risk":
                    section[
                        "XGBoost_Risk"
                    ].mean(),

                "XGBoost_Above_0.5":
                    (
                        section["XGBoost_Risk"]
                        >= THRESHOLD
                    ).mean(),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# FIRST THRESHOLD CROSSING — EXPLORATORY ONLY
# ============================================================

def exploratory_first_warning(
    trajectory,
):

    rows = []

    for episode_id, group in trajectory.groupby(
        "Episode_ID"
    ):

        group = group.sort_values(
            "Relative_Trading_Day"
        )

        onset = group[
            "Stress_Onset"
        ].iloc[0]

        for model, col in [
            ("Logistic", "Logistic_Risk"),
            ("XGBoost", "XGBoost_Risk"),
        ]:

            # PRE-STRESS ONLY
            pre = group[
                group["Relative_Trading_Day"] < 0
            ]

            warnings = pre[
                pre[col] >= THRESHOLD
            ]

            if len(warnings) > 0:

                first = warnings.iloc[0]

                first_date = first["Date"]

                lead_time = abs(
                    int(
                        first[
                            "Relative_Trading_Day"
                        ]
                    )
                )

                detected = True

            else:

                first_date = pd.NaT
                lead_time = np.nan
                detected = False

            rows.append(
                {
                    "Episode_ID":
                        episode_id,

                    "Model":
                        model,

                    "Stress_Onset":
                        onset,

                    "Detected_Within_120D":
                        detected,

                    "Exploratory_First_Warning":
                        first_date,

                    "Exploratory_Lead_Time":
                        lead_time,
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
        " 120-DAY PRE-STRESS RISK TRAJECTORY\n"
        " Exploratory Signal Build-Up Analysis\n"
        "============================================"
    )

    (
        oos,
        targets,
        logistic_col,
        xgb_col,
    ) = load_data()

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

    episodes = identify_episodes(
        combined["Is_Stress_Event"]
    )

    print(
        f"\nStress episodes identified: "
        f"{len(episodes)}"
    )

    trajectory = build_trajectory(
        combined,
        episodes,
        logistic_col,
        xgb_col,
    )

    aggregate = aggregate_trajectory(
        trajectory
    )

    bin_summary = build_bin_summary(
        trajectory
    )

    first_warning = exploratory_first_warning(
        trajectory
    )

    # ========================================================
    # SAVE
    # ========================================================

    trajectory.to_csv(
        OUTPUT_DIR
        / "episode_120d_trajectory.csv",
        index=False,
    )

    aggregate.to_csv(
        OUTPUT_DIR
        / "aggregate_120d_trajectory.csv",
        index=False,
    )

    bin_summary.to_csv(
        OUTPUT_DIR
        / "risk_build_up_by_window.csv",
        index=False,
    )

    first_warning.to_csv(
        OUTPUT_DIR
        / "exploratory_first_warning.csv",
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
        220,
    )

    print(
        "\n========== RISK BUILD-UP BY WINDOW =========="
    )

    print(
        bin_summary.to_string(
            index=False
        )
    )

    print(
        "\n========== EXPLORATORY FIRST WARNINGS =========="
    )

    print(
        first_warning.to_string(
            index=False
        )
    )

    print(
        "\n========== SELECTED TRAJECTORY POINTS =========="
    )

    selected_days = [
        -120,
        -90,
        -60,
        -40,
        -20,
        -15,
        -10,
        -5,
        -1,
        0,
    ]

    selected = aggregate[
        aggregate[
            "Relative_Trading_Day"
        ].isin(selected_days)
    ]

    print(
        selected.to_string(
            index=False
        )
    )

    print(
        "\n========== SAVED =========="
    )

    for filename in [
        "episode_120d_trajectory.csv",
        "aggregate_120d_trajectory.csv",
        "risk_build_up_by_window.csv",
        "exploratory_first_warning.csv",
    ]:

        print(
            OUTPUT_DIR / filename
        )

    print(
        "\n120-DAY TRAJECTORY ANALYSIS COMPLETE"
    )


if __name__ == "__main__":
    main()