import os
import pandas as pd
import numpy as np
import joblib
import logging
from src.config import DATA_FEATURES_DIR, DATA_PROCESSED_DIR, MODELS_DIR
from src.models.logistic import build_logistic_model
from src.models.xgboost_model import build_xgboost_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WalkForwardValidator:
    def __init__(self, input_filename="feature_matrix.csv", initial_train_years=5, step_months=1):
        self.input_path = DATA_FEATURES_DIR / input_filename
        self.output_path = DATA_PROCESSED_DIR / "oos_predictions.csv"
        # 1년 약 252영업일, 1달 약 21영업일
        self.min_train_size = initial_train_years * 252
        self.step_size = step_months * 21
        
    def run_validation(self):
        """
        기획서 (Page 8 - Section 11 & 12)
        시간 순서를 엄격히 준수한 Expanding Window 기반 Walk-Forward Validation 수행.
        각 윈도우 내에서 독립적으로 Scaling 및 Model Fitting을 수행하여 Data Leakage를 차단합니다.
        """
        logger.info(f"Reading feature matrix from {self.input_path}")
        df = pd.read_csv(self.input_path, index_col='Date', parse_dates=True)
        
        target_col = 'Target_10D'
        feature_cols = [c for c in df.columns if c not in ['SPY', 'VIX', 'HY_Spread', 'MSI', 'Is_Stress_Event', target_col]]
        
        X = df[feature_cols]
        y = df[target_col]
        
        n_samples = len(df)
        logger.info(f"Total samples: {n_samples}, Initial Train Size: {self.min_train_size}, Step Size: {self.step_size}")
        
        # Out-of-Sample 예측 확률을 저장할 DataFrame
        results = pd.DataFrame(index=df.index)
        results['Actual_Target'] = y
        results['MSI'] = df['MSI']
        results['SPY'] = df['SPY']
        results['VIX'] = df['VIX']
        results['HY_Spread'] = df['HY_Spread']
        
        results['Prob_Logistic'] = np.nan
        results['Prob_XGBoost'] = np.nan
        
        current_train_end = self.min_train_size
        fold_count = 0
        
        # 윈도우 반복문
        while current_train_end < n_samples:
            test_end = min(current_train_end + self.step_size, n_samples)
            
            # Train / Test 슬라이싱 (Expanding Window)
            X_train, y_train = X.iloc[:current_train_end], y.iloc[:current_train_end]
            X_test, y_test = X.iloc[current_train_end:test_end], y.iloc[current_train_end:test_end]
            
            if len(X_test) == 0:
                break
                
            # Class Imbalance 비율 산출 (XGBoost scale_pos_weight 용)
            neg_count = (y_train == 0).sum()
            pos_count = (y_train == 1).sum()
            scale_pos_weight = neg_count / (pos_count + 1e-8)
            
            # 1. Baseline Model: Logistic Regression
            model_log = build_logistic_model()
            model_log.fit(X_train, y_train)
            prob_log = model_log.predict_proba(X_test)[:, 1]
            
            # 2. Main Model: XGBoost
            model_xgb = build_xgboost_model(scale_pos_weight=scale_pos_weight)
            model_xgb.fit(X_train, y_train)
            prob_xgb = model_xgb.predict_proba(X_test)[:, 1]
            
            # 예측값 기록
            results.iloc[current_train_end:test_end, results.columns.get_loc('Prob_Logistic')] = prob_log
            results.iloc[current_train_end:test_end, results.columns.get_loc('Prob_XGBoost')] = prob_xgb
            
            current_train_end = test_end
            fold_count += 1
            
        logger.info(f"Completed {fold_count} Walk-Forward Folds.")
        
        # OOS 예측 데이터 결측치(초기 학습 기간 5년) 제거
        oos_results = results.dropna(subset=['Prob_Logistic', 'Prob_XGBoost']).copy()
        
        # 결과 저장
        os.makedirs(DATA_PROCESSED_DIR, exist_ok=True)
        os.makedirs(MODELS_DIR, exist_ok=True)
        
        oos_results.to_csv(self.output_path)
        logger.info(f"Out-of-Sample Predictions saved to: {self.output_path}")
        logger.info(f"OOS Dataset Shape: {oos_results.shape}")
        
        # 마지막으로 학습된 모델 저장 (최신 배포/추론용)
        joblib.dump(model_log, MODELS_DIR / "logistic_latest.joblib")
        joblib.dump(model_xgb, MODELS_DIR / "xgboost_latest.joblib")
        logger.info(f"Latest trained models saved in: {MODELS_DIR}")
        
        return oos_results

if __name__ == "__main__":
    validator = WalkForwardValidator()
    validator.run_validation()
