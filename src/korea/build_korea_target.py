import os
import numpy as np
import pandas as pd


# ============================================================
# Paths
# ============================================================

INPUT_PATH = "data/processed/korea/korea_stress_index.csv"
OUTPUT_PATH = "data/processed/korea/korea_targets.csv"


# ============================================================
# Methodology
# ============================================================

TARGET_WINDOWS = [1, 5, 10, 20]

STRESS_QUANTILE = 0.90
THRESHOLD_MIN_PERIODS = 252


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 72)
    print("KOREA FORWARD STRESS TARGET GENERATOR")
    print("=" * 72)

    # --------------------------------------------------------
    # 1. Load Korea MSI
    # --------------------------------------------------------

    if not os.path.exists(INPUT_PATH):
        raise FileNotFoundError(
            f"Input file not found: {INPUT_PATH}"
        )

    df = pd.read_csv(INPUT_PATH)

    df["Date"] = pd.to_datetime(df["Date"])

    df = (
        df.sort_values("Date")
        .reset_index(drop=True)
    )

    required = [
        "Date",
        "Korea_MSI",
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    print()
    print("Input rows:", f"{len(df):,}")

    print(
        "Date range:",
        df["Date"].min().date(),
        "→",
        df["Date"].max().date(),
    )

    # --------------------------------------------------------
    # 2. Rebuild Stress Threshold
    #
    # Same logic as U.S. TargetGenerator:
    #
    # threshold(t) uses MSI observations available through t-1.
    # --------------------------------------------------------

    historical_msi = (
        df["Korea_MSI"].shift(1)
    )

    df["Stress_Threshold"] = (
        historical_msi
        .expanding(
            min_periods=THRESHOLD_MIN_PERIODS
        )
        .quantile(
            STRESS_QUANTILE
        )
    )

    # --------------------------------------------------------
    # 3. Stress Event
    #
    # Same comparison rule as the U.S. implementation:
    #
    # MSI >= past-only Stress Threshold
    #
    # Initial observations without a valid threshold remain NaN.
    # --------------------------------------------------------

    df["Is_Stress_Event"] = np.where(
        df["Stress_Threshold"].notna(),
        (
            df["Korea_MSI"]
            >= df["Stress_Threshold"]
        ).astype(float),
        np.nan,
    )

    # --------------------------------------------------------
    # 4. Multi-Horizon Forward Targets
    #
    # Target_ND(t) = 1 if at least one Stress Event occurs
    # during t+1 ... t+N trading observations.
    #
    # The current day's event is NOT included.
    # --------------------------------------------------------

    target_cols = []

    for horizon in TARGET_WINDOWS:

        target_col = (
            f"Target_{horizon}D"
        )

        target_cols.append(
            target_col
        )

        future_events = pd.concat(
            [
                df[
                    "Is_Stress_Event"
                ].shift(-i)
                for i in range(
                    1,
                    horizon + 1,
                )
            ],
            axis=1,
        )

        df[target_col] = (
            future_events.max(
                axis=1,
                skipna=False,
            )
        )

    # --------------------------------------------------------
    # 5. Keep valid Stress Event period
    #
    # Same principle as U.S.:
    # remove only the initial period where the threshold/event
    # is not observable.
    #
    # End-of-sample forward-target NaNs are intentionally kept.
    # --------------------------------------------------------

    df.dropna(
        subset=[
            "Stress_Threshold",
            "Is_Stress_Event",
        ],
        inplace=True,
    )

    df["Is_Stress_Event"] = (
        df["Is_Stress_Event"]
        .astype(int)
    )

    for target_col in target_cols:

        df[target_col] = (
            df[target_col]
            .astype("Int64")
        )

    # --------------------------------------------------------
    # 6. QA
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("TARGET QA")
    print("=" * 72)

    print()
    print(
        "Valid target-period rows:",
        f"{len(df):,}",
    )

    print(
        "Target dataset range:",
        df["Date"].min().date(),
        "→",
        df["Date"].max().date(),
    )

    print()

    stress_count = int(
        df["Is_Stress_Event"].sum()
    )

    stress_rate = (
        df["Is_Stress_Event"].mean()
    )

    print(
        "Stress Event days:",
        f"{stress_count:,}",
    )

    print(
        "Stress Event rate:",
        f"{stress_rate:.4%}",
    )

    print()
    print("-" * 72)
    print("FORWARD TARGET PREVALENCE")
    print("-" * 72)

    for target_col in target_cols:

        valid = (
            df[target_col]
            .dropna()
        )

        positives = int(
            valid.sum()
        )

        prevalence = (
            valid.mean()
        )

        print()
        print(target_col)

        print(
            "  Valid observations:",
            f"{len(valid):,}",
        )

        print(
            "  Positive labels:",
            f"{positives:,}",
        )

        print(
            "  Prevalence:",
            f"{prevalence:.4%}",
        )

        print(
            "  End-of-sample NaN:",
            f"{df[target_col].isna().sum():,}",
        )

    # --------------------------------------------------------
    # 7. Verify exact horizon behavior
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("HORIZON CONSISTENCY QA")
    print("=" * 72)

    # Longer horizons should contain all positives from
    # shorter horizons whenever both labels are observable.

    comparisons = [
        ("Target_1D", "Target_5D"),
        ("Target_5D", "Target_10D"),
        ("Target_10D", "Target_20D"),
    ]

    all_consistent = True

    for shorter, longer in comparisons:

        valid = df[
            df[shorter].notna()
            & df[longer].notna()
        ]

        violations = (
            (
                valid[shorter] == 1
            )
            & (
                valid[longer] == 0
            )
        ).sum()

        print(
            f"{shorter} -> {longer} violations:",
            int(violations),
        )

        if violations != 0:
            all_consistent = False

    print()

    print(
        "Horizon nesting:",
        (
            "PASS"
            if all_consistent
            else "FAIL"
        ),
    )

    # --------------------------------------------------------
    # 8. Inspect recent labels
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("LATEST 25 OBSERVATIONS")
    print("=" * 72)

    display_cols = [
        "Date",
        "Korea_MSI",
        "Stress_Threshold",
        "Is_Stress_Event",
        "Target_1D",
        "Target_5D",
        "Target_10D",
        "Target_20D",
    ]

    print(
        df[
            display_cols
        ]
        .tail(25)
        .to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # 9. Save
    # --------------------------------------------------------

    os.makedirs(
        os.path.dirname(
            OUTPUT_PATH
        ),
        exist_ok=True,
    )

    output_cols = [
        "Date",
        "Korea_MSI",
        "Stress_Threshold",
        "Is_Stress_Event",
        "Target_1D",
        "Target_5D",
        "Target_10D",
        "Target_20D",
    ]

    df[
        output_cols
    ].to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("=" * 72)
    print("SAVE COMPLETE")
    print("=" * 72)

    print(
        "Saved:",
        OUTPUT_PATH,
    )

    print(
        "Rows:",
        f"{len(df):,}",
    )

    print()
    print(
        "Target_10D(t) = 1 when at least one "
        "Korea Stress Event occurs during "
        "t+1 through t+10 trading observations."
    )


if __name__ == "__main__":
    main()
    