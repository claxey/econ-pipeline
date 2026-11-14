"""Raw layer in Postgres.

Every run APPENDS rows to raw.world_bank_observations, tagged with a run_id and a load time.
Nothing is overwritten, so the full history of every value (including revisions) is kept.
Re-running the same run_id replaces that run's rows only, so a retried Airflow task is safe.

Works with SQLAlchemy 1.4 (what Airflow pins) and 2.x.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from pipeline import collect

RAW_DDL = [
    "CREATE SCHEMA IF NOT EXISTS raw",
    """CREATE TABLE IF NOT EXISTS raw.world_bank_observations (
        run_id text NOT NULL, loaded_at timestamptz NOT NULL,
        source_id text NOT NULL, country text NOT NULL, year integer NOT NULL,
        value double precision, provider_last_updated text, raw_sha256 text)""",
    """CREATE INDEX IF NOT EXISTS idx_wbo_key
        ON raw.world_bank_observations (source_id, country, year)""",
    """CREATE TABLE IF NOT EXISTS raw.ingest_runs (
        run_id text NOT NULL, loaded_at timestamptz NOT NULL, source_id text NOT NULL,
        status text NOT NULL, rows_loaded integer, raw_file text, raw_sha256 text,
        provider_last_updated text, message text)""",
    """CREATE TABLE IF NOT EXISTS raw.source_catalog (
        source_id text PRIMARY KEY, name text, provider text, indicator_code text,
        docs_url text, frequency text)""",
]


def get_engine(url=None):
    url = url or os.environ.get("WAREHOUSE_URL")
    if not url:
        raise RuntimeError("Set WAREHOUSE_URL, e.g. postgresql+psycopg2://user:pass@host:5432/db")
    return create_engine(url)


def ensure_raw_schema(engine):
    with engine.begin() as conn:
        for stmt in RAW_DDL:
            conn.execute(text(stmt))


def _save_catalog(engine, config):
    rows = [{"source_id": s["id"], "name": s["name"], "provider": s["provider"],
             "indicator_code": s["indicator"], "docs_url": s["docs_url"], "frequency": s["frequency"]}
            for s in config["sources"]]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM raw.source_catalog"))
        conn.execute(text(
            "INSERT INTO raw.source_catalog VALUES "
            "(:source_id, :name, :provider, :indicator_code, :docs_url, :frequency)"), rows)


def load_raw(engine, config, run_id, session=None, raw_dir="data/raw", max_workers=4):
    """Download all sources at the same time, then write them to the raw layer one source at a time.

    A source that fails is logged in raw.ingest_runs. The good sources are still loaded, and
    the function raises at the end so the Airflow task shows as failed and gets retried.
    """
    ensure_raw_schema(engine)
    _save_catalog(engine, config)
    loaded_at = datetime.now(timezone.utc)
    results = collect.fetch_many(config, session, max_workers)
    summary, failed = [], []
    for src in config["sources"]:
        sid = src["id"]
        res, err, _ = results[sid]
        try:
            if err:
                raise err
            rows, updated, pages = res
            raw_file, digest = collect.save_raw(pages, sid, raw_dir)
            params = [{"run_id": run_id, "loaded_at": loaded_at, "source_id": sid, "country": c,
                       "year": y, "value": v, "updated": updated, "sha": digest} for c, y, v in rows]
            with engine.begin() as conn:    # one transaction: delete this run's rows, insert, log
                conn.execute(text("DELETE FROM raw.world_bank_observations "
                                  "WHERE run_id = :r AND source_id = :s"), {"r": run_id, "s": sid})
                conn.execute(text("DELETE FROM raw.ingest_runs WHERE run_id = :r AND source_id = :s"),
                             {"r": run_id, "s": sid})
                if params:
                    conn.execute(text(
                        "INSERT INTO raw.world_bank_observations VALUES "
                        "(:run_id, :loaded_at, :source_id, :country, :year, :value, :updated, :sha)"), params)
                conn.execute(text(
                    "INSERT INTO raw.ingest_runs VALUES "
                    "(:r, :t, :s, 'ok', :n, :f, :sha, :u, '')"),
                    {"r": run_id, "t": loaded_at, "s": sid, "n": sum(1 for p in params if p["value"] is not None),
                     "f": raw_file, "sha": digest, "u": updated})
            summary.append({"source_id": sid, "status": "ok", "rows": len(params)})
        except Exception as exc:
            failed.append(sid)
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM raw.ingest_runs WHERE run_id = :r AND source_id = :s"),
                             {"r": run_id, "s": sid})
                conn.execute(text(
                    "INSERT INTO raw.ingest_runs VALUES (:r, :t, :s, 'error', 0, '', '', '', :m)"),
                    {"r": run_id, "t": loaded_at, "s": sid, "m": str(exc)[:300]})
            summary.append({"source_id": sid, "status": "error", "message": str(exc)[:120]})
    if failed:
        raise RuntimeError(f"Sources failed: {', '.join(failed)}. The other sources were loaded.")
    return summary
