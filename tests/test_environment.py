import sys
import pytest

def test_python_version():
    assert sys.version_info >= (3, 10), "Python 3.10 이상이 필요합니다."

def test_imports():
    import pandas as pd
    import numpy as np
    import sklearn
    import xgboost as xgb
    import yfinance as yf
    import fastapi
    import fredapi
    
    assert pd.__version__ is not None
    assert np.__version__ is not None
    assert sklearn.__version__ is not None
    assert xgb.__version__ is not None
    
def test_xgboost_smoke():
    import xgboost as xgb
    import numpy as np
    
    # 더미 데이터 학습 테스트
    X = np.random.rand(10, 5)
    y = np.random.randint(2, size=10)
    
    model = xgb.XGBClassifier(n_estimators=2, max_depth=2, use_label_encoder=False, eval_metric='logloss')
    model.fit(X, y)
    
    preds = model.predict(X)
    assert len(preds) == 10
