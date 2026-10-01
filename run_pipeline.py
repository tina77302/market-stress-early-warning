#!/usr/bin/env python3
"""
Market Stress Early Warning System - Full Pipeline Runner
모든 파이프라인 단계를 순서대로 실행하는 엔트리포인트
"""
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger("pipeline")

def run_pipeline():
    logger.info("=" * 60)
    logger.info("  MARKET STRESS EARLY WARNING - FULL PIPELINE START")
    logger.info("=" * 60)

    # [2] 데이터 수집
    logger.info("\n[STEP 2] Fetching raw market data (SPY, VIX, Credit Spread)...")
    from src.data.fetcher import MarketDataFetcher
    MarketDataFetcher().run_pipeline()

    # [3] 데이터 정제
    logger.info("\n[STEP 3] Cleaning market data...")
    from src.data.cleaner import MarketDataCleaner
    MarketDataCleaner().clean()

    # [4] Market Stress Index 생성
    logger.info("\n[STEP 4] Calculating Market Stress Index (MSI)...")
    from src.features.stress_index import StressIndexCalculator
    StressIndexCalculator().calculate_msi()

    # [5+6] Stress Event 정의 및 10일 Target 생성
    logger.info("\n[STEP 5+6] Defining stress events & generating 10D targets...")
    from src.features.targets import TargetGenerator
    TargetGenerator().generate_targets()

    # [7] Feature Engineering
    logger.info("\n[STEP 7] Engineering ML features...")
    from src.features.engineering import FeatureEngineer
    FeatureEngineer().generate_features()

    # [8+9+10] Walk-Forward Validation (Logistic + XGBoost)
    logger.info("\n[STEP 8+9+10] Running Walk-Forward Validation...")
    from src.models.walk_forward import WalkForwardValidator
    WalkForwardValidator().run_validation()

    # [11+12] 성능 평가 및 Historical Event 분석
    logger.info("\n[STEP 11+12] Evaluating model performance & historical events...")
    from src.models.evaluation import ModelEvaluator
    evaluator = ModelEvaluator()
    evaluator.evaluate_overall()
    evaluator.evaluate_historical_events()

    logger.info("\n" + "=" * 60)
    logger.info("  PIPELINE COMPLETED SUCCESSFULLY!")
    logger.info("  Next: Run `uvicorn src.api.main:app --port 8000` to start API")
    logger.info("  Next: Run `npm run dev` in /frontend to start Dashboard")
    logger.info("=" * 60)

if __name__ == "__main__":
    run_pipeline()
