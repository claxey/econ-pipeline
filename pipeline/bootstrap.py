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
    """Return True if it had to build the data, False if the data was already there."""
    con = connect(db_path)
    try:
        if con.execute("SELECT COUNT(*) FROM observations").fetchone()[0] > 0:
            return False
        config = yaml.safe_load(open(config_path))
        collect.run(con, config, session)
        forecast.run(con)
        tracker.build(con, config, tracker_path)
        if con.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0:
            raise RuntimeError("The download finished but no data was loaded. Check the Run log.")
        return True
    finally:
        con.close()
