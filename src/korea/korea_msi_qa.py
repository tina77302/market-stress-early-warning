import os

import numpy as np
import pandas as pd


# ============================================================
# Paths
# ============================================================

INPUT_PATH = "data/processed/korea/korea_stress_index.csv"


# ============================================================
# Configuration
# ============================================================

FOCUS_YEARS = [2015, 2022, 2026]

CHANNELS = [
    "Equity_Stress_Z",
    "Volatility_Stress_Z",
    "Credit_Stress_Z",
]


# ============================================================
# Load
# ============================================================

def load_data():

    if not os.path.exists(INPUT_PATH):
        raise FileNotFoundError(
            f"File not found: {INPUT_PATH}"
        )

    df = pd.read_csv(INPUT_PATH)

    df["Date"] = pd.to_datetime(df["Date"])

    required = [
        "Date",
        "KOSPI200",
        "VKOSPI",
        "Korea_Credit_Spread_bp",
        "Equity_Stress_Z",
        "Volatility_Stress_Z",
        "Credit_Stress_Z",
        "Korea_MSI",
        "Stress_Threshold",
        "Is_Stress_Event",
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    df = (
        df.sort_values("Date")
        .reset_index(drop=True)
    )

    return df


# ============================================================
# Dominant channel
# ============================================================

def add_dominant_channel(df):

    out = df.copy()

    valid = out[CHANNELS].notna().all(axis=1)

    out["Dominant_Channel"] = pd.NA
    out["Dominant_Abs_Z"] = np.nan
    out["Second_Largest_Abs_Z"] = np.nan
    out["Dominance_Ratio"] = np.nan

    abs_values = out.loc[
        valid,
        CHANNELS,
    ].abs()

    # Largest absolute channel
    dominant = abs_values.idxmax(axis=1)

    out.loc[
        valid,
        "Dominant_Channel",
    ] = dominant

    out.loc[
        valid,
        "Dominant_Abs_Z",
    ] = abs_values.max(axis=1)

    # Second-largest absolute channel
    sorted_abs = np.sort(
        abs_values.to_numpy(),
        axis=1,
    )

    second = sorted_abs[:, -2]

    out.loc[
        valid,
        "Second_Largest_Abs_Z",
    ] = second

    # Ratio:
    # largest absolute z-score / second-largest absolute z-score
    #
    # This is descriptive only.
    denominator = np.where(
        second > 0,
        second,
        np.nan,
    )

    ratio = (
        sorted_abs[:, -1]
        / denominator
    )

    out.loc[
        valid,
        "Dominance_Ratio",
    ] = ratio

    return out


# ============================================================
# Overall channel QA
# ============================================================

def print_overall_channel_qa(df):

    valid = df.dropna(
        subset=CHANNELS + ["Korea_MSI"]
    ).copy()

    print()
    print("=" * 72)
    print("OVERALL CHANNEL QA")
    print("=" * 72)

    print()
    print("Valid MSI observations:", f"{len(valid):,}")

    print()
    print("Channel summary:")

    print(
        valid[
            CHANNELS + ["Korea_MSI"]
        ]
        .describe()
        .T
    )

    print()
    print("Channel correlations:")

    print(
        valid[
            CHANNELS + ["Korea_MSI"]
        ].corr()
    )

    print()
    print("Mean absolute z-score:")

    print(
        valid[
            CHANNELS
        ]
        .abs()
        .mean()
        .sort_values(
            ascending=False
        )
    )

    print()
    print("Median absolute z-score:")

    print(
        valid[
            CHANNELS
        ]
        .abs()
        .median()
        .sort_values(
            ascending=False
        )
    )

    print()
    print("95th percentile absolute z-score:")

    print(
        valid[
            CHANNELS
        ]
        .abs()
        .quantile(0.95)
        .sort_values(
            ascending=False
        )
    )

    print()
    print("99th percentile absolute z-score:")

    print(
        valid[
            CHANNELS
        ]
        .abs()
        .quantile(0.99)
        .sort_values(
            ascending=False
        )
    )


# ============================================================
# Dominance QA
# ============================================================

def print_dominance_qa(df):

    valid = df.dropna(
        subset=[
            "Dominant_Channel",
            "Dominance_Ratio",
        ]
    ).copy()

    print()
    print("=" * 72)
    print("CHANNEL DOMINANCE QA")
    print("=" * 72)

    print()
    print("Dominant channel counts:")

    counts = (
        valid["Dominant_Channel"]
        .value_counts()
    )

    print(counts)

    print()
    print("Dominant channel shares:")

    shares = (
        valid["Dominant_Channel"]
        .value_counts(
            normalize=True
        )
        .mul(100)
    )

    print(
        shares.round(2)
    )

    print()
    print("Dominance ratio summary:")

    print(
        valid["Dominance_Ratio"]
        .describe(
            percentiles=[
                0.50,
                0.75,
                0.90,
                0.95,
                0.99,
            ]
        )
    )

    print()

    # --------------------------------------------------------
    # These are diagnostics, NOT model thresholds.
    # --------------------------------------------------------

    for ratio_threshold in [2, 3, 5]:

        count = (
            valid["Dominance_Ratio"]
            >= ratio_threshold
        ).sum()

        share = (
            count / len(valid)
        )

        print(
            f"Dominance ratio >= "
            f"{ratio_threshold}: "
            f"{count:,} "
            f"({share:.2%})"
        )


# ============================================================
# Stress-event channel QA
# ============================================================

def print_stress_event_qa(df):

    stress = df[
        df["Is_Stress_Event"] == 1
    ].copy()

    print()
    print("=" * 72)
    print("STRESS EVENT CHANNEL QA")
    print("=" * 72)

    print()
    print(
        "Stress Event observations:",
        f"{len(stress):,}",
    )

    print()

    print("Mean channel z-score on Stress Event days:")

    print(
        stress[
            CHANNELS
        ]
        .mean()
        .sort_values(
            ascending=False
        )
    )

    print()

    print("Median channel z-score on Stress Event days:")

    print(
        stress[
            CHANNELS
        ]
        .median()
        .sort_values(
            ascending=False
        )
    )

    print()

    print("Dominant channel on Stress Event days:")

    stress_counts = (
        stress["Dominant_Channel"]
        .value_counts()
    )

    print(stress_counts)

    print()

    print("Dominant channel share on Stress Event days:")

    stress_shares = (
        stress["Dominant_Channel"]
        .value_counts(
            normalize=True
        )
        .mul(100)
    )

    print(
        stress_shares.round(2)
    )


# ============================================================
# Year-by-year QA
# ============================================================

def print_yearly_qa(df):

    valid = df[
        df["Is_Stress_Event"].notna()
    ].copy()

    valid["Year"] = (
        valid["Date"].dt.year
    )

    print()
    print("=" * 72)
    print("YEARLY CHANNEL QA")
    print("=" * 72)

    yearly = (
        valid.groupby("Year")
        .agg(
            Days=(
                "Date",
                "count",
            ),
            Stress_Days=(
                "Is_Stress_Event",
                "sum",
            ),
            Mean_MSI=(
                "Korea_MSI",
                "mean",
            ),
            Median_MSI=(
                "Korea_MSI",
                "median",
            ),
            Mean_Equity_Z=(
                "Equity_Stress_Z",
                "mean",
            ),
            Mean_Volatility_Z=(
                "Volatility_Stress_Z",
                "mean",
            ),
            Mean_Credit_Z=(
                "Credit_Stress_Z",
                "mean",
            ),
            Mean_VKOSPI=(
                "VKOSPI",
                "mean",
            ),
            Mean_Credit_Spread_bp=(
                "Korea_Credit_Spread_bp",
                "mean",
            ),
        )
    )

    yearly["Stress_Rate"] = (
        yearly["Stress_Days"]
        / yearly["Days"]
    )

    columns = [
        "Days",
        "Stress_Days",
        "Stress_Rate",
        "Mean_MSI",
        "Median_MSI",
        "Mean_Equity_Z",
        "Mean_Volatility_Z",
        "Mean_Credit_Z",
        "Mean_VKOSPI",
        "Mean_Credit_Spread_bp",
    ]

    print(
        yearly[columns]
        .to_string()
    )


# ============================================================
# Focus years
# ============================================================

def print_focus_years(df):

    print()
    print("=" * 72)
    print("FOCUS YEARS: 2015 / 2022 / 2026")
    print("=" * 72)

    for year in FOCUS_YEARS:

        year_df = df[
            (
                df["Date"].dt.year
                == year
            )
            & (
                df[
                    "Is_Stress_Event"
                ].notna()
            )
        ].copy()

        if year_df.empty:
            continue

        stress = year_df[
            year_df[
                "Is_Stress_Event"
            ] == 1
        ].copy()

        print()
        print("-" * 72)
        print(f"YEAR {year}")
        print("-" * 72)

        print(
            "Evaluated days:",
            f"{len(year_df):,}",
        )

        print(
            "Stress days:",
            f"{len(stress):,}",
        )

        print(
            "Stress rate:",
            f"{len(stress) / len(year_df):.2%}",
        )

        if stress.empty:
            continue

        print()
        print(
            "Stress-day mean channel z-scores:"
        )

        print(
            stress[
                CHANNELS
            ]
            .mean()
            .sort_values(
                ascending=False
            )
        )

        print()
        print(
            "Stress-day median channel z-scores:"
        )

        print(
            stress[
                CHANNELS
            ]
            .median()
            .sort_values(
                ascending=False
            )
        )

        print()
        print(
            "Dominant channel counts "
            "on stress days:"
        )

        print(
            stress[
                "Dominant_Channel"
            ]
            .value_counts()
        )

        print()
        print(
            "Top 10 MSI days:"
        )

        cols = [
            "Date",
            "KOSPI200",
            "VKOSPI",
            "Korea_Credit_Spread_bp",
            "Equity_Stress_Z",
            "Volatility_Stress_Z",
            "Credit_Stress_Z",
            "Korea_MSI",
            "Stress_Threshold",
            "Dominant_Channel",
            "Dominance_Ratio",
        ]

        print(
            stress[cols]
            .nlargest(
                10,
                "Korea_MSI",
            )
            .to_string(
                index=False
            )
        )


# ============================================================
# Extreme single-channel observations
# ============================================================

def print_extreme_channel_days(df):

    print()
    print("=" * 72)
    print("EXTREME SINGLE-CHANNEL DAYS")
    print("=" * 72)

    for channel in CHANNELS:

        print()
        print("-" * 72)
        print(channel)
        print("-" * 72)

        cols = [
            "Date",
            "KOSPI200",
            "VKOSPI",
            "Korea_Credit_Spread_bp",
            "Equity_Stress_Z",
            "Volatility_Stress_Z",
            "Credit_Stress_Z",
            "Korea_MSI",
            "Stress_Threshold",
            "Is_Stress_Event",
            "Dominant_Channel",
            "Dominance_Ratio",
        ]

        print(
            df[
                df[channel].notna()
            ][cols]
            .nlargest(
                10,
                channel,
            )
            .to_string(
                index=False
            )
        )


# ============================================================
# Stress episode duration
# ============================================================

def print_episode_qa(df):

    valid = df[
        df["Is_Stress_Event"].notna()
    ].copy()

    valid["Is_Stress_Event"] = (
        valid["Is_Stress_Event"]
        .astype(int)
    )

    # New group whenever event state changes
    valid["State_Group"] = (
        valid["Is_Stress_Event"]
        .ne(
            valid[
                "Is_Stress_Event"
            ].shift()
        )
        .cumsum()
    )

    episodes = []

    for _, group in valid.groupby(
        "State_Group"
    ):

        if (
            group[
                "Is_Stress_Event"
            ].iloc[0]
            != 1
        ):
            continue

        episodes.append(
            {
                "Start": (
                    group["Date"]
                    .iloc[0]
                ),
                "End": (
                    group["Date"]
                    .iloc[-1]
                ),
                "Trading_Days": len(group),
                "Peak_MSI": (
                    group[
                        "Korea_MSI"
                    ].max()
                ),
                "Mean_MSI": (
                    group[
                        "Korea_MSI"
                    ].mean()
                ),
            }
        )

    episodes = pd.DataFrame(
        episodes
    )

    print()
    print("=" * 72)
    print("STRESS EPISODE DURATION QA")
    print("=" * 72)

    if episodes.empty:
        print("No stress episodes found.")
        return

    print()
    print(
        "Number of episodes:",
        f"{len(episodes):,}",
    )

    print()

    print(
        "Episode duration summary:"
    )

    print(
        episodes[
            "Trading_Days"
        ].describe(
            percentiles=[
                0.50,
                0.75,
                0.90,
                0.95,
            ]
        )
    )

    print()
    print(
        "20 longest stress episodes:"
    )

    print(
        episodes
        .sort_values(
            "Trading_Days",
            ascending=False,
        )
        .head(20)
        .to_string(
            index=False
        )
    )


# ============================================================
# Main
# ============================================================

def main():

    df = load_data()

    df = add_dominant_channel(
        df
    )

    print("=" * 72)
    print("KOREA MSI DIAGNOSTIC QA")
    print("=" * 72)

    print(
        "Rows:",
        f"{len(df):,}",
    )

    print(
        "Date range:",
        df["Date"].min().date(),
        "→",
        df["Date"].max().date(),
    )

    print_overall_channel_qa(df)

    print_dominance_qa(df)

    print_stress_event_qa(df)

    print_yearly_qa(df)

    print_focus_years(df)

    print_extreme_channel_days(df)

    print_episode_qa(df)

    print()
    print("=" * 72)
    print("QA COMPLETE")
    print("=" * 72)

    print(
        "No MSI definition, threshold, "
        "or Stress Event label was modified."
    )


if __name__ == "__main__":
    main()