import pandas as pd
from churn_pipeline.generate import generate_data


def test_reproducible_synthetic_data_generation(tmp_path):
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    generate_data(dir_a, seed=42, customer_count=50)
    generate_data(dir_b, seed=42, customer_count=50)

    cust_a = pd.read_csv(dir_a / "customers.csv")
    cust_b = pd.read_csv(dir_b / "customers.csv")
    pd.testing.assert_frame_equal(cust_a, cust_b)

    subs_a = pd.read_csv(dir_a / "subscriptions.csv")
    subs_b = pd.read_csv(dir_b / "subscriptions.csv")
    pd.testing.assert_frame_equal(subs_a, subs_b)

    events_a = pd.read_csv(dir_a / "payment_events.csv")
    events_b = pd.read_csv(dir_b / "payment_events.csv")
    pd.testing.assert_frame_equal(events_a, events_b)


def test_different_seeds_produce_different_data(tmp_path):
    dir_a = tmp_path / "run_1"
    dir_b = tmp_path / "run_2"

    generate_data(dir_a, seed=10, customer_count=50)
    generate_data(dir_b, seed=99, customer_count=50)

    cust_a = pd.read_csv(dir_a / "customers.csv")
    cust_b = pd.read_csv(dir_b / "customers.csv")
    assert not cust_a.equals(cust_b)


def test_generated_schema_and_integrity(tmp_path):
    out_dir = tmp_path / "schema_test"
    generate_data(out_dir, seed=77, customer_count=100)

    cust = pd.read_csv(out_dir / "customers.csv")
    subs = pd.read_csv(out_dir / "subscriptions.csv")
    events = pd.read_csv(out_dir / "payment_events.csv")

    assert len(cust) == 100
    assert len(subs) == 100
    assert len(events) == 100

    # Ensure no duplicate IDs
    assert not cust["customer_id"].duplicated().any()
    assert not subs["subscription_id"].duplicated().any()
    assert not events["payment_event_id"].duplicated().any()

    # Verify foreign keys
    assert set(subs["customer_id"]).issubset(set(cust["customer_id"]))
    assert set(events["subscription_id"]).issubset(set(subs["subscription_id"]))

    # Verify date relationships
    s_dates = pd.to_datetime(subs["start_date"])
    e_dates = pd.to_datetime(subs["end_date"])
    valid_dates = e_dates.isna() | (e_dates >= s_dates)
    assert valid_dates.all()

    # Verify status alignment
    churned_subs = subs[subs["subscription_status"] == "churned"]
    active_subs = subs[subs["subscription_status"] == "active"]
    assert churned_subs["end_date"].notna().all()
    assert active_subs["end_date"].isna().all()

    # Verify contract_type and payment_method are present and non-empty
    assert "contract_type" in subs.columns
    assert "payment_method" in subs.columns
    assert subs["contract_type"].notna().all()
    assert subs["payment_method"].notna().all()
