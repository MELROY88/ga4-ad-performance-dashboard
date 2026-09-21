"""Loads the CSVs in data/ into a SQLite file (sql/marketing.db) so sql/marketing_queries.sql can be run."""
import sqlite3
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
db = ROOT / "sql" / "marketing.db"
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
for f in sorted((ROOT / "data").glob("*.csv")):
    pd.read_csv(f).to_sql(f.stem, con, index=False)
con.execute("CREATE INDEX ix_perf ON fact_performance_weekly(campaign_id, country_code, week_start)")
con.commit(); con.close()
print("loaded ->", db)
