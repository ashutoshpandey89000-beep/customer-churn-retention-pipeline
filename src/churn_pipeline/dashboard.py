"""Executive customer churn and retention visualization dashboard generator."""

from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pandas as pd
from sqlalchemy import create_engine, text
from .config import database_url


def generate_dashboard_figure(output_path="screenshots/churn_dashboard_verified.png"):
    """Generate high-resolution visual dashboard from verified PostgreSQL views and curated data."""
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            kpi_df = pd.read_sql(text("SELECT * FROM analytics.kpi_summary"), conn).iloc[0]
            plan_df = pd.read_sql(text("SELECT * FROM analytics.plan_performance ORDER BY churn_rate_pct DESC"), conn)
            contract_df = pd.read_sql(text("SELECT * FROM analytics.contract_performance ORDER BY churn_rate_pct DESC"), conn)
            pay_df = pd.read_sql(text("SELECT * FROM analytics.payment_method_performance ORDER BY churn_rate_pct DESC"), conn)
            tenure_df = pd.read_sql(text("SELECT * FROM analytics.tenure_cohorts ORDER BY churn_rate_pct DESC"), conn)
            monthly_df = pd.read_sql(text("SELECT * FROM analytics.monthly_churn ORDER BY month"), conn)
    finally:
        engine.dispose()

    # Styling settings
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig = plt.figure(figsize=(18, 12), dpi=150)
    fig.patch.set_facecolor("#0F172A")  # Deep slate dark mode

    # Title & Subtitle Header
    plt.figtext(
        0.05, 0.94, "CUSTOMER CHURN & RETENTION EXECUTIVE DASHBOARD",
        fontsize=22, fontweight="bold", color="#F8FAFC", family="sans-serif"
    )
    plt.figtext(
        0.05, 0.915, "Verified Production Pipeline Analytics • PostgreSQL 16 Warehouse • Synthetic Cohort (N=1,000)",
        fontsize=12, color="#94A3B8", family="sans-serif"
    )

    # 4 KPI Cards at Top
    kpis = [
        ("TOTAL CUSTOMERS", f"{int(kpi_df['total_customers']):,}", "#38BDF8", "100% Cohort Population"),
        ("CHURN RATE", f"{float(kpi_df['overall_churn_rate_pct']):.1f}%", "#F43F5E", f"{int(kpi_df['churned_customers']):,} Churned Users"),
        ("RETENTION RATE", f"{float(kpi_df['overall_retention_rate_pct']):.1f}%", "#10B981", f"{int(kpi_df['retained_customers']):,} Active Users"),
        ("ACTIVE MRR", f"${float(kpi_df['active_mrr']):,.0f}", "#FBBF24", f"Lost MRR: ${float(kpi_df['churned_mrr']):,.0f}"),
    ]

    card_width = 0.20
    spacing = 0.03
    start_x = 0.05

    for i, (title, val, color, sub) in enumerate(kpis):
        x = start_x + i * (card_width + spacing)
        # Bounding box
        rect = patches.FancyBboxPatch(
            (x, 0.81), card_width, 0.085,
            boxstyle="round,pad=0.015,rounding_size=0.015",
            facecolor="#1E293B", edgecolor="#334155", linewidth=1.5,
            transform=fig.transFigure, clip_on=False
        )
        fig.patches.append(rect)
        plt.figtext(x + 0.015, 0.875, title, fontsize=10, fontweight="bold", color="#94A3B8")
        plt.figtext(x + 0.015, 0.835, val, fontsize=20, fontweight="bold", color=color)
        plt.figtext(x + 0.015, 0.818, sub, fontsize=9, color="#64748B")

    # Layout for 6 subplots below KPI cards
    # Row 1: Contract Churn, Plan Churn, Payment Method Churn
    # Row 2: Tenure Cohort Churn, Revenue Comparison, Monthly Churn Trend
    axes = []
    # top row
    ax1 = fig.add_axes([0.05, 0.44, 0.27, 0.31])  # Contract
    ax2 = fig.add_axes([0.365, 0.44, 0.27, 0.31]) # Plan
    ax3 = fig.add_axes([0.68, 0.44, 0.27, 0.31])  # Payment Method
    # bottom row
    ax4 = fig.add_axes([0.05, 0.07, 0.27, 0.30])  # Tenure
    ax5 = fig.add_axes([0.365, 0.07, 0.27, 0.30]) # Revenue Comparison
    ax6 = fig.add_axes([0.68, 0.07, 0.27, 0.30])  # Monthly Trend

    for ax in [ax1, ax2, ax3, ax4, ax5, ax6]:
        ax.set_facecolor("#1E293B")
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.tick_params(colors="#94A3B8", labelsize=9)
        ax.grid(color="#334155", linestyle="--", linewidth=0.7, alpha=0.5)

    # 1. Contract Performance
    bars1 = ax1.bar(contract_df["contract_type"], contract_df["churn_rate_pct"], color=["#F43F5E", "#F59E0B", "#10B981"], width=0.55)
    ax1.set_title("Churn Rate by Contract Type", fontsize=12, fontweight="bold", color="#F8FAFC", pad=10)
    ax1.set_ylabel("Churn Rate (%)", color="#94A3B8", fontsize=10)
    ax1.set_ylim(0, 50)
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 1.2, f"{yval:.1f}%", ha="center", va="bottom", color="#F8FAFC", fontweight="bold", fontsize=9)

    # 2. Plan Performance
    bars2 = ax2.bar(plan_df["plan_name"], plan_df["churn_rate_pct"], color="#38BDF8", width=0.55)
    ax2.set_title("Churn Rate by Plan Name", fontsize=12, fontweight="bold", color="#F8FAFC", pad=10)
    ax2.set_ylabel("Churn Rate (%)", color="#94A3B8", fontsize=10)
    ax2.set_ylim(0, 45)
    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 1.0, f"{yval:.1f}%", ha="center", va="bottom", color="#F8FAFC", fontweight="bold", fontsize=9)

    # 3. Payment Method
    bars3 = ax3.barh(pay_df["payment_method"], pay_df["churn_rate_pct"], color="#A855F7", height=0.55)
    ax3.set_title("Churn Rate by Billing Method", fontsize=12, fontweight="bold", color="#F8FAFC", pad=10)
    ax3.set_xlabel("Churn Rate (%)", color="#94A3B8", fontsize=10)
    ax3.set_xlim(0, 50)
    for bar in bars3:
        xval = bar.get_width()
        ax3.text(xval + 1.0, bar.get_y() + bar.get_height()/2.0, f"{xval:.1f}%", ha="left", va="center", color="#F8FAFC", fontweight="bold", fontsize=9)

    # 4. Tenure Cohorts
    tenure_sorted = tenure_df.sort_values("avg_tenure_months")
    bars4 = ax4.bar(tenure_sorted["tenure_group"], tenure_sorted["churn_rate_pct"], color="#EC4899", width=0.55)
    ax4.set_title("Churn Rate by Customer Tenure", fontsize=12, fontweight="bold", color="#F8FAFC", pad=10)
    ax4.set_ylabel("Churn Rate (%)", color="#94A3B8", fontsize=10)
    ax4.set_ylim(0, 115)
    for bar in bars4:
        yval = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2.0, yval + 2.0, f"{yval:.1f}%", ha="center", va="bottom", color="#F8FAFC", fontweight="bold", fontsize=9)

    # 5. Revenue Breakdown: Active MRR vs Churned MRR
    rev_categories = ["Active MRR", "Churned MRR (Lost)"]
    rev_amounts = [float(kpi_df["active_mrr"]), float(kpi_df["churned_mrr"])]
    bars5 = ax5.bar(rev_categories, rev_amounts, color=["#10B981", "#EF4444"], width=0.5)
    ax5.set_title("Monthly Recurring Revenue (MRR)", fontsize=12, fontweight="bold", color="#F8FAFC", pad=10)
    ax5.set_ylabel("USD ($)", color="#94A3B8", fontsize=10)
    ax5.set_ylim(0, max(rev_amounts) * 1.25)
    for bar in bars5:
        yval = bar.get_height()
        ax5.text(bar.get_x() + bar.get_width()/2.0, yval + 400, f"${yval:,.0f}", ha="center", va="bottom", color="#F8FAFC", fontweight="bold", fontsize=9)

    # 6. Monthly Trend
    monthly_df["month_dt"] = pd.to_datetime(monthly_df["month"])
    ax6.plot(monthly_df["month_dt"], monthly_df["eligible_customers"], color="#38BDF8", linewidth=2.2, label="Eligible Customers")
    ax6.plot(monthly_df["month_dt"], monthly_df["active_customers"], color="#10B981", linewidth=2.2, linestyle="--", label="Retained Active")
    ax6.set_title("Cohort Growth & Retention Trend", fontsize=12, fontweight="bold", color="#F8FAFC", pad=10)
    ax6.set_ylabel("Customer Count", color="#94A3B8", fontsize=10)
    ax6.legend(facecolor="#1E293B", edgecolor="#334155", labelcolor="#F8FAFC", fontsize=8, loc="upper left")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    print(f"Verified executive dashboard saved to: {out}")
    return out


if __name__ == "__main__":
    generate_dashboard_figure()
