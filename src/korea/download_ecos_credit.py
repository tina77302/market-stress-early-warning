import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

try:
    from .ingestion import configure, sessions, resume_date as next_resume_date, atomic_csv, receipt
except ImportError:
    from ingestion import configure, sessions, resume_date as next_resume_date, atomic_csv, receipt


# ============================================================
# Configuration
# ============================================================

load_dotenv()

API_KEY = os.getenv("ECOS_API_KEY")

if not API_KEY:
    raise ValueError("ECOS_API_KEY가 .env에 없습니다.")


BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"

STAT_CODE = "817Y002"
FREQUENCY = "D"

START_DATE = "20100104"
END_DATE = None  # resolved at main(), never frozen at import

SERIES = {
    "Korea_Treasury_3Y": "010200000",
    "Korea_Corporate_AAminus_3Y": "010310000",
}

OUTPUT_PATH = "data/raw/korea/ecos_credit.csv"

# 이미 수집 완료한 KRX 거래일 데이터
KRX_PATH = "data/raw/korea/krx_indices.csv"

MAX_RETRIES = 5


# ============================================================
# Safe numeric conversion
# ============================================================

def to_float(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return float(value.replace(",", ""))


# ============================================================
# ECOS API request
# ============================================================

def fetch_series(series_name, item_code):

    url = (
        f"{BASE_URL}/"
        f"{API_KEY}/json/kr/"
        f"1/10000/"
        f"{STAT_CODE}/"
        f"{FREQUENCY}/"
        f"{START_DATE}/"
        f"{END_DATE}/"
        f"{item_code}"
    )

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            response = requests.get(
                url,
                timeout=60,
            )

            print(
                f"{series_name} | "
                f"HTTP {response.status_code} | "
                f"attempt {attempt}/{MAX_RETRIES}"
            )

            response.raise_for_status()

            data = response.json()

            # ------------------------------------------------
            # ECOS API error
            # ------------------------------------------------

            if "RESULT" in data:

                result = data["RESULT"]

                if result.get("CODE") == "INFO-200":
                    return pd.DataFrame({"Date": pd.Series(dtype="datetime64[ns]"), series_name: pd.Series(dtype=float)})
                raise RuntimeError(
                    f"ECOS API Error: "
                    f"{result.get('CODE')} | "
                    f"{result.get('MESSAGE')}"
                )

            if "StatisticSearch" not in data:

                raise RuntimeError(
                    "StatisticSearch가 응답에 없습니다."
                )

            rows = data["StatisticSearch"].get(
                "row",
                [],
            )

            print(
                f"{series_name} rows returned: "
                f"{len(rows):,}"
            )

            parsed = []

            for row in rows:

                parsed.append(
                    {
                        "Date": row.get("TIME"),
                        series_name: to_float(
                            row.get("DATA_VALUE")
                        ),
                    }
                )

            df = pd.DataFrame(parsed)

            if df.empty:
                return pd.DataFrame({"Date": pd.Series(dtype="datetime64[ns]"), series_name: pd.Series(dtype=float)})

            df["Date"] = pd.to_datetime(
                df["Date"],
                format="%Y%m%d",
            )

            df = (
                df.sort_values("Date")
                .drop_duplicates(
                    subset=["Date"],
                    keep="last",
                )
                .reset_index(drop=True)
            )

            df = df.loc[df.Date.between(pd.Timestamp(START_DATE), pd.Timestamp(END_DATE))]
            receipt(OUTPUT_PATH, series_name, df)
            return df

        except (
            requests.RequestException,
            ValueError,
        ) as exc:

            print(
                f"[WARNING] {series_name}: "
                f"{type(exc).__name__}"
            )

            if attempt < MAX_RETRIES:

                wait_seconds = attempt * 2

                print(
                    f"Retrying in "
                    f"{wait_seconds}s..."
                )

                time.sleep(wait_seconds)

    raise RuntimeError(
        f"{series_name} failed after "
        f"{MAX_RETRIES} attempts."
    )


# ============================================================
# Load KRX trading calendar
# ============================================================

def load_krx_calendar():

    if not os.path.exists(KRX_PATH):

        raise FileNotFoundError(
            f"KRX file not found: {KRX_PATH}"
        )

    krx = pd.read_csv(KRX_PATH)

    if "Date" not in krx.columns:

        raise ValueError(
            "Date column not found in KRX file."
        )

    krx["Date"] = pd.to_datetime(
        krx["Date"]
    )

    # KOSPI와 KOSPI200이 같이 들어 있으므로
    # 날짜만 unique하게 사용
    calendar = (
        krx[["Date"]]
        .drop_duplicates()
        .sort_values("Date")
        .reset_index(drop=True)
    )

    return calendar


# ============================================================
# QA
# ============================================================

def run_qa(raw_credit, aligned_credit, calendar):

    print()
    print("=" * 60)
    print("DATA QA")
    print("=" * 60)

    print()
    print("Raw ECOS credit rows:")
    print(f"{len(raw_credit):,}")

    print(
        "Raw ECOS date range:",
        raw_credit["Date"].min().date(),
        "→",
        raw_credit["Date"].max().date(),
    )

    print()

    print("KRX trading dates:")
    print(f"{len(calendar):,}")

    print(
        "KRX date range:",
        calendar["Date"].min().date(),
        "→",
        calendar["Date"].max().date(),
    )

    print()

    print("Aligned rows:")
    print(f"{len(aligned_credit):,}")

    print()

    print("Missing values after KRX alignment:")
    print(
        aligned_credit.isna().sum()
    )

    print()

    duplicate_count = (
        aligned_credit
        .duplicated(subset=["Date"])
        .sum()
    )

    print(
        "Duplicate dates:",
        duplicate_count,
    )

    print()

    treasury_missing = (
        aligned_credit[
            "Korea_Treasury_3Y"
        ]
        .isna()
        .sum()
    )

    corporate_missing = (
        aligned_credit[
            "Korea_Corporate_AAminus_3Y"
        ]
        .isna()
        .sum()
    )

    spread_missing = (
        aligned_credit[
            "Korea_Credit_Spread"
        ]
        .isna()
        .sum()
    )

    print(
        "Treasury missing on KRX dates:",
        treasury_missing,
    )

    print(
        "Corporate missing on KRX dates:",
        corporate_missing,
    )

    print(
        "Credit spread missing on KRX dates:",
        spread_missing,
    )

    print()

    # --------------------------------------------------------
    # ECOS dates that are not KRX trading dates
    # --------------------------------------------------------

    krx_dates = set(calendar["Date"])

    ecos_extra_dates = raw_credit[
        ~raw_credit["Date"].isin(
            krx_dates
        )
    ]

    print(
        "ECOS dates outside KRX trading calendar:",
        len(ecos_extra_dates),
    )

    if not ecos_extra_dates.empty:

        print(
            ecos_extra_dates[
                [
                    "Date",
                    "Korea_Treasury_3Y",
                    "Korea_Corporate_AAminus_3Y",
                    "Korea_Credit_Spread",
                ]
            ].head(20)
        )

    print()

    print("First rows:")
    print(aligned_credit.head())

    print()

    print("Last rows:")
    print(aligned_credit.tail())


# ============================================================
# Main
# ============================================================

def main():

    global START_DATE, END_DATE, OUTPUT_PATH, KRX_PATH
    args = configure()
    START_DATE, END_DATE = args.start.strftime("%Y%m%d"), args.end.strftime("%Y%m%d")
    OUTPUT_PATH, KRX_PATH = str(args.raw / "ecos_credit.csv"), str(args.raw / "krx_indices.csv")

    print("=" * 60)
    print("BOK ECOS Korea Credit Data Download")
    print("=" * 60)

    print(
        "Period:",
        START_DATE,
        "→",
        END_DATE,
    )

    print()

    # --------------------------------------------------------
    # Download Treasury
    # --------------------------------------------------------

    treasury = fetch_series(
        "Korea_Treasury_3Y",
        SERIES["Korea_Treasury_3Y"],
    )

    # --------------------------------------------------------
    # Download Corporate AA-
    # --------------------------------------------------------

    corporate = fetch_series(
        "Korea_Corporate_AAminus_3Y",
        SERIES[
            "Korea_Corporate_AAminus_3Y"
        ],
    )

    # --------------------------------------------------------
    # Merge ECOS series
    # --------------------------------------------------------

    if treasury.empty and corporate.empty:
        print("No new ECOS observations; existing files preserved.")
        return

    credit = pd.merge(
        treasury,
        corporate,
        on="Date",
        how="outer",
        validate="one_to_one",
    )

    credit = (
        credit
        .sort_values("Date")
        .reset_index(drop=True)
    )

    # ========================================================
    # Credit Spread
    #
    # AA- Corporate Bond 3Y Yield
    # minus
    # Korea Treasury 3Y Yield
    #
    # Both original ECOS series are annual percentage rates.
    # Therefore this column is measured in percentage points.
    # ========================================================

    credit["Korea_Credit_Spread"] = (
        credit["Korea_Corporate_AAminus_3Y"]
        - credit["Korea_Treasury_3Y"]
    )

    # Optional basis-point representation for interpretation
    credit["Korea_Credit_Spread_bp"] = (
        credit["Korea_Credit_Spread"]
        * 100
    )

    # --------------------------------------------------------
    # KRX trading calendar
    # --------------------------------------------------------

    calendar = load_krx_calendar()

    # Restrict calendar to target period
    start_dt = pd.to_datetime(
        START_DATE,
        format="%Y%m%d",
    )

    end_dt = pd.to_datetime(
        END_DATE,
        format="%Y%m%d",
    )

    calendar = calendar[
        (calendar["Date"] >= start_dt)
        & (calendar["Date"] <= end_dt)
    ].copy()

    # --------------------------------------------------------
    # Align credit data to Korean equity trading dates
    #
    # IMPORTANT:
    # We do NOT forward-fill here.
    # First inspect actual missing dates.
    # --------------------------------------------------------

    aligned = pd.merge(
        calendar,
        credit,
        on="Date",
        how="left",
        validate="one_to_one",
    )

    # --------------------------------------------------------
    # QA before any missing-value treatment
    # --------------------------------------------------------

    run_qa(
        raw_credit=credit,
        aligned_credit=aligned,
        calendar=calendar,
    )

    # --------------------------------------------------------
    # Save
    #
    # Keep missing values as-is for now.
    # Missing-value treatment will be decided only after QA.
    # --------------------------------------------------------

    os.makedirs(
        os.path.dirname(OUTPUT_PATH),
        exist_ok=True,
    )

    # Preserve older observations if a bounded/no-new-data response is returned.
    if os.path.exists(OUTPUT_PATH):
        old = pd.read_csv(OUTPUT_PATH, parse_dates=["Date"]).set_index("Date")
        aligned = aligned.set_index("Date").combine_first(old).sort_index().reset_index()
    aligned["Korea_Credit_Spread"] = aligned["Korea_Corporate_AAminus_3Y"] - aligned["Korea_Treasury_3Y"]
    aligned["Korea_Credit_Spread_bp"] = aligned["Korea_Credit_Spread"] * 100
    atomic_csv(aligned, OUTPUT_PATH)
    unaligned_path = args.raw / "ecos_credit_unaligned.csv"
    if unaligned_path.exists():
        credit = credit.set_index("Date").combine_first(pd.read_csv(unaligned_path, parse_dates=["Date"]).set_index("Date")).sort_index().reset_index()
    atomic_csv(credit, unaligned_path)

    print()
    print("=" * 60)
    print("SAVE COMPLETE")
    print("=" * 60)

    print("Saved:", OUTPUT_PATH)
    print(f"Rows: {len(aligned):,}")

    print()

    print(
        "IMPORTANT: No forward-fill or "
        "missing-value imputation was applied."
    )


if __name__ == "__main__":
    main()