import pytest
from sqlalchemy import text

from pipeline import forecast_pg, warehouse
from tests.test_pipeline import CONFIG, FakeSession

TWO = {**CONFIG, "sources": [
    {"id": "a", "name": "A", "provider": "WB", "indicator": "A", "docs_url": "x", "frequency": "annual"},
    {"id": "b", "name": "B", "provider": "WB", "indicator": "B", "docs_url": "x", "frequency": "annual"}]}


@pytest.fixture()
def engine(pg_url):
    e = warehouse.get_engine(pg_url)
    with e.begin() as c:
        for s in ("raw", "marts", "forecasts"):
            c.execute(text(f"DROP SCHEMA IF EXISTS {s} CASCADE"))
    return e


def scalar(engine, sql, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar()


def test_load_appends_and_keeps_history(engine, tmp_path):
    warehouse.load_raw(engine, TWO, "run-1", FakeSession(), raw_dir=str(tmp_path))
    n1 = scalar(engine, "select count(*) from raw.world_bank_observations")
    warehouse.load_raw(engine, TWO, "run-2", FakeSession(), raw_dir=str(tmp_path))
    assert scalar(engine, "select count(*) from raw.world_bank_observations") == 2 * n1
    assert scalar(engine, "select count(distinct run_id) from raw.world_bank_observations") == 2


def test_rerunning_same_run_id_is_idempotent(engine, tmp_path):
    for _ in range(3):
        warehouse.load_raw(engine, TWO, "run-1", FakeSession(), raw_dir=str(tmp_path))
    assert scalar(engine, "select count(*) from raw.world_bank_observations") == 2 * 24
    assert scalar(engine, "select count(*) from raw.ingest_runs") == 2
    assert scalar(engine, "select count(*) from raw.source_catalog") == 2


def test_failed_source_is_logged_good_source_still_loads_and_task_fails(engine, tmp_path, monkeypatch):
    from pipeline import collect
    monkeypatch.setattr(collect.time, "sleep", lambda s: None)

    class Mixed:
        def get(self, url, params=None, timeout=None):
            if url.endswith("/A"):
                raise ValueError("boom")
            return FakeSession().get(url, params, timeout)

    with pytest.raises(RuntimeError, match="a"):
        warehouse.load_raw(engine, TWO, "run-1", Mixed(), raw_dir=str(tmp_path))
    assert scalar(engine, "select status from raw.ingest_runs where source_id='a'") == "error"
    assert scalar(engine, "select status from raw.ingest_runs where source_id='b'") == "ok"
    assert scalar(engine, "select count(*) from raw.world_bank_observations where source_id='b'") == 24


def test_forecast_reads_marts_and_is_idempotent(engine):
    with engine.begin() as c:
        c.execute(text("create schema marts"))
        c.execute(text("create table marts.fct_indicator_yearly (source_id text, country_code text, "
                       "year int, value numeric)"))
        c.execute(text("insert into marts.fct_indicator_yearly select 'a','IND', y, 5 + 0.1*(y-2000) "
                       "from generate_series(2000, 2023) y"))
        c.execute(text("insert into marts.fct_indicator_yearly select 'a','CHN', y, 3 "
                       "from generate_series(2018, 2023) y"))   # too short to forecast
    out = forecast_pg.run(engine, "run-1")
    forecast_pg.run(engine, "run-1")
    assert out["skipped_short_series"] == ["a/CHN"]
    assert scalar(engine, "select count(*) from forecasts.indicator_forecasts") == 3
    assert scalar(engine, "select min(year) from forecasts.indicator_forecasts") == 2024
