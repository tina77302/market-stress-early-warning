# Refresh attribution

Both markets previously served SHAP from offline analysis JSON files, while the
refresh worker published newer inference snapshots independently. The client
requires the SHAP date to equal `latest.last_updated`, so stale explanations
produce no drivers. MarketDetail groups the API's top eight drivers by
SPY_/KOSPI200_, VIX_/VKOSPI_, and Credit_/BAA_ prefixes. Korea's feature names
match those groups; no frontend change is needed.

The worker now explains its exact validated one-row feature frame using the
same loaded frozen pipeline used for its unrounded inference check. The scaler
is applied before explaining the classifier, as in the offline analysis scripts.
XGBoost's native exact TreeSHAP (`pred_contribs=True`, approximation disabled)
avoids adding the offline `shap` dependency to production. Contributions use
raw model margin and are checked to sum, with the bias, to that margin. They
are explanatory contributions, not causal effects or probability-point changes.
The existing date/model/feature-count/top-drivers JSON contract is preserved.

Attribution includes the observation/common-feature date, model SHA-256,
provenance, feature-row SHA-256 and base value. Model bytes are checked again
after explanation. Date, market, model, checksum, feature count and provenance
are checked before the snapshot is written and again before publication/read.
Attribution is embedded in the signed snapshot payload: one SQLite transaction
publishes the snapshot, its explanation, the current pointer and job success.
There is no second mutable JSON publication and no reader-visible staged file.
A calculation or publication failure leaves the previous pointer untouched.
The markets keep separate pointers and refresh locks.

The SHAP endpoints now read the explanation from their market's committed
snapshot. A legacy snapshot without attribution returns HTTP 503 until a
successful refresh; offline artifacts are neither edited nor used as fallback.
Latest/historical/validation behavior is unchanged. Separate latest and SHAP
requests can straddle a refresh; the existing client date check still fails
closed. The UI continues to aggregate only the supplied top eight drivers;
a group absent from those eight remains unavailable by the existing semantics.

Deployment requires the updated backend and a successful refresh per market.
No model retraining, weight changes, cache-date relabeling or threshold changes
are involved. Local tests use isolated copies of cached source histories, not
production providers or the production operations database.
