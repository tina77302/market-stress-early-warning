import warnings
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)

from xgboost import XGBClassifier


# ============================================================
# CONFIG
# ============================================================

FEATURE_MATRIX = Path("data/features/feature_matrix.csv")
BANKING_FEATURES = Path("data/processed/banking_features_daily.csv")

OUTPUT_DIR = Path("data/processed/banking_ablation")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "Target_10D"

MIN_TRAIN_SIZE = 5 * 252
STEP = 21
PURGE = 10
THRESHOLD = 0.50


# ============================================================
# CORE 17 FEATURES
# ============================================================

CORE_FEATURES = [
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


# ============================================================
# BANKING 4 FEATURES
# ============================================================

BANK_FEATURES = [
    "Bank_Deposits_4W_Change",
    "Bank_Deposits_13W_Change",
    "Primary_Credit_4W_SignedLog",
    "Primary_Credit_52W_ZScore",
]

EXTENDED_FEATURES = CORE_FEATURES + BANK_FEATURES


# ============================================================
# LOAD DATA
# ============================================================

print("\n========== LOAD DATA ==========")

base = pd.read_csv(
    FEATURE_MATRIX,
    parse_dates=["Date"],
)

bank = pd.read_csv(
    BANKING_FEATURES,
    parse_dates=["Date"],
)

base = (
    base
    .set_index("Date")
    .sort_index()
)

bank = (
    bank
    .set_index("Date")
    .sort_index()
)


# Keep only banking features
bank = bank[BANK_FEATURES]


# Join banking data to existing feature matrix
df = base.join(
    bank,
    how="left",
)


# ============================================================
# COMMON-SAMPLE DESIGN
# ============================================================

# Critical:
# Compare 17F and 21F on EXACTLY the same observations.
#
# Otherwise banking features starting later could make the
# comparison unfair.

required_columns = (
    CORE_FEATURES
    + BANK_FEATURES
    + [TARGET]
)

df = df[required_columns].copy()

df = df.dropna(
    subset=required_columns
)

df[TARGET] = df[TARGET].astype(int)


print(f"Common sample start : {df.index.min().date()}")
print(f"Common sample end   : {df.index.max().date()}")
print(f"Common observations : {len(df):,}")
print(
    f"Target prevalence   : "
    f"{df[TARGET].mean():.4%}"
)


# ============================================================
# MODEL BUILDERS
# ============================================================

def build_logistic():

    return LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        random_state=42,
    )


def build_xgb(scale_pos_weight):

    return XGBClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        n_jobs=-1,
    )


# ============================================================
# WALK-FORWARD
# ============================================================

def run_walk_forward(
    data,
    feature_cols,
    experiment_name,
):

    X = data[feature_cols].copy()
    y = data[TARGET].copy()

    results = pd.DataFrame(
        index=data.index
    )

    results["Actual_Target"] = y

    results["Prob_Logistic"] = np.nan
    results["Prob_XGBoost"] = np.nan


    fold = 0

    print(
        f"\n========== {experiment_name} =========="
    )

    print(
        f"Features : {len(feature_cols)}"
    )


    for test_start in range(
        MIN_TRAIN_SIZE,
        len(data),
        STEP,
    ):

        test_end = min(
            test_start + STEP,
            len(data),
        )


        # ----------------------------------------------------
        # 10-observation label-overlap purge
        # ----------------------------------------------------

        train_end = test_start - PURGE

        if train_end <= 0:
            continue


        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]

        X_test = X.iloc[
            test_start:test_end
        ]


        if len(X_test) == 0:
            continue


        # Need both classes
        if y_train.nunique() < 2:
            continue


        # ----------------------------------------------------
        # Imputation
        # Fit ONLY on training data
        # ----------------------------------------------------

        imputer = SimpleImputer(
            strategy="median"
        )

        X_train_imp = imputer.fit_transform(
            X_train
        )

        X_test_imp = imputer.transform(
            X_test
        )


        # ----------------------------------------------------
        # Scaling
        # Fit ONLY on training data
        #
        # Used for Logistic.
        # XGBoost uses imputed raw features.
        # ----------------------------------------------------

        scaler = StandardScaler()

        X_train_scaled = scaler.fit_transform(
            X_train_imp
        )

        X_test_scaled = scaler.transform(
            X_test_imp
        )


        # ----------------------------------------------------
        # Logistic
        # ----------------------------------------------------

        logistic = build_logistic()

        logistic.fit(
            X_train_scaled,
            y_train,
        )

        prob_logistic = (
            logistic.predict_proba(
                X_test_scaled
            )[:, 1]
        )


        # ----------------------------------------------------
        # XGBoost class weight
        # ----------------------------------------------------

        positive = y_train.sum()
        negative = len(y_train) - positive

        scale_pos_weight = (
            negative / positive
            if positive > 0
            else 1.0
        )


        # ----------------------------------------------------
        # XGBoost
        # ----------------------------------------------------

        xgb = build_xgb(
            scale_pos_weight
        )

        xgb.fit(
            X_train_imp,
            y_train,
        )

        prob_xgb = (
            xgb.predict_proba(
                X_test_imp
            )[:, 1]
        )


        test_index = X_test.index

        results.loc[
            test_index,
            "Prob_Logistic",
        ] = prob_logistic

        results.loc[
            test_index,
            "Prob_XGBoost",
        ] = prob_xgb


        fold += 1

        if fold % 25 == 0:

            print(
                f"Fold {fold:>3} | "
                f"Train end "
                f"{X_train.index[-1].date()} | "
                f"Test "
                f"{X_test.index[0].date()} "
                f"→ "
                f"{X_test.index[-1].date()}"
            )


    # Keep actual OOS rows only
    oos = results.dropna(
        subset=[
            "Prob_Logistic",
            "Prob_XGBoost",
        ]
    ).copy()


    print(
        f"\nOOS observations : {len(oos):,}"
    )

    print(
        f"OOS period       : "
        f"{oos.index.min().date()} "
        f"→ "
        f"{oos.index.max().date()}"
    )

    print(
        f"OOS prevalence   : "
        f"{oos['Actual_Target'].mean():.4%}"
    )


    return oos


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    oos,
    experiment,
    model_name,
    probability_col,
):

    y_true = (
        oos["Actual_Target"]
        .astype(int)
    )

    y_prob = oos[probability_col]

    y_pred = (
        y_prob >= THRESHOLD
    ).astype(int)


    tn, fp, fn, tp = confusion_matrix(
        y_true,
        y_pred,
        labels=[0, 1],
    ).ravel()


    far = (
        fp / (fp + tn)
        if (fp + tn) > 0
        else np.nan
    )

    missed_rate = (
        fn / (fn + tp)
        if (fn + tp) > 0
        else np.nan
    )


    return {
        "Experiment": experiment,
        "Features": (
            17
            if experiment == "Core_17F"
            else 21
        ),
        "Model": model_name,

        "OOS_Observations": len(oos),
        "OOS_Prevalence": y_true.mean(),

        "ROC_AUC": roc_auc_score(
            y_true,
            y_prob,
        ),

        "PR_AUC": average_precision_score(
            y_true,
            y_prob,
        ),

        "Brier": brier_score_loss(
            y_true,
            y_prob,
        ),

        "Precision": precision_score(
            y_true,
            y_pred,
            zero_division=0,
        ),

        "Recall": recall_score(
            y_true,
            y_pred,
            zero_division=0,
        ),

        "F1": f1_score(
            y_true,
            y_pred,
            zero_division=0,
        ),

        "FAR": far,
        "Missed_Rate": missed_rate,

        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,

        "Start_Date": oos.index.min(),
        "End_Date": oos.index.max(),
    }


# ============================================================
# RUN CORE 17F
# ============================================================

core_oos = run_walk_forward(
    data=df,
    feature_cols=CORE_FEATURES,
    experiment_name="CORE 17F",
)


# ============================================================
# RUN 21F BANKING EXTENSION
# ============================================================

bank_oos = run_walk_forward(
    data=df,
    feature_cols=EXTENDED_FEATURES,
    experiment_name="CORE 17F + BANKING 4F",
)


# ============================================================
# METRIC TABLE
# ============================================================

metrics = []


for experiment, oos in [
    ("Core_17F", core_oos),
    ("Banking_21F", bank_oos),
]:

    metrics.append(
        calculate_metrics(
            oos,
            experiment,
            "Logistic",
            "Prob_Logistic",
        )
    )

    metrics.append(
        calculate_metrics(
            oos,
            experiment,
            "XGBoost",
            "Prob_XGBoost",
        )
    )


metrics_df = pd.DataFrame(
    metrics
)


# ============================================================
# DELTA TABLE
# ============================================================

delta_rows = []

for model in [
    "Logistic",
    "XGBoost",
]:

    core_row = (
        metrics_df[
            (metrics_df["Experiment"] == "Core_17F")
            & (metrics_df["Model"] == model)
        ]
        .iloc[0]
    )

    bank_row = (
        metrics_df[
            (metrics_df["Experiment"] == "Banking_21F")
            & (metrics_df["Model"] == model)
        ]
        .iloc[0]
    )


    delta_rows.append(
        {
            "Model": model,

            "Delta_ROC_AUC":
                bank_row["ROC_AUC"]
                - core_row["ROC_AUC"],

            "Delta_PR_AUC":
                bank_row["PR_AUC"]
                - core_row["PR_AUC"],

            "Delta_Brier":
                bank_row["Brier"]
                - core_row["Brier"],

            "Delta_Precision":
                bank_row["Precision"]
                - core_row["Precision"],

            "Delta_Recall":
                bank_row["Recall"]
                - core_row["Recall"],

            "Delta_F1":
                bank_row["F1"]
                - core_row["F1"],

            "Delta_FAR":
                bank_row["FAR"]
                - core_row["FAR"],

            "Delta_Missed_Rate":
                bank_row["Missed_Rate"]
                - core_row["Missed_Rate"],
        }
    )


delta_df = pd.DataFrame(
    delta_rows
)


# ============================================================
# SAVE RESULTS
# ============================================================

metrics_path = (
    OUTPUT_DIR
    / "banking_ablation_metrics.csv"
)

delta_path = (
    OUTPUT_DIR
    / "banking_ablation_delta.csv"
)

core_path = (
    OUTPUT_DIR
    / "oos_core_17f.csv"
)

bank_path = (
    OUTPUT_DIR
    / "oos_banking_21f.csv"
)


metrics_df.to_csv(
    metrics_path,
    index=False,
)

delta_df.to_csv(
    delta_path,
    index=False,
)

core_oos.to_csv(
    core_path
)

bank_oos.to_csv(
    bank_path
)


# ============================================================
# DISPLAY
# ============================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    220,
)


print(
    "\n\n========== FINAL OOS METRICS =========="
)

print(
    metrics_df[
        [
            "Experiment",
            "Model",
            "OOS_Observations",
            "OOS_Prevalence",
            "ROC_AUC",
            "PR_AUC",
            "Brier",
            "Precision",
            "Recall",
            "F1",
            "FAR",
            "Missed_Rate",
        ]
    ]
    .round(6)
    .to_string(index=False)
)


print(
    "\n\n========== BANKING FEATURE DELTA =========="
)

print(
    delta_df
    .round(6)
    .to_string(index=False)
)


print(
    "\nInterpretation:"
)

print(
    "Positive ROC/PR/F1 delta = improvement."
)

print(
    "Negative Brier/FAR/Missed delta = improvement."
)

print(
    "\nIMPORTANT:"
)

print(
    "This experiment does NOT overwrite deployment models."
)

print(
    "Banking features should only be adopted if they provide "
    "consistent incremental OOS value."
)

print(
    f"\nSaved metrics → {metrics_path}"
)

print(
    f"Saved delta   → {delta_path}"
)

print(
    "\nBANKING ABLATION COMPLETE"
)