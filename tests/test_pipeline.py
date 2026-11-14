import pandas as pd

from pipeline import collect, forecast, tracker
from pipeline.db import connect


def make_payload(page, pages):
    rows = [{"indicator": {"id": "X"}, "country": {"id": "IN"}, "countryiso3code": "IND",
             "date": str(y), "value": 5.0 + 0.1 * (y - 2000) if y != 2010 else None}
            for y in range(2000, 2024)]
    half = rows[:12] if page == 1 else rows[12:]
    return [{"page": page, "pages": pages, "lastupdated": "2025-07-01"}, half]


class FakeResp:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class FakeSession:
    def get(self, url, params=None, timeout=None):
        return FakeResp(make_payload(params["page"], 2))


CONFIG = {"countries": ["IND"], "start_year": 2000,
          "sources": [{"id": "gdp_growth", "name": "GDP", "provider": "World Bank",
                       "indicator": "X", "docs_url": "http://x", "frequency": "annual"}]}


def test_pagination_and_missing_values(tmp_path):
    rows, updated, pages = collect.fetch_indicator("X", ["IND"], 2000, 2023, FakeSession())
    assert len(rows) == 24 and len(pages) == 2 and updated == "2025-07-01"


def test_collect_loads_logs_and_is_idempotent(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    for _ in range(2):
        collect.run(con, CONFIG, FakeSession(), raw_dir=str(tmp_path / "raw"))
    assert con.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 23  # 2010 null skipped, no dupes
    log = con.execute("SELECT status, sha256 FROM ingest_log").fetchall()
    assert [s for s, _ in log] == ["ok", "ok"] and log[0][1] == log[1][1]


def test_bad_source_is_logged_not_fatal(tmp_path):
    class Boom:
        def get(self, *a, **k): raise ValueError("boom")
    con = connect(str(tmp_path / "t.db"))
    collect.run(con, CONFIG, Boom(), raw_dir=str(tmp_path / "raw"))
    assert con.execute("SELECT status FROM ingest_log").fetchone()[0] == "error"


def test_forecast_and_tracker(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    collect.run(con, CONFIG, FakeSession(), raw_dir=str(tmp_path / "raw"))
    forecast.run(con, horizon=3)
    f = pd.read_sql("SELECT * FROM forecasts", con)
    assert len(f) == 3 and list(f["year"]) == [2024, 2025, 2026]
    t = tracker.build(con, CONFIG, str(tmp_path / "tracker.csv"))
    assert t.loc[0, "provider_last_updated"] == "2025-07-01"
