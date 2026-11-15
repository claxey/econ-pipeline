"""Build the database on first start.

Hosts like Streamlit Community Cloud start with a fresh copy of the repo and do not keep
files between restarts, so the database is not there. This downloads the data and builds
it when it is missing or empty.
"""
import yaml

from pipeline import collect, forecast, tracker
from pipeline.db import connect


def ensure_data(db_path="data/indicators.db", config_path="sources.yaml",
                tracker_path="data/resource_tracker.csv", session=None):
    """Build missing indicator data; return True when a collection was attempted."""
    con = connect(db_path)
    try:
        config = yaml.safe_load(open(config_path, encoding="utf-8"))
        expected = {src["id"] for src in config.get("sources", [])}
        loaded = {row[0] for row in con.execute(
            "SELECT DISTINCT source_id FROM observations").fetchall()}
        missing = expected - loaded
        if not missing:
            return False
        pending_config = dict(config)
        pending_config["sources"] = [
            src for src in config.get("sources", []) if src["id"] in missing
        ]
        collect.run(con, pending_config, session)
        forecast.run(con)
        tracker.build(con, config, tracker_path)
        if con.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0:
            raise RuntimeError("The download finished but no data was loaded. Check the Run log.")
        return True
    finally:
        con.close()
