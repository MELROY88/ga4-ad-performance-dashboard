# Data model (star schema)

Import all seven CSVs from `/data` (Home > Get data > Text/CSV). Set types: dates as Date, money as Fixed decimal, IDs as Whole number.

```
dim_date (date) 1 ──< fact_performance_weekly >── 1 dim_campaign (campaign_id)
                          │  │
     dim_country (country_code) 1 ──┘  └── 1 dim_device (device)

dim_date (date) 1 ──< fact_site_daily          fact_cohort_retention (stand-alone)
```

| Relationship | From (many) | To (one) | Notes |
|---|---|---|---|
| Weekly fact to campaign | fact_performance_weekly[campaign_id] | dim_campaign[campaign_id] | single direction |
| Weekly fact to country | fact_performance_weekly[country_code] | dim_country[country_code] | single direction |
| Weekly fact to device | fact_performance_weekly[device] | dim_device[device] | single direction |
| Weekly fact to date | fact_performance_weekly[week_start] | dim_date[date] | keep only the weekly relationship active; dim_date[date] contains every day, so weeks match on Mondays |
| Daily fact to date | fact_site_daily[date] | dim_date[date] | second relationship on the same date table |

Mark `dim_date` as the date table (Table tools > Mark as date table > `date`).
Hide the key columns in report view and sort `dim_date[month]` by `month_num`, `weekday` by `weekday_num`.

`fact_cohort_retention` has no relationships. It feeds one matrix visual directly.
