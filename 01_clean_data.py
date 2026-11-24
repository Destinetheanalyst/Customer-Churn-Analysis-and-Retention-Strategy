import argparse
from pathlib import Path

import numpy as np
import pandas as pd

RAW_FILE = "WA_Fn-UseC_-Telco-Customer-Churn.csv"
ADDON_COLS = ["online_security", "online_backup", "device_protection",
              "tech_support", "streaming_tv", "streaming_movies"]
RENAME = {
    "customerID": "customer_id", "gender": "gender", "SeniorCitizen": "senior_citizen",
    "Partner": "partner", "Dependents": "dependents", "tenure": "tenure_months",
    "PhoneService": "phone_service", "MultipleLines": "multiple_lines",
    "InternetService": "internet_service", "OnlineSecurity": "online_security",
    "OnlineBackup": "online_backup", "DeviceProtection": "device_protection",
    "TechSupport": "tech_support", "StreamingTV": "streaming_tv",
    "StreamingMovies": "streaming_movies", "Contract": "contract",
    "PaperlessBilling": "paperless_billing", "PaymentMethod": "payment_method",
    "MonthlyCharges": "monthly_charges", "TotalCharges": "total_charges", "Churn": "churn",
}

LOG = []


def log(step, kind, rule, count):
    """kind: clean = data was changed, add = column created, trap = left as is on purpose"""
    LOG.append({"step": step, "kind": kind, "rule": rule, "count": int(count)})
    print(f"[{step:>4}] {kind:<5} {rule}: {int(count):,}")


def main(raw: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)

    # ---------------- Load ----------------
    df = pd.read_csv(raw / RAW_FILE, dtype=str, keep_default_na=False)
    n_raw = len(df)
    print(f"Loaded {n_raw:,} rows and {df.shape[1]} columns")

    # 1. Column names
    df = df.rename(columns=RENAME)
    log(1, "clean", "Columns renamed to snake_case", len(RENAME))

    # 2. Whitespace
    stripped = df.apply(lambda c: c.str.strip())
    n_ws = int((df != stripped).to_numpy().sum())
    df = stripped
    log(2, "clean", "Cells with leading or trailing whitespace trimmed (all in total_charges)", n_ws)

    # 3. Numeric columns and the blank total_charges
    blank_total = df["total_charges"] == ""
    df["tenure_months"] = df["tenure_months"].astype(int)
    df["monthly_charges"] = df["monthly_charges"].astype(float)
    df["total_charges"] = pd.to_numeric(df["total_charges"].replace("", np.nan))
    assert blank_total.sum() == (df["tenure_months"] == 0).sum()
    assert set(df.loc[blank_total, "tenure_months"]) == {0}
    df["is_new_unbilled"] = blank_total.map({True: "Yes", False: "No"})
    df["total_charges"] = df["total_charges"].fillna(0.0)
    log(3, "clean", "Blank total_charges set to 0.00 (all are tenure-0 customers, not yet billed) and flagged is_new_unbilled", blank_total.sum())

    # 4. Consistent Yes/No coding
    df["senior_citizen"] = df["senior_citizen"].map({"0": "No", "1": "Yes"})
    log(4, "clean", "senior_citizen recoded from 0/1 to No/Yes to match the other columns (Yes count)", (df["senior_citizen"] == "Yes").sum())

    # 5. Collapse the three-level answers
    cols3 = ADDON_COLS + ["multiple_lines"]
    n_collapsed = int(df[cols3].isin(["No internet service", "No phone service"]).to_numpy().sum())
    df[cols3] = df[cols3].replace({"No internet service": "No", "No phone service": "No"})
    log(5, "clean", "'No internet service' and 'No phone service' collapsed to 'No' (internet_service and phone_service already carry that fact), cells changed", n_collapsed)

    # 6. internet_service 'No' -> 'No internet'
    n_none = int((df["internet_service"] == "No").sum())
    df["internet_service"] = df["internet_service"].replace({"No": "No internet"})
    log(6, "clean", "internet_service 'No' renamed 'No internet' so it is not mistaken for a Yes/No answer (and the text 'None' is avoided: pandas reads it as a missing value)", n_none)

    # 7. Target
    df["churn_flag"] = (df["churn"] == "Yes").astype(int)
    log(7, "add", "churn_flag (1 = churned) created", df["churn_flag"].sum())

    # 8. Tenure bands (yearly)
    df["tenure_band"] = pd.cut(df["tenure_months"], bins=[-1, 12, 24, 36, 48, 60, 72],
                               labels=["0-12", "13-24", "25-36", "37-48", "49-60", "61-72"]).astype(str)
    df["tenure_band_order"] = pd.cut(df["tenure_months"], bins=[-1, 12, 24, 36, 48, 60, 72], labels=[1, 2, 3, 4, 5, 6]).astype(int)
    log(8, "add", "tenure_band and tenure_band_order created (yearly bands, tenure-0 customers sit in 0-12)", len(df))

    # 9. Add-on count and autopay
    df["num_addons"] = (df[ADDON_COLS] == "Yes").sum(axis=1)
    df["autopay"] = df["payment_method"].str.contains("automatic").map({True: "Yes", False: "No"})
    log(9, "add", "num_addons (0 to 6 optional services) created, customers with at least one", (df["num_addons"] > 0).sum())
    log(10, "add", "autopay (bank transfer or credit card) created, customers on autopay", (df["autopay"] == "Yes").sum())

    # 11. Things we deliberately did NOT change
    n_dup = int(df.drop(columns="customer_id").duplicated().sum())
    log(11, "trap", "Rows identical to another customer on every column except ID: kept (all tenure 1, simplest plans: a shared plan is not a duplicate)", n_dup)
    billed = df[df["is_new_unbilled"] == "No"]
    gap = (billed["total_charges"] - billed["tenure_months"] * billed["monthly_charges"]).abs() > 0.2 * billed["total_charges"]
    log(12, "trap", "total_charges differs from tenure x monthly_charges by more than 20% (price changes over time): kept as recorded", gap.sum())
    log(13, "trap", "Class imbalance: 26.5% of customers churned, so 'predict nobody leaves' is already 73.5% accurate and accuracy is not a valid score. Count = churned customers", df["churn_flag"].sum())
    log(14, "trap", "No dates in the file, so this is a snapshot. Tenure is the length of stay for churned customers but is still growing for active ones. Count = active customers", (df["churn_flag"] == 0).sum())

    # ---------------- Tables ----------------
    customers = df[["customer_id", "gender", "senior_citizen", "partner", "dependents", "tenure_months",
                    "tenure_band", "tenure_band_order", "is_new_unbilled", "churn", "churn_flag"]]
    services = df[["customer_id", "phone_service", "multiple_lines", "internet_service"] + ADDON_COLS + ["num_addons"]]
    billing = df[["customer_id", "contract", "paperless_billing", "payment_method", "autopay",
                  "monthly_charges", "total_charges"]]
    flat = customers.merge(services, on="customer_id").merge(billing, on="customer_id")
    assert len(flat) == len(customers) == len(services) == len(billing) == n_raw
    for name, t in [("customers", customers), ("services", services), ("billing", billing), ("customers_flat", flat)]:
        t.to_csv(out / f"{name}.csv", index=False, lineterminator="\n")

    # ---------------- Reconciliation ----------------
    pd.DataFrame(LOG).to_csv(out / "data_quality_log.csv", index=False, lineterminator="\n")
    print("\n--- RECONCILIATION (these must match your Excel checkpoints) ---")
    print(f"Customers: {len(flat):,} | unique IDs: {flat['customer_id'].nunique():,}")
    print(f"Churn Yes / No: {int(flat['churn_flag'].sum()):,} / {int((1 - flat['churn_flag']).sum()):,} ({flat['churn_flag'].mean()*100:.2f}%)")
    print(f"Senior citizens: {(flat['senior_citizen'] == 'Yes').sum():,}")
    print(f"Tenure min / max / at 0: {flat['tenure_months'].min()} / {flat['tenure_months'].max()} / {(flat['tenure_months'] == 0).sum()}")
    print(f"Monthly charges sum / mean / min / max: {flat['monthly_charges'].sum():,.2f} / {flat['monthly_charges'].mean():.2f} / {flat['monthly_charges'].min():.2f} / {flat['monthly_charges'].max():.2f}")
    print(f"Total charges sum: {flat['total_charges'].sum():,.2f}")
    print(f"Monthly charges of churned customers: {flat.loc[flat['churn_flag'] == 1, 'monthly_charges'].sum():,.2f}")
    print("Contract:", flat["contract"].value_counts().to_dict())
    print("Internet service:", flat["internet_service"].value_counts().to_dict())
    assert len(flat) == 7043 and flat["customer_id"].is_unique
    assert flat["churn_flag"].sum() == 1869
    assert round(flat["monthly_charges"].sum(), 2) == 456116.60
    assert round(flat["total_charges"].sum(), 2) == 16056168.70
    print("\nAll reconciliation checks passed.")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=root / "data" / "raw")
    ap.add_argument("--out", type=Path, default=root / "data" / "cleaned")
    a = ap.parse_args()
    main(a.raw, a.out)
