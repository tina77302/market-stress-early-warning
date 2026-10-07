import os
import requests
from dotenv import load_dotenv

# 프로젝트 루트의 .env 불러오기
load_dotenv()

API_KEY = os.getenv("KRX_API_KEY")

if not API_KEY:
    raise ValueError("KRX_API_KEY가 .env에 없습니다.")

# KRX Open API - 주가지수 일별 시세
url = "http://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd"

headers = {
    "AUTH_KEY": API_KEY,
}

params = {
    "basDd": "20261002",
}

print("KRX API 연결 테스트")
print("=" * 50)

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30,
)

print("HTTP Status:", response.status_code)

try:
    data = response.json()
except Exception:
    print("JSON 응답이 아닙니다.")
    print(response.text[:1000])
    raise

if response.status_code != 200:
    print("API 요청 실패")
    print(data)
else:
    output = data.get("OutBlock_1", [])

    print("받은 지수 개수:", len(output))

    # KOSPI / KOSPI 200만 확인
    selected = [
        row
        for row in output
        if row.get("IDX_NM") in {"코스피", "코스피 200", "KOSPI", "KOSPI 200"}
    ]

    print("\nKOSPI / KOSPI 200 결과")
    print("=" * 50)

    if not selected:
        print("해당 지수를 찾지 못했습니다.")
        print("\n응답 샘플:")
        for row in output[:5]:
            print(row)
    else:
        for row in selected:
            print(row)