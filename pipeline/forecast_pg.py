"""Forecast step for the warehouse: reads the cleaned marts table, writes forecasts.indicator_forecasts."""
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import text

from pipeline.forecast import MIN_POINTS, forecast_series

DDL = [
    "CREATE SCHEMA IF NOT EXISTS forecasts",
    """CREATE TABLE IF NOT EXISTS forecasts.indicator_forecasts (
        run_id text NOT NULL, created_at timestamptz NOT NULL, source_id text NOT NULL,
        country_code text NOT NULL, year integer NOT NULL, forecast double precision,
        lower double precision, upper double precision, model text)""",
]


def run(engine, run_id, horizon=3):
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))
        rows = conn.execute(text(
            "SELECT source_id, country_code, year, value FROM marts.fct_indicator_yearly")).fetchall()
    df = pd.DataFrame(rows, columns=["source_id", "country_code", "year", "value"])
    df["value"] = df["value"].astype(float)
    created_at = datetime.now(timezone.utc)
    out, skipped = [], []
    for (sid, country), g in df.groupby(["source_id", "country_code"]):
        if len(g) < MIN_POINTS:
            skipped.append(f"{sid}/{country}")
            continue
        fc = forecast_series(g.set_index("year")["value"], horizon)
        for r in fc.itertuples():
            out.append({"run_id": run_id, "created_at": created_at, "source_id": sid, "country_code": country,
                        "year": int(r.year), "forecast": float(r.forecast),
                        "lower": None if pd.isna(r.lower) else float(r.lower),
                        "upper": None if pd.isna(r.upper) else float(r.upper), "model": r.model})
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM forecasts.indicator_forecasts WHERE run_id = :r"), {"r": run_id})
        if out:
            conn.execute(text(
                "INSERT INTO forecasts.indicator_forecasts VALUES "
                "(:run_id, :created_at, :source_id, :country_code, :year, :forecast, :lower, :upper, :model)"), out)
    return {"forecast_rows": len(out), "skipped_short_series": skipped}
