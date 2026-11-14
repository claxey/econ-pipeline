import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    source_id TEXT, country TEXT, year INTEGER, value REAL,
    PRIMARY KEY (source_id, country, year)
);
CREATE TABLE IF NOT EXISTS ingest_log (
    run_ts TEXT, source_id TEXT, rows INTEGER, status TEXT,
    raw_file TEXT, sha256 TEXT, provider_last_updated TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS forecasts (
    source_id TEXT, country TEXT, year INTEGER, forecast REAL,
    lower REAL, upper REAL, model TEXT, run_ts TEXT,
    PRIMARY KEY (source_id, country, year, run_ts)
);
CREATE TABLE IF NOT EXISTS revisions (
    run_ts TEXT, source_id TEXT, country TEXT, year INTEGER,
    kind TEXT, old_value REAL, new_value REAL
);
CREATE TABLE IF NOT EXISTS recheck_log (
    run_ts TEXT, source_id TEXT, status TEXT, new_rows INTEGER,
    revised_rows INTEGER, missing_rows INTEGER, seconds REAL, message TEXT
);
"""


def connect(path="data/indicators.db"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con
