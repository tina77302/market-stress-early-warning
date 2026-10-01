import os
import pandas as pd
import logging
from src.config import DATA_RAW_DIR, DATA_PROCESSED_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MarketDataCleaner:
    def __init__(self, input_filename="raw_market_data.csv", output_filename="cleaned_market_data.csv"):
        self.input_path = DATA_RAW_DIR / input_filename
        self.output_path = DATA_PROCESSED_DIR / output_filename
        
    def clean(self):
        """
        원본 데이터를 불러와 결측치를 처리하고 영업일 기준으로 정렬합니다.
        주식시장과 채권시장의 휴장일이 다를 수 있으므로 이를 보정합니다.
        """
        logger.info(f"Reading raw data from {self.input_path}")
        if not self.input_path.exists():
            raise FileNotFoundError(f"{self.input_path} 가 존재하지 않습니다. 먼저 fetcher를 실행하세요.")
            
        df = pd.read_csv(self.input_path, index_col='Date', parse_dates=True)
        
        # 1. 주말 및 공휴일로 인한 결측치 처리 (앞선 영업일 데이터로 채움, 최대 5일)
        logger.info("Forward-filling missing values due to different market holidays...")
        df.ffill(limit=5, inplace=True)
        
        # 2. 여전히 남은 결측치 (주로 데이터셋 극초반부)는 제거
        initial_shape = df.shape
        df.dropna(inplace=True)
        dropped_rows = initial_shape[0] - df.shape[0]
        if dropped_rows > 0:
            logger.info(f"Dropped {dropped_rows} rows with NaNs at the beginning of the dataset.")
            
        # 3. 데이터 검증 (음수 스프레드나 비정상 값 확인)
        if (df['VIX'] <= 0).any():
            logger.warning("VIX contains zero or negative values. Please check the data.")
        
        # 4. 정제된 데이터 저장
        os.makedirs(DATA_PROCESSED_DIR, exist_ok=True)
        df.to_csv(self.output_path)
        
        logger.info(f"Cleaned data successfully saved to: {self.output_path}")
        logger.info(f"Cleaned Dataset Shape: {df.shape}")
        
        return df

if __name__ == "__main__":
    cleaner = MarketDataCleaner()
    cleaner.clean()
