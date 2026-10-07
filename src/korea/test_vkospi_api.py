import os

import requests
from dotenv import load_dotenv


# ============================================================
# Configuration
# ============================================================

load_dotenv()

API_KEY = os.getenv("KRX_API_KEY")

if not API_KEY:
    raise ValueError("KRX_API_KEY가 .env에 없습니다.")

URL = "http://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd"

# 최근 정상 거래일로 테스트
TEST_DATE = "20261002"


# ============================================================
# Request
# ============================================================

print("=" * 60)
print("KRX Derivatives Index API Test")
print("=" * 60)
print("Test date:", TEST_DATE)
print()

response = requests.get(
    URL,
    headers={"AUTH_KEY": API_KEY},
    params={"basDd": TEST_DATE},
    timeout=30,
)

print("HTTP Status:", response.status_code)

try:
    data = response.json()

except ValueError:
    print()
    print("JSON 응답이 아닙니다.")
    print(response.text[:1000])
    raise


# ============================================================
# Check response
# ============================================================

if response.status_code != 200:
    print()
    print("API 요청 실패")
    print(data)
    raise SystemExit


rows = data.get("OutBlock_1", [])

print("받은 지수 개수:", len(rows))
print()


# ============================================================
# Print all index names
# ============================================================

print("=" * 60)
print("INDEX NAMES")
print("=" * 60)

for row in rows:
    print(
        row.get("IDX_NM"),
        "| Close:",
        row.get("CLSPRC_IDX"),
    )


# ============================================================
# Search volatility-related indices
# ============================================================

keywords = [
    "V-KOSPI",
    "VKOSPI",
    "변동성",
    "VOLATILITY",
]

matches = []

for row in rows:

    name = str(row.get("IDX_NM", ""))

    if any(
        keyword.lower() in name.lower()
        for keyword in keywords
    ):
        matches.append(row)


print()
print("=" * 60)
print("VOLATILITY INDEX MATCHES")
print("=" * 60)

if not matches:
    print("변동성 관련 지수를 자동으로 찾지 못했습니다.")

else:
    for row in matches:
        print(row)