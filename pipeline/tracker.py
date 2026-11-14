"""Resource tracker: one row per source with URL, cadence, last provider update and last successful pull."""
import pandas as pd


def build(con, config, path="data/resource_tracker.csv"):
    log = pd.read_sql(
        "SELECT source_id, MAX(run_ts) AS last_success, provider_last_updated "
        "FROM ingest_log WHERE status='ok' GROUP BY source_id", con)
    last = log.set_index("source_id").to_dict("index")
    rows = []
    for s in config["sources"]:
        info = last.get(s["id"], {})
        rows.append({
            "source_id": s["id"], "name": s["name"], "provider": s["provider"],
            "indicator_code": s["indicator"], "url": s["docs_url"], "frequency": s["frequency"],
            "provider_last_updated": info.get("provider_last_updated", ""),
            "last_successful_pull": info.get("last_success", ""),
        })
    out = pd.DataFrame(rows)
    out.to_csv(path, index=False)
    return out
