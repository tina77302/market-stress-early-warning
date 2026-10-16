import os
import time
from datetime import datetime, timedelta

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

API_KEY = os.getenv("KRX_API_KEY")

if not API_KEY:
    raise ValueError("KRX_API_KEY가 .env에 없습니다.")

URL = "http://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd"

START_DATE = datetime(2010, 1, 4)
END_DATE = None  # resolved at main()

OUTPUT_PATH = "data/raw/korea/krx_indices.csv"

TARGET_INDICES = {
    "코스피": "KOSPI",
    "코스피 200": "KOSPI200",
}

# 몇 번 요청할 때마다 중간 저장할지
CHECKPOINT_EVERY = 100

# 일반 요청 사이 대기시간
REQUEST_DELAY = 0.20

# 한 날짜 요청 실패 시 최대 재시도 횟수
MAX_RETRIES = 5


# ============================================================
# KRX request
# ============================================================

def fetch_krx_date(date: datetime, max_retries: int = MAX_RETRIES):
    bas_dd = date.strftime("%Y%m%d")

    for attempt in range(1, max_retries + 1):

        try:
            response = requests.get(
                URL,
                headers={"AUTH_KEY": API_KEY},
                params={"basDd": bas_dd},
                timeout=30,
            )

            if response.status_code == 200:

                try:
                    data = response.json()
                    return data.get("OutBlock_1", [])

                except ValueError:
                    print(
                        f"[WARNING] {bas_dd} "
                        f"Non-JSON response "
                        f"(attempt {attempt}/{max_retries})"
                    )

            else:
                print(
                    f"[WARNING] {bas_dd} "
                    f"HTTP {response.status_code} "
                    f"(attempt {attempt}/{max_retries})"
                )

            if attempt < max_retries:
                wait_seconds = attempt * 2

                print(
                    f"Retrying in {wait_seconds}s..."
                )

                time.sleep(wait_seconds)

        except requests.RequestException as exc:

            print(
                f"[WARNING] {bas_dd} "
                f"request error: {exc} "
                f"(attempt {attempt}/{max_retries})"
            )

            if attempt < max_retries:
                wait_seconds = attempt * 2

                print(
                    f"Retrying in {wait_seconds}s..."
                )

                time.sleep(wait_seconds)

    print(
        f"[ERROR] {bas_dd} failed after "
        f"{max_retries} attempts."
    )

    return None


# ============================================================
# Convert KRX response
# ============================================================
def to_float(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return float(value.replace(",", ""))

def parse_rows(raw_rows):
    parsed = []

    for row in raw_rows:

        index_name = row.get("IDX_NM")

        if index_name not in TARGET_INDICES:
            continue

        parsed.append(
            {
                "Date": row["BAS_DD"],
                "Index": TARGET_INDICES[index_name],
                "Close": to_float(row.get("CLSPRC_IDX")),
                "Change": to_float(row.get("CMPPREVDD_IDX")),
                "ReturnPct": to_float(row.get("FLUC_RT")),
                "Open": to_float(row.get("OPNPRC_IDX")),
                "High": to_float(row.get("HGPRC_IDX")),
                "Low": to_float(row.get("LWPRC_IDX")),
                "Volume": to_float(row.get("ACC_TRDVOL")),
                "TradingValue": to_float(row.get("ACC_TRDVAL")),
                "MarketCap": to_float(row.get("MKTCAP")),
            }
        )

    return parsed
    


# ============================================================
# Save checkpoint
# ============================================================

def save_checkpoint(existing_df, new_rows):

    frames = []

    if existing_df is not None and not existing_df.empty:
        frames.append(existing_df.copy())

    if new_rows:
        frames.append(pd.DataFrame(new_rows))

    if not frames:
        return pd.DataFrame()

    df = pd.concat(
        frames,
        ignore_index=True,
    )

    df["Date"] = pd.to_datetime(
        df["Date"],
        format="mixed",
    )

    df = (
        df.sort_values(["Date", "Index"])
        .drop_duplicates(
            subset=["Date", "Index"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    os.makedirs(
        os.path.dirname(OUTPUT_PATH),
        exist_ok=True,
    )

    atomic_csv(df, OUTPUT_PATH)

    return df


# ============================================================
# Existing data / Resume
# ============================================================

def load_existing_data():

    if not os.path.exists(OUTPUT_PATH):
        return pd.DataFrame(), START_DATE

    df = pd.read_csv(OUTPUT_PATH)

    if df.empty:
        return pd.DataFrame(), START_DATE

    df["Date"] = pd.to_datetime(df["Date"])

    # --------------------------------------------------------
    # 이전 QA용 CSV인지 확인
    # --------------------------------------------------------

    earliest_date = df["Date"].min()

    if earliest_date > START_DATE:

        print()
        print("=" * 60)
        print("OLD QA FILE DETECTED")
        print("=" * 60)

        print(
            f"Existing file starts at "
            f"{earliest_date.date()}."
        )

        print(
            "This is not the full historical dataset."
        )

        print(
            "Existing rows will be preserved "
            "during historical backfill."
        )

        print()

        return df, START_DATE

    # --------------------------------------------------------
    # 정상적인 장기 데이터라면 이어받기
    # --------------------------------------------------------

    last_date = df["Date"].max()

    complete = df.loc[df.Close.notna()].groupby("Date")["Index"].nunique()
    resume_date = next_resume_date(complete.index[complete >= 2], START_DATE, END_DATE)

    print()
    print("=" * 60)
    print("RESUME MODE")
    print("=" * 60)

    print(
        f"Existing rows: {len(df):,}"
    )

    print(
        f"Existing date range: "
        f"{df['Date'].min().date()} "
        f"→ {last_date.date()}"
    )

    print(
        f"Resume from: {resume_date.date()}"
    )

    print()

    return df, resume_date


# ============================================================
# Final QA
# ============================================================

def print_final_qa(df):

    print()
    print("=" * 60)
    print("DOWNLOAD COMPLETE")
    print("=" * 60)

    print(
        f"Saved: {OUTPUT_PATH}"
    )

    print(
        f"Rows: {len(df):,}"
    )

    print(
        f"Trading dates: {df['Date'].nunique():,}"
    )

    print()

    print("Date range by index:")

    print(
        df.groupby("Index")["Date"]
        .agg(["min", "max", "count"])
    )

    print()

    print("Missing values:")

    print(
        df.isna().sum()
    )

    print()

    print("Duplicate Date/Index rows:")

    duplicate_count = df.duplicated(
        subset=["Date", "Index"]
    ).sum()

    print(duplicate_count)

    print()

    # 각 거래일마다 두 지수가 모두 존재하는지 확인
    counts = (
        df.groupby("Date")["Index"]
        .nunique()
    )

    incomplete_dates = counts[counts < 2]

    print(
        "Trading dates missing one of "
        "KOSPI / KOSPI200:"
    )

    print(len(incomplete_dates))

    if len(incomplete_dates) > 0:
        print(incomplete_dates.head(20))

    print()

    print("First rows:")
    print(df.head())

    print()

    print("Last rows:")
    print(df.tail())


# ============================================================
# Main
# ============================================================

def main():

    global START_DATE, END_DATE, OUTPUT_PATH
    args = configure()
    START_DATE, END_DATE = args.start, args.end
    OUTPUT_PATH = str(args.raw / "krx_indices.csv")

    existing_df, current_date = load_existing_data()
    if not existing_df.empty:
        receipt(OUTPUT_PATH, "KRX_indices", existing_df, origin="LOCAL_BASELINE_READ")

    new_rows = []

    request_count = 0
    trading_dates_collected = 0
    failed_dates = []

    print("=" * 60)
    print("KRX KOSPI / KOSPI200 Historical Download")
    print("=" * 60)

    print(
        "Target start:",
        START_DATE.date(),
    )

    print(
        "Target end:  ",
        END_DATE.date(),
    )

    print(
        "Current start:",
        current_date.date(),
    )

    print()

    # 이미 다운로드 완료된 경우
    if current_date > END_DATE:

        print(
            "Historical data is already up to date."
        )

        print_final_qa(existing_df)

        return

    completed = (existing_df.loc[existing_df.Close.notna()].groupby("Date")["Index"].nunique()
                 if not existing_df.empty else pd.Series(dtype=int))
    completed_dates = completed.index[completed >= 2]
    eligible_sessions = set(sessions(START_DATE, END_DATE).difference(pd.DatetimeIndex(completed_dates)))
    while current_date <= END_DATE:

        # 토요일 / 일요일 제외
        if pd.Timestamp(current_date) in eligible_sessions:

            raw_rows = fetch_krx_date(
                current_date
            )

            request_count += 1

            # 완전한 요청 실패
            if raw_rows is None:

                failed_dates.append(
                    current_date.strftime("%Y-%m-%d")
                )

            else:

                parsed = parse_rows(raw_rows)

                parsed = [r for r in parsed if pd.Timestamp(r["Date"]).normalize() == pd.Timestamp(current_date)]
                if parsed:
                    receipt(OUTPUT_PATH, "KRX_indices", pd.DataFrame(parsed))

                    new_rows.extend(parsed)

                    trading_dates_collected += 1

            # ------------------------------------------------
            # Checkpoint
            # ------------------------------------------------

            if request_count % CHECKPOINT_EVERY == 0:

                existing_df = save_checkpoint(
                    existing_df,
                    new_rows,
                )

                new_rows = []

                print(
                    f"Requests: {request_count:,} | "
                    f"New trading dates: "
                    f"{trading_dates_collected:,} | "
                    f"Current date: "
                    f"{current_date.date()} | "
                    f"Saved rows: "
                    f"{len(existing_df):,}"
                )

            time.sleep(REQUEST_DELAY)

        current_date += timedelta(days=1)

    # ========================================================
    # Final save
    # ========================================================

    final_df = save_checkpoint(
        existing_df,
        new_rows,
    )

    # ========================================================
    # Failed-date report
    # ========================================================

    if failed_dates:

        print()
        print("=" * 60)
        print("FAILED REQUEST DATES")
        print("=" * 60)

        print(
            f"Failed dates: {len(failed_dates)}"
        )

        for date in failed_dates:
            print(date)

        print()
        print(
            "These dates should be checked "
            "before modelling."
        )

    # ========================================================
    # Final QA
    # ========================================================

    print_final_qa(final_df)
    if failed_dates:
        raise RuntimeError("Ingestion incomplete; failed sessions will be retried")


if __name__ == "__main__":
    main()
