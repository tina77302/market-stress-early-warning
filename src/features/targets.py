import os
import pandas as pd
import logging
from src.config import DATA_FEATURES_DIR, TARGET_WINDOW_DAYS, STRESS_QUANTILE_THRESHOLD

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TargetGenerator:
    def __init__(self, input_filename="market_stress_index.csv", output_filename="targets.csv"):
        self.input_path = DATA_FEATURES_DIR / input_filename
        self.output_path = DATA_FEATURES_DIR / output_filename
        self.target_window = TARGET_WINDOW_DAYS
        
    def generate_targets(self):
        """
        1. [5단계] Stress Event 정의: MSI 지수가 상위 N% (또는 특정 임계치)를 넘으면 스트레스 이벤트(1)로 정의합니다.
        2. [6단계] 10일 Target 생성: 향후 10영업일 이내에 스트레스 이벤트가 한 번이라도 발생하면 현재 시점의 정답(Target)을 1로 라벨링합니다.
        """
        logger.info(f"Reading Market Stress Index from {self.input_path}")
        df = pd.read_csv(self.input_path, index_col='Date', parse_dates=True)
        
        # 1. Stress Event 정의
        # MSI가 전체 기간 중 상위 10%(0.90 분위수) 이상인 날을 'Extreme Stress'로 정의
        # 실시간 예측 환경을 가정하여 Expanding(누적) 분위수를 사용하여 미래 참조(Look-ahead bias)를 엄격히 차단합니다.
        # 단, 초기 데이터(예: 첫 252일)는 분위수 계산이 불안정하므로 최소 252일 이후부터 라벨링
        min_periods = 252
        expanding_quantile = df['MSI'].expanding(min_periods=min_periods).quantile(STRESS_QUANTILE_THRESHOLD)
        
        # 현재 MSI가 누적 상위 10% 기준선을 넘으면 Stress Event (1)
        df['Is_Stress_Event'] = (df['MSI'] >= expanding_quantile).astype(int)
        
        # 2. 10일 전방 타깃 생성 (Target)
        # 향후 10일(t+1 ~ t+10) 내에 Is_Stress_Event가 1인 날이 존재하는지 확인 (미래 참조)
        # Shift(-1)부터 Shift(-10)까지 확인하여 하나라도 1이면 1 (Rolling Max를 미래 방향으로 적용)
        logger.info(f"Generating {self.target_window}-day forward targets...")
        
        # 미래 데이터를 참조하여 Target을 만드므로 pandas의 rolling을 뒤집어서 적용
        # 현재 시점 기준 향후 N일을 봐야 하므로 데이터를 역순으로 뒤집은 뒤 rolling max 계산 후 다시 뒤집음
        target_col = f'Target_{self.target_window}D'
        df[target_col] = df['Is_Stress_Event'].iloc[::-1].rolling(window=self.target_window, min_periods=1).max().iloc[::-1]
        
        # shift(-1)을 적용하여 '오늘'의 이벤트는 제외하고 '내일 이후 10일간'만 보도록 조정
        df[target_col] = df[target_col].shift(-1)
        
        # 마지막 10일은 미래 데이터가 부족하여 정확한 라벨링이 불가능하므로 NaN 처리
        df.loc[df.index[-self.target_window]:, target_col] = float('nan')
        
        # 결측치가 있는 행(초기 252일, 마지막 10일) 제거
        df.dropna(subset=[target_col, 'Is_Stress_Event'], inplace=True)
        df[target_col] = df[target_col].astype(int)
        
        logger.info(f"Stress Events Found: {df['Is_Stress_Event'].sum()} days")
        logger.info(f"Positive Targets (1): {df[target_col].sum()} days out of {len(df)}")
        
        # 결과 저장
        os.makedirs(DATA_FEATURES_DIR, exist_ok=True)
        df.to_csv(self.output_path)
        logger.info(f"Targets successfully generated and saved to: {self.output_path}")
        logger.info(f"Targets Dataset Shape: {df.shape}")
        
        return df

if __name__ == "__main__":
    generator = TargetGenerator()
    generator.generate_targets()
