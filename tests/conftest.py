"""
Shared fixtures.

Every pipeline module binds the data/model directories from ``src.config``
as module-level constants at import time, so each test redirects those
constants to a temporary directory before instantiating anything.  Nothing
under ``data/`` or ``models/`` in the repository is read or written.
"""
import importlib
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


PATH_MODULES = [
    "src.data.cleaner",
    "src.features.stress_index",
    "src.features.targets",
    "src.features.engineering",
    "src.models.walk_forward",
    "src.models.evaluation",
    "src.models.early_warning_evaluation",
    "src.models.multi_horizon_validation",
    "src.api.main",
]

PATH_NAMES = [
    "DATA_RAW_DIR",
    "DATA_PROCESSED_DIR",
    "DATA_FEATURES_DIR",
    "MODELS_DIR",
]

FEATURE_COLS = [
    "SPY_1D_Return",
    "SPY_5D_Return",
    "SPY_20D_Return",
    "SPY_20D_Vol",
    "SPY_60D_Vol",
    "SPY_Drawdown",
    "SPY_20D_Momentum",
    "VIX_Level",
    "VIX_1D_Change",
    "VIX_5D_Change",
    "VIX_20D_Momentum",
    "VIX_252D_ZScore",
    "Credit_Level",
    "Credit_1D_Change",
    "Credit_5D_Change",
    "Credit_20D_Momentum",
    "Credit_252D_ZScore",
]


@pytest.fixture
def data_dirs(tmp_path, monkeypatch):
    """Redirect every module-level data/model path into ``tmp_path``."""
    dirs = SimpleNamespace(
        DATA_RAW_DIR=tmp_path / "raw",
        DATA_PROCESSED_DIR=tmp_path / "processed",
        DATA_FEATURES_DIR=tmp_path / "features",
        MODELS_DIR=tmp_path / "models",
    )
    for d in vars(dirs).values():
        d.mkdir(parents=True, exist_ok=True)

    for mod_name in PATH_MODULES:
        mod = importlib.import_module(mod_name)
        for name in PATH_NAMES:
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, getattr(dirs, name))

    return dirs


STRESS_START = 800   # raw-row position of the injected stress episode
STRESS_LEN = 40


def make_market_data(n_days=1000, seed=7, stress_start=STRESS_START, stress_len=STRESS_LEN):
    """
    Deterministic synthetic SPY / VIX / credit-spread history.

    A single stress episode is injected so that both target classes exist
    and so that tests can reason about where stress should appear.  It is
    placed late enough to fall inside the walk-forward OOS window used by
    the model tests (one year of warm-up training after ~400 warm-up rows).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-04", periods=n_days)

    spy_ret = rng.normal(0.0004, 0.009, n_days)
    vix = np.empty(n_days)
    spread = np.empty(n_days)
    vix[0], spread[0] = 18.0, 2.0

    for i in range(1, n_days):
        vix[i] = vix[i - 1] + 0.05 * (18.0 - vix[i - 1]) + rng.normal(0, 0.8)
        spread[i] = spread[i - 1] + 0.03 * (2.0 - spread[i - 1]) + rng.normal(0, 0.03)

    s = slice(stress_start, stress_start + stress_len)
    spy_ret[s] -= 0.012
    vix[s] += np.linspace(10, 25, stress_len)
    spread[s] += np.linspace(0.5, 1.5, stress_len)

    spy = 100.0 * np.cumprod(1.0 + spy_ret)
    vix = np.clip(vix, 9.0, None)
    spread = np.clip(spread, 0.5, None)

    df = pd.DataFrame(
        {"SPY": spy, "VIX": vix, "BAA_Treasury_Spread": spread},
        index=pd.Index(dates, name="Date"),
    )
    return df


@pytest.fixture
def market_df():
    return make_market_data()


@pytest.fixture
def cleaned_csv(data_dirs, market_df):
    """Write synthetic data where the cleaner would have left it."""
    path = data_dirs.DATA_PROCESSED_DIR / "cleaned_market_data.csv"
    market_df.to_csv(path)
    return path


@pytest.fixture
def feature_pipeline(data_dirs, cleaned_csv):
    """Run MSI -> targets -> features on the synthetic data."""
    from src.features.stress_index import StressIndexCalculator
    from src.features.targets import TargetGenerator
    from src.features.engineering import FeatureEngineer

    msi = StressIndexCalculator().calculate_msi()
    targets = TargetGenerator().generate_targets()
    features = FeatureEngineer().generate_features()

    return SimpleNamespace(
        dirs=data_dirs,
        msi=msi,
        targets=targets,
        features=features,
    )


def make_oos_predictions(n=300, seed=3, start="2015-01-05"):
    """Synthetic walk-forward OOS prediction table with informative scores."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n)
    actual = (rng.random(n) < 0.2).astype(int)

    # Informative but imperfect probabilities.
    noise = rng.normal(0, 0.15, n)
    prob_log = np.clip(0.25 + 0.5 * actual + noise, 0.0, 1.0)
    prob_xgb = np.clip(0.20 + 0.55 * actual + noise, 0.0, 1.0)

    return pd.DataFrame(
        {
            "Actual_Target": actual,
            "MSI": rng.normal(0, 1, n),
            "SPY": 100 + np.cumsum(rng.normal(0, 1, n)),
            "VIX": 15 + rng.random(n) * 10,
            "BAA_Treasury_Spread": 2 + rng.random(n),
            "Prob_Logistic": prob_log,
            "Prob_XGBoost": prob_xgb,
        },
        index=pd.Index(dates, name="Date"),
    )
