"""
analyse.py
----------
Turns the star-schema CSVs into the numbers behind the dashboard and README:

* KPI summary (with year-over-year deltas)
* Channel / campaign / market / device scorecards (ROAS, CPA, CPC, CTR, CVR, AOV)
* Purchase funnel and drop-off by device
* Seasonality: event uplift vs a matched baseline
* Cohort retention matrix
* Anomaly detection on daily sessions, purchases and spend (robust z-score)
* insights.json: the headline findings, computed rather than hand-written

Run:  python src/analyse.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT = ROOT / "data", ROOT / "outputs"
OUT.mkdir(exist_ok=True)

fact = pd.read_csv(DATA / "fact_performance_weekly.csv", parse_dates=["week_start"])
daily = pd.read_csv(DATA / "fact_site_daily.csv", parse_dates=["date"])
camp = pd.read_csv(DATA / "dim_campaign.csv")
country = pd.read_csv(DATA / "dim_country.csv")
cohort = pd.read_csv(DATA / "fact_cohort_retention.csv")

fact = fact.merge(camp[["campaign_id", "campaign", "platform", "channel_group", "kind"]], on="campaign_id")
fact = fact.merge(country[["country_code", "country"]], on="country_code")
fact["year"] = fact.week_start.dt.year

SUM = ["impressions", "clicks", "spend_aed", "sessions", "engaged_sessions", "new_users",
       "add_to_cart", "begin_checkout", "purchases", "revenue_aed"]


def kpis(g: pd.DataFrame) -> pd.DataFrame:
    """Add the standard marketing ratios to a grouped sum table."""
    g = g.copy()
    g["ROAS"] = g.revenue_aed / g.spend_aed.replace(0, np.nan)
    g["CPA_aed"] = g.spend_aed / g.purchases.replace(0, np.nan)
    g["CPC_aed"] = g.spend_aed / g.clicks.replace(0, np.nan)
    g["CTR_pct"] = 100 * g.clicks / g.impressions.replace(0, np.nan)
    g["CVR_pct"] = 100 * g.purchases / g.sessions.replace(0, np.nan)
    g["engagement_pct"] = 100 * g.engaged_sessions / g.sessions.replace(0, np.nan)
    g["AOV_aed"] = g.revenue_aed / g.purchases.replace(0, np.nan)
    g["revenue_per_session"] = g.revenue_aed / g.sessions.replace(0, np.nan)
    return g.round(3)


def scorecard(by):
    return kpis(fact.groupby(by, as_index=False)[SUM].sum())


# ---------------------------------------------------------------- scorecards
overall = kpis(fact[SUM].sum().to_frame().T)
by_year = scorecard("year")
by_channel = scorecard("channel_group").sort_values("revenue_aed", ascending=False)
by_campaign = scorecard(["campaign", "platform", "channel_group"]).sort_values("revenue_aed", ascending=False)
by_country = scorecard("country").sort_values("revenue_aed", ascending=False)
by_device = scorecard("device").sort_values("revenue_aed", ascending=False)
paid = fact[fact.kind == "paid"]
paid_by_campaign = kpis(paid.groupby(["campaign", "platform"], as_index=False)[SUM].sum()).sort_values("ROAS", ascending=False)
paid_by_platform = kpis(paid.groupby("platform", as_index=False)[SUM].sum()).sort_values("ROAS", ascending=False)
paid_total = kpis(paid[SUM].sum().to_frame().T)
monthly = kpis(fact.assign(month=fact.week_start.dt.to_period("M").astype(str)).groupby("month", as_index=False)[SUM].sum())

for name, tbl in {"overall": overall, "by_year": by_year, "by_channel": by_channel, "by_campaign": by_campaign,
                  "by_country": by_country, "by_device": by_device, "paid_by_campaign": paid_by_campaign,
                  "paid_by_platform": paid_by_platform, "monthly": monthly}.items():
    tbl.to_csv(OUT / f"{name}.csv", index=False)

# ---------------------------------------------------------------- funnel
funnel_steps = ["sessions", "engaged_sessions", "add_to_cart", "begin_checkout", "purchases"]
funnel = fact.groupby("device")[funnel_steps].sum()
funnel.loc["All devices"] = funnel.sum()
funnel_rates = funnel.div(funnel.sessions, axis=0).mul(100).round(2)
step_rates = pd.DataFrame({
    "engage_rate": funnel.engaged_sessions / funnel.sessions,
    "cart_rate": funnel.add_to_cart / funnel.engaged_sessions,
    "checkout_rate": funnel.begin_checkout / funnel.add_to_cart,
    "purchase_rate": funnel.purchases / funnel.begin_checkout,
}).mul(100).round(1)
funnel_rates.to_csv(OUT / "funnel_pct_of_sessions.csv")
step_rates.to_csv(OUT / "funnel_step_conversion.csv")

# ---------------------------------------------------------------- seasonality
daily["is_event"] = daily.event.notna() & (daily.event != "")
baseline = daily[~daily.is_event].groupby("weekday")[["sessions", "purchases", "revenue_aed"]].mean()
ev = daily[daily.is_event].copy()
ev = ev.join(baseline, on="weekday", rsuffix="_base")
season = ev.groupby("event").agg(days=("date", "count"), sessions=("sessions", "mean"), sessions_base=("sessions_base", "mean"),
                                 revenue=("revenue_aed", "mean"), revenue_base=("revenue_aed_base", "mean"))
season["sessions_uplift_pct"] = (100 * (season.sessions / season.sessions_base - 1)).round(1)
season["revenue_uplift_pct"] = (100 * (season.revenue / season.revenue_base - 1)).round(1)
season = season.sort_values("revenue_uplift_pct", ascending=False)
season.round(0).to_csv(OUT / "event_uplift.csv")

# ---------------------------------------------------------------- cohorts
cohort["retention_pct"] = (100 * cohort.active_customers / cohort.cohort_size).round(1)
cohort_matrix = cohort.pivot(index="cohort_month", columns="months_since", values="retention_pct")
cohort_matrix.to_csv(OUT / "cohort_retention_matrix.csv")

# ---------------------------------------------------------------- anomalies
def detect(df: pd.DataFrame, metric: str, min_change: float = 0.30, z_cut: float = 4.0) -> pd.DataFrame:
    """Flag days that break sharply from the same weekday in the previous four weeks.

    1. baseline  = median of the same weekday over the last 4 weeks (handles weekly rhythm)
    2. lr        = log(actual / baseline)
    3. z         = robust z-score of lr (median / MAD over 'quiet' days only)
    Days inside a planned event window (plus 28 days of afterglow, when the baseline
    still contains promo weeks) are not scored, so campaigns are not mistaken for incidents.
    """
    x = df[metric].astype(float)
    base = pd.concat([x.shift(k) for k in (7, 14, 21, 28)], axis=1).median(axis=1)
    lr = np.log(x / base)
    quiet = ~df.muted
    med = lr[quiet].median()
    mad = (lr[quiet] - med).abs().median() * 1.4826
    z = (lr - med) / mad
    hit = quiet & (z.abs() > z_cut) & (lr.abs() > min_change)
    return pd.DataFrame({"date": df.date[hit].dt.date.astype(str), "metric": metric, "value": x[hit].round(1),
                         "change_vs_baseline_pct": (100 * (np.exp(lr[hit]) - 1)).round(0),
                         "robust_z": z[hit].round(1), "direction": np.where(lr[hit] > 0, "spike", "drop")})


daily = daily.sort_values("date").reset_index(drop=True)
event_days = daily.date.where(daily.is_event)
last_event = event_days.ffill()
daily["muted"] = daily.is_event | ((daily.date - last_event).dt.days <= 28).fillna(False) | (daily.index < 35)
anomalies = pd.concat([detect(daily, m) for m in ["sessions", "purchases", "spend_aed"]]).sort_values(["date", "metric"])
anomalies.to_csv(OUT / "anomalies.csv", index=False)

# ---------------------------------------------------------------- headline insights
def pct(a, b):
    return round(100 * (a / b - 1), 1)

y = by_year.set_index("year")
paid_year = kpis(paid.groupby("year", as_index=False)[SUM].sum()).set_index("year")
pc = paid_by_campaign.set_index("campaign")
best, worst = pc.ROAS.idxmax(), pc.ROAS.idxmin()
big_spend = pc.sort_values("spend_aed", ascending=False)
ch = by_channel.set_index("channel_group")
mob = kpis(fact.groupby("device", as_index=False)[SUM].sum()).set_index("device")
tt = kpis(paid[paid.platform == "TikTok Ads"].groupby("year", as_index=False)[SUM].sum()).set_index("year")
mp = kpis(paid[paid.campaign == "Meta - Prospecting"].assign(h=lambda d: np.where(d.week_start >= "2025-03-01", "recent", "early"))
          .groupby("h", as_index=False)[SUM].sum()).set_index("h")
share_paid_rev = round(100 * paid.revenue_aed.sum() / fact.revenue_aed.sum(), 1)
top_country = by_country.iloc[0]
weak_country = by_country.sort_values("CVR_pct").iloc[0]
after_promo = cohort[(cohort.months_since == 3)].assign(promo=lambda d: d.cohort_month.str[-2:].isin(["11", "12"]))
ret_promo = after_promo[after_promo.promo].retention_pct.mean()
ret_norm = after_promo[~after_promo.promo].retention_pct.mean()

insights = {
    "total_revenue_aed": round(float(overall.revenue_aed[0])),
    "total_spend_aed": round(float(overall.spend_aed[0])),
    "total_sessions": int(overall.sessions[0]),
    "total_purchases": int(overall.purchases[0]),
    "overall_cvr_pct": float(overall.CVR_pct[0]),
    "paid_roas": float(paid_total.ROAS[0]),
    "paid_cpa_aed": float(paid_total.CPA_aed[0]),
    "revenue_yoy_pct": pct(y.loc[2025, "revenue_aed"], y.loc[2024, "revenue_aed"]),
    "sessions_yoy_pct": pct(y.loc[2025, "sessions"], y.loc[2024, "sessions"]),
    "spend_yoy_pct": pct(y.loc[2025, "spend_aed"], y.loc[2024, "spend_aed"]),
    "paid_roas_2024": float(paid_year.loc[2024, "ROAS"]),
    "paid_roas_2025": float(paid_year.loc[2025, "ROAS"]),
    "best_campaign": best, "best_campaign_roas": float(pc.loc[best, "ROAS"]),
    "worst_campaign": worst, "worst_campaign_roas": float(pc.loc[worst, "ROAS"]),
    "largest_spend_campaign": big_spend.index[0],
    "largest_spend_share_pct": round(100 * float(big_spend.spend_aed.iloc[0] / big_spend.spend_aed.sum()), 1),
    "largest_spend_roas": float(big_spend.ROAS.iloc[0]),
    "paid_share_of_revenue_pct": share_paid_rev,
    "top_channel_by_revenue": ch.index[0],
    "mobile_share_sessions_pct": round(100 * float(mob.loc["Mobile", "sessions"] / mob.sessions.sum()), 1),
    "mobile_cvr_pct": float(mob.loc["Mobile", "CVR_pct"]), "desktop_cvr_pct": float(mob.loc["Desktop", "CVR_pct"]),
    "tiktok_cpc_2024": float(tt.loc[2024, "CPC_aed"]), "tiktok_cpc_2025": float(tt.loc[2025, "CPC_aed"]),
    "tiktok_roas_2024": float(tt.loc[2024, "ROAS"]), "tiktok_roas_2025": float(tt.loc[2025, "ROAS"]),
    "meta_prospecting_ctr_early": float(mp.loc["early", "CTR_pct"]), "meta_prospecting_ctr_recent": float(mp.loc["recent", "CTR_pct"]),
    "top_country": top_country.country, "top_country_share_pct": round(100 * float(top_country.revenue_aed / by_country.revenue_aed.sum()), 1),
    "lowest_cvr_country": weak_country.country, "lowest_cvr_pct": float(weak_country.CVR_pct),
    "biggest_event": season.index[0], "biggest_event_revenue_uplift_pct": float(season.revenue_uplift_pct.iloc[0]),
    "ramadan_revenue_uplift_pct": float(season.loc["Ramadan 2025", "revenue_uplift_pct"]),
    "promo_cohort_m3_retention_pct": round(float(ret_promo), 1), "regular_cohort_m3_retention_pct": round(float(ret_norm), 1),
    "anomalies_found": int(len(anomalies)),
    "funnel_biggest_leak": "add_to_cart" if step_rates.loc["All devices", "cart_rate"] < 40 else "checkout",
    "cart_rate_pct": float(step_rates.loc["All devices", "cart_rate"]),
    "checkout_rate_pct": float(step_rates.loc["All devices", "checkout_rate"]),
    "purchase_rate_pct": float(step_rates.loc["All devices", "purchase_rate"]),
}
(OUT / "insights.json").write_text(json.dumps(insights, indent=2))

pd.set_option("display.width", 200, "display.max_columns", 30)
print("PAID BY CAMPAIGN\n", paid_by_campaign[["campaign", "spend_aed", "revenue_aed", "ROAS", "CPA_aed", "CPC_aed", "CTR_pct", "CVR_pct"]].to_string(index=False))
print("\nEVENT UPLIFT\n", season[["days", "sessions_uplift_pct", "revenue_uplift_pct"]])
print("\nANOMALIES\n", anomalies.to_string(index=False))
print("\nFUNNEL STEPS\n", step_rates)
print("\nINSIGHTS\n", json.dumps(insights, indent=2))
