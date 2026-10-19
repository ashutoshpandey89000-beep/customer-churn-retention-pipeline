# Architecture

1. Generate synthetic customer, subscription and payment-event CSV files.
2. Validate required columns, unique/non-null IDs, numeric ranges and relationships between entities.
3. Parse date columns and standardize values.
4. Load relational tables into PostgreSQL transactionally.
5. Create SQL views for monthly churn, subscription plan performance, signup cohorts and payment status.
6. Use Apache Airflow to orchestrate data generation and ETL.
7. Use pytest to test key data-quality validation rules.

The data is synthetic and intended to demonstrate pipeline engineering. It should not be used to make real business or customer decisions.
