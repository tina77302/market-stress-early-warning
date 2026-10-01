from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

def build_logistic_model():
    """
    기획서 (Page 7 - Baseline Model)
    단순하고 해석하기 쉬운 선형 로지스틱 회귀 Baseline 모델을 구축합니다.
    데이터 누수를 막기 위해 StandardScaler와 Pipeline으로 묶습니다.
    """
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('classifier', LogisticRegression(
            C=1.0,
            class_weight='balanced', # 불균형 라벨 대응
            random_state=42,
            max_iter=1000
        ))
    ])
    return pipeline
