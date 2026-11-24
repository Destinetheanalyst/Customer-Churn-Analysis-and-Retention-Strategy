# Customer Churn Analysis and Retention Strategy

*An end-to-end analytics project using Excel, MySQL, Python, and Power BI*

## Overview

This project analyses 7,043 telecom customers (the IBM Telco Customer Churn sample) to answer five questions: who is leaving, why, how well can customers be ranked by risk, who should receive a retention offer, and when does an offer pay for itself. It covers raw-data inspection and cleaning, SQL analysis, a validated model, a retention-economics model in Excel, and a Power BI report.
<img width="1378" height="766" alt="Screenshot 2026-11-21 134350" src="https://github.com/user-attachments/assets/5e947724-e49a-4673-afa1-6043c3aa73e2" />


| Result | Value |
| --- | --- |
| Churn rate | 26.5% (1,869 of 7,043 customers) |
| Monthly revenue held by churners | 30.5% |
| Month-to-month contracts | 55% of customers, 89% of churners |
| Model, on customers it never saw | ROC-AUC 0.84 |
| Retention plan, base assumptions | contact 1,360 customers, net benefit about 38,000 |
| **Break-even offer success rate** | **14.1%** (30% assumed) |

## Business Questions

1. Which customers churn most, and is it tenure, contract, or something else?
2. Can a model rank customers by churn risk, and how well does it do on customers it has never seen?
3. What does the model rely on, and does it treat different groups fairly?
4. Which customers should get a retention offer, and when does an offer pay for itself?

## Dataset

- **Source:** the IBM Telco Customer Churn sample (Kaggle): 7,043 customers, 21 columns covering plans, services, contract, tenure, charges and a churn flag. One row per customer.
- **Limitations:** The file has **no dates**, so it is a snapshot and not a follow-up study. It has no cost data, and the currency is not stated. The churn definition (“left within the last month”) comes from the dataset’s description and cannot be verified from the file.
<img width="1919" height="971" alt="Screenshot 2026-11-24 093503" src="https://github.com/user-attachments/assets/e44de51e-655e-44ab-a2a8-5b6676109382" />

## Approach

```
raw CSV → Excel (inspect) → Python (clean: 3 tidy tables + 1 flat table) → Excel (reconcile)
                                  ├→ MySQL (16 analytical queries)
                                  └→ Python (drivers, model, scores) → Excel (retention economics)
                                                                    → Power BI report
```

| Tool | Role in the project |
| --- | --- |
| Excel | Inspecting the raw data, reconciling totals, and a retention-economics workbook with live formulas (15,646 formulas, recalculated with zero errors and checked against Python) |
| MySQL 8 | Three tables with keys; 16 queries using CTEs, window functions and joins |
| Python (pandas, scikit-learn, matplotlib) | Cleaning, drivers, validated model, segments, fairness check, out-of-fold scoring, economics |
| Power BI | A three-page report built on the MySQL tables |
| Jupyter | Both Python scripts as documented notebooks with saved outputs |

## Key Findings

1. **Churn is concentrated.** Month-to-month customers are 55% of the base and 89% of churners (42.7% churn, against 11.3% for one-year and 2.8% for two-year contracts). One group, month-to-month on fiber optic paying by electronic check, is 19% of customers and 42% of all churners (60.4% churn). First-year customers are 31% of the base but 55.5% of churners.
2. **It is the contract, not just newness.** Within every tenure band, month-to-month customers churn at several times the rate of two-year customers.
3. **Add-ons look protective inside each internet type.** Fiber optic churn falls from 60.4% with no add-ons to 9.2% with all six. The overall table hides this because “no add-ons” mixes people with no internet (very low churn) and internet customers who bought nothing (high churn). Customers choose add-ons, so this is an association.
4. **Gender has no effect** (23.9% vs 23.3%). Senior citizens churn at about 42% vs 24%, but the model doesn't use either attribute.
5. **A simple rule gets far; the model sharpens the top of the list.** Flagging every month-to-month customer reaches 89% of churners but flags 55% of customers (43% precision). The model’s top 20% reaches half of all churners at 66% precision, which is where an offer budget is spent.
6. **The economics hinge on one unknown number.** Contacting everyone loses money (-30,862), and random outreach also loses. The base-case list nets about 38,000, **but if the real success rate is 15% and an offer costs 50, that same list loses 31,887.** The break-even success rate is 14.1%. The data cannot reveal the real rate; an A/B test must.
<img width="1372" height="763" alt="Screenshot 2026-11-23 101728" src="https://github.com/user-attachments/assets/04031971-9cea-4edb-a360-b0294311c213" />

## What Makes the Analysis Trustworthy

- **Rules fixed before the results.** Gender and age are not model features. The model is chosen by cross-validation on the training split only, preferring the simple logistic regression unless another beats it by more than 0.01 average precision. The test split is used once. Risk tiers are fixed in advance.
- **No leakage.** Every feature is known before a customer leaves. Each customer is scored by a model that never saw them (out-of-fold), and actual churn rises from 7.5% in the Low tier to 32.4% in Medium and 65.6% in High.
- **Robustness.** Adding gender and age changes AUC by 0.0001. Removing tenure, the strongest feature, lowers AUC only from 0.842 to 0.830.
- **Fairness check.** Gender is treated almost identically (flagged 25.3% vs 24.7%). Senior citizens are flagged about twice as often (43.4% vs 21.4%) because they churn more and have more fiber and month-to-month plans, and the model is less accurate for them (AUC 0.80 vs 0.85). Offers that restrict service should be reviewed first.
- **Honest sensitivity.** One table re-picks the best contact list for each assumption, so it can never go negative. The other keeps the base-case list while the assumptions change, which is the real risk, and it does go negative.
- **A real bug found and fixed.** The cleaned category `None` (customers with no internet) is read by pandas as a missing value, which silently dropped 1,526 customers from every grouping. It is now `No internet`.
- **Reconciled across tools.** The same totals (7,043 customers, 1,869 churned, 456,116.60 in monthly charges) appear in Excel, Python and MySQL.

## Power BI Report

A three-page report built on the MySQL tables:

| Page | Content |
| --- | --- |
| Churn Overview | Customers, monthly revenue and churned revenue, churn by tenure band, payment method, contract and number of add-ons |
| Customer Segmentation | Churn by demographics and services |
| Retention Opportunities | Churn by contract and payment method, tenure by contract, and churned revenue by segment |

The report is descriptive. The model’s scores, the at-risk list, and the retention economics live in `data/outputs/`, the notebooks, and the Excel workbook. The `powerbi/` folder holds wireframes, DAX measures and a build guide for extending the report with them.
<img width="1372" height="769" alt="Screenshot 2026-11-23 101808" src="https://github.com/user-attachments/assets/a1990d5b-c81a-4ca9-9b3f-c633cccd944d" />



## Recommendations

| # | Recommendation | Evidence |
| --- | --- | --- |
| 1 | Run an A/B test of the retention offer before committing budget | The plan breaks even at a 14.1% success rate and loses 31,887 at 15% with a cost of 50 |
| 2 | Start with month-to-month customers in their first year on fiber optic paying by electronic check | 1,307 customers, 60.4% churn, 42% of all churners |
| 3 | Test whether longer contracts or autopay reduce churn | Month-to-month churns at 42.7% vs 11.3% and 2.8%; electronic check at 45.3% vs 15% to 19%. These are hypotheses to test, not causes |
| 4 | Use the model to rank customers, and review fairness for seniors | The top 20% reaches half of churners at 66% precision; seniors are flagged twice as often |

## Repository Structure

```
churn-analysis-project/
├── data/
│   ├── raw/          (not committed; download from Kaggle)
│   ├── cleaned/      (customers, services, billing, flat table, data quality log)
│   └── outputs/      (scores, at-risk list, drivers, economics, summary JSON)
├── python/           (01_clean_data.py, 02_analysis.py)
├── notebooks/        (cleaning and analysis, with saved outputs)
├── sql/              (schema, load script, 16 analysis queries)
├── excel/            (Retention_Economics.xlsx)
├── powerbi/          (wireframes, build guide, DAX measures, theme)
├── docs/             (project plan with checkpoints)
├── images/           (7 charts)
└── README.md
```

## How to Reproduce

1. Download `WA_Fn-UseC_-Telco-Customer-Churn.csv` from Kaggle into `data/raw/`.
2. Install and run:

```
pip install -r requirements.txt
python python/01_clean_data.py
python python/02_analysis.py
```

3. Prefer notebooks? Run `pip install -r requirements-notebooks.txt`, start `jupyter lab`, and run the two notebooks in `notebooks/` in order.
4. MySQL 8.0 or later: run `sql/01_schema.sql`, then `sql/02_load_data.sql` (edit the folder path first), then the queries in `sql/03_analysis_queries.sql`.
5. Open `excel/Retention_Economics.xlsx` and change the yellow assumption cells.

## Limitations

- No dates, so this is a snapshot. Tenure means different things for customers who left and customers who stayed, and these are not survival curves.
- Associations, not causes. Fiber customers pay more and differ in other ways.
- Offer cost, success rate, and margin are **assumptions**, not data.
- One sample dataset, with no cost data. Probabilities assume the same churn pattern continues.

## Next Steps

- Run an A/B test of the retention offer, then re-run the economics with the measured success rate.
- Add dates to build real cohorts and survival curves.
- Add customer-level cost and margin.
- Extend the Power BI report with the risk tiers, the at-risk list, and the economics.

## Author

**Nnaemeka Destine Dike**, Business Analyst. https://www.linkedin.com/in/nnaemekadestinedike · https://medium.com/@destine.dike234 · destine.dike234@gmail.com
