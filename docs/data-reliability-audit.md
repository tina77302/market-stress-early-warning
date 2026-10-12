# Pipeline audit before operational changes

| Responsibility | U.S. | Korea |
| --- | --- | --- |
| Fetch | `src/data/fetcher.py`: `MarketDataFetcher.fetch_yahoo_data`, `fetch_fred_credit_spread` (Yahoo/FRED) | `download_krx_indices.fetch_krx_date`, `download_vkospi.fetch_krx_date` (KRX); `download_ecos_credit.fetch_series` (ECOS) |
| Clean | `src/data/cleaner.py`: `MarketDataCleaner.clean` | loaders in `build_korea_features.load_data` and `build_korea_stress_index.load_*` |
| Features | `src/features/engineering.py`: `FeatureEngineer.generate_features` | `build_korea_features.build_features` |
| MSI | `src/features/stress_index.py`: `StressIndexCalculator.calculate_msi` | `build_korea_stress_index.main`, `past_only_rolling_zscore` |
| Models | API `load_xgboost_model` → `models/saved/xgboost_latest.joblib` | API `load_korea_xgboost_model` → `models/korea/xgboost_10d_latest.joblib` |
| Inference | API `get_latest_risk`, exact 17-column order | API `get_korea_latest_risk`, exact 17-column order |
| Current API | `/api/latest` | `/api/korea/latest` |

Existing risks: CSVs published independently; request-time inference can mix file generations; no job ledger/lock/source freshness; U.S. fetch has no HTTP timeout; Korea scripts have fixed historical end dates and checkpoint directly to active files. Existing U.S. cleaner fills VIX/credit for at most five historical rows. Korea inner joins can conceal a lagging series. Full `run_pipeline.py` also retrains and must never be invoked by operations.

Operational boundary: fetch independently, validate raw series, stage complete history, reuse unchanged research calculations in an isolated process, infer with existing model, validate final common-date outputs, then publish via one SQLite transaction. Legacy research outputs remain untouched. Historical U.S. filling is reused only before the actual common observation date; all current inputs must be genuinely observed on that date. Cached legacy adoption is explicitly labeled with unknown retrieval provenance and never considered current.
