import pandas as pd
from datetime import date
from churn_pipeline.generate import generate_data
from churn_pipeline.transform import load_and_validate, build_curated_data, generate_data_quality_report


def test_curated_data_features_and_tenure(tmp_path):
    raw_dir = tmp_path / "raw"
    generate_data(raw_dir, seed=77, customer_count=200)

    frames = load_and_validate(raw_dir)
    curated = build_curated_data(frames, cutoff_date=date(2025, 12, 31))

    assert len(curated) == 200
    assert "tenure_days" in curated.columns
    assert "tenure_months" in curated.columns
    assert "tenure_group" in curated.columns
    assert "is_churned" in curated.columns
    assert "is_retained" in curated.columns
    assert "monthly_recurring_revenue" in curated.columns
    assert "total_revenue" in curated.columns

    # Verify tenure calculations are non-negative
    assert (curated["tenure_days"] >= 0).all()
    assert (curated["tenure_months"] >= 0.0).all()

    # Verify tenure group values
    valid_groups = {"0-6 Months", "6-12 Months", "12-24 Months", "24+ Months"}
    assert set(curated["tenure_group"].unique()).issubset(valid_groups)

    # Verify binary flags
    assert set(curated["is_churned"].unique()).issubset({0, 1})
    assert set(curated["is_retained"].unique()).issubset({0, 1})
    assert (curated["is_churned"] + curated["is_retained"] == 1).all()


def test_reconciliation_and_kpi_mathematics(tmp_path):
    raw_dir = tmp_path / "raw"
    curated_dir = tmp_path / "curated"
    generate_data(raw_dir, seed=77, customer_count=100)

    frames = load_and_validate(raw_dir)
    curated = build_curated_data(frames, cutoff_date=date(2025, 12, 31))
    report = generate_data_quality_report(frames, curated, output_dir=curated_dir)

    # 1. Total population reconciliation
    total = report["business_kpis"]["total_customers"]
    churned = report["business_kpis"]["churned_customers"]
    retained = report["business_kpis"]["retained_customers"]
    assert total == 100
    assert churned + retained == total
    assert report["reconciliation"]["reconciliation_match"] is True

    # 2. Churn rate and retention rate sum to 100%
    churn_rate = report["business_kpis"]["overall_churn_rate_pct"]
    retention_rate = report["business_kpis"]["overall_retention_rate_pct"]
    assert round(churn_rate + retention_rate, 1) == 100.0

    # 3. Report files are generated
    assert (curated_dir / "data_quality_report.json").exists()
    assert (curated_dir / "data_quality_report.md").exists()
