
USE telco_churn;

LOAD DATA LOCAL INFILE 'C:/path/to/churn-analysis-project/data/cleaned/customers.csv'
INTO TABLE customers
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES;

LOAD DATA LOCAL INFILE 'C:/path/to/churn-analysis-project/data/cleaned/services.csv'
INTO TABLE services
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES;

LOAD DATA LOCAL INFILE 'C:/path/to/churn-analysis-project/data/cleaned/billing.csv'
INTO TABLE billing
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES;



-- VERIFYING
SELECT COUNT(*)             AS customers,        
       SUM(c.churn_flag)    AS churned,          
       SUM(b.monthly_charges) AS monthly_charges, 
       SUM(b.total_charges)   AS total_charges    
FROM customers c
JOIN billing b ON b.customer_id = c.customer_id;
SHOW WARNINGS;   -- should be empty
