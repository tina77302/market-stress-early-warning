import os
import requests
import pandas as pd
from dotenv import load_dotenv


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

SERIES = {
    "Korea_Treasury_3Y": "010200000",
    "Korea_Corporate_AAminus_3Y": "010310000",
}

# 짧은 기간 테스트
START_DATE = "20260921"
END_DATE = "20261002"


# ============================================================
# ECOS API request
# ============================================================

def fetch_series(series_name, item_code):

    url = (
        f"{BASE_URL}/"
        f"{API_KEY}/json/kr/"
        f"1/1000/"
        f"{STAT_CODE}/"
        f"{FREQUENCY}/"
        f"{START_DATE}/"
        f"{END_DATE}/"
        f"{item_code}"
    )

    print()
    print("=" * 60)
    print(f"REQUEST: {series_name}")
    print("=" * 60)

    response = requests.get(
        url,
        timeout=30,
    )

    print("HTTP Status:", response.status_code)

    response.raise_for_status()

    data = response.json()

    # --------------------------------------------------------
    # ECOS error handling
    # --------------------------------------------------------

    if "RESULT" in data:

        result = data["RESULT"]

        raise RuntimeError(
            f"ECOS API Error: "
            f"{result.get('CODE')} | "
            f"{result.get('MESSAGE')}"
        )

    if "StatisticSearch" not in data:

        raise RuntimeError(
            "StatisticSearch가 응답에 없습니다.\n"
            f"Response keys: {list(data.keys())}"
        )

    rows = data["StatisticSearch"].get(
        "row",
        [],
    )

    print("Rows returned:", len(rows))

    parsed_rows = []

    for row in rows:

        value = row.get("DATA_VALUE")

        if value is None or value == "":
            numeric_value = None
        else:
            numeric_value = float(
                str(value).replace(",", "")
            )

        parsed_rows.append(
            {
                "Date": row.get("TIME"),
                "Series": series_name,
                "ItemName": row.get("ITEM_NAME1"),
                "Value": numeric_value,
                "Unit": row.get("UNIT_NAME"),
            }
        )

    return pd.DataFrame(parsed_rows)


# ============================================================
# Main
# ============================================================

def main():

    all_frames = []

    for series_name, item_code in SERIES.items():

        df = fetch_series(
            series_name,
            item_code,
        )

        if df.empty:

            print(
                f"[WARNING] No data returned: "
                f"{series_name}"
            )

        else:

            print()
            print(df)

            all_frames.append(df)

    if not all_frames:

        raise RuntimeError(
            "두 금리 모두 데이터를 받지 못했습니다."
        )

    combined = pd.concat(
        all_frames,
        ignore_index=True,
    )

    print()
    print("=" * 60)
    print("COMBINED RESULT")
    print("=" * 60)

    print(combined)

    print()
    print("Series counts:")
    print(
        combined["Series"]
        .value_counts()
    )

    print()
    print("Missing values:")
    print(
        combined.isna().sum()
    )


if __name__ == "__main__":
    main()