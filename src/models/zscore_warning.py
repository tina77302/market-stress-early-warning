import argparse
import logging

import numpy as np
import pandas as pd

from src.config import DATA_FEATURES_DIR, DATA_PROCESSED_DIR


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Stress Event uses the past 90th percentile of MSI (targets.py).
# The Z-score WATCH warning fires earlier, at the past 80th percentile.
WATCH_QUANTILE = 0.80
MIN_PERIODS = 252

MARKETS = {
    "us": {
        "input_path": DATA_FEATURES_DIR / "market_stress_index.csv",
        "output_path": DATA_FEATURES_DIR / "zscore_warning.csv",
        "msi_col": "MSI",
    },
    "kr": {
        "input_path": DATA_PROCESSED_DIR / "korea" / "korea_stress_index.csv",
        "output_path": DATA_PROCESSED_DIR / "korea" / "korea_zscore_warning.csv",
        "msi_col": "Korea_MSI",
    },
}


def add_zscore_warning(
    df,
    msi_col="MSI",
    quantile=WATCH_QUANTILE,
    min_periods=MIN_PERIODS,
):
    """
    Z-score WATCH warning.

    MSI는 주식·변동성·신용 세 채널의 past-only 252일 Z-score
    동일 가중 평균입니다. 날짜 t의 MSI가 t-1까지의 과거 MSI
    분포에서 quantile 분위수 이상이면 ZScore_Warning = 1.

    Stress Event(90% 분위수)와 같은 방식으로 계산하되 기준을
    낮춰, 스트레스 이벤트에 도달하기 전에 경보를 냅니다.
    Threshold 계산에 날짜 t 이후의 정보는 사용하지 않습니다.

    검증: docs/experiments/warning-methods-comparison.md
    (experiments/warning-methods 브랜치)
    """

    if msi_col not in df.columns:
        raise ValueError(f"Missing MSI column: {msi_col}")

    out = df.copy()

    # 현재 t를 제외하고 t-1까지의 MSI만 threshold 계산에 사용
    historical_msi = out[msi_col].shift(1)

    out["ZScore_Watch_Threshold"] = (
        historical_msi
        .expanding(min_periods=min_periods)
        .quantile(quantile)
    )

    # Threshold가 없는 초기 구간과 MSI 결측은 0이 아니라 NaN
    valid = out["ZScore_Watch_Threshold"].notna() & out[msi_col].notna()
    out["ZScore_Warning"] = np.where(
        valid,
        (out[msi_col] >= out["ZScore_Watch_Threshold"]).astype(float),
        np.nan
    )

    return out


def latest_zscore_warning(df, msi_col="MSI"):
    """Return the most recent row with a defined Z-score warning."""

    valid = df[df["ZScore_Warning"].notna()]

    if valid.empty:
        raise ValueError("No row with a defined Z-score warning.")

    row = valid.iloc[-1]

    return {
        "date": pd.Timestamp(row.name).date().isoformat(),
        "msi": float(row[msi_col]),
        "watch_threshold": float(row["ZScore_Watch_Threshold"]),
        "warning_active": bool(row["ZScore_Warning"] == 1),
    }


def run(market):
    config = MARKETS[market]

    logger.info(f"Reading MSI from {config['input_path']}")

    df = pd.read_csv(
        config["input_path"],
        index_col="Date",
        parse_dates=True,
        encoding="utf-8-sig"
    )
    df.sort_index(inplace=True)

    if df.index.duplicated().any():
        raise ValueError("Duplicate dates found.")

    df = add_zscore_warning(df, msi_col=config["msi_col"])

    output = df[
        [config["msi_col"], "ZScore_Watch_Threshold", "ZScore_Warning"]
    ]
    output.to_csv(config["output_path"])

    defined = output["ZScore_Warning"].dropna()
    latest = latest_zscore_warning(df, msi_col=config["msi_col"])

    logger.info(f"Saved: {config['output_path']}")
    logger.info(
        f"{market.upper()} warning days: "
        f"{int(defined.sum()):,} / {len(defined):,} "
        f"({defined.mean():.1%})"
    )
    logger.info(
        f"{market.upper()} latest {latest['date']}: "
        f"MSI {latest['msi']:.3f}, "
        f"watch threshold {latest['watch_threshold']:.3f}, "
        f"warning {'ON' if latest['warning_active'] else 'off'}"
    )

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Z-score WATCH warning from the Market Stress Index."
    )
    parser.add_argument(
        "--market",
        choices=["us", "kr", "all"],
        default="all"
    )
    args = parser.parse_args()

    markets = ["us", "kr"] if args.market == "all" else [args.market]

    for market in markets:
        if not MARKETS[market]["input_path"].exists():
            logger.warning(
                f"Skipping {market.upper()}: "
                f"{MARKETS[market]['input_path']} not found."
            )
            continue
        run(market)


if __name__ == "__main__":
    main()
