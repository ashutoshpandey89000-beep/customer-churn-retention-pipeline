"""Data validation, cleaning, feature engineering, and curation module."""

from pathlib import Path
from datetime import date, datetime, timezone
import json
import pandas as pd

REQUIRED = {
    "customers.csv": {
        "customer_id",
        "customer_name",
        "city",
        "signup_date",
        "acquisition_channel",
    },
    "subscriptions.csv": {
        "subscription_id",
        "customer_id",
        "plan_name",
        "monthly_price",
        "start_date",
        "end_date",
        "subscription_status",
    },
    "payment_events.csv": {
        "payment_event_id",
        "subscription_id",
        "event_date",
        "payment_status",
        "amount",
    },
}

IDS = {
    "customers.csv": "customer_id",
    "subscriptions.csv": "subscription_id",
    "payment_events.csv": "payment_event_id",
}

VALID_STATUSES = {"active", "churned"}
VALID_PAY_STATUSES = {"paid", "failed", "refunded"}


def validate_frame(filename, frame):
    """Validate column requirements, nulls, duplicates, numeric ranges, and basic constraints."""
    missing = REQUIRED[filename] - set(frame.columns)
    if missing:
        return [f"{filename}: missing columns {sorted(missing)}"]

    errors = []
    id_col = IDS[filename]

    if frame[id_col].isna().any():
        errors.append(f"{filename}: null {id_col}")
    if frame[id_col].duplicated().any():
        errors.append(f"{filename}: duplicate {id_col}")

    # Numeric range validations
    for col in (
        {"subscriptions.csv": ["monthly_price"], "payment_events.csv": ["amount"]}.get(
            filename, []
        )
    ):
        vals = pd.to_numeric(frame[col], errors="coerce")
        if vals.isna().any() or (vals < 0).any():
            errors.append(f"{filename}: invalid or negative {col}")

    # Categorical and date checks
    if filename == "subscriptions.csv":
        if not set(frame["subscription_status"].dropna().unique()).issubset(VALID_STATUSES):
            errors.append(
                f"{filename}: invalid subscription_status values found (expected {VALID_STATUSES})"
            )

        # Check date ordering if both start_date and end_date exist
        s_dates = pd.to_datetime(frame["start_date"], errors="coerce")
        e_dates = pd.to_datetime(frame["end_date"], errors="coerce")
        invalid_dates = (e_dates.notna()) & (e_dates < s_dates)
        if invalid_dates.any():
            errors.append(f"{filename}: end_date precedes start_date in {invalid_dates.sum()} rows")

        # Churned subscriptions must have an end_date
        churned_no_end = (frame["subscription_status"] == "churned") & (e_dates.isna())
        if churned_no_end.any():
            errors.append(f"{filename}: churned status without end_date in {churned_no_end.sum()} rows")

    elif filename == "payment_events.csv":
        if not set(frame["payment_status"].dropna().unique()).issubset(VALID_PAY_STATUSES):
            errors.append(
                f"{filename}: invalid payment_status values found (expected {VALID_PAY_STATUSES})"
            )

    return errors


def load_and_validate(raw_dir):
    """Load raw CSV datasets from raw_dir and perform schema and referential integrity validations.

    Returns:
        dict: mapping of filename to parsed pandas.DataFrame.
    Raises:
        ValueError: if any file is missing or validation rule fails.
    """
    raw = Path(raw_dir)
    frames = {}
    errors = []

    for filename in REQUIRED:
        path = raw / filename
        if not path.exists():
            errors.append(f"Missing input file: {path}")
            continue
        frame = pd.read_csv(path)
        errors.extend(validate_frame(filename, frame))
        frames[filename] = frame

    if errors:
        raise ValueError("Data quality checks failed:\n- " + "\n- ".join(errors))

    # Referential integrity checks
    customers = set(frames["customers.csv"]["customer_id"])
    subs = set(frames["subscriptions.csv"]["subscription_id"])

    if not set(frames["subscriptions.csv"]["customer_id"]).issubset(customers):
        raise ValueError("subscriptions.csv contains unknown customer_id")
    if not set(frames["payment_events.csv"]["subscription_id"]).issubset(subs):
        raise ValueError("payment_events.csv contains unknown subscription_id")

    # Standardize date types
    for filename, frame in frames.items():
        for col in frame.columns:
            if col.endswith("_date") or col in {"signup_date", "start_date", "end_date", "event_date"}:
                frame[col] = pd.to_datetime(frame[col], errors="coerce").dt.date

        # Provide sensible defaults for optional columns if missing
        if filename == "subscriptions.csv":
            if "contract_type" not in frame.columns:
                frame["contract_type"] = "Month-to-Month"
            else:
                frame["contract_type"] = frame["contract_type"].fillna("Month-to-Month")

            if "payment_method" not in frame.columns:
                frame["payment_method"] = "Credit Card"
            else:
                frame["payment_method"] = frame["payment_method"].fillna("Credit Card")

    return frames


def build_curated_data(frames, cutoff_date=None):
    """Transform and enrich raw data into a curated customer churn and retention dataset.

    Calculates:
        - tenure_days and tenure_months
        - tenure_group (0-6M, 6-12M, 12-24M, 24M+)
        - is_churned and is_retained flags
        - monthly_recurring_revenue (MRR)
        - total_revenue (aggregate paid amount)

    Returns:
        pandas.DataFrame: Curated customer retention features.
    """
    cust_df = frames["customers.csv"].copy()
    subs_df = frames["subscriptions.csv"].copy()
    events_df = frames["payment_events.csv"].copy()

    if cutoff_date is None:
        # Default analysis cutoff date
        cutoff_date = date(2025, 12, 31)

    # Compute paid amounts per subscription
    paid_events = events_df[events_df["payment_status"] == "paid"]
    paid_summary = (
        paid_events.groupby("subscription_id")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total_revenue"})
    )

    # Merge customer and subscription data
    merged = pd.merge(cust_df, subs_df, on="customer_id", how="inner")
    merged = pd.merge(merged, paid_summary, on="subscription_id", how="left")
    merged["total_revenue"] = merged["total_revenue"].fillna(0.0).round(2)

    # Calculate tenure
    tenure_days_list = []
    for _, row in merged.iterrows():
        s_date = row["start_date"]
        e_date = row["end_date"]
        if pd.notna(e_date):
            td = (e_date - s_date).days
        else:
            td = (cutoff_date - s_date).days
        tenure_days_list.append(max(0, td))

    merged["tenure_days"] = tenure_days_list
    merged["tenure_months"] = (merged["tenure_days"] / 30.4375).round(1)

    def assign_tenure_group(days):
        if days < 183:
            return "0-6 Months"
        elif days < 366:
            return "6-12 Months"
        elif days < 731:
            return "12-24 Months"
        else:
            return "24+ Months"

    merged["tenure_group"] = merged["tenure_days"].apply(assign_tenure_group)
    merged["is_churned"] = (merged["subscription_status"] == "churned").astype(int)
    merged["is_retained"] = (merged["subscription_status"] == "active").astype(int)
    merged["monthly_recurring_revenue"] = merged.apply(
        lambda r: r["monthly_price"] if r["subscription_status"] == "active" else 0.0,
        axis=1,
    )

    columns_order = [
        "customer_id",
        "customer_name",
        "city",
        "acquisition_channel",
        "subscription_id",
        "plan_name",
        "contract_type",
        "payment_method",
        "monthly_price",
        "start_date",
        "end_date",
        "subscription_status",
        "tenure_days",
        "tenure_months",
        "tenure_group",
        "is_churned",
        "is_retained",
        "monthly_recurring_revenue",
        "total_revenue",
    ]
    return merged[columns_order]


def generate_data_quality_report(frames, curated_df, output_dir=None):
    """Generate a formal data-quality and KPI audit report.

    Parameters:
        frames (dict): Raw input DataFrames.
        curated_df (DataFrame): Curated features DataFrame.
        output_dir (str or Path, optional): Directory to save JSON and Markdown reports.

    Returns:
        dict: The complete audit report.
    """
    total_customers = len(curated_df)
    churned_customers = int(curated_df["is_churned"].sum())
    retained_customers = int(curated_df["is_retained"].sum())

    churn_rate = (
        round((churned_customers / total_customers) * 100, 2)
        if total_customers > 0
        else 0.0
    )
    retention_rate = (
        round((retained_customers / total_customers) * 100, 2)
        if total_customers > 0
        else 0.0
    )
    avg_tenure = (
        round(curated_df["tenure_months"].mean(), 1)
        if total_customers > 0
        else 0.0
    )

    active_mrr = float(
        curated_df.loc[curated_df["subscription_status"] == "active", "monthly_price"].sum()
    )
    churned_mrr = float(
        curated_df.loc[curated_df["subscription_status"] == "churned", "monthly_price"].sum()
    )
    total_mrr = active_mrr + churned_mrr
    total_rev_collected = float(curated_df["total_revenue"].sum())

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "PASSED",
        "checks_performed": {
            "required_columns_check": "PASSED",
            "primary_key_uniqueness": "PASSED",
            "null_identifier_check": "PASSED",
            "numeric_ranges_check": "PASSED",
            "date_ordering_check": "PASSED",
            "referential_integrity_check": "PASSED",
            "domain_values_check": "PASSED",
        },
        "records_ingested": {
            "customers": len(frames["customers.csv"]),
            "subscriptions": len(frames["subscriptions.csv"]),
            "payment_events": len(frames["payment_events.csv"]),
            "curated_records": len(curated_df),
        },
        "reconciliation": {
            "eligible_customers": total_customers,
            "churned_plus_retained": churned_customers + retained_customers,
            "reconciliation_match": (churned_customers + retained_customers) == total_customers,
        },
        "business_kpis": {
            "total_customers": total_customers,
            "churned_customers": churned_customers,
            "retained_customers": retained_customers,
            "overall_churn_rate_pct": churn_rate,
            "overall_retention_rate_pct": retention_rate,
            "average_tenure_months": avg_tenure,
            "active_mrr": round(active_mrr, 2),
            "churned_mrr": round(churned_mrr, 2),
            "total_mrr": round(total_mrr, 2),
            "total_revenue_collected": round(total_rev_collected, 2),
        },
    }

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        json_path = out / "data_quality_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        md_path = out / "data_quality_report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Customer Churn Pipeline - Data Quality & KPI Audit Report\n\n")
            f.write(f"- **Generated:** `{report['timestamp']}`\n")
            f.write(f"- **Overall Status:** `{report['status']}`\n\n")
            f.write("## 1. Quality Validations\n\n")
            f.write("| Quality Check | Status |\n| :--- | :--- |\n")
            for check, status in report["checks_performed"].items():
                f.write(f"| {check.replace('_', ' ').title()} | **{status}** |\n")
            f.write("\n## 2. Ingested Records\n\n")
            for entity, count in report["records_ingested"].items():
                f.write(f"- **{entity.replace('_', ' ').title()}:** {count:,}\n")
            f.write("\n## 3. Reconciliation & KPIs\n\n")
            f.write(f"- **Eligible Customers:** {total_customers:,}\n")
            f.write(f"- **Churned Customers:** {churned_customers:,} ({churn_rate}%)\n")
            f.write(f"- **Retained Customers:** {retained_customers:,} ({retention_rate}%)\n")
            f.write(f"- **Reconciliation:** {'MATCH (100%)' if report['reconciliation']['reconciliation_match'] else 'DISCREPANCY'}\n")
            f.write(f"- **Average Customer Tenure:** {avg_tenure} months\n")
            f.write(f"- **Active MRR:** ${active_mrr:,.2f}\n")
            f.write(f"- **Churned MRR (Lost):** ${churned_mrr:,.2f}\n")
            f.write(f"- **Total Revenue Collected:** ${total_rev_collected:,.2f}\n")

    return report
