import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
CLEAN, OUT, IMG = ROOT / "data" / "cleaned", ROOT / "data" / "outputs", ROOT / "images"
OUT.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)

SEED = 42
TEST_SIZE = 0.25
NUMERIC = ["tenure_months", "monthly_charges"]
CATEGORICAL = ["partner", "dependents", "phone_service", "multiple_lines", "internet_service", "online_security",
               "online_backup", "device_protection", "tech_support", "streaming_tv", "streaming_movies",
               "contract", "paperless_billing", "payment_method"]
PROTECTED = ["gender", "senior_citizen"]
TIERS = {"High": 0.50, "Medium": 0.20}
ASSUMPTIONS = {"offer_cost_per_contact": 25.0, "offer_success_rate": 0.30,
               "gross_margin": 0.40, "months_of_value": 12}
SUMMARY = {"assumptions": ASSUMPTIONS}

INK, GREY, RED, BLUE, GREEN, AMBER = "#1f2937", "#9ca3af", "#dc2626", "#2563eb", "#16a34a", "#d97706"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 11, "figure.dpi": 150})


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def make_pipeline(model, numeric, categorical, drop=None):
    pre = ColumnTransformer([("num", StandardScaler(), numeric),
                             ("cat", OneHotEncoder(drop=drop, handle_unknown="ignore"), categorical)])
    return Pipeline([("pre", pre), ("model", model)])


def gain_table(y, p, bins=10):
    d = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)}).sort_values("p", ascending=False).reset_index(drop=True)
    d["decile"] = (np.arange(len(d)) * bins // len(d)) + 1
    g = d.groupby("decile").agg(customers=("y", "size"), churned=("y", "sum"), avg_predicted=("p", "mean")).reset_index()
    g["churn_rate_pct"] = (100 * g.churned / g.customers).round(1)
    g["cumulative_pct_of_churners"] = (100 * g.churned.cumsum() / g.churned.sum()).round(1)
    g["lift"] = ((g.churned / g.customers) / (d.y.mean())).round(2)
    g["avg_predicted"] = g.avg_predicted.round(3)
    return g


def calibration_table(y, p, bins=10):
    d = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    d["bin"] = pd.qcut(d.p.rank(method="first"), bins, labels=False) + 1
    g = d.groupby("bin").agg(customers=("y", "size"), mean_predicted=("p", "mean"), actual_rate=("y", "mean")).reset_index()
    return g.round(3)


def bootstrap_ci(y, p, metric, n=1000):
    rng = np.random.default_rng(SEED)
    y, p = np.asarray(y), np.asarray(p)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        vals.append(metric(y[i], p[i]))
    return np.percentile(vals, [2.5, 97.5])


def leaf_rules(tree, feature_names, categories):
    """Plain-English rule for every leaf of a fitted decision tree, with redundant conditions merged."""
    t = tree.tree_
    rules = {}

    def decode(raw, thr, went_right):
        if raw in NUMERIC:
            return ("num", raw, ">" if went_right else "<=", thr)
        for c in CATEGORICAL:                       # a one-hot column such as contract_Month-to-month
            if raw.startswith(c + "_"):
                return ("cat", c, "=" if went_right else "!=", raw[len(c) + 1:])
        return ("num", raw, ">" if went_right else "<=", thr)

    def simplify(conds):
        parts = []
        for col in dict.fromkeys(c[1] for c in conds):
            cs = [c for c in conds if c[1] == col]
            if cs[0][0] == "cat":
                eq = [c[3] for c in cs if c[2] == "="]
                neq = [c[3] for c in cs if c[2] == "!="]
                left = [v for v in categories[col] if v not in neq]
                if eq:
                    parts.append(f"{col} = {eq[0]}")
                elif len(left) == 1:
                    parts.append(f"{col} = {left[0]}")
                else:
                    parts.append(f"{col} is not " + " or ".join(neq))
            else:
                lo = max([c[3] for c in cs if c[2] == ">"], default=None)
                hi = min([c[3] for c in cs if c[2] == "<="], default=None)
                if lo is not None and hi is not None:
                    parts.append(f"{lo:.1f} < {col} <= {hi:.1f}")
                elif hi is not None:
                    parts.append(f"{col} <= {hi:.1f}")
                else:
                    parts.append(f"{col} > {lo:.1f}")
        return " AND ".join(parts) if parts else "everyone"

    def walk(node, conds):
        if t.children_left[node] == -1:
            rules[node] = simplify(conds)
            return
        raw, thr = feature_names[t.feature[node]].split("__")[-1], t.threshold[node]
        walk(t.children_left[node], conds + [decode(raw, thr, False)])
        walk(t.children_right[node], conds + [decode(raw, thr, True)])

    walk(0, [])
    return rules


def main():
    # ---------------- 1. Load ----------------
    flat = pd.read_csv(CLEAN / "customers_flat.csv")
    assert len(flat) == 7043 and flat["customer_id"].is_unique
    overall = flat["churn_flag"].mean()
    print(f"Customers: {len(flat):,} | churn rate {overall*100:.2f}%")

    # ---------------- 2. Churn by segment (descriptive) ----------------
    seg_tables = {}
    for col in ["contract", "tenure_band", "internet_service", "payment_method"]:
        seg_tables[col] = (flat.groupby(col).agg(customers=("churn_flag", "size"), churn_rate_pct=("churn_flag", lambda s: round(100 * s.mean(), 1)))
                           .reset_index().sort_values("churn_rate_pct", ascending=False))
    pd.concat({k: v.rename(columns={k: "segment"}) for k, v in seg_tables.items()}, names=["dimension"]).reset_index(level=0) \
        .to_csv(OUT / "churn_by_segment.csv", index=False, lineterminator="\n")
    for k, v in seg_tables.items():
        print(f"\nChurn by {k}:\n{v.to_string(index=False)}")
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.2))
    order = {"tenure_band": ["0-12", "13-24", "25-36", "37-48", "49-60", "61-72"]}
    for ax, (col, title) in zip(axes.ravel(), [("contract", "Contract"), ("tenure_band", "Tenure (months)"),
                                                ("internet_service", "Internet service"), ("payment_method", "Payment method")]):
        t = seg_tables[col].set_index(col)
        t = t.loc[order[col]] if col in order else t.sort_values("churn_rate_pct")
        ax.bar(t.index, t.churn_rate_pct, color=[RED if v > 30 else BLUE for v in t.churn_rate_pct])
        ax.axhline(overall * 100, color=INK, ls="--", lw=1)
        for i, v in enumerate(t.churn_rate_pct):
            ax.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=8)
        ax.set_title(title, loc="left")
        ax.set_ylim(0, 62)
        ax.tick_params(axis="x", labelrotation=15 if col == "payment_method" else 0, labelsize=8)
    fig.suptitle(f"Churn rate by segment (dashed line = company average {overall*100:.1f}%)", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(IMG / "01_churn_by_segment.png")
    plt.close(fig)

    # ---------------- 3. Is it tenure or contract? ----------------
    within = flat.pivot_table(index="tenure_band", columns="contract", values="churn_flag", aggfunc="mean") * 100
    within = within.loc[order["tenure_band"]].round(1)
    print("\nChurn rate (%) by tenure band within each contract:\n", within.to_string())
    by_m = flat.groupby(["contract", "tenure_months"]).agg(c=("churn_flag", "sum"), n=("churn_flag", "size")).reset_index()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for contract, colr in zip(["Month-to-month", "One year", "Two year"], [RED, AMBER, GREEN]):
        g = by_m[by_m.contract == contract].set_index("tenure_months")[["c", "n"]].reindex(range(0, 73), fill_value=0)
        rate = g.c.rolling(7, center=True, min_periods=3).sum() / g.n.rolling(7, center=True, min_periods=3).sum() * 100
        ax.plot(rate.index, rate.values, color=colr, lw=2.2, label=contract)
    ax.set_xlabel("Tenure (months)")
    ax.set_ylabel("Churn rate (7-month rolling)")
    ax.set_title("Month-to-month customers churn more at every tenure, not just early on", loc="left")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(IMG / "02_churn_by_tenure_and_contract.png")
    plt.close(fig)

    # ---------------- 4. Train / test split ----------------
    X = flat[NUMERIC + CATEGORICAL]
    y = flat["churn_flag"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=TEST_SIZE, stratify=y, random_state=SEED)
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    print(f"\nTrain {len(X_train):,} (churn {y_train.mean()*100:.2f}%) | Test {len(X_test):,} (churn {y_test.mean()*100:.2f}%)")

    # ---------------- 5. Baselines ----------------
    test_info = flat.loc[X_test.index]
    rule_m2m = (test_info["contract"] == "Month-to-month").astype(int)
    rule_hi = ((test_info["contract"] == "Month-to-month") & (test_info["internet_service"] == "Fiber optic")
               & (test_info["payment_method"] == "Electronic check") & (test_info["tenure_months"] <= 12)).astype(int)
    def pr(rule):
        tp = int(((rule == 1) & (y_test == 1)).sum())
        return {"flagged": int(rule.sum()), "precision_pct": round(100 * tp / max(rule.sum(), 1), 1), "recall_pct": round(100 * tp / y_test.sum(), 1)}
    baselines = {"majority_class_accuracy_pct": round(100 * (1 - y_test.mean()), 1),
                 "rule_month_to_month": pr(rule_m2m), "rule_high_risk_profile": pr(rule_hi)}
    print("\nBaselines on the test set:", json.dumps(baselines))
    SUMMARY["baselines"] = baselines

    # ---------------- 6. Model comparison (cross-validation on TRAIN only) ----------------
    lr_grid = GridSearchCV(make_pipeline(LogisticRegression(max_iter=3000), NUMERIC, CATEGORICAL, drop="first"),
                           {"model__C": [0.01, 0.1, 1, 10]}, scoring="average_precision", cv=cv)
    lr_grid.fit(X_train, y_train)
    candidates = {
        "Logistic regression": lr_grid.best_estimator_,
        "Gradient boosting": make_pipeline(HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=SEED), NUMERIC, CATEGORICAL),
        "Random forest": make_pipeline(RandomForestClassifier(n_estimators=300, min_samples_leaf=10, random_state=SEED, n_jobs=1), NUMERIC, CATEGORICAL),
    }
    rows = []
    for name, est in candidates.items():
        r = cross_validate(clone(est), X_train, y_train, cv=cv, scoring={"ap": "average_precision", "auc": "roc_auc"})
        rows.append({"model": name, "cv_average_precision": r["test_ap"].mean(), "cv_ap_std": r["test_ap"].std(),
                     "cv_roc_auc": r["test_auc"].mean(), "cv_auc_std": r["test_auc"].std()})
    comp = pd.DataFrame(rows).round(4)
    comp.to_csv(OUT / "model_comparison.csv", index=False, lineterminator="\n")
    print(f"\nCross-validation on the training split (logistic regression C = {lr_grid.best_params_['model__C']}):\n{comp.to_string(index=False)}")
    best_other = comp[comp.model != "Logistic regression"].sort_values("cv_average_precision", ascending=False).iloc[0]
    lr_ap = comp.loc[comp.model == "Logistic regression", "cv_average_precision"].iloc[0]
    chosen = best_other["model"] if best_other["cv_average_precision"] > lr_ap + 0.01 else "Logistic regression"
    print(f"Chosen model: {chosen} (rule: logistic regression unless another beats it by more than 0.01 average precision)")
    SUMMARY["model_comparison"] = comp.to_dict(orient="records")
    SUMMARY["chosen_model"] = chosen
    SUMMARY["logistic_C"] = lr_grid.best_params_["model__C"]

    # ---------------- 7. Final model: the test set, used once ----------------
    final = clone(candidates[chosen]).fit(X_train, y_train)
    p_test = final.predict_proba(X_test)[:, 1]
    auc, ap = roc_auc_score(y_test, p_test), average_precision_score(y_test, p_test)
    auc_ci, ap_ci = bootstrap_ci(y_test, p_test, roc_auc_score), bootstrap_ci(y_test, p_test, average_precision_score)
    print(f"\nTEST: ROC-AUC {auc:.3f} (95% CI {auc_ci[0]:.3f} to {auc_ci[1]:.3f}) | average precision {ap:.3f} "
          f"(95% CI {ap_ci[0]:.3f} to {ap_ci[1]:.3f}) | churn rate in test {y_test.mean():.3f}")
    lift = gain_table(y_test, p_test)
    lift.to_csv(OUT / "lift_table.csv", index=False, lineterminator="\n")
    print("\nLift by decile (test):\n", lift.to_string(index=False))
    top = {}
    order_idx = np.argsort(-p_test)
    for share in (0.10, 0.20, 0.30):
        k = int(round(share * len(p_test)))
        caught = int(y_test.to_numpy()[order_idx[:k]].sum())
        top[f"top_{int(share*100)}pct"] = {"customers": k, "precision_pct": round(100 * caught / k, 1), "recall_pct": round(100 * caught / y_test.sum(), 1)}
    print("\nIf the top 10/20/30% by risk are contacted:", json.dumps(top))
    calib = calibration_table(y_test, p_test)
    calib.to_csv(OUT / "calibration_table.csv", index=False, lineterminator="\n")
    print("\nCalibration (test):\n", calib.to_string(index=False))
    SUMMARY["test"] = {"roc_auc": round(auc, 3), "roc_auc_ci95": [round(auc_ci[0], 3), round(auc_ci[1], 3)],
                       "average_precision": round(ap, 3), "ap_ci95": [round(ap_ci[0], 3), round(ap_ci[1], 3)],
                       "test_churn_rate": round(float(y_test.mean()), 4), "top_contacted": top}
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    fpr, tpr, _ = roc_curve(y_test, p_test)
    axes[0].plot(fpr, tpr, color=BLUE, lw=2.2)
    axes[0].plot([0, 1], [0, 1], color=GREY, ls="--")
    axes[0].set_xlabel("False positive rate")
    axes[0].set_ylabel("True positive rate")
    axes[0].set_title(f"ROC curve (AUC {auc:.2f})", loc="left")
    prec, rec, _ = precision_recall_curve(y_test, p_test)
    axes[1].plot(rec, prec, color=BLUE, lw=2.2)
    axes[1].axhline(y_test.mean(), color=GREY, ls="--")
    axes[1].text(0.02, y_test.mean() + 0.015, "no model (churn rate)", color=GREY, fontsize=8)
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    axes[1].set_title(f"Precision vs recall (average precision {ap:.2f})", loc="left")
    fig.tight_layout()
    fig.savefig(IMG / "03_model_roc_pr.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6.5, 4.4))
    x = np.r_[0, np.arange(1, 11) * 10]
    ax.plot(x, np.r_[0, lift.cumulative_pct_of_churners], color=BLUE, lw=2.4, marker="o", label="Model")
    ax.plot([0, 100], [0, 100], color=GREY, ls="--", label="Contact at random")
    ax.set_xlabel("% of customers contacted (highest risk first)")
    ax.set_ylabel("% of churners reached")
    ax.set_title(f"Gain: contacting the top 30% reaches {lift.cumulative_pct_of_churners.iloc[2]:.0f}% of churners", loc="left")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(IMG / "04_gain_curve.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    ax.plot(calib.mean_predicted, calib.actual_rate, color=BLUE, marker="o", lw=2)
    ax.plot([0, 1], [0, 1], color=GREY, ls="--")
    ax.set_xlabel("Predicted churn probability (decile average)")
    ax.set_ylabel("Actual churn rate")
    ax.set_title("Calibration: do probabilities mean what they say?", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(IMG / "05_calibration.png")
    plt.close(fig)

    # ---------------- 8. Drivers ----------------
    perm = permutation_importance(final, X_test, y_test, scoring="average_precision", n_repeats=20, random_state=SEED, n_jobs=1)
    imp = pd.DataFrame({"feature": X_test.columns, "importance": perm.importances_mean, "std": perm.importances_std}).sort_values("importance", ascending=False)
    imp.round(4).to_csv(OUT / "feature_importance.csv", index=False, lineterminator="\n")
    print("\nPermutation importance (drop in average precision when a feature is shuffled):\n", imp.round(4).head(10).to_string(index=False))
    lr_pipe = make_pipeline(LogisticRegression(C=lr_grid.best_params_["model__C"], max_iter=3000), NUMERIC, CATEGORICAL, drop="first").fit(X_train, y_train)
    names = lr_pipe.named_steps["pre"].get_feature_names_out()
    odds = pd.DataFrame({"term": [n.split("__")[-1] for n in names], "odds_ratio": np.exp(lr_pipe.named_steps["model"].coef_[0])})
    odds["meaning"] = np.where(odds.term.isin(NUMERIC), "per 1 standard deviation increase", "vs the reference value of that attribute")
    odds = odds.sort_values("odds_ratio", ascending=False).round(3)
    odds.to_csv(OUT / "odds_ratios.csv", index=False, lineterminator="\n")
    print("\nHighest odds ratios (more likely to churn):\n", odds.head(6).to_string(index=False))
    print("\nLowest odds ratios (less likely to churn):\n", odds.tail(6).to_string(index=False))
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    t = imp.head(10).iloc[::-1]
    ax.barh(t.feature, t.importance, xerr=t["std"], color=BLUE)
    ax.set_xlabel("Drop in average precision when the feature is shuffled (test set)")
    ax.set_title("What the model relies on most", loc="left")
    fig.tight_layout()
    fig.savefig(IMG / "06_feature_importance.png")
    plt.close(fig)
    SUMMARY["top_features"] = imp.head(5).feature.tolist()

    # ---------------- 9. Ablation and fairness ----------------
    def cv_scores(numeric, categorical):
        pipe = make_pipeline(LogisticRegression(C=lr_grid.best_params_["model__C"], max_iter=3000), numeric, categorical, drop="first")
        r = cross_validate(pipe, flat.loc[X_train.index, numeric + categorical], y_train, cv=cv, scoring={"ap": "average_precision", "auc": "roc_auc"})
        return round(r["test_auc"].mean(), 4), round(r["test_ap"].mean(), 4)
    auc_without, ap_without = cv_scores(NUMERIC, CATEGORICAL)
    auc_with, ap_with = cv_scores(NUMERIC, CATEGORICAL + PROTECTED)
    auc_notenure, ap_notenure = cv_scores(["monthly_charges"], CATEGORICAL)
    print(f"\nAblation (train CV, logistic regression):\n  features as used ............ AUC {auc_without}  AP {ap_without}"
          f"\n  + gender and senior ......... AUC {auc_with}  AP {ap_with}   (change in AUC {auc_with - auc_without:+.4f})"
          f"\n  without tenure_months ....... AUC {auc_notenure}  AP {ap_notenure}   (change in AUC {auc_notenure - auc_without:+.4f})")
    SUMMARY["ablation"] = {"auc_without_protected": auc_without, "auc_with_protected": auc_with, "ap_without_protected": ap_without,
                           "ap_with_protected": ap_with, "auc_without_tenure": auc_notenure, "ap_without_tenure": ap_notenure}
    flag_k = int(round(0.25 * len(p_test)))
    flagged = np.zeros(len(p_test), dtype=int)
    flagged[order_idx[:flag_k]] = 1
    fair_rows = []
    for col in PROTECTED:
        for val in sorted(test_info[col].unique()):
            m = (test_info[col] == val).to_numpy()
            yy, ff, pp = y_test.to_numpy()[m], flagged[m], p_test[m]
            fair_rows.append({"attribute": col, "group": val, "customers": int(m.sum()), "actual_churn_rate_pct": round(100 * yy.mean(), 1),
                              "flagged_pct": round(100 * ff.mean(), 1), "recall_pct": round(100 * (ff[yy == 1].mean()), 1),
                              "precision_pct": round(100 * yy[ff == 1].mean(), 1) if ff.sum() else None, "auc": round(roc_auc_score(yy, pp), 3)})
    fair = pd.DataFrame(fair_rows)
    fair.to_csv(OUT / "fairness_check.csv", index=False, lineterminator="\n")
    print("\nFairness check (top 25% flagged), test set:\n", fair.to_string(index=False))

    # ---------------- 10. Segments (a small decision tree, for plain-English rules) ----------------
    seg_pre = ColumnTransformer([("num", "passthrough", NUMERIC), ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL)])
    Xs_train = seg_pre.fit_transform(X_train)
    Xs_test = seg_pre.transform(X_test)
    tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=100, random_state=SEED).fit(Xs_train, y_train)
    rules = leaf_rules(tree, seg_pre.get_feature_names_out(), {c: sorted(flat[c].unique()) for c in CATEGORICAL})
    leaf_train, leaf_test = tree.apply(Xs_train), tree.apply(Xs_test)
    seg_rows = []
    for leaf, rule in rules.items():
        mt, me = leaf_train == leaf, leaf_test == leaf
        seg_rows.append({"rule": rule, "customers_train": int(mt.sum()), "churn_rate_train_pct": round(100 * y_train.to_numpy()[mt].mean(), 1),
                         "customers_test": int(me.sum()), "churn_rate_test_pct": round(100 * y_test.to_numpy()[me].mean(), 1) if me.sum() else None})
    seg = pd.DataFrame(seg_rows).sort_values("churn_rate_train_pct", ascending=False).reset_index(drop=True)
    seg.insert(0, "segment", [f"S{i+1}" for i in range(len(seg))])
    seg.to_csv(OUT / "segment_rules.csv", index=False, lineterminator="\n")
    print("\nSegments found by a depth-3 decision tree (train rates, then held-out test rates):\n", seg.to_string(index=False))

    # ---------------- 11. Score every customer (out-of-fold: nobody is scored by a model that saw them) ----------------
    cv_all = StratifiedKFold(5, shuffle=True, random_state=SEED)
    p_oof = cross_val_predict(clone(candidates[chosen]), X, y, cv=cv_all, method="predict_proba")[:, 1]
    oof_auc, oof_ap = roc_auc_score(y, p_oof), average_precision_score(y, p_oof)
    print(f"\nOut-of-fold scores for all customers: ROC-AUC {oof_auc:.3f}, average precision {oof_ap:.3f}")
    scored = flat.copy()
    scored["churn_probability"] = p_oof.round(4)
    scored["risk_tier"] = np.where(p_oof >= TIERS["High"], "High", np.where(p_oof >= TIERS["Medium"], "Medium", "Low"))
    tiers = scored.groupby("risk_tier").agg(customers=("churn_flag", "size"), actual_churn_rate_pct=("churn_flag", lambda s: round(100 * s.mean(), 1)),
                                            avg_probability=("churn_probability", lambda s: round(s.mean(), 3))).reindex(["High", "Medium", "Low"])
    print("\nRisk tiers (out-of-fold):\n", tiers.to_string())
    tiers.reset_index().to_csv(OUT / "risk_tiers.csv", index=False, lineterminator="\n")
    SUMMARY["oof"] = {"roc_auc": round(oof_auc, 3), "average_precision": round(oof_ap, 3)}
    SUMMARY["tiers"] = tiers.reset_index().to_dict(orient="records")

    # ---------------- 12. Retention economics (active customers) ----------------
    a = ASSUMPTIONS
    scored["value_if_retained"] = (scored.monthly_charges * a["gross_margin"] * a["months_of_value"]).round(2)
    scored["expected_benefit"] = (scored.churn_probability * a["offer_success_rate"] * scored.value_if_retained - a["offer_cost_per_contact"]).round(2)
    scored["contact_recommended"] = ((scored.expected_benefit > 0) & (scored.churn_flag == 0)).astype(int)
    scored.to_csv(OUT / "scored_customers.csv", index=False, lineterminator="\n")
    active = scored[scored.churn_flag == 0].copy()
    contacted = active[active.expected_benefit > 0]
    base = {"active_customers": len(active), "contacted": len(contacted), "contact_cost": round(len(contacted) * a["offer_cost_per_contact"], 2),
            "expected_net_benefit": round(contacted.expected_benefit.sum(), 2),
            "expected_customers_retained": round((contacted.churn_probability * a["offer_success_rate"]).sum(), 1),
            "contact_everyone_net_benefit": round(active.expected_benefit.sum(), 2),
            "random_same_size_net_benefit": round(active.expected_benefit.mean() * len(contacted), 2)}
    print("\nRETENTION ECONOMICS (base assumptions", json.dumps(a), "):\n", json.dumps(base, indent=1))
    SUMMARY["economics_base"] = base
    active.sort_values("expected_benefit", ascending=False)[
        ["customer_id", "churn_probability", "risk_tier", "contract", "tenure_months", "internet_service", "payment_method", "monthly_charges",
         "value_if_retained", "expected_benefit", "contact_recommended"]].to_csv(OUT / "at_risk_active_customers.csv", index=False, lineterminator="\n")
    cut_rows = []
    for t in np.round(np.arange(0.05, 0.851, 0.05), 2):
        sel = active[active.churn_probability >= t]
        cut_rows.append({"min_probability": t, "customers_contacted": len(sel), "expected_churners_reached": round(sel.churn_probability.sum(), 1),
                         "contact_cost": round(len(sel) * a["offer_cost_per_contact"], 2), "expected_net_benefit": round(sel.expected_benefit.sum(), 2)})
    cuts = pd.DataFrame(cut_rows)
    cuts.to_csv(OUT / "economics_cutoffs.csv", index=False, lineterminator="\n")
    best_cut = cuts.loc[cuts.expected_net_benefit.idxmax()]
    print(f"\nBest single probability cutoff: {best_cut.min_probability} (net benefit {best_cut.expected_net_benefit:,.0f}) "
          f"vs per-customer rule {base['expected_net_benefit']:,.0f}")
    sens_rows = []
    for s in (0.15, 0.30, 0.45):
        for c in (10.0, 25.0, 50.0):
            b = active.churn_probability * s * active.value_if_retained - c
            sens_rows.append({"offer_success_rate": s, "offer_cost_per_contact": c, "customers_contacted": int((b > 0).sum()),
                              "expected_net_benefit": round(b[b > 0].sum(), 2)})
    sens = pd.DataFrame(sens_rows)
    sens.to_csv(OUT / "economics_sensitivity.csv", index=False, lineterminator="\n")
    print("\nSensitivity A: net benefit when the contact list is RE-OPTIMISED for each assumption (cannot go negative):\n",
          sens.pivot(index="offer_success_rate", columns="offer_cost_per_contact", values="expected_net_benefit").to_string())
    SUMMARY["economics_best_cutoff"] = {"min_probability": float(best_cut.min_probability), "expected_net_benefit": float(best_cut.expected_net_benefit)}
    SUMMARY["economics_sensitivity"] = sens.to_dict(orient="records")
    # Sensitivity B is the honest risk test: we send offers to the BASE-CASE list, then the real success rate or cost turns out different.
    fixed_rows = []
    for s in (0.15, 0.30, 0.45):
        for c in (10.0, 25.0, 50.0):
            b = contacted.churn_probability * s * contacted.value_if_retained - c
            fixed_rows.append({"offer_success_rate": s, "offer_cost_per_contact": c, "customers_contacted": len(contacted),
                               "expected_net_benefit": round(b.sum(), 2)})
    fixed = pd.DataFrame(fixed_rows)
    fixed.to_csv(OUT / "economics_sensitivity_fixed_list.csv", index=False, lineterminator="\n")
    breakeven = a["offer_cost_per_contact"] * len(contacted) / (contacted.churn_probability * contacted.value_if_retained).sum()
    print("\nSensitivity B: net benefit when the BASE-CASE contact list is used but the real assumptions differ (this CAN go negative):\n",
          fixed.pivot(index="offer_success_rate", columns="offer_cost_per_contact", values="expected_net_benefit").to_string())
    print(f"Break-even offer success rate for the base-case list at cost {a['offer_cost_per_contact']:.0f}: {breakeven:.1%} (assumed: {a['offer_success_rate']:.0%})")
    SUMMARY["economics_sensitivity_fixed_list"] = fixed.to_dict(orient="records")
    SUMMARY["breakeven_success_rate"] = round(float(breakeven), 4)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(cuts.min_probability, cuts.expected_net_benefit / 1000, color=BLUE, lw=2.4, marker="o", ms=4)
    ax.axhline(base["expected_net_benefit"] / 1000, color=GREEN, ls="--", lw=1.4)
    ax.text(0.84, base["expected_net_benefit"] / 1000, " best per-customer rule", color=GREEN, fontsize=8, va="bottom", ha="right")
    ax.set_xlabel("Contact every active customer with churn probability at or above")
    ax.set_ylabel("Expected net benefit (thousands)")
    ax.set_title(f"Net benefit peaks when customers at {best_cut.min_probability:.0%} churn risk or above are contacted", loc="left")
    fig.tight_layout()
    fig.savefig(IMG / "07_economics_cutoff.png")
    plt.close(fig)

    # ---------------- 13. Save summary ----------------
    (OUT / "analysis_summary.json").write_text(json.dumps(SUMMARY, indent=2, default=str))
    print("\nWrote:", ", ".join(sorted(p.name for p in OUT.glob("*"))))
    print("Charts:", ", ".join(sorted(p.name for p in IMG.glob("0*.png"))))


if __name__ == "__main__":
    main()
