"""Apache Airflow DAG orchestrating customer churn data generation, ETL curation, PostgreSQL loading, and KPI verification."""

from datetime import datetime
import sys
import json
from pathlib import Path
from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT = "/opt/airflow/project"
if f"{PROJECT}/src" not in sys.path:
    sys.path.insert(0, f"{PROJECT}/src")

from churn_pipeline.generate import generate_data
from churn_pipeline.transform import load_and_validate, build_curated_data, generate_data_quality_report
from churn_pipeline.load import run_pipeline
from churn_pipeline.config import database_url
from sqlalchemy import create_engine, text

RAW_DIR = f"{PROJECT}/data/raw"
CURATED_DIR = f"{PROJECT}/data/curated"


def task_generate():
    """Generate reproducible synthetic customer subscription records."""
    paths = generate_data(RAW_DIR, seed=77, customer_count=1000)
    print(f"Generated synthetic data files: {paths}")


def task_validate_and_transform():
    """Validate data quality, compute retention features, and publish audit report."""
    frames = load_and_validate(RAW_DIR)
    curated_df = build_curated_data(frames)
    curated_path = Path(CURATED_DIR)
    curated_path.mkdir(parents=True, exist_ok=True)
    curated_df.to_csv(curated_path / "curated_customer_retention.csv", index=False)
    report = generate_data_quality_report(frames, curated_df, output_dir=CURATED_DIR)
    print(f"Data Quality Validation Status: {report['status']}")
    print(f"Audit Summary:\n{json.dumps(report['business_kpis'], indent=2)}")


def task_load_postgres():
    """Load tables transactionally into PostgreSQL and publish analytical views."""
    counts = run_pipeline(RAW_DIR, curated_dir=CURATED_DIR)
    print(f"Successfully loaded tables into PostgreSQL: {counts}")


def task_verify_kpis():
    """Execute SQL analytics check against PostgreSQL to verify calculated KPIs."""
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM analytics.kpi_summary")).mappings().first()
            if not result:
                raise ValueError("KPI summary view returned no records!")
            print("Verified PostgreSQL Analytics KPIs:")
            for k, v in result.items():
                print(f"  {k}: {v}")

            # Verification assertion
            total = result["total_customers"]
            churned = result["churned_customers"]
            retained = result["retained_customers"]
            if churned + retained != total:
                raise ValueError(f"Reconciliation error: {churned} + {retained} != {total}")
            print("Reconciliation check PASSED: churned + retained == total")
    finally:
        engine.dispose()


default_args = {
    "owner": "data_engineering",
    "depends_on_past": False,
    "email_on_failure": False,
}

with DAG(
    dag_id="customer_churn_retention_pipeline",
    description="End-to-end customer churn data generation, ETL curation, PostgreSQL loading, and KPI verification",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["portfolio", "churn", "retention", "etl", "postgres"],
) as dag:

    gen = PythonOperator(
        task_id="generate_synthetic_data",
        python_callable=task_generate,
    )

    transform = PythonOperator(
        task_id="validate_and_transform",
        python_callable=task_validate_and_transform,
    )

    load = PythonOperator(
        task_id="load_to_postgres",
        python_callable=task_load_postgres,
    )

    verify = PythonOperator(
        task_id="verify_analytics_kpis",
        python_callable=task_verify_kpis,
    )

    gen >> transform >> load >> verify
