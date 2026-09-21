-- Marketing analytics queries for the Marhaba Lifestyle dataset (SQLite; works in Postgres/BigQuery with minor tweaks).
-- Load first:  python src/load_sqlite.py     Run:  sqlite3 sql/marketing.db < sql/marketing_queries.sql

.headers on
.mode column

-- 1. Headline KPIs
SELECT ROUND(SUM(revenue_aed)/1e6,2) AS revenue_m, ROUND(SUM(sessions)/1e6,2) AS sessions_m,
       SUM(purchases) AS purchases, ROUND(100.0*SUM(purchases)/SUM(sessions),2) AS cvr_pct,
       ROUND(SUM(revenue_aed)/SUM(purchases),1) AS aov
FROM fact_performance_weekly;

-- 2. Paid campaign scorecard: ROAS, CPA, CPC, CTR (owned channels excluded)
SELECT c.campaign, c.platform,
       ROUND(SUM(f.spend_aed)/1e6,2) AS spend_m,
       ROUND(SUM(f.revenue_aed)/SUM(f.spend_aed),2) AS roas,
       ROUND(SUM(f.spend_aed)/SUM(f.purchases),1) AS cpa,
       ROUND(SUM(f.spend_aed)/SUM(f.clicks),2) AS cpc,
       ROUND(100.0*SUM(f.clicks)/SUM(f.impressions),2) AS ctr_pct
FROM fact_performance_weekly f JOIN dim_campaign c USING (campaign_id)
WHERE c.kind='paid'
GROUP BY c.campaign, c.platform ORDER BY roas DESC;

-- 3. Year-over-year by market (window function LAG)
WITH y AS (
  SELECT f.country_code, d.year, SUM(f.revenue_aed) AS rev
  FROM fact_performance_weekly f JOIN dim_date d ON d.date=f.week_start
  GROUP BY f.country_code, d.year)
SELECT co.country, ROUND(rev/1e6,2) AS rev_m, year,
       ROUND(100.0*(rev/LAG(rev) OVER (PARTITION BY y.country_code ORDER BY year)-1),1) AS yoy_pct
FROM y JOIN dim_country co USING (country_code) ORDER BY co.country, year;

-- 4. Monthly revenue with running total and 3-month moving average
WITH m AS (
  SELECT d.year_month, SUM(f.revenue_aed) AS rev
  FROM fact_performance_weekly f JOIN dim_date d ON d.date=f.week_start GROUP BY d.year_month)
SELECT year_month, ROUND(rev/1e6,2) AS rev_m,
       ROUND(SUM(rev) OVER (ORDER BY year_month)/1e6,1) AS cumulative_m,
       ROUND(AVG(rev) OVER (ORDER BY year_month ROWS 2 PRECEDING)/1e6,2) AS ma3_m
FROM m;

-- 5. Budget re-allocation candidates: spend share vs revenue share of paid campaigns
WITH p AS (
  SELECT c.campaign, SUM(f.spend_aed) AS spend, SUM(f.revenue_aed) AS rev
  FROM fact_performance_weekly f JOIN dim_campaign c USING (campaign_id) WHERE c.kind='paid' GROUP BY c.campaign)
SELECT campaign,
       ROUND(100.0*spend/SUM(spend) OVER (),1) AS spend_share_pct,
       ROUND(100.0*rev/SUM(rev) OVER (),1)   AS revenue_share_pct,
       ROUND(rev/spend,2) AS roas,
       CASE WHEN rev/spend < 2.5 THEN 'review / cut' WHEN rev/spend >= 4 THEN 'candidate to scale' ELSE 'hold' END AS action
FROM p ORDER BY roas DESC;

-- 6. Device gap: conversion rate by device and market
SELECT co.country, f.device, ROUND(100.0*SUM(f.purchases)/SUM(f.sessions),2) AS cvr_pct
FROM fact_performance_weekly f JOIN dim_country co USING (country_code)
GROUP BY co.country, f.device ORDER BY co.country, cvr_pct DESC;

-- 7. Funnel step conversion by device
SELECT device,
  ROUND(100.0*SUM(engaged_sessions)/SUM(sessions),1) AS engaged_pct,
  ROUND(100.0*SUM(add_to_cart)/SUM(engaged_sessions),1) AS cart_pct,
  ROUND(100.0*SUM(begin_checkout)/SUM(add_to_cart),1) AS checkout_pct,
  ROUND(100.0*SUM(purchases)/SUM(begin_checkout),1) AS purchase_pct
FROM fact_performance_weekly GROUP BY device;

-- 8. Event uplift: average daily revenue in each event vs the non-event daily average
WITH base AS (SELECT AVG(revenue_aed) AS b FROM fact_site_daily WHERE COALESCE(event,'')='')
SELECT event, COUNT(*) AS days, ROUND(AVG(revenue_aed)/1e3,1) AS avg_daily_rev_k,
       ROUND(100.0*(AVG(revenue_aed)/(SELECT b FROM base)-1),1) AS uplift_pct
FROM fact_site_daily WHERE COALESCE(event,'')<>'' GROUP BY event ORDER BY uplift_pct DESC;

-- 9. Simple anomaly screen: days more than 40% off the same-weekday 4-week average
WITH x AS (
  SELECT date, sessions,
         AVG(sessions) OVER (PARTITION BY weekday ORDER BY date ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS base
  FROM fact_site_daily)
SELECT date, sessions, ROUND(base) AS baseline, ROUND(100.0*(sessions/base-1),1) AS diff_pct
FROM x WHERE base IS NOT NULL AND ABS(sessions/base-1) > 0.4 AND date NOT IN
  (SELECT date FROM fact_site_daily WHERE COALESCE(event,'')<>'')
ORDER BY date;

-- 10. Cohort retention at month 3 (promo vs regular acquisition months)
SELECT CASE WHEN substr(cohort_month,6,2) IN ('11','12') THEN 'promo (Nov/Dec)' ELSE 'regular' END AS cohort_type,
       ROUND(100.0*SUM(active_customers)/SUM(cohort_size),1) AS m3_retention_pct
FROM fact_cohort_retention WHERE months_since=3 GROUP BY 1;
