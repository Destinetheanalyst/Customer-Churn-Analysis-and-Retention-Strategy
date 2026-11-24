
USE telco_churn;


-- Q0. Load validation
SELECT COUNT(*)                         AS customers,
       SUM(c.churn_flag)                AS churned,
       ROUND(SUM(b.monthly_charges), 2) AS monthly_charges,
       ROUND(SUM(b.total_charges), 2)   AS total_charges
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id;


-- Q1. The headline: overall churn and the revenue behind it 
SELECT COUNT(*)                                                        AS customers,
       SUM(c.churn_flag)                                               AS churned,
       ROUND(100.0 * SUM(c.churn_flag) / COUNT(*), 2)                  AS churn_rate_pct,
       ROUND(SUM(b.monthly_charges), 2)                                AS monthly_revenue,
       ROUND(SUM(CASE WHEN c.churn_flag = 1 THEN b.monthly_charges ELSE 0 END), 2) AS monthly_revenue_of_churners,
       ROUND(100.0 * SUM(CASE WHEN c.churn_flag = 1 THEN b.monthly_charges ELSE 0 END) / SUM(b.monthly_charges), 1) AS pct_revenue_of_churners,
       ROUND(AVG(CASE WHEN c.churn_flag = 1 THEN c.tenure_months END), 1) AS avg_tenure_churned,
       ROUND(AVG(CASE WHEN c.churn_flag = 0 THEN c.tenure_months END), 1) AS avg_tenure_stayed,
       ROUND(AVG(CASE WHEN c.churn_flag = 1 THEN b.monthly_charges END), 2) AS avg_monthly_churned,
       ROUND(AVG(CASE WHEN c.churn_flag = 0 THEN b.monthly_charges END), 2) AS avg_monthly_stayed
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id;


-- Q2. Churn by contract
SELECT b.contract,
       COUNT(*)                                                         AS customers,
       SUM(c.churn_flag)                                                AS churned,
       ROUND(100.0 * SUM(c.churn_flag) / COUNT(*), 1)                   AS churn_rate_pct,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)               AS pct_of_customers,
       ROUND(100.0 * SUM(c.churn_flag) / SUM(SUM(c.churn_flag)) OVER (), 1) AS pct_of_all_churners,
       ROUND(AVG(b.monthly_charges), 2)                                 AS avg_monthly_charge
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id
GROUP BY b.contract
ORDER BY churn_rate_pct DESC;


-- Q3. Churn by tenure band 
SELECT c.tenure_band,
       COUNT(*)                                       AS customers,
       SUM(c.churn_flag)                              AS churned,
       ROUND(100.0 * SUM(c.churn_flag) / COUNT(*), 1) AS churn_rate_pct,
       ROUND(100.0 * SUM(c.churn_flag) / SUM(SUM(c.churn_flag)) OVER (), 1) AS pct_of_all_churners,
       ROUND(AVG(b.monthly_charges), 2)               AS avg_monthly_charge
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id
GROUP BY c.tenure_band_order, c.tenure_band
ORDER BY c.tenure_band_order;


-- Q4. Which attributes separate churners best? .
WITH seg AS (
    SELECT 'contract' AS dimension, b.contract AS segment, c.churn_flag FROM customers c JOIN billing b ON b.customer_id = c.customer_id
    UNION ALL SELECT 'payment_method', b.payment_method, c.churn_flag FROM customers c JOIN billing b ON b.customer_id = c.customer_id
    UNION ALL SELECT 'paperless_billing', b.paperless_billing, c.churn_flag FROM customers c JOIN billing b ON b.customer_id = c.customer_id
    UNION ALL SELECT 'autopay', b.autopay, c.churn_flag FROM customers c JOIN billing b ON b.customer_id = c.customer_id
    UNION ALL SELECT 'tenure_band', c.tenure_band, c.churn_flag FROM customers c
    UNION ALL SELECT 'senior_citizen', c.senior_citizen, c.churn_flag FROM customers c
    UNION ALL SELECT 'partner', c.partner, c.churn_flag FROM customers c
    UNION ALL SELECT 'dependents', c.dependents, c.churn_flag FROM customers c
    UNION ALL SELECT 'gender', c.gender, c.churn_flag FROM customers c
    UNION ALL SELECT 'internet_service', s.internet_service, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
    UNION ALL SELECT 'online_security', s.online_security, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
    UNION ALL SELECT 'tech_support', s.tech_support, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
    UNION ALL SELECT 'online_backup', s.online_backup, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
    UNION ALL SELECT 'device_protection', s.device_protection, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
    UNION ALL SELECT 'streaming_tv', s.streaming_tv, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
    UNION ALL SELECT 'streaming_movies', s.streaming_movies, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
    UNION ALL SELECT 'multiple_lines', s.multiple_lines, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
    UNION ALL SELECT 'phone_service', s.phone_service, c.churn_flag FROM customers c JOIN services s ON s.customer_id = c.customer_id
),
rates AS (
    SELECT dimension, segment, COUNT(*) AS customers, 100.0 * SUM(churn_flag) / COUNT(*) AS rate
    FROM seg
    GROUP BY dimension, segment
)
SELECT dimension,
       COUNT(*)                                             AS values_in_attribute,
       ROUND(MIN(rate), 1)                                  AS lowest_rate_pct,
       ROUND(MAX(rate), 1)                                  AS highest_rate_pct,
       ROUND(MAX(rate) - MIN(rate), 1)                      AS spread_pts,
       RANK() OVER (ORDER BY MAX(rate) - MIN(rate) DESC)    AS spread_rank
FROM rates
GROUP BY dimension
ORDER BY spread_rank;


-- Q5. Add-ons look protective, but check inside each internet type 
SELECT s.internet_service,
       s.num_addons,
       COUNT(*)                                       AS customers,
       ROUND(100.0 * SUM(c.churn_flag) / COUNT(*), 1) AS churn_rate_pct
FROM customers c
JOIN services s ON s.customer_id = c.customer_id
GROUP BY s.internet_service, s.num_addons
ORDER BY s.internet_service, s.num_addons;


-- Q6. Contract x tenure band: is it tenure or contract? (churn rate %, customers) 
SELECT c.tenure_band,
       SUM(CASE WHEN b.contract = 'Month-to-month' THEN 1 ELSE 0 END)                       AS m2m_customers,
       ROUND(100.0 * SUM(CASE WHEN b.contract = 'Month-to-month' THEN c.churn_flag ELSE 0 END)
             / NULLIF(SUM(CASE WHEN b.contract = 'Month-to-month' THEN 1 ELSE 0 END), 0), 1) AS m2m_rate_pct,
       SUM(CASE WHEN b.contract = 'One year' THEN 1 ELSE 0 END)                             AS one_year_customers,
       ROUND(100.0 * SUM(CASE WHEN b.contract = 'One year' THEN c.churn_flag ELSE 0 END)
             / NULLIF(SUM(CASE WHEN b.contract = 'One year' THEN 1 ELSE 0 END), 0), 1)      AS one_year_rate_pct,
       SUM(CASE WHEN b.contract = 'Two year' THEN 1 ELSE 0 END)                             AS two_year_customers,
       ROUND(100.0 * SUM(CASE WHEN b.contract = 'Two year' THEN c.churn_flag ELSE 0 END)
             / NULLIF(SUM(CASE WHEN b.contract = 'Two year' THEN 1 ELSE 0 END), 0), 1)      AS two_year_rate_pct
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id
GROUP BY c.tenure_band_order, c.tenure_band
ORDER BY c.tenure_band_order;


-- Q7. Contract x internet type (churn rate %, customers) 
SELECT s.internet_service,
       SUM(CASE WHEN b.contract = 'Month-to-month' THEN 1 ELSE 0 END)                       AS m2m_customers,
       ROUND(100.0 * SUM(CASE WHEN b.contract = 'Month-to-month' THEN c.churn_flag ELSE 0 END)
             / NULLIF(SUM(CASE WHEN b.contract = 'Month-to-month' THEN 1 ELSE 0 END), 0), 1) AS m2m_rate_pct,
       SUM(CASE WHEN b.contract = 'One year' THEN 1 ELSE 0 END)                             AS one_year_customers,
       ROUND(100.0 * SUM(CASE WHEN b.contract = 'One year' THEN c.churn_flag ELSE 0 END)
             / NULLIF(SUM(CASE WHEN b.contract = 'One year' THEN 1 ELSE 0 END), 0), 1)      AS one_year_rate_pct,
       SUM(CASE WHEN b.contract = 'Two year' THEN 1 ELSE 0 END)                             AS two_year_customers,
       ROUND(100.0 * SUM(CASE WHEN b.contract = 'Two year' THEN c.churn_flag ELSE 0 END)
             / NULLIF(SUM(CASE WHEN b.contract = 'Two year' THEN 1 ELSE 0 END), 0), 1)      AS two_year_rate_pct
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id
JOIN services s ON s.customer_id = c.customer_id
GROUP BY s.internet_service
ORDER BY s.internet_service;


-- Q8. Where do the churners concentrate? (Pareto of contract x internet x payment) 
-- Cumulative share is computed over ALL 36 combinations, then the top 10 are shown.
WITH combos AS (
    SELECT b.contract, s.internet_service, b.payment_method,
           COUNT(*) AS customers, SUM(c.churn_flag) AS churned
    FROM customers c
    JOIN billing b ON b.customer_id = c.customer_id
    JOIN services s ON s.customer_id = c.customer_id
    GROUP BY b.contract, s.internet_service, b.payment_method
),
ranked AS (
    SELECT contract, internet_service, payment_method, customers, churned,
           ROUND(100.0 * churned / customers, 1) AS churn_rate_pct,
           ROUND(100.0 * SUM(churned) OVER (ORDER BY churned DESC, customers DESC, contract, internet_service, payment_method)
                 / SUM(churned) OVER (), 1) AS cumulative_pct_of_churners
    FROM combos
)
SELECT * FROM ranked
ORDER BY churned DESC, customers DESC
LIMIT 10;


-- Q9. Contract x payment method, compared with the company average 
SELECT b.contract,
       b.payment_method,
       COUNT(*)                                                     AS customers,
       ROUND(100.0 * SUM(c.churn_flag) / COUNT(*), 1)               AS churn_rate_pct,
       ROUND(100.0 * SUM(c.churn_flag) / COUNT(*)
             - (SELECT 100.0 * AVG(churn_flag) FROM customers), 1)  AS pts_vs_company_average
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id
GROUP BY b.contract, b.payment_method
ORDER BY churn_rate_pct DESC;


-- Q10. Does price matter? Churn by monthly-charge quartile (NTILE) -----------------
WITH q AS (
    SELECT c.churn_flag, b.monthly_charges,
           NTILE(4) OVER (ORDER BY b.monthly_charges) AS charge_quartile
    FROM customers c
    JOIN billing b ON b.customer_id = c.customer_id
)
SELECT charge_quartile,
       MIN(monthly_charges)                          AS from_charge,
       MAX(monthly_charges)                          AS to_charge,
       COUNT(*)                                      AS customers,
       ROUND(100.0 * SUM(churn_flag) / COUNT(*), 1)  AS churn_rate_pct
FROM q
GROUP BY charge_quartile
ORDER BY charge_quartile;


-- Q11. Revenue at risk: monthly charges of churners by contract x internet type ------
SELECT b.contract,
       s.internet_service,
       SUM(c.churn_flag)                                                           AS churned,
       ROUND(SUM(CASE WHEN c.churn_flag = 1 THEN b.monthly_charges ELSE 0 END), 2) AS monthly_revenue_lost,
       ROUND(100.0 * SUM(CASE WHEN c.churn_flag = 1 THEN b.monthly_charges ELSE 0 END)
             / SUM(SUM(CASE WHEN c.churn_flag = 1 THEN b.monthly_charges ELSE 0 END)) OVER (), 1) AS pct_of_revenue_lost,
       RANK() OVER (ORDER BY SUM(CASE WHEN c.churn_flag = 1 THEN b.monthly_charges ELSE 0 END) DESC) AS revenue_rank
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id
JOIN services s ON s.customer_id = c.customer_id
GROUP BY b.contract, s.internet_service
ORDER BY revenue_rank
LIMIT 6;


-- Q12. A simple rule-based high-risk profile (the baseline a model must beat) 
WITH flagged AS (
    SELECT c.churn_flag,
           CASE WHEN b.contract = 'Month-to-month'
                 AND s.internet_service = 'Fiber optic'
                 AND b.payment_method = 'Electronic check'
                 AND c.tenure_months <= 12
                THEN 'High-risk profile' ELSE 'Everyone else' END AS grp
    FROM customers c
    JOIN billing b ON b.customer_id = c.customer_id
    JOIN services s ON s.customer_id = c.customer_id
)
SELECT grp,
       COUNT(*)                                                  AS customers,
       SUM(churn_flag)                                           AS churned,
       ROUND(100.0 * SUM(churn_flag) / COUNT(*), 1)              AS churn_rate_pct,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)        AS pct_of_customers,
       ROUND(100.0 * SUM(churn_flag) / SUM(SUM(churn_flag)) OVER (), 1) AS pct_of_all_churners
FROM flagged
GROUP BY grp
ORDER BY churn_rate_pct DESC;


-- Q13. Churn by exact tenure month, with a 3-month moving average
WITH by_month AS (
    SELECT tenure_months,
           COUNT(*)                                       AS customers,
           100.0 * SUM(churn_flag) / COUNT(*)             AS rate
    FROM customers
    WHERE tenure_months <= 24
    GROUP BY tenure_months
)
SELECT tenure_months,
       customers,
       ROUND(rate, 1) AS churn_rate_pct,
       ROUND(AVG(rate) OVER (ORDER BY tenure_months ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS moving_avg_3m_pct
FROM by_month
ORDER BY tenure_months;


-- Q14. Support services inside ONE comparable group (month-to-month, fiber optic) 

SELECT s.tech_support,
       s.online_security,
       COUNT(*)                                       AS customers,
       ROUND(100.0 * SUM(c.churn_flag) / COUNT(*), 1) AS churn_rate_pct
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id
JOIN services s ON s.customer_id = c.customer_id
WHERE b.contract = 'Month-to-month' AND s.internet_service = 'Fiber optic'
GROUP BY s.tech_support, s.online_security
ORDER BY churn_rate_pct DESC;


-- Q15. Protected attributes: why gender and age are NOT used to target offers 
SELECT c.gender,
       c.senior_citizen,
       COUNT(*)                                       AS customers,
       ROUND(100.0 * SUM(c.churn_flag) / COUNT(*), 1) AS churn_rate_pct
FROM customers c
GROUP BY c.gender, c.senior_citizen
ORDER BY c.gender, c.senior_citizen;
