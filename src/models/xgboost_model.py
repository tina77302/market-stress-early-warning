import xgboost as xgb
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

def build_xgboost_model(scale_pos_weight=1.0):
    """
    기획서 (Page 7 - Main Model)
    비선형 관계와 피처 간 상호작용(Interaction)을 포착하기 위한 XGBoost 메인 모델 구축.
    """
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('classifier', xgb.XGBClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos_weight, # 불균형 라벨 대응
            eval_metric='logloss',
            random_state=42
        ))
    ])
    return pipeline
