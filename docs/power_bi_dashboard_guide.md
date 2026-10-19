# Power BI & Excel Dashboard Integration Guide

This guide details how to connect **Power BI Desktop** or **Microsoft Excel** to the curated customer churn dataset and PostgreSQL warehouse views created by this pipeline.

---

## 1. Data Connection Options

You can build the analyst dashboard using either of two methods:

### Option A: Direct PostgreSQL Connection (Recommended for Live BI)
1. In Power BI Desktop, click **Get Data** > **Database** > **PostgreSQL database**.
2. **Server:** `localhost:5433` (or custom host port configured in `.env`).
3. **Database:** `churn_analytics`.
4. **Authentication:** Database credentials (User: `churn_user`, Password: `change_me_local_only`).
5. In the Navigator pane, select the `analytics` schema views:
   - `analytics.kpi_summary`
   - `analytics.contract_performance`
   - `analytics.plan_performance`
   - `analytics.payment_method_performance`
   - `analytics.tenure_cohorts`
   - `analytics.monthly_churn`
   - `curated_customer_retention` (table)

### Option B: Curated Flat Dataset (Self-Contained File)
1. In Power BI or Excel, click **Get Data** > **Text/CSV**.
2. Browse to: `data/curated/curated_customer_retention.csv`.
3. Click **Load**.

---

## 2. Data Dictionary (`curated_customer_retention.csv`)

| Column Name | Data Type | Description | Sample Values |
| :--- | :--- | :--- | :--- |
| `customer_id` | Integer | Unique identifier for each customer | `1`, `2`, `3` |
| `customer_name` | String | Formatted customer display name | `Customer 00001` |
| `city` | String | Customer metropolitan location | `Pune`, `Mumbai`, `Delhi` |
| `acquisition_channel` | String | Marketing acquisition funnel | `organic`, `paid_search`, `referral` |
| `subscription_id` | Integer | Unique subscription identifier | `1`, `2`, `3` |
| `plan_name` | String | Subscription service plan | `Basic`, `Standard`, `Premium`, `Family` |
| `contract_type` | String | Billing commitment horizon | `Month-to-Month`, `One-Year`, `Two-Year` |
| `payment_method` | String | Method used for recurring billing | `Credit Card`, `UPI`, `Electronic Check` |
| `monthly_price` | Decimal | Plan recurring monthly charge in USD | `9.99`, `19.99`, `34.99`, `44.99` |
| `start_date` | Date | Subscription commencement date | `2023-04-12` |
| `end_date` | Date (Nullable) | Subscription termination date (Null if active) | `2024-02-18`, `null` |
| `subscription_status` | String | Current account status | `active`, `churned` |
| `tenure_days` | Integer | Duration active or until churn in days | `185`, `450` |
| `tenure_months` | Decimal | Duration in months (`tenure_days / 30.4375`) | `6.1`, `14.8` |
| `tenure_group` | String | Standard tenure cohort | `0-6 Months`, `6-12 Months`, `12-24 Months`, `24+ Months` |
| `is_churned` | Integer | Binary churn flag (1 = churned, 0 = active) | `1`, `0` |
| `is_retained` | Integer | Binary retention flag (1 = active, 0 = churned)| `0`, `1` |
| `monthly_recurring_revenue` | Decimal | Current active MRR (`monthly_price` if active)| `0.00`, `34.99` |
| `total_revenue` | Decimal | Cumulative revenue collected from paid events | `19.99`, `139.96` |

---

## 3. Power BI DAX Measures

Create the following measures in Power BI:

```dax
// 1. Total Customer Count
Total Customers = COUNTROWS(curated_customer_retention)

// 2. Churned Customer Count
Churned Customers = CALCULATE(COUNTROWS(curated_customer_retention), curated_customer_retention[is_churned] = 1)

// 3. Retained Customer Count
Retained Customers = CALCULATE(COUNTROWS(curated_customer_retention), curated_customer_retention[is_retained] = 1)

// 4. Overall Churn Rate (%)
Churn Rate % = DIVIDE([Churned Customers], [Total Customers], 0) * 100

// 5. Overall Retention Rate (%)
Retention Rate % = DIVIDE([Retained Customers], [Total Customers], 0) * 100

// 6. Active Monthly Recurring Revenue (MRR)
Active MRR = CALCULATE(SUM(curated_customer_retention[monthly_price]), curated_customer_retention[subscription_status] = "active")

// 7. Churned MRR Lost
Churned MRR Lost = CALCULATE(SUM(curated_customer_retention[monthly_price]), curated_customer_retention[subscription_status] = "churned")

// 8. Average Customer Tenure (Months)
Average Tenure (Months) = AVERAGE(curated_customer_retention[tenure_months])
```

---

## 4. Visual Layout Specifications

| Visual Type | Fields / Axes | Recommended Formatting | Insight Delivered |
| :--- | :--- | :--- | :--- |
| **Card Visuals (Top)** | `Total Customers`, `Churn Rate %`, `Retention Rate %`, `Active MRR` | Large bold callout metrics, KPI badges | Immediate executive snapshot of cohort size and health |
| **Clustered Column Chart** | **X-Axis:** `contract_type`<br>**Y-Axis:** `Churn Rate %` | Sort descending; highlight Month-to-Month in coral/red | Demonstrates contract horizon sensitivity (39% vs 8%) |
| **Clustered Column Chart** | **X-Axis:** `plan_name`<br>**Y-Axis:** `Churn Rate %` | Sky blue palette; order by tier price | Pinpoints price elasticity and premium plan drop-off |
| **Horizontal Bar Chart** | **Y-Axis:** `payment_method`<br>**X-Axis:** `Churn Rate %` | Purple/violet tones | Reveals billing friction (e.g. Electronic Check friction) |
| **Clustered Column Chart** | **X-Axis:** `tenure_group`<br>**Y-Axis:** `Churn Rate %` | Categorical colors | Identifies early lifecycle churn vulnerability (< 6 mo) |
| **Donut / Clustered Bar** | **Legend:** Status (`active`, `churned`)<br>**Values:** `Active MRR`, `Churned MRR Lost` | Green for active, Red for lost | Quantifies revenue retention impact |
| **Line Chart** | **X-Axis:** `month`<br>**Y-Axis:** `eligible_customers`, `active_customers` | Continuous timeline; dual trendlines | Shows growth trajectory and cumulative active retention |
