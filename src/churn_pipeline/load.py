"""PostgreSQL schema management, idempotent data loading, and analytics view publication."""

from pathlib import Path
from sqlalchemy import create_engine, text
from .config import database_url
from .transform import load_and_validate, build_curated_data, generate_data_quality_report

TABLE_DDL = [
    "CREATE SCHEMA IF NOT EXISTS analytics",
    """CREATE TABLE IF NOT EXISTS churn_customers (
        customer_id INTEGER PRIMARY KEY,
        customer_name TEXT NOT NULL,
        city TEXT NOT NULL,
        signup_date DATE NOT NULL,
        acquisition_channel TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS churn_subscriptions (
        subscription_id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL REFERENCES churn_customers(customer_id),
        plan_name TEXT NOT NULL,
        contract_type TEXT NOT NULL DEFAULT 'Month-to-Month',
        payment_method TEXT NOT NULL DEFAULT 'Credit Card',
        monthly_price NUMERIC(10,2) NOT NULL CHECK (monthly_price >= 0),
        start_date DATE NOT NULL,
        end_date DATE NULL CHECK (end_date IS NULL OR end_date >= start_date),
        subscription_status TEXT NOT NULL CHECK (subscription_status IN ('active', 'churned'))
    )""",
    """CREATE TABLE IF NOT EXISTS churn_payment_events (
        payment_event_id INTEGER PRIMARY KEY,
        subscription_id INTEGER NOT NULL REFERENCES churn_subscriptions(subscription_id),
        event_date DATE NOT NULL,
        payment_status TEXT NOT NULL CHECK (payment_status IN ('paid', 'failed', 'refunded')),
        amount NUMERIC(10,2) NOT NULL CHECK (amount >= 0)
    )""",
    """CREATE TABLE IF NOT EXISTS curated_customer_retention (
        customer_id INTEGER PRIMARY KEY REFERENCES churn_customers(customer_id),
        customer_name TEXT NOT NULL,
        city TEXT NOT NULL,
        acquisition_channel TEXT NOT NULL,
        subscription_id INTEGER NOT NULL REFERENCES churn_subscriptions(subscription_id),
        plan_name TEXT NOT NULL,
        contract_type TEXT NOT NULL,
        payment_method TEXT NOT NULL,
        monthly_price NUMERIC(10,2) NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NULL,
        subscription_status TEXT NOT NULL,
        tenure_days INTEGER NOT NULL,
        tenure_months NUMERIC(6,1) NOT NULL,
        tenure_group TEXT NOT NULL,
        is_churned INTEGER NOT NULL,
        is_retained INTEGER NOT NULL,
        monthly_recurring_revenue NUMERIC(10,2) NOT NULL,
        total_revenue NUMERIC(10,2) NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_subs_customer_id ON churn_subscriptions(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_subs_status ON churn_subscriptions(subscription_status)",
    "CREATE INDEX IF NOT EXISTS idx_payments_sub_id ON churn_payment_events(subscription_id)",
    "CREATE INDEX IF NOT EXISTS idx_curated_tenure_grp ON curated_customer_retention(tenure_group)",
]

VIEW_DDL = [
    """CREATE OR REPLACE VIEW analytics.kpi_summary AS
    SELECT
        COUNT(*) AS total_customers,
        COUNT(*) FILTER (WHERE subscription_status = 'churned') AS churned_customers,
        COUNT(*) FILTER (WHERE subscription_status = 'active') AS retained_customers,
        ROUND(100.0 * COUNT(*) FILTER (WHERE subscription_status = 'churned') / NULLIF(COUNT(*), 0), 2) AS overall_churn_rate_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE subscription_status = 'active') / NULLIF(COUNT(*), 0), 2) AS overall_retention_rate_pct,
        ROUND(AVG(tenure_months), 1) AS average_tenure_months,
        ROUND(SUM(monthly_price) FILTER (WHERE subscription_status = 'active'), 2) AS active_mrr,
        ROUND(SUM(monthly_price) FILTER (WHERE subscription_status = 'churned'), 2) AS churned_mrr,
        ROUND(SUM(monthly_price), 2) AS total_mrr,
        ROUND(SUM(total_revenue), 2) AS total_revenue_collected
    FROM curated_customer_retention""",

    """CREATE OR REPLACE VIEW analytics.monthly_churn AS
    WITH months AS (
        SELECT generate_series(
            date_trunc('month', MIN(start_date)),
            date_trunc('month', MAX(COALESCE(end_date, start_date))),
            interval '1 month'
        )::date AS month_start
        FROM churn_subscriptions
    ),
    monthly_metrics AS (
        SELECT
            m.month_start AS month,
            (m.month_start + interval '1 month' - interval '1 day')::date AS month_end,
            COUNT(s.subscription_id) FILTER (
                WHERE s.start_date <= (m.month_start + interval '1 month' - interval '1 day')::date
                  AND (s.end_date IS NULL OR s.end_date >= m.month_start)
            ) AS eligible_customers,
            COUNT(s.subscription_id) FILTER (
                WHERE s.subscription_status = 'churned'
                  AND s.end_date >= m.month_start
                  AND s.end_date <= (m.month_start + interval '1 month' - interval '1 day')::date
            ) AS churned_customers,
            COUNT(s.subscription_id) FILTER (
                WHERE s.start_date <= (m.month_start + interval '1 month' - interval '1 day')::date
                  AND (s.end_date IS NULL OR s.end_date > (m.month_start + interval '1 month' - interval '1 day')::date)
            ) AS active_customers
        FROM months m
        CROSS JOIN churn_subscriptions s
        GROUP BY m.month_start
    )
    SELECT
        month,
        eligible_customers,
        churned_customers,
        active_customers,
        ROUND(100.0 * churned_customers / NULLIF(eligible_customers, 0), 2) AS churn_rate_pct,
        ROUND(100.0 * active_customers / NULLIF(eligible_customers, 0), 2) AS retention_rate_pct
    FROM monthly_metrics
    ORDER BY month""",

    """CREATE OR REPLACE VIEW analytics.plan_performance AS
    SELECT
        plan_name,
        COUNT(*) AS subscribers,
        COUNT(*) FILTER (WHERE subscription_status='churned') AS churned_subscribers,
        COUNT(*) FILTER (WHERE subscription_status='active') AS active_subscribers,
        ROUND(100.0 * COUNT(*) FILTER (WHERE subscription_status='churned') / NULLIF(COUNT(*),0), 2) AS churn_rate_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE subscription_status='active') / NULLIF(COUNT(*),0), 2) AS retention_rate_pct,
        ROUND(SUM(monthly_price) FILTER (WHERE subscription_status='active'), 2) AS monthly_revenue,
        ROUND(AVG(monthly_price), 2) AS avg_monthly_price
    FROM churn_subscriptions
    GROUP BY plan_name""",

    """CREATE OR REPLACE VIEW analytics.contract_performance AS
    SELECT
        contract_type,
        COUNT(*) AS subscribers,
        COUNT(*) FILTER (WHERE subscription_status='churned') AS churned_subscribers,
        COUNT(*) FILTER (WHERE subscription_status='active') AS active_subscribers,
        ROUND(100.0 * COUNT(*) FILTER (WHERE subscription_status='churned') / NULLIF(COUNT(*),0), 2) AS churn_rate_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE subscription_status='active') / NULLIF(COUNT(*),0), 2) AS retention_rate_pct,
        ROUND(SUM(monthly_price) FILTER (WHERE subscription_status='active'), 2) AS monthly_revenue
    FROM churn_subscriptions
    GROUP BY contract_type""",

    """CREATE OR REPLACE VIEW analytics.payment_method_performance AS
    SELECT
        payment_method,
        COUNT(*) AS subscribers,
        COUNT(*) FILTER (WHERE subscription_status='churned') AS churned_subscribers,
        COUNT(*) FILTER (WHERE subscription_status='active') AS active_subscribers,
        ROUND(100.0 * COUNT(*) FILTER (WHERE subscription_status='churned') / NULLIF(COUNT(*),0), 2) AS churn_rate_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE subscription_status='active') / NULLIF(COUNT(*),0), 2) AS retention_rate_pct,
        ROUND(SUM(monthly_price) FILTER (WHERE subscription_status='active'), 2) AS active_mrr
    FROM churn_subscriptions
    GROUP BY payment_method""",

    """CREATE OR REPLACE VIEW analytics.tenure_cohorts AS
    SELECT
        tenure_group,
        COUNT(*) AS subscribers,
        COUNT(*) FILTER (WHERE is_churned = 1) AS churned_subscribers,
        COUNT(*) FILTER (WHERE is_retained = 1) AS active_subscribers,
        ROUND(100.0 * COUNT(*) FILTER (WHERE is_churned = 1) / NULLIF(COUNT(*), 0), 2) AS churn_rate_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE is_retained = 1) / NULLIF(COUNT(*), 0), 2) AS retention_rate_pct,
        ROUND(AVG(tenure_months), 1) AS avg_tenure_months,
        ROUND(SUM(monthly_price) FILTER (WHERE is_churned = 1), 2) AS mrr_lost_to_churn,
        ROUND(SUM(monthly_recurring_revenue), 2) AS active_mrr
    FROM curated_customer_retention
    GROUP BY tenure_group""",

    """CREATE OR REPLACE VIEW analytics.customer_cohorts AS
    SELECT
        date_trunc('month', c.signup_date)::date AS signup_month,
        COUNT(*) AS customers,
        COUNT(*) FILTER (WHERE s.subscription_status='churned') AS churned_customers,
        COUNT(*) FILTER (WHERE s.subscription_status='active') AS retained_customers,
        ROUND(100.0 * COUNT(*) FILTER (WHERE s.subscription_status='churned') / NULLIF(COUNT(*),0), 2) AS cohort_churn_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE s.subscription_status='active') / NULLIF(COUNT(*),0), 2) AS cohort_retention_pct
    FROM churn_customers c
    JOIN churn_subscriptions s ON s.customer_id=c.customer_id
    GROUP BY 1""",

    """CREATE OR REPLACE VIEW analytics.payment_status_summary AS
    SELECT
        payment_status,
        COUNT(*) AS event_count,
        ROUND(SUM(amount), 2) AS total_amount,
        ROUND(AVG(amount), 2) AS avg_amount
    FROM churn_payment_events
    GROUP BY payment_status""",

    """CREATE OR REPLACE VIEW analytics.revenue_by_status AS
    SELECT
        subscription_status,
        COUNT(*) AS customer_count,
        ROUND(SUM(monthly_price), 2) AS total_recurring_revenue,
        ROUND(AVG(monthly_price), 2) AS avg_monthly_price,
        ROUND(SUM(total_revenue), 2) AS total_revenue_collected
    FROM curated_customer_retention
    GROUP BY subscription_status""",
]

TABLE_ORDER = [
    ("customers.csv", "churn_customers"),
    ("subscriptions.csv", "churn_subscriptions"),
    ("payment_events.csv", "churn_payment_events"),
]


def run_pipeline(raw_dir, curated_dir="data/curated", engine=None):
    """Execute the complete validation, feature engineering, and PostgreSQL loading pipeline.

    Parameters:
        raw_dir (str or Path): Directory with raw CSV files.
        curated_dir (str or Path): Directory where curated dataset and report will be saved.
        engine (SQLAlchemy Engine, optional): Custom engine for test isolation.

    Returns:
        dict: Mapping of loaded table names to loaded row counts.
    """
    frames = load_and_validate(raw_dir)
    curated_df = build_curated_data(frames)

    # Persist curated dataset and data quality audit report
    curated_path = Path(curated_dir)
    curated_path.mkdir(parents=True, exist_ok=True)
    curated_df.to_csv(curated_path / "curated_customer_retention.csv", index=False)
    generate_data_quality_report(frames, curated_df, output_dir=curated_dir)

    owns_engine = engine is None
    engine = engine or create_engine(database_url(), pool_pre_ping=True)

    try:
        with engine.begin() as conn:
            # 1. Ensure schema and tables exist
            for stmt in TABLE_DDL:
                conn.execute(text(stmt))

            # 2. Idempotent cleanup: truncate in reverse foreign-key order
            conn.execute(
                text("TRUNCATE churn_payment_events, curated_customer_retention, churn_subscriptions, churn_customers CASCADE")
            )

            # 3. Parameterized bulk insert for raw tables
            for filename, table in TABLE_ORDER:
                frames[filename].to_sql(
                    table,
                    conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=1000,
                )

            # 4. Insert curated features table
            curated_df.to_sql(
                "curated_customer_retention",
                conn,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )

            # 5. Create or replace analytical views
            for stmt in VIEW_DDL:
                conn.execute(text(stmt))

        result = {name: len(frame) for name, frame in frames.items()}
        result["curated_customer_retention.csv"] = len(curated_df)
        return result
    finally:
        if owns_engine:
            engine.dispose()
