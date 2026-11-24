
CREATE DATABASE IF NOT EXISTS telco_churn CHARACTER SET utf8mb4;
USE telco_churn;

-- Child tables first, so foreign keys never block a drop
DROP TABLE IF EXISTS billing;
DROP TABLE IF EXISTS services;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id        VARCHAR(12) NOT NULL,
    gender             VARCHAR(6)  NOT NULL,
    senior_citizen     VARCHAR(3)  NOT NULL,
    partner            VARCHAR(3)  NOT NULL,
    dependents         VARCHAR(3)  NOT NULL,
    tenure_months      SMALLINT    NOT NULL,
    tenure_band        VARCHAR(6)  NOT NULL,   
    tenure_band_order  SMALLINT    NOT NULL,   
    is_new_unbilled    VARCHAR(3)  NOT NULL,   
    churn              VARCHAR(3)  NOT NULL,   
    churn_flag         SMALLINT    NOT NULL,   
    PRIMARY KEY (customer_id)
);

CREATE TABLE services (
    customer_id        VARCHAR(12) NOT NULL,
    phone_service      VARCHAR(3)  NOT NULL,
    multiple_lines     VARCHAR(3)  NOT NULL,
    internet_service   VARCHAR(11) NOT NULL,   -- DSL / Fiber optic / No internet
    online_security    VARCHAR(3)  NOT NULL,
    online_backup      VARCHAR(3)  NOT NULL,
    device_protection  VARCHAR(3)  NOT NULL,
    tech_support       VARCHAR(3)  NOT NULL,
    streaming_tv       VARCHAR(3)  NOT NULL,
    streaming_movies   VARCHAR(3)  NOT NULL,
    num_addons         SMALLINT    NOT NULL,   -- 0 to 6 optional services
    PRIMARY KEY (customer_id),
    CONSTRAINT fk_services_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE billing (
    customer_id        VARCHAR(12)   NOT NULL,
    contract           VARCHAR(14)   NOT NULL, -- Month-to-month / One year / Two year
    paperless_billing  VARCHAR(3)    NOT NULL,
    payment_method     VARCHAR(25)   NOT NULL,
    autopay            VARCHAR(3)    NOT NULL,
    monthly_charges    DECIMAL(8,2)  NOT NULL, -- currency not stated in the source file
    total_charges      DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (customer_id),
    INDEX ix_billing_contract (contract),
    CONSTRAINT fk_billing_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
