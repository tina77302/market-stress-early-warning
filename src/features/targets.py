import os
import numpy as np
import pandas as pd
import logging

from src.config import (
    DATA_FEATURES_DIR,
    TARGET_WINDOW_DAYS,
    STRESS_QUANTILE_THRESHOLD
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TargetGenerator:
    def __init__(
        self,
        input_filename="market_stress_index.csv",
        output_filename="targets.csv"
    ):
        self.input_path = DATA_FEATURES_DIR / input_filename
        self.output_path = DATA_FEATURES_DIR / output_filename
        self.target_windows = [1, 5, 10, 20]
        

    def generate_targets(self):
        """
        Stress Event:
            날짜 t의 MSI가 t-1까지의 과거 MSI 분포에서
            설정된 분위수 threshold 이상이면 1.

        Target_ND:
            날짜 t 이후 t+1 ~ t+N 거래일 중
            Stress Event가 한 번이라도 발생하면 1.

        Threshold와 현재 Event 판정에는 미래 정보가 사용되지 않습니다.
        Target은 supervised learning의 정답(label)이므로
        의도적으로 미래 N거래일의 Event를 사용합니다.
        """

        logger.info(
            f"Reading Market Stress Index from {self.input_path}"
        )

        df = pd.read_csv(
            self.input_path,
            index_col="Date",
            parse_dates=True
        )

        df.sort_index(inplace=True)

        # --------------------------------------------------
        # 1. Past-only Stress Threshold
        # --------------------------------------------------

        min_periods = 252

        # 현재 t를 제외하고 t-1까지의 MSI만 threshold 계산에 사용
        historical_msi = df["MSI"].shift(1)

        df["Stress_Threshold"] = (
            historical_msi
            .expanding(min_periods=min_periods)
            .quantile(STRESS_QUANTILE_THRESHOLD)
        )

        # --------------------------------------------------
        # 2. Stress Event 정의
        # --------------------------------------------------

        # Threshold가 아직 존재하지 않는 초기 구간은
        # 0으로 간주하지 않고 NaN으로 유지
        df["Is_Stress_Event"] = np.where(
            df["Stress_Threshold"].notna(),
            (df["MSI"] >= df["Stress_Threshold"]).astype(float),
            np.nan
        )

               # --------------------------------------------------
        # 3. Multi-Horizon Forward Targets
        # --------------------------------------------------

        target_cols = []

        for horizon in self.target_windows:
            target_col = f"Target_{horizon}D"
            target_cols.append(target_col)

            logger.info(
                f"Generating {horizon}-day forward targets..."
            )

            future_events = pd.concat(
                [
                    df["Is_Stress_Event"].shift(-i)
                    for i in range(1, horizon + 1)
                ],
                axis=1
            )

            df[target_col] = future_events.max(
                axis=1,
                skipna=False
            )

        # --------------------------------------------------
        # 4. 기본 유효 구간 유지
        # --------------------------------------------------

        # 초기 threshold 미정 구간만 제거.
        # 각 horizon 끝부분의 NaN은 그대로 유지해서
        # 모델별로 사용 가능한 label만 선택하도록 한다.
        df.dropna(
            subset=[
                "Stress_Threshold",
                "Is_Stress_Event",
            ],
            inplace=True
        )

        df["Is_Stress_Event"] = (
            df["Is_Stress_Event"].astype(int)
        )

        for target_col in target_cols:
            df[target_col] = df[target_col].astype("Int64")
            
                # --------------------------------------------------
        # 5. QA
        # --------------------------------------------------

        logger.info(
            f"Stress Events Found: "
            f"{df['Is_Stress_Event'].sum()} days"
        )

        for target_col in target_cols:
            valid = df[target_col].dropna()

            logger.info(
                f"{target_col}: "
                f"{int(valid.sum())} positives / "
                f"{len(valid)} observations "
                f"({valid.mean():.2%})"
            )

        logger.info(
            f"Target Dataset Start Date: {df.index.min()}"
        )

        logger.info(
            f"Target Dataset End Date: {df.index.max()}"
        )
            # --------------------------------------------------
        # 6. 저장
        # --------------------------------------------------

        os.makedirs(
            DATA_FEATURES_DIR,
            exist_ok=True
        )

        df.to_csv(self.output_path)

        logger.info(
            f"Targets successfully generated and saved to: "
            f"{self.output_path}"
        )

        logger.info(
            f"Targets Dataset Shape: {df.shape}"
        )

        return df


if __name__ == "__main__":
    generator = TargetGenerator()
    generator.generate_targets()