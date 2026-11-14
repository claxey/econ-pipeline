"""Collect indicator data from the World Bank API, keep the raw response, load to SQLite."""
import hashlib, json, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"


def fetch_indicator(indicator, countries, start_year, end_year, session=None, retries=3):
    """Return (rows, provider_last_updated, raw_pages). Follows API pagination with retries."""
    session = session or requests.Session()
    url = API.format(countries=";".join(countries), indicator=indicator)
    params = {"format": "json", "per_page": 1000, "date": f"{start_year}:{end_year}", "page": 1}
    rows, raw_pages, last_updated = [], [], None
    while True:
        for attempt in range(1, retries + 1):
            try:
                resp = session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                payload = resp.json()
                break
            except (requests.RequestException, ValueError):
                if attempt == retries:
                    raise
                time.sleep(2 ** attempt)
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            raise ValueError(f"Unexpected API response for {indicator}: {str(payload)[:200]}")
        meta, data = payload
        last_updated = meta.get("lastupdated")
        raw_pages.append(payload)
        for r in data:
            rows.append((r["countryiso3code"] or r["country"]["id"], int(r["date"]),
                         None if r["value"] is None else float(r["value"])))
        if params["page"] >= int(meta.get("pages", 1)):
            break
        params["page"] += 1
    return rows, last_updated, raw_pages


def save_raw(raw_pages, source_id, raw_dir="data/raw"):
    """Write the untouched API response to disk and return (path, sha256) for the audit trail."""
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    blob = json.dumps(raw_pages, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(raw_dir) / f"{source_id}_{stamp}.json"
    path.write_bytes(blob)
    return str(path), digest


def load(con, source_id, rows):
    con.executemany(
        "INSERT INTO observations VALUES (?,?,?,?) "
        "ON CONFLICT(source_id,country,year) DO UPDATE SET value=excluded.value",
        [(source_id, c, y, v) for c, y, v in rows if v is not None],
    )
    con.commit()


def fetch_many(config, session=None, max_workers=4):
    """Fetch every source at the same time (network waiting is the slow part, so threads help).

    Returns {source_id: (result, error, seconds)}. Each thread gets its own requests Session.
    Database writes are NOT done here; the caller does them one at a time.
    """
    end_year = datetime.now(timezone.utc).year

    def work(src):
        t0 = time.perf_counter()
        try:
            res = fetch_indicator(src["indicator"], config["countries"], config["start_year"],
                                  end_year, session or requests.Session())
            return src["id"], (res, None, time.perf_counter() - t0)
        except Exception as exc:
            return src["id"], (None, exc, time.perf_counter() - t0)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return dict(pool.map(work, config["sources"]))


def run(con, config, session=None, raw_dir="data/raw", max_workers=4):
    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = fetch_many(config, session, max_workers)
    for src in config["sources"]:
        res, err, _ = results[src["id"]]
        try:
            if err:
                raise err
            rows, updated, pages = res
            raw_file, digest = save_raw(pages, src["id"], raw_dir)
            load(con, src["id"], rows)
            n = sum(1 for _, _, v in rows if v is not None)
            log = (run_ts, src["id"], n, "ok", raw_file, digest, updated, "")
        except Exception as exc:  # keep going; one bad source should not stop the run
            log = (run_ts, src["id"], 0, "error", "", "", "", str(exc)[:300])
        con.execute("INSERT INTO ingest_log VALUES (?,?,?,?,?,?,?,?)", log)
        con.commit()
