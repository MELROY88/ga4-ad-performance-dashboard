"""
generate_data.py
----------------
Creates a synthetic, fully reproducible dataset that mimics what a GA4 export
joined with paid-media platform spend looks like for a fictional GCC
entertainment + retail brand ("Marhaba Lifestyle").

Nothing here is real company data. Every number is produced from a seeded
random process so results are identical on every run.

Outputs (written to ../data):
    dim_date.csv, dim_campaign.csv, dim_country.csv, dim_device.csv
    fact_performance_weekly.csv   week x campaign x country x device
    fact_site_daily.csv           one row per day (site level, with injected anomalies)
    fact_cohort_retention.csv     monthly customer cohorts and retention
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2026
START, END = "2024-01-01", "2025-12-31"
OUT = Path(__file__).resolve().parents[1] / "data"
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(SEED)

# --------------------------------------------------------------------------
# 1. Dimensions
# --------------------------------------------------------------------------
# id, campaign, platform, channel_group, daily_budget_AED, cpc_AED, ctr, kind
CAMPAIGNS = [
    (1, "Search - Brand", "Google Ads", "Paid Search", 1500, 1.10, 0.180, "paid"),
    (2, "Search - Generic", "Google Ads", "Paid Search", 3200, 2.60, 0.045, "paid"),
    (3, "Performance Max - Retail", "Google Ads", "Performance Max", 4200, 1.70, 0.021, "paid"),
    (4, "YouTube - Awareness", "Google Ads", "Paid Video", 2600, 0.42, 0.008, "paid"),
    (5, "Meta - Prospecting", "Meta Ads", "Paid Social", 3600, 1.35, 0.011, "paid"),
    (6, "Meta - Retargeting", "Meta Ads", "Paid Social", 1700, 0.95, 0.024, "paid"),
    (7, "Meta - Seasonal Promo", "Meta Ads", "Paid Social", 2100, 1.20, 0.014, "paid"),
    (8, "TikTok - Spark Ads", "TikTok Ads", "Paid Social", 2400, 0.72, 0.009, "paid"),
    (9, "TikTok - Traffic", "TikTok Ads", "Paid Social", 1500, 0.55, 0.007, "paid"),
    (10, "LinkedIn - Corporate Bookings", "LinkedIn Ads", "Paid Social", 1100, 7.80, 0.006, "paid"),
    (11, "Organic Search", "Owned", "Organic Search", 0, 0, 0, "organic"),
    (12, "Email & CRM", "Owned", "Email / CRM", 0, 0, 0, "owned"),
    (13, "Direct", "Owned", "Direct", 0, 0, 0, "owned"),
    (14, "Referral & Partners", "Owned", "Referral", 0, 0, 0, "owned"),
]
dim_campaign = pd.DataFrame(
    CAMPAIGNS,
    columns=["campaign_id", "campaign", "platform", "channel_group", "daily_budget_aed",
             "base_cpc_aed", "base_ctr", "kind"],
)

COUNTRIES = [  # code, name, traffic share, cpc multiplier, AOV AED, conv multiplier
    ("AE", "UAE", 0.45, 1.00, 118, 1.00),
    ("SA", "Saudi Arabia", 0.30, 0.88, 104, 0.92),
    ("QA", "Qatar", 0.12, 1.12, 131, 1.05),
    ("OM", "Oman", 0.07, 0.72, 92, 0.85),
    ("BH", "Bahrain", 0.06, 0.80, 98, 0.90),
]
dim_country = pd.DataFrame(COUNTRIES, columns=["country_code", "country", "share", "cpc_mult", "aov_aed", "conv_mult"])

DEVICES = [  # name, traffic share, conv multiplier, engagement multiplier
    ("Mobile", 0.72, 0.85, 0.94),
    ("Desktop", 0.23, 1.32, 1.12),
    ("Tablet", 0.05, 1.05, 1.00),
]
dim_device = pd.DataFrame(DEVICES, columns=["device", "share", "conv_mult", "engagement_mult"])

# --------------------------------------------------------------------------
# 2. Calendar and seasonality
# --------------------------------------------------------------------------
dates = pd.date_range(START, END, freq="D")
dim_date = pd.DataFrame({"date": dates})
dim_date["year"] = dim_date.date.dt.year
dim_date["quarter"] = "Q" + dim_date.date.dt.quarter.astype(str)
dim_date["month_num"] = dim_date.date.dt.month
dim_date["month"] = dim_date.date.dt.strftime("%b")
dim_date["year_month"] = dim_date.date.dt.strftime("%Y-%m")
dim_date["week_start"] = (dim_date.date - pd.to_timedelta(dim_date.date.dt.weekday, unit="D")).dt.date
dim_date["weekday"] = dim_date.date.dt.strftime("%a")
dim_date["weekday_num"] = dim_date.date.dt.weekday
# Thu-Sat are the strongest entertainment days in the GCC
dim_date["is_peak_day"] = dim_date.weekday_num.isin([3, 4, 5]).astype(int)

EVENTS = {  # name: (start, end, traffic lift, conversion lift, promo intensity)
    "Ramadan 2024": ("2024-03-11", "2024-04-09", 1.10, 0.92, 0.6),
    "Eid Al Fitr 2024": ("2024-04-10", "2024-04-14", 1.65, 1.30, 1.0),
    "Summer Promo 2024": ("2024-07-01", "2024-08-15", 0.86, 1.05, 0.5),
    "White Friday 2024": ("2024-11-22", "2024-12-01", 1.55, 1.45, 1.2),
    "Dubai Shopping Festival 24/25": ("2024-12-05", "2025-01-12", 1.30, 1.18, 0.9),
    "Ramadan 2025": ("2025-03-01", "2025-03-29", 1.10, 0.92, 0.6),
    "Eid Al Fitr 2025": ("2025-03-30", "2025-04-03", 1.68, 1.32, 1.0),
    "Summer Promo 2025": ("2025-07-01", "2025-08-15", 0.86, 1.05, 0.5),
    "White Friday 2025": ("2025-11-21", "2025-11-30", 1.58, 1.48, 1.2),
    "Dubai Shopping Festival 25/26": ("2025-12-04", "2025-12-31", 1.30, 1.18, 0.9),
}
traffic_season = np.ones(len(dates))
conv_season = np.ones(len(dates))
promo = np.zeros(len(dates))
event_name = np.array([""] * len(dates), dtype=object)
for name, (s, e, t, c, p) in EVENTS.items():
    m = (dates >= s) & (dates <= e)
    traffic_season[m] *= t
    conv_season[m] *= c
    promo[m] = p
    event_name[m] = name
dim_date["event"] = event_name

weekday_lift = np.array([0.90, 0.92, 0.96, 1.10, 1.22, 1.24, 1.02])[dates.weekday]
trend = 1 + 0.16 * np.arange(len(dates)) / len(dates)  # organic growth across the two years
day_idx = np.arange(len(dates))

# --------------------------------------------------------------------------
# 3. Daily grain simulation  (date x campaign x country x device)
# --------------------------------------------------------------------------
n_d, n_c, n_k, n_v = len(dates), len(CAMPAIGNS), len(COUNTRIES), len(DEVICES)
shape = (n_d, n_c, n_k, n_v)

country_share = dim_country.share.values[None, None, :, None]
device_share = dim_device.share.values[None, None, None, :]
cpc_mult = dim_country.cpc_mult.values[None, None, :, None]
conv_country = dim_country.conv_mult.values[None, None, :, None]
conv_device = dim_device.conv_mult.values[None, None, None, :]
eng_device = dim_device.engagement_mult.values[None, None, None, :]

day = lambda a: a[:, None, None, None]
noise = lambda s=0.10: rng.lognormal(0, s, shape)

budget = dim_campaign.daily_budget_aed.values[None, :, None, None].astype(float)
base_cpc = dim_campaign.base_cpc_aed.values[None, :, None, None]
base_ctr = dim_campaign.base_ctr.values[None, :, None, None]
is_paid = (dim_campaign.kind.values == "paid")[None, :, None, None]

# Paid spend: budget scaled by season, with campaign-specific promo response
promo_response = np.array([0.15, 0.25, 0.45, 0.30, 0.40, 0.55, 1.20, 0.50, 0.35, 0.05, 0, 0, 0, 0])[None, :, None, None]
spend_scale = (1 + day(promo) * promo_response) * day(1 + 0.05 * np.sin(day_idx / 45)) * day(np.where(dates.year == 2025, 1.10, 1.0))
spend = budget * spend_scale * country_share * device_share * noise(0.08)
spend = np.where(is_paid, spend, 0.0)

# Efficiency drift: TikTok gets pricier, Meta prospecting fatigues late 2025
cpc_drift = np.ones(shape)
tiktok = np.isin(dim_campaign.platform.values, ["TikTok Ads"])[None, :, None, None]
cpc_drift = np.where(tiktok, cpc_drift * day(1 + 0.22 * day_idx / n_d), cpc_drift)
meta_pro = (dim_campaign.campaign_id.values == 5)[None, :, None, None]
ctr_drift = np.where(meta_pro, day(1 - 0.20 * np.clip((day_idx - 420) / 311, 0, 1)), 1.0)

cpc = base_cpc * cpc_mult * cpc_drift * noise(0.06) * day(1 + 0.10 * (promo > 0))
ctr = base_ctr * eng_device * ctr_drift * noise(0.06)
clicks = np.where(is_paid, spend / np.where(cpc == 0, 1, cpc), 0.0)
impressions = np.where(is_paid, clicks / np.where(ctr == 0, 1, ctr), 0.0)

# Sessions: paid sessions come from clicks (some lost to tracking/bounce); owned channels use baselines
paid_sessions = clicks * 0.93
owned_base = {11: 5200, 12: 2300, 13: 3600, 14: 780}  # daily sessions, whole GCC
owned_sessions = np.zeros(shape)
for cid, base in owned_base.items():
    idx = cid - 1
    growth = 1 + (0.30 if cid == 11 else 0.05) * day_idx / n_d
    owned_sessions[:, idx] = (base * day(growth * traffic_season * weekday_lift)[:, 0] * country_share[:, 0] * device_share[:, 0]
                               * noise(0.08)[:, idx])
# email is driven by send calendar: heavier on promo days
owned_sessions[:, 11] *= day(1 + 0.8 * promo)[:, 0]
sessions = np.where(is_paid, paid_sessions * day(weekday_lift * (0.7 + 0.3 * traffic_season)), owned_sessions)

# Funnel rates (base, by campaign intent)
eng_rate = np.array([.82, .70, .68, .40, .58, .74, .62, .48, .44, .66, .72, .78, .70, .68])[None, :, None, None] * eng_device
atc_rate = np.array([.30, .17, .19, .05, .09, .26, .14, .07, .05, .10, .14, .24, .22, .12])[None, :, None, None]
chk_rate = np.full((1, n_c, 1, 1), 0.52)
pur_rate = np.array([.68, .56, .58, .46, .50, .66, .57, .48, .45, .60, .62, .70, .69, .56])[None, :, None, None]

cs = day(conv_season) * conv_country * conv_device
engaged = sessions * eng_rate * noise(0.03)
carts = sessions * atc_rate * cs * noise(0.06)
checkouts = carts * chk_rate * noise(0.05)
purchases = checkouts * pur_rate * noise(0.05)
new_users = sessions * np.array([.62, .55, .70, .90, .80, .22, .74, .88, .90, .70, .58, .18, .28, .55])[None, :, None, None]
new_users = new_users * noise(0.03)

aov_country = dim_country.aov_aed.values[None, None, :, None]
aov_campaign = np.array([1.00, 1.04, 1.02, 0.96, 1.00, 1.06, 0.92, 0.90, 0.88, 1.85, 1.02, 1.10, 1.08, 1.00])[None, :, None, None]
aov = aov_country * aov_campaign * day(1 + 0.18 * (promo > 0) - 0.12 * (promo >= 1.0)) * noise(0.07)
revenue = purchases * aov

# --------------------------------------------------------------------------
# 4. Inject realistic data-quality incidents (used by the anomaly detector)
# --------------------------------------------------------------------------
def rows_for(start, end):
    return (dates >= start) & (dates <= end)

# a) GA4 tag broke after a site release: 3 days of under-reported sessions/purchases
m = rows_for("2025-06-10", "2025-06-12")
for arr in (sessions, engaged, carts, checkouts, purchases, revenue, new_users):
    arr[m] *= 0.38
# b) Budget mis-set on Meta Prospecting: spend spike for 2 days
mask_days = np.where(rows_for("2024-09-18", "2024-09-19"))[0]
spend[mask_days, 4] *= 4.2
clicks[mask_days, 4] *= 3.6
impressions[mask_days, 4] *= 3.4
sessions[mask_days, 4] *= 3.3
# c) Viral organic spike (press coverage of a big premiere)
m = np.where(rows_for("2025-02-20", "2025-02-21"))[0]
for arr in (sessions, engaged, carts, checkouts, purchases, revenue, new_users):
    arr[m, 10] *= 4.5

# --------------------------------------------------------------------------
# 5. Flatten to tidy tables
# --------------------------------------------------------------------------
def flat(a):
    return a.reshape(-1)

di, ci, ki, vi = np.meshgrid(np.arange(n_d), np.arange(n_c), np.arange(n_k), np.arange(n_v), indexing="ij")
df = pd.DataFrame({
    "date": dates[flat(di)],
    "campaign_id": dim_campaign.campaign_id.values[flat(ci)],
    "country_code": dim_country.country_code.values[flat(ki)],
    "device": dim_device.device.values[flat(vi)],
    "impressions": flat(impressions), "clicks": flat(clicks), "spend_aed": flat(spend),
    "sessions": flat(sessions), "engaged_sessions": flat(engaged), "new_users": flat(new_users),
    "add_to_cart": flat(carts), "begin_checkout": flat(checkouts),
    "purchases": flat(purchases), "revenue_aed": flat(revenue),
})

# --- site daily
site_daily = df.groupby("date", as_index=False)[
    ["impressions", "clicks", "spend_aed", "sessions", "engaged_sessions", "new_users",
     "add_to_cart", "begin_checkout", "purchases", "revenue_aed"]].sum()
site_daily = site_daily.merge(dim_date[["date", "weekday", "event"]], on="date")

# --- weekly fact (star-schema friendly, smaller)
df = df.merge(dim_date[["date", "week_start"]], on="date")
weekly = df.groupby(["week_start", "campaign_id", "country_code", "device"], as_index=False)[
    ["impressions", "clicks", "spend_aed", "sessions", "engaged_sessions", "new_users",
     "add_to_cart", "begin_checkout", "purchases", "revenue_aed"]].sum()
count_cols = ["impressions", "clicks", "sessions", "engaged_sessions", "new_users", "add_to_cart", "begin_checkout", "purchases"]
weekly[count_cols] = weekly[count_cols].round().astype(int)
weekly[["spend_aed", "revenue_aed"]] = weekly[["spend_aed", "revenue_aed"]].round(2)
weekly = weekly.sort_values(["week_start", "campaign_id", "country_code", "device"]).reset_index(drop=True)

for c in count_cols:
    site_daily[c] = site_daily[c].round().astype(int)
site_daily[["spend_aed", "revenue_aed"]] = site_daily[["spend_aed", "revenue_aed"]].round(2)

# --------------------------------------------------------------------------
# 6. Cohort retention (monthly acquisition cohorts)
# --------------------------------------------------------------------------
months = pd.period_range("2024-01", "2025-12", freq="M")
new_by_month = (site_daily.assign(ym=site_daily.date.dt.to_period("M")).groupby("ym").purchases.sum() * 0.62).round()
rows = []
for i, ym in enumerate(months):
    size = int(new_by_month[ym])
    for k in range(0, len(months) - i):
        # retention decays quickly, then flattens; loyalty programme lifts month 3 and 6
        base = 1.0 if k == 0 else 0.34 * np.exp(-0.34 * (k - 1)) + 0.075
        if k in (3, 6):
            base *= 1.12
        if ym.month in (11, 12):  # promo-acquired cohorts retain worse
            base *= 0.86 if k else 1
        share = min(1.0, base * rng.lognormal(0, 0.04))
        rows.append([str(ym), k, size, int(round(size * share))])
cohort = pd.DataFrame(rows, columns=["cohort_month", "months_since", "cohort_size", "active_customers"])

# --------------------------------------------------------------------------
# 7. Write files
# --------------------------------------------------------------------------
dim_date.assign(date=dim_date.date.dt.date).to_csv(OUT / "dim_date.csv", index=False)
dim_campaign.to_csv(OUT / "dim_campaign.csv", index=False)
dim_country.drop(columns=["share", "cpc_mult", "conv_mult"]).to_csv(OUT / "dim_country.csv", index=False)
dim_device.drop(columns=["share", "conv_mult", "engagement_mult"]).to_csv(OUT / "dim_device.csv", index=False)
weekly.to_csv(OUT / "fact_performance_weekly.csv", index=False)
site_daily.assign(date=site_daily.date.dt.date).to_csv(OUT / "fact_site_daily.csv", index=False)
cohort.to_csv(OUT / "fact_cohort_retention.csv", index=False)

print(f"weekly fact rows : {len(weekly):,}")
print(f"daily site rows  : {len(site_daily):,}")
print(f"total revenue    : AED {site_daily.revenue_aed.sum():,.0f}")
print(f"total spend      : AED {site_daily.spend_aed.sum():,.0f}")
