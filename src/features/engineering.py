import os
import pandas as pd
import numpy as np
import logging
from src.config import DATA_FEATURES_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FeatureEngineer:
    def __init__(self, input_filename="targets.csv", output_filename="feature_matrix.csv"):
        self.input_path = DATA_FEATURES_DIR / input_filename
        self.output_path = DATA_FEATURES_DIR / output_filename
        
    def generate_features(self):
        """
        기획서(Page 6) 명세에 맞춰 SPY, VIX, HY Spread 기반의 머신러닝 피처(Features)를 생성합니다.
        
        생성 피처 목록:
        - SPY: 1D/5D/20D Return, 20D/60D Rolling Volatility, Drawdown, 20D Momentum
        - VIX: Level, 1D/5D Change, 20D Momentum, 252D Rolling Z-Score
        - HY Spread: Level, 1D/5D Change, 20D Momentum, 252D Rolling Z-Score
        """
        logger.info(f"Reading target dataset from {self.input_path}")
        df = pd.read_csv(self.input_path, index_col='Date', parse_dates=True)
        
        logger.info("Engineering features based on specification (Page 6)...")
        
        # --- 1. SPY Features ---
        df['SPY_1D_Return'] = df['SPY'].pct_change(1)
        df['SPY_5D_Return'] = df['SPY'].pct_change(5)
        df['SPY_20D_Return'] = df['SPY'].pct_change(20)
        
        # Rolling Volatility (연율화 표준편차)
        df['SPY_20D_Vol'] = df['SPY_1D_Return'].rolling(20).std() * np.sqrt(252)
        df['SPY_60D_Vol'] = df['SPY_1D_Return'].rolling(60).std() * np.sqrt(252)
        
        # Drawdown (전고점 대비 고점 대비 낙폭)
        rolling_peak = df['SPY'].cummax()
        df['SPY_Drawdown'] = (df['SPY'] - rolling_peak) / rolling_peak
        
        # Momentum (20일 이동평균 대비 이격도)
        df['SPY_20D_Momentum'] = df['SPY'] / df['SPY'].rolling(20).mean() - 1.0
        
        # --- 2. VIX Features ---
        df['VIX_Level'] = df['VIX']
        df['VIX_1D_Change'] = df['VIX'].diff(1)
        df['VIX_5D_Change'] = df['VIX'].diff(5)
        df['VIX_20D_Momentum'] = df['VIX'] / df['VIX'].rolling(20).mean() - 1.0
        
        vix_mean = df['VIX'].rolling(252, min_periods=60).mean()
        vix_std = df['VIX'].rolling(252, min_periods=60).std()
        df['VIX_252D_ZScore'] = (df['VIX'] - vix_mean) / (vix_std + 1e-8)
        
        # --- 3. HY Credit Spread Features ---
        df['HY_Level'] = df['HY_Spread']
        df['HY_1D_Change'] = df['HY_Spread'].diff(1)
        df['HY_5D_Change'] = df['HY_Spread'].diff(5)
        df['HY_20D_Momentum'] = df['HY_Spread'] / df['HY_Spread'].rolling(20).mean() - 1.0
        
        hy_mean = df['HY_Spread'].rolling(252, min_periods=60).mean()
        hy_std = df['HY_Spread'].rolling(252, min_periods=60).std()
        df['HY_252D_ZScore'] = (df['HY_Spread'] - hy_mean) / (hy_std + 1e-8)
        
        # --- 4. NaNs 처리 (피처 계산으로 생긴 초반 60~252일 결측치 제거) ---
        initial_count = len(df)
        df.dropna(inplace=True)
        final_count = len(df)
        logger.info(f"Dropped {initial_count - final_count} initial NaN rows due to rolling feature calculations.")
        
        # 결과 저장
        os.makedirs(DATA_FEATURES_DIR, exist_ok=True)
        df.to_csv(self.output_path)
        
        logger.info(f"Feature matrix successfully created and saved to: {self.output_path}")
        logger.info(f"Feature Matrix Shape: {df.shape}")
        
        # 피처 컬럼 목록 출력
        feature_cols = [c for c in df.columns if c not in ['SPY', 'VIX', 'HY_Spread', 'MSI', 'Is_Stress_Event', 'Target_10D']]
        logger.info(f"Generated {len(feature_cols)} ML Features: {feature_cols}")
        
        return df

if __name__ == "__main__":
    engineer = FeatureEngineer()
    engineer.generate_features()
