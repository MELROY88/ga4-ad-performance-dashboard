"""
build_dashboard.py
------------------
Bundles the star-schema data and the computed insights into ONE self-contained
HTML file (dashboard/index.html). No server, no internet, no dependencies:
open the file in any browser.

The dashboard logic lives in dashboard/template.html (vanilla JS + SVG).
This script only injects data and writes the final file.

Run:  python src/build_dashboard.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT, DASH = ROOT / "data", ROOT / "outputs", ROOT / "dashboard"

weekly = pd.read_csv(DATA / "fact_performance_weekly.csv", parse_dates=["week_start"])
daily = pd.read_csv(DATA / "fact_site_daily.csv", parse_dates=["date"])
camp = pd.read_csv(DATA / "dim_campaign.csv")
country = pd.read_csv(DATA / "dim_country.csv")
cohort = pd.read_csv(DATA / "fact_cohort_retention.csv")
dim_date = pd.read_csv(DATA / "dim_date.csv", parse_dates=["date"])
anomalies = pd.read_csv(OUT / "anomalies.csv")
ins = json.loads((OUT / "insights.json").read_text())

# ---- month x campaign x country x device rows (compact arrays keep the file small)
weekly["ym"] = weekly.week_start.dt.strftime("%Y-%m")
cols = ["impressions", "clicks", "spend_aed", "sessions", "engaged_sessions", "new_users",
        "add_to_cart", "begin_checkout", "purchases", "revenue_aed"]
m = weekly.groupby(["ym", "campaign_id", "country_code", "device"], as_index=False)[cols].sum()
m[["spend_aed", "revenue_aed"]] = m[["spend_aed", "revenue_aed"]].round(0)
rows = m[["ym", "campaign_id", "country_code", "device"] + cols].values.tolist()

# ---- events (start/end) for shading
ev = (dim_date[dim_date.event.notna() & (dim_date.event != "")]
      .groupby("event").date.agg(["min", "max"]).reset_index().sort_values("min"))
events = [[r.event, r["min"].strftime("%Y-%m-%d"), r["max"].strftime("%Y-%m-%d")] for _, r in ev.iterrows()]

payload = {
    "rows": rows,
    "campaigns": camp[["campaign_id", "campaign", "platform", "channel_group", "kind"]].values.tolist(),
    "countries": country[["country_code", "country"]].values.tolist(),
    "daily": daily.assign(date=daily.date.dt.strftime("%Y-%m-%d"))[
        ["date", "weekday", "sessions", "purchases", "revenue_aed", "spend_aed"]].values.tolist(),
    "cohort": cohort[["cohort_month", "months_since", "cohort_size", "active_customers"]].values.tolist(),
    "events": events,
    "anomalies": anomalies[["date", "metric", "change_vs_baseline_pct", "direction"]].values.tolist(),
}

fm = lambda v: f"{v/1e6:,.1f}M"
notes = [
    f"<b>{ins['best_campaign']}</b> is the most efficient paid campaign at {ins['best_campaign_roas']:.1f}x ROAS, "
    f"while <b>{ins['worst_campaign']}</b> returns only {ins['worst_campaign_roas']:.2f}x. That is a budget conversation.",
    f"<b>{ins['largest_spend_campaign']}</b> takes the biggest share of paid budget ({ins['largest_spend_share_pct']}%) at "
    f"{ins['largest_spend_roas']:.1f}x ROAS. Worth testing incrementality before scaling.",
    f"Mobile is {ins['mobile_share_sessions_pct']}% of sessions but converts at {ins['mobile_cvr_pct']:.1f}% versus "
    f"{ins['desktop_cvr_pct']:.1f}% on desktop. The mobile journey is the largest conversion opportunity.",
    f"The biggest leak in the funnel is engaged visit to add-to-cart ({ins['cart_rate_pct']:.1f}%). "
    f"Once a cart exists, {ins['checkout_rate_pct']:.0f}% start checkout and {ins['purchase_rate_pct']:.0f}% of those buy.",
    f"<b>{ins['biggest_event']}</b> lifts daily revenue by about {ins['biggest_event_revenue_uplift_pct']:.0f}% over a normal "
    f"same-weekday baseline. Ramadan alone is closer to +{ins['ramadan_revenue_uplift_pct']:.0f}%.",
    f"Customers acquired in Nov/Dec promo months retain worse at month 3 ({ins['promo_cohort_m3_retention_pct']}% vs "
    f"{ins['regular_cohort_m3_retention_pct']}%). Discount-led acquisition needs a CRM follow-up plan.",
    f"{ins['anomalies_found']} anomaly flags surfaced automatically: a GA4 tracking drop, a Meta budget spike and a viral organic spike.",
]
payload["insights"] = notes

html = (DASH / "template.html").read_text()
html = html.replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":")))
(DASH / "index.html").write_text(html)
print(f"dashboard/index.html written  ({len(html)/1024:,.0f} KB, {len(rows):,} data rows)")
