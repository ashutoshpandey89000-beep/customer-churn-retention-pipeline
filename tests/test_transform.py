import pytest
import pandas as pd
from churn_pipeline.transform import validate_frame, load_and_validate


def test_valid_customer_data_passes():
    frame = pd.DataFrame({
        "customer_id": [1],
        "customer_name": ["A"],
        "city": ["Pune"],
        "signup_date": ["2024-01-01"],
        "acquisition_channel": ["organic"],
    })
    assert validate_frame("customers.csv", frame) == []


def test_duplicate_customer_id_fails():
    frame = pd.DataFrame({
        "customer_id": [1, 1],
        "customer_name": ["A", "B"],
        "city": ["Pune", "Delhi"],
        "signup_date": ["2024-01-01", "2024-01-02"],
        "acquisition_channel": ["organic", "referral"],
    })
    assert any("duplicate customer_id" in e for e in validate_frame("customers.csv", frame))


def test_missing_subscription_columns_fail():
    assert "missing columns" in validate_frame("subscriptions.csv", pd.DataFrame({"subscription_id": [1]}))[0]


def test_negative_monthly_price_fails():
    frame = pd.DataFrame({
        "subscription_id": [1],
        "customer_id": [1],
        "plan_name": ["Basic"],
        "monthly_price": [-2],
        "start_date": ["2024-01-01"],
        "end_date": [None],
        "subscription_status": ["active"],
    })
    assert any("negative" in e for e in validate_frame("subscriptions.csv", frame))


def test_null_customer_id_fails():
    frame = pd.DataFrame({
        "customer_id": [None],
        "customer_name": ["Missing ID"],
        "city": ["Pune"],
        "signup_date": ["2024-01-01"],
        "acquisition_channel": ["organic"],
    })
    errors = validate_frame("customers.csv", frame)
    assert any("null customer_id" in e for e in errors)


def test_negative_payment_amount_fails():
    frame = pd.DataFrame({
        "payment_event_id": [1],
        "subscription_id": [1],
        "event_date": ["2024-05-01"],
        "payment_status": ["paid"],
        "amount": [-15.50],
    })
    errors = validate_frame("payment_events.csv", frame)
    assert any("negative amount" in e for e in errors)


def test_end_date_before_start_date_fails():
    frame = pd.DataFrame({
        "subscription_id": [1],
        "customer_id": [1],
        "plan_name": ["Standard"],
        "monthly_price": [19.99],
        "start_date": ["2024-06-01"],
        "end_date": ["2024-01-01"],
        "subscription_status": ["churned"],
    })
    errors = validate_frame("subscriptions.csv", frame)
    assert any("end_date precedes start_date" in e for e in errors)


def test_churned_without_end_date_fails():
    frame = pd.DataFrame({
        "subscription_id": [1],
        "customer_id": [1],
        "plan_name": ["Standard"],
        "monthly_price": [19.99],
        "start_date": ["2024-01-01"],
        "end_date": [None],
        "subscription_status": ["churned"],
    })
    errors = validate_frame("subscriptions.csv", frame)
    assert any("churned status without end_date" in e for e in errors)


def test_invalid_subscription_status_fails():
    frame = pd.DataFrame({
        "subscription_id": [1],
        "customer_id": [1],
        "plan_name": ["Standard"],
        "monthly_price": [19.99],
        "start_date": ["2024-01-01"],
        "end_date": [None],
        "subscription_status": ["pending_review"],
    })
    errors = validate_frame("subscriptions.csv", frame)
    assert any("invalid subscription_status" in e for e in errors)


def test_invalid_payment_status_fails():
    frame = pd.DataFrame({
        "payment_event_id": [1],
        "subscription_id": [1],
        "event_date": ["2024-05-01"],
        "payment_status": ["chargeback_dispute"],
        "amount": [19.99],
    })
    errors = validate_frame("payment_events.csv", frame)
    assert any("invalid payment_status" in e for e in errors)


def test_load_and_validate_missing_file_raises_value_error(tmp_path):
    # Empty directory missing required CSVs
    with pytest.raises(ValueError, match="Missing input file"):
        load_and_validate(tmp_path)


def test_referential_integrity_unknown_customer_raises_value_error(tmp_path):
    pd.DataFrame({
        "customer_id": [1],
        "customer_name": ["Alice"],
        "city": ["Mumbai"],
        "signup_date": ["2024-01-01"],
        "acquisition_channel": ["organic"],
    }).to_csv(tmp_path / "customers.csv", index=False)

    pd.DataFrame({
        "subscription_id": [1],
        "customer_id": [999],  # Unknown customer
        "plan_name": ["Basic"],
        "monthly_price": [9.99],
        "start_date": ["2024-01-01"],
        "end_date": [None],
        "subscription_status": ["active"],
    }).to_csv(tmp_path / "subscriptions.csv", index=False)

    pd.DataFrame({
        "payment_event_id": [1],
        "subscription_id": [1],
        "event_date": ["2024-01-01"],
        "payment_status": ["paid"],
        "amount": [9.99],
    }).to_csv(tmp_path / "payment_events.csv", index=False)

    with pytest.raises(ValueError, match="unknown customer_id"):
        load_and_validate(tmp_path)
