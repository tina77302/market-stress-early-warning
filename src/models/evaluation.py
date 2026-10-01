import pandas as pd
import numpy as np
import logging
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, precision_score, recall_score, f1_score, confusion_matrix
from src.config import DATA_PROCESSED_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelEvaluator:
    def __init__(self, input_filename="oos_predictions.csv"):
        self.input_path = DATA_PROCESSED_DIR / input_filename
        
    def evaluate_overall(self):
        """
        기획서 (Page 9 - Section 13)
        OOS(Out-of-Sample) 예측 결과에 대해 ROC-AUC, PR-AUC, Precision, Recall, F1, False Alarm Rate를 평가합니다.
        """
        logger.info(f"Reading OOS predictions from {self.input_path}")
        df = pd.read_csv(self.input_path, index_col='Date', parse_dates=True)
        
        y_true = df['Actual_Target']
        
        models = {
            'Logistic Regression (Baseline)': df['Prob_Logistic'],
            'XGBoost (Main Model)': df['Prob_XGBoost']
        }
        
        results = []
        
        for name, y_prob in models.items():
            # 1. ROC-AUC & PR-AUC
            roc_auc = roc_auc_score(y_true, y_prob)
            precision_curve, recall_curve, _ = precision_recall_curve(y_true, y_prob)
            pr_auc = auc(recall_curve, precision_curve)
            
            # 2. Binary classification metrics (Threshold = 0.5)
            y_pred = (y_prob >= 0.5).astype(int)
            tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
            
            precision = precision_score(y_true, y_pred, zero_division=0)
            recall = recall_score(y_true, y_pred, zero_division=0)
            f1 = f1_score(y_true, y_pred, zero_division=0)
            
            false_alarm_rate = fp / (fp + tn + 1e-8) # FPR
            missed_event_rate = fn / (fn + tp + 1e-8) # FNR
            
            results.append({
                'Model': name,
                'ROC-AUC': round(roc_auc, 4),
                'PR-AUC': round(pr_auc, 4),
                'Precision': round(precision, 4),
                'Recall': round(recall, 4),
                'F1 Score': round(f1, 4),
                'False Alarm Rate': round(false_alarm_rate, 4),
                'Missed Event Rate': round(missed_event_rate, 4)
            })
            
        metrics_df = pd.DataFrame(results)
        logger.info("\n" + metrics_df.to_string(index=False))
        return metrics_df
        
    def evaluate_historical_events(self):
        """
        기획서 (Page 9 & 12 - Section 14)
        과거 주요 금융위기 및 충격 구간에서 모델이 사전에 경보(Risk Probability 상승)를 울렸는지 분석합니다.
        """
        logger.info("Evaluating Historical Crisis Events (Page 9 & 12)...")
        df = pd.read_csv(self.input_path, index_col='Date', parse_dates=True)
        
        events = {
            '2008 Financial Crisis': ('2007-10-01', '2009-03-31'),
            '2011 Eurozone / US Debt': ('2011-07-01', '2011-12-31'),
            '2015-2016 China / Oil Shock': ('2015-08-01', '2016-02-28'),
            '2018 Volatility Shock (Volmageddon)': ('2018-01-15', '2018-03-31'),
            '2020 COVID-19 Crash': ('2020-02-01', '2020-04-30'),
            '2022 Inflation / Rate Shock': ('2022-01-01', '2022-10-31'),
            '2023 US Banking Stress (SVB)': ('2023-03-01', '2023-04-30')
        }
        
        event_summary = []
        for event_name, (start_date, end_date) in events.items():
            sub = df.loc[start_date:end_date]
            if len(sub) == 0:
                continue
                
            avg_prob_xgb = sub['Prob_XGBoost'].mean()
            max_prob_xgb = sub['Prob_XGBoost'].max()
            high_risk_days_xgb = (sub['Prob_XGBoost'] >= 0.5).sum()
            total_days = len(sub)
            
            event_summary.append({
                'Event': event_name,
                'Start-End': f"{start_date} ~ {end_date}",
                'Total Days': total_days,
                'XGB High Risk Days': high_risk_days_xgb,
                'XGB Max Risk Prob': f"{max_prob_xgb*100:.1f}%",
                'XGB Avg Risk Prob': f"{avg_prob_xgb*100:.1f}%"
            })
            
        event_df = pd.DataFrame(event_summary)
        logger.info("\n" + event_df.to_string(index=False))
        return event_df

if __name__ == "__main__":
    evaluator = ModelEvaluator()
    evaluator.evaluate_overall()
    evaluator.evaluate_historical_events()
