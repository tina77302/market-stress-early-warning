import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data Paths
DATA_DIR = PROJECT_ROOT / "data"
DATA_RAW_DIR = DATA_DIR / "raw"
DATA_PROCESSED_DIR = DATA_DIR / "processed"
DATA_FEATURES_DIR = DATA_DIR / "features"

# Models Path
MODELS_DIR = PROJECT_ROOT / "models" / "saved"

# API & Data Fetching Config
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
START_DATE = "2000-01-01"

# Target & ML Config
TARGET_WINDOW_DAYS = 10
STRESS_QUANTILE_THRESHOLD = 0.90 # Top 10% events are considered "Stress"
