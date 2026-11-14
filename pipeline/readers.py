"""Read everything the dashboard needs, from either SQLite (default) or the Postgres warehouse.

Both readers return the same dict of DataFrames so the dashboard does not care which one it got:
obs, fc, log, rechecks, revisions, tracker, mode
"""
import os
import sqlite3

import pandas as pd
from sqlalchemy import text


def _frame(rows, cols):
    return pd.DataFrame([tuple(r) for r in rows], columns=cols)


def read_sqlite(db_path, tracker_path=None):
    con = sqlite3.connect(db_path)

    def q(sql):
        try:
            return pd.read_sql(sql, con)
        except Exception:      # table does not exist until the first recheck
            return pd.DataFrame()

    out = {
        "obs": q("SELECT * FROM observations"),
        "fc": q("SELECT * FROM forecasts WHERE run_ts = (SELECT MAX(run_ts) FROM forecasts)"),
        "log": q("SELECT * FROM ingest_log ORDER BY run_ts DESC"),
        "rechecks": q("SELECT * FROM recheck_log ORDER BY run_ts DESC"),
        "revisions": q("SELECT * FROM revisions ORDER BY run_ts DESC"),
        "tracker": pd.read_csv(tracker_path) if tracker_path and os.path.exists(tracker_path) else pd.DataFrame(),
        "rpt": pd.DataFrame(),
        "mode": "sqlite",
    }
    con.close()
    return out


def read_warehouse(engine):
    def q(sql, cols):
        try:
            with engine.connect() as conn:
                return _frame(conn.execute(text(sql)).fetchall(), cols)
        except Exception:
            return pd.DataFrame(columns=cols)

    obs = q("SELECT source_id, country_code, year, value FROM marts.fct_indicator_yearly",
            ["source_id", "country", "year", "value"])
    obs["value"] = obs["value"].astype(float)
    fc = q("""SELECT source_id, country_code, year, forecast, lower, upper, model
              FROM forecasts.indicator_forecasts
              WHERE created_at = (SELECT MAX(created_at) FROM forecasts.indicator_forecasts)""",
           ["source_id", "country", "year", "forecast", "lower", "upper", "model"])
    log = q("""SELECT loaded_at, source_id, rows_loaded, status, raw_file, raw_sha256,
                      provider_last_updated, message
               FROM raw.ingest_runs ORDER BY loaded_at DESC""",
            ["run_ts", "source_id", "rows", "status", "raw_file", "sha256", "provider_last_updated", "message"])
    revisions = q("""SELECT loaded_at, source_id, country_code, year, previous_value, value
                     FROM marts.fct_indicator_revisions ORDER BY loaded_at DESC""",
                  ["run_ts", "source_id", "country", "year", "old_value", "new_value"])
    if not revisions.empty:
        revisions["kind"] = "revised"
    tracker = q("""SELECT c.source_id, c.name, c.provider, c.indicator_code, c.docs_url AS url, c.frequency,
                          r.provider_last_updated, r.loaded_at AS last_successful_pull
                   FROM raw.source_catalog c
                   LEFT JOIN (SELECT source_id, provider_last_updated, loaded_at,
                                     row_number() OVER (PARTITION BY source_id ORDER BY loaded_at DESC) AS rn
                              FROM raw.ingest_runs WHERE status = 'ok') r
                          ON r.source_id = c.source_id AND r.rn = 1""",
                ["source_id", "name", "provider", "indicator_code", "url", "frequency",
                 "provider_last_updated", "last_successful_pull"])
    rpt = q("""SELECT indicator_name, source_id, country_name, country_code, latest_year, latest_value,
                      change_vs_prev_year, avg_last_5_years, rank_among_countries,
                      forecast_year, forecast_value, forecast_lower, forecast_upper
               FROM reporting.rpt_latest_indicators ORDER BY source_id, rank_among_countries""",
            ["indicator_name", "source_id", "country_name", "country_code", "latest_year", "latest_value",
             "change_vs_prev_year", "avg_last_5_years", "rank_among_countries", "forecast_year",
             "forecast_value", "forecast_lower", "forecast_upper"])
    for col in ("latest_value", "change_vs_prev_year", "avg_last_5_years", "forecast_value",
                "forecast_lower", "forecast_upper"):
        rpt[col] = pd.to_numeric(rpt[col], errors="coerce").round(2)
    return {"obs": obs, "fc": fc, "log": log, "rechecks": pd.DataFrame(), "revisions": revisions,
            "tracker": tracker, "rpt": rpt, "mode": "warehouse"}
