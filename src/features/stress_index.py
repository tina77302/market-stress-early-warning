import os
import pandas as pd
import numpy as np
import logging
from src.config import DATA_PROCESSED_DIR, DATA_FEATURES_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StressIndexCalculator:
    def __init__(self, input_filename="cleaned_market_data.csv", output_filename="market_stress_index.csv", rolling_window=252):
        self.input_path = DATA_PROCESSED_DIR / input_filename
        self.output_path = DATA_FEATURES_DIR / output_filename
        self.rolling_window = rolling_window
        
    def calculate_msi(self):
        """
        주식(SPY), 변동성(VIX), 신용(HY Spread) 데이터를 바탕으로
        Rolling Z-Score를 구한 뒤 동일 가중치(Equal Weight)로 결합하여 Market Stress Index를 생성합니다.
        (Look-ahead bias 방지를 위해 과거 1년(252영업일) 데이터를 기준으로 Z-Score 계산)
        """
        logger.info(f"Calculating Market Stress Index (Rolling Window: {self.rolling_window} days)")
        df = pd.read_csv(self.input_path, index_col='Date', parse_dates=True)
        
        # 1. SPY 모멘텀 (스트레스 상황일수록 주가가 하락하므로 방향을 반대로 뒤집음)
        # 21일(약 1개월) 수익률의 반대 방향: 주가 하락 시 양수(+)값을 갖도록 설계
        df['SPY_Stress'] = -df['SPY'].pct_change(periods=21)
        
        # 2. VIX와 Spread는 높을수록 스트레스 (그대로 사용)
        df['VIX_Stress'] = df['VIX']
        df['Credit_Stress'] = df['HY_Spread']
        
        # 3. Z-Score 표준화 함수 (Rolling)
        def rolling_zscore(series, window):
            rolling_mean = series.rolling(window=window, min_periods=window//2).mean()
            rolling_std = series.rolling(window=window, min_periods=window//2).std()
            return (series - rolling_mean) / (rolling_std + 1e-8) # 0 나누기 방지
            
        logger.info("Applying rolling standardization (Z-score)...")
        df['Z_SPY'] = rolling_zscore(df['SPY_Stress'], self.rolling_window)
        df['Z_VIX'] = rolling_zscore(df['VIX_Stress'], self.rolling_window)
        df['Z_Credit'] = rolling_zscore(df['Credit_Stress'], self.rolling_window)
        
        # 4. 종합 Market Stress Index (MSI) 산출
        # 3가지 스트레스 지표의 단순 평균 사용
        df['MSI'] = df[['Z_SPY', 'Z_VIX', 'Z_Credit']].mean(axis=1)
        
        # 결측치(초기 21일 등 계산 불가 구간) 제거
        df.dropna(subset=['MSI'], inplace=True)
        
        # 5. 결과 저장
        os.makedirs(DATA_FEATURES_DIR, exist_ok=True)
        
        # 필요한 컬럼만 추출하여 저장
        output_df = df[['SPY', 'VIX', 'HY_Spread', 'MSI']].copy()
        output_df.to_csv(self.output_path)
        
        logger.info(f"Market Stress Index successfully calculated and saved to: {self.output_path}")
        logger.info(f"MSI Dataset Shape: {output_df.shape}")
        
        return output_df

if __name__ == "__main__":
    calc = StressIndexCalculator()
    calc.calculate_msi()
