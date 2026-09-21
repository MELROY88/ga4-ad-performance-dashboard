# Building this dashboard in Power BI (or Tableau)

The HTML dashboard in `/dashboard` is the finished, runnable version. Use this guide to rebuild the same views in Power BI Desktop in about 90 minutes. Every number in the report should match the HTML page, which makes a good self-check.

## Steps
1. Load the CSVs and build the relationships in `data_model.md`.
2. Create the measures from `measures.dax`.
3. View > Themes > Browse for themes > `theme.json`.
4. Build the three pages below.
5. Add slicers for Year, Country, Channel group, and Device on each page, then sync them (View > Sync slicers).

## Page 1: Executive overview
```
+---------------------------------------------------------------+
| Slicers: Year | Country | Channel group | Device              |
+--------+--------+--------+--------+--------+--------+--------+
| Revenue| Session| Purch. | CVR    | AOV    | Spend  | ROAS   |  <- 7 cards, YoY in the subtitle
+--------+--------+--------+--------+--------+--------+--------+
| Clustered column + line: month vs Revenue (bars),            |
| Paid ROAS (line, secondary axis)                 | Smart     |
|                                                  | narrative |
+--------------------------------------------------+-----------+
| Funnel: Sessions > Engaged > Cart > Checkout > Purchase      |
+---------------------------------------------------------------+
```
Check: with no filters, Revenue = AED 168.3M, ROAS = 4.01x, CVR = 4.38%.

## Page 2: Campaign and budget
```
| Table: campaign, spend, revenue, ROAS, CPA, CPC, CTR         |
|   conditional format ROAS: green >= 4, amber 2.5 to 4, red < 2.5 |
| Scatter: X = Spend Share %, Y = Revenue Share %, size = Spend, legend = platform |
| Bar: Paid ROAS by country       | Matrix: device x country CVR|
```
Story to tell: the campaigns below the diagonal (spend share above revenue share) are where budget is being wasted. In this dataset they are Meta Prospecting, Search Generic and TikTok.

## Page 3: Time, events and quality
```
| Line: daily sessions (fact_site_daily) + Anomaly Flag as markers |
| Matrix: weekday (rows) x month (columns), Sessions, colour scale |
| Matrix: cohort_month (rows) x months_since (columns), Cohort Retention %, colour scale |
```
Use a reference band or a second axis for `dim_date[event]` so promo periods are visible.

## Tableau notes
- Connect to each CSV, relate tables in the Data Source tab (same keys as above).
- Paid ROAS: `SUM(IF [kind]='paid' THEN [revenue_aed] END) / SUM([spend_aed])`
- Revenue YoY: `(SUM([revenue_aed]) - LOOKUP(SUM([revenue_aed]), -12)) / ABS(LOOKUP(SUM([revenue_aed]), -12))` on a month axis.
- Anomaly: table calc `WINDOW_AVG(SUM([sessions]), -28, -1)` with the weekday in the partition.

## Publishing
Export each page as PNG (File > Export) and save in `/images`. Add the `.pbix` to the repo (it is small because the data is under 2 MB).
