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

URL = "http://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd"

START_DATE = datetime(2010, 1, 4)
END_DATE = None  # resolved at main()

OUTPUT_PATH = "data/raw/korea/vkospi.csv"

TARGET_INDEX = "코스피 200 변동성지수"

CHECKPOINT_EVERY = 100
REQUEST_DELAY = 0.20
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
# KRX request
# ============================================================

def fetch_krx_date(date, max_retries=MAX_RETRIES):
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
                print(f"Retrying in {wait_seconds}s...")
                time.sleep(wait_seconds)

        except requests.RequestException as exc:

            print(
                f"[WARNING] {bas_dd} request error: {exc} "
                f"(attempt {attempt}/{max_retries})"
            )

            if attempt < max_retries:
                wait_seconds = attempt * 2
                print(f"Retrying in {wait_seconds}s...")
                time.sleep(wait_seconds)

    print(
        f"[ERROR] {bas_dd} failed after "
        f"{max_retries} attempts."
    )

    return None


# ============================================================
# Extract VKOSPI
# ============================================================

def parse_vkospi(raw_rows):
    for row in raw_rows:

        if row.get("IDX_NM") == TARGET_INDEX:

            return {
                "Date": row.get("BAS_DD"),
                "Index": "VKOSPI",
                "Close": to_float(row.get("CLSPRC_IDX")),
                "Change": to_float(row.get("CMPPREVDD_IDX")),
                "ReturnPct": to_float(row.get("FLUC_RT")),
                "Open": to_float(row.get("OPNPRC_IDX")),
                "High": to_float(row.get("HGPRC_IDX")),
                "Low": to_float(row.get("LWPRC_IDX")),
            }

    return None


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
        df.sort_values("Date")
        .drop_duplicates(
            subset=["Date"],
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
# Resume
# ============================================================

def load_existing_data():

    if not os.path.exists(OUTPUT_PATH):
        return pd.DataFrame(), START_DATE

    df = pd.read_csv(OUTPUT_PATH)

    if df.empty:
        return pd.DataFrame(), START_DATE

    df["Date"] = pd.to_datetime(df["Date"])

    earliest_date = df["Date"].min()

    if earliest_date > START_DATE:

        print()
        print("=" * 60)
        print("PARTIAL FILE DETECTED")
        print("=" * 60)

        print(
            f"Existing file starts at "
            f"{earliest_date.date()}."
        )

        print(
            "Historical collection will restart "
            "from the target start date."
        )

        print()

        return df, START_DATE

    last_date = df["Date"].max()
    resume_date = next_resume_date(df.loc[df.Close.notna(), "Date"], START_DATE, END_DATE)

    print()
    print("=" * 60)
    print("RESUME MODE")
    print("=" * 60)

    print(f"Existing rows: {len(df):,}")

    print(
        f"Existing date range: "
        f"{earliest_date.date()} → "
        f"{last_date.date()}"
    )

    print(
        f"Resume from: {resume_date.date()}"
    )

    print()

    return df, resume_date


# ============================================================
# Final QA
# ============================================================

def print_final_qa(df, failed_dates):

    print()
    print("=" * 60)
    print("DOWNLOAD COMPLETE")
    print("=" * 60)

    print(f"Saved: {OUTPUT_PATH}")
    print(f"Rows: {len(df):,}")

    if not df.empty:

        print(
            "Date range:",
            df["Date"].min().date(),
            "→",
            df["Date"].max().date(),
        )

        print()

        print("Missing values:")
        print(df.isna().sum())

        print()

        duplicate_count = df.duplicated(
            subset=["Date"]
        ).sum()

        print(
            "Duplicate dates:",
            duplicate_count,
        )

        print()

        print("First rows:")
        print(df.head())

        print()

        print("Last rows:")
        print(df.tail())

    print()

    print(
        "Completely failed API request dates:",
        len(failed_dates),
    )

    if failed_dates:
        for date in failed_dates[:20]:
            print(date)


# ============================================================
# Main
# ============================================================

def main():

    global START_DATE, END_DATE, OUTPUT_PATH
    args = configure()
    START_DATE, END_DATE = args.start, args.end
    OUTPUT_PATH = str(args.raw / "vkospi.csv")

    existing_df, current_date = load_existing_data()
    if not existing_df.empty:
        receipt(OUTPUT_PATH, "VKOSPI", existing_df, origin="LOCAL_BASELINE_READ")

    new_rows = []

    request_count = 0
    collected_count = 0
    failed_dates = []

    print("=" * 60)
    print("KRX VKOSPI Historical Download")
    print("=" * 60)

    print("Target index:", TARGET_INDEX)
    print("Target start:", START_DATE.date())
    print("Target end:  ", END_DATE.date())
    print("Current start:", current_date.date())

    print()

    if current_date > END_DATE:

        print("Historical data is already up to date.")

        print_final_qa(
            existing_df,
            failed_dates,
        )

        return

    completed_dates = existing_df.loc[existing_df.Close.notna(), "Date"] if not existing_df.empty else []
    eligible_sessions = set(sessions(START_DATE, END_DATE).difference(pd.DatetimeIndex(completed_dates)))
    while current_date <= END_DATE:

        # Saturday / Sunday
        if pd.Timestamp(current_date) in eligible_sessions:

            raw_rows = fetch_krx_date(
                current_date
            )

            request_count += 1

            if raw_rows is None:

                failed_dates.append(
                    current_date.strftime("%Y-%m-%d")
                )

            else:

                parsed = parse_vkospi(
                    raw_rows
                )

                if parsed is not None and pd.Timestamp(parsed["Date"]).normalize() == pd.Timestamp(current_date):
                    receipt(OUTPUT_PATH, "VKOSPI", pd.DataFrame([parsed]))

                    new_rows.append(parsed)
                    collected_count += 1

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
                    f"VKOSPI dates: "
                    f"{collected_count:,} | "
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

    print_final_qa(
        final_df,
        failed_dates,
    )
    if failed_dates:
        raise RuntimeError("Ingestion incomplete; failed sessions will be retried")


if __name__ == "__main__":
    main()
