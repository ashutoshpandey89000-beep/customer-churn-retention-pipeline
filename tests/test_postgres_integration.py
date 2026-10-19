import pytest
import pandas as pd
from sqlalchemy import create_engine, text
from churn_pipeline.config import database_url
from churn_pipeline.generate import generate_data
from churn_pipeline.load import run_pipeline, TABLE_DDL, VIEW_DDL
from churn_pipeline.transform import load_and_validate, build_curated_data, generate_data_quality_report


@pytest.fixture(scope="module")
def db_engine():
    """Attempt connecting to PostgreSQL. Skip if database is unavailable."""
    url = database_url()
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        yield engine
        engine.dispose()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not accessible at {url}: {exc}")


def test_database_connection(db_engine):
    with db_engine.connect() as conn:
        res = conn.execute(text("SELECT current_database(), current_user")).fetchone()
        assert res[0] == "churn_analytics"
        assert res[1] == "churn_user"


def test_idempotent_loading_and_row_counts(db_engine, tmp_path):
    raw_dir = tmp_path / "raw"
    curated_dir = tmp_path / "curated"
    generate_data(raw_dir, seed=77, customer_count=50)

    # First run
    run1 = run_pipeline(raw_dir, curated_dir=curated_dir, engine=db_engine)
    assert run1["customers.csv"] == 50
    assert run1["curated_customer_retention.csv"] == 50

    with db_engine.connect() as conn:
        count1 = conn.execute(text("SELECT COUNT(*) FROM churn_customers")).scalar()
        assert count1 == 50

    # Second run with same data must NOT create duplicates (idempotency check)
    run2 = run_pipeline(raw_dir, curated_dir=curated_dir, engine=db_engine)
    assert run2["customers.csv"] == 50

    with db_engine.connect() as conn:
        count2 = conn.execute(text("SELECT COUNT(*) FROM churn_customers")).scalar()
        assert count2 == 50, "Repeated pipeline run must not create duplicate records"


def test_sql_analytics_views_and_kpis(db_engine, tmp_path):
    raw_dir = tmp_path / "raw"
    curated_dir = tmp_path / "curated"
    generate_data(raw_dir, seed=77, customer_count=100)
    run_pipeline(raw_dir, curated_dir=curated_dir, engine=db_engine)

    with db_engine.connect() as conn:
        # 1. KPI Summary
        kpi = conn.execute(text("SELECT * FROM analytics.kpi_summary")).mappings().first()
        assert kpi is not None
        assert kpi["total_customers"] == 100
        assert kpi["churned_customers"] + kpi["retained_customers"] == 100
        assert 0.0 <= float(kpi["overall_churn_rate_pct"]) <= 100.0
        assert 0.0 <= float(kpi["overall_retention_rate_pct"]) <= 100.0
        assert float(kpi["active_mrr"]) > 0
        assert float(kpi["total_revenue_collected"]) > 0

        # 2. Plan Performance
        plans = conn.execute(text("SELECT * FROM analytics.plan_performance")).mappings().all()
        assert len(plans) == 4
        for p in plans:
            assert p["subscribers"] == p["churned_subscribers"] + p["active_subscribers"]
            assert float(p["churn_rate_pct"]) >= 0

        # 3. Contract Performance
        contracts = conn.execute(text("SELECT * FROM analytics.contract_performance")).mappings().all()
        assert len(contracts) >= 1
        for c in contracts:
            assert c["subscribers"] == c["churned_subscribers"] + c["active_subscribers"]

        # 4. Payment Method Performance
        methods = conn.execute(text("SELECT * FROM analytics.payment_method_performance")).mappings().all()
        assert len(methods) >= 1

        # 5. Tenure Cohorts
        tenure_rows = conn.execute(text("SELECT * FROM analytics.tenure_cohorts")).mappings().all()
        assert len(tenure_rows) >= 1

        # 6. Monthly Churn
        monthly = conn.execute(text("SELECT * FROM analytics.monthly_churn")).mappings().all()
        assert len(monthly) > 0
        for m in monthly:
            assert m["eligible_customers"] >= m["churned_customers"]


def test_transaction_rollback_on_failure(db_engine, tmp_path):
    """Verify that if an error occurs during loading, transactions roll back cleanly."""
    raw_dir = tmp_path / "raw"
    curated_dir = tmp_path / "curated"
    generate_data(raw_dir, seed=77, customer_count=30)
    run_pipeline(raw_dir, curated_dir=curated_dir, engine=db_engine)

    # Initial count
    with db_engine.connect() as conn:
        initial_count = conn.execute(text("SELECT COUNT(*) FROM churn_customers")).scalar()
        assert initial_count == 30

    # Attempt a faulty pipeline run where an invalid SQL statement is injected
    try:
        with db_engine.begin() as conn:
            conn.execute(text("INSERT INTO churn_customers VALUES (999, 'Test', 'City', '2024-01-01', 'organic')"))
            # Trigger deliberate database error (e.g. division by zero or invalid syntax)
            conn.execute(text("SELECT 1/0"))
    except Exception:
        pass  # Expected error

    # Verify that the uncommitted row (999) was rolled back
    with db_engine.connect() as conn:
        customer_999 = conn.execute(text("SELECT * FROM churn_customers WHERE customer_id = 999")).first()
        assert customer_999 is None, "Failed transaction was not properly rolled back"
