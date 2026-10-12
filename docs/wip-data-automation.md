# WIP handoff — 2026-10-12

Data automation is unfinished and must be reviewed before production deployment.

Completed code is saved under src/operations. Pipeline audit and operational design are in data-reliability-audit.md and data-reliability.md. Existing model/research artifacts were not modified or retrained. Prior product work (accounts, paper trading, multiple administrators, bilingual UI, navigation/methodology/validation) is included in this WIP branch.

Last checks: 25 operational tests passed; TypeScript and production frontend build passed. Full combined backend regression run was interrupted/stopped and needs rerunning outside the restricted networking sandbox. Final browser verification of data-health notices and new admin history remains outstanding. Do not assume automation is fully finished.

Live refresh succeeded for both markets on October 12. U.S.: SPY/VIX October 9, FRED DBAA/DGS10 October 8, common feature date October 8, MSI -0.885, stress threshold 1.292, score 10.1/100, warning false; overall DELAYED. Korea: KOSPI200/VKOSPI and both ECOS yields October 8, MSI 0.298, threshold 1.116, score 12.1/100, warning false; current under configured close+6h publication window. Re-run live verification after restoring local credentials/data; runtime ledger, source observations and snapshots are intentionally excluded from Git.

Outstanding: finish regression/API/admin/browser checks; review scheduler lifecycle/heartbeat and failure recovery, freshness policy and source-unit checks; verify authenticated admin authorization and monitoring endpoints; inspect final diff; persist final input-level live report with retrieval timestamps. Review limitations documented in data-reliability.md (single-host SQLite/locks, unbounded retention, external watchdog, publication allowances). No notification credentials or delivery implementation exists.

Another computer needs private .env values supplied separately, historical data and existing model artifacts. Do not commit these credentials or copy account databases into Git. KRX refresh requires historical seed; do not run full run_pipeline.py because it retrains models. Production scheduling is enabled by default in Docker Compose; keep MARKET_REFRESH_ENABLED=false during setup/review.

Resume with the WIP branch, install requirements, restore private configuration and required data/model artifacts, then run the targeted tests and operational CLI documented in data-reliability.md. Stop any frontend server before rebuilding shared .next outputs.
