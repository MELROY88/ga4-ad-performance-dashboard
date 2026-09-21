"""Takes the README screenshots of the dashboard with Playwright (pip install playwright)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
url = (ROOT / "dashboard" / "index.html").as_uri()
img = ROOT / "images"; img.mkdir(exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
    pg.goto(url); pg.wait_for_timeout(600)
    pg.screenshot(path=img / "01_overview.png", clip={"x": 0, "y": 0, "width": 1440, "height": 1000})
    pg.locator("text=Campaign scorecard").first.scroll_into_view_if_needed()
    pg.screenshot(path=img / "00_full_page.png", full_page=True)
    pg.goto(url + "?year=2025&country=SA"); pg.wait_for_timeout(600)
    pg.screenshot(path=img / "02_filtered_2025_ksa.png", clip={"x": 0, "y": 0, "width": 1440, "height": 1000})
    pg.goto(url); pg.wait_for_timeout(600)
    for name, sel in [("03_campaign_scorecard.png", "text=Campaign scorecard"),
                      ("04_anomalies_timeline.png", "text=Daily sessions, events and anomalies"),
                      ("05_cohort_retention.png", "text=Customer cohort retention")]:
        el = pg.locator(sel).first.locator("xpath=ancestor::*[contains(@class,'card')][1]")
        el.screenshot(path=img / name)
    b.close()
print("done")
