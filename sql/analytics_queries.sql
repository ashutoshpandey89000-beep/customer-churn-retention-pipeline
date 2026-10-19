-- ============================================================================
-- Customer Churn & Retention Analytics Queries
-- ============================================================================

-- 1. Executive Portfolio KPI Summary
-- Overall customer count, churn/retention rates, average tenure, MRR and total revenue
SELECT * FROM analytics.kpi_summary;

-- 2. Monthly Churn and Retention Trends
-- Evaluates eligible population entering each month against churned subscribers
SELECT
    month,
    eligible_customers,
    churned_customers,
    active_customers,
    churn_rate_pct,
    retention_rate_pct
FROM analytics.monthly_churn
ORDER BY month;

-- 3. Subscription Plan Performance & Churn Rates
-- Compares churn rates, active subscribers, and monthly revenue across plans
SELECT
    plan_name,
    subscribers,
    churned_subscribers,
    active_subscribers,
    churn_rate_pct,
    retention_rate_pct,
    monthly_revenue,
    avg_monthly_price
FROM analytics.plan_performance
ORDER BY monthly_revenue DESC NULLS LAST;

-- 4. Churn by Contract Type
-- Evaluates commitment horizon impact (Month-to-Month vs 1-Year vs 2-Year)
SELECT
    contract_type,
    subscribers,
    churned_subscribers,
    active_subscribers,
    churn_rate_pct,
    retention_rate_pct,
    monthly_revenue
FROM analytics.contract_performance
ORDER BY churn_rate_pct DESC;

-- 5. Churn by Payment Method
-- Identifies friction points by billing channel (Credit Card, UPI, Electronic Check, etc.)
SELECT
    payment_method,
    subscribers,
    churned_subscribers,
    active_subscribers,
    churn_rate_pct,
    retention_rate_pct,
    active_mrr
FROM analytics.payment_method_performance
ORDER BY churn_rate_pct DESC;

-- 6. Churn by Customer Tenure Cohort
-- Analyzes drop-off at lifecycle milestones (0-6M, 6-12M, 12-24M, 24M+)
SELECT
    tenure_group,
    subscribers,
    churned_subscribers,
    active_subscribers,
    churn_rate_pct,
    retention_rate_pct,
    avg_tenure_months,
    mrr_lost_to_churn,
    active_mrr
FROM analytics.tenure_cohorts
ORDER BY churn_rate_pct DESC;

-- 7. Signup Cohort Retention Analysis
-- Tracks customer lifecycle by original acquisition month
SELECT
    signup_month,
    customers,
    churned_customers,
    retained_customers,
    cohort_churn_pct,
    cohort_retention_pct
FROM analytics.customer_cohorts
ORDER BY signup_month;

-- 8. Payment Event Value and Transaction Status Summary
-- Breakdown of paid, failed, and refunded payments
SELECT
    payment_status,
    event_count,
    total_amount,
    avg_amount
FROM analytics.payment_status_summary
ORDER BY total_amount DESC;

-- 9. Revenue Comparison: Active vs Churned Accounts
-- Quantifies total recurring revenue and lifetime collections by account status
SELECT
    subscription_status,
    customer_count,
    total_recurring_revenue AS recurring_mrr,
    avg_monthly_price,
    total_revenue_collected
FROM analytics.revenue_by_status;

-- 10. Churn by Acquisition Channel
-- Measures effectiveness and customer quality across marketing funnels
SELECT
    c.acquisition_channel,
    COUNT(*) AS customers,
    COUNT(*) FILTER (WHERE s.subscription_status = 'churned') AS churned,
    COUNT(*) FILTER (WHERE s.subscription_status = 'active') AS retained,
    ROUND(100.0 * COUNT(*) FILTER (WHERE s.subscription_status = 'churned') / NULLIF(COUNT(*), 0), 2) AS churn_pct,
    ROUND(SUM(s.monthly_price) FILTER (WHERE s.subscription_status = 'active'), 2) AS active_channel_mrr
FROM churn_customers c
JOIN churn_subscriptions s ON s.customer_id = c.customer_id
GROUP BY c.acquisition_channel
ORDER BY churn_pct DESC;
