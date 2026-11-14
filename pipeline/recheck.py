"""Re-check stored data against the live source.

All sources are fetched at the same time. Each live value is compared with what is in
the database, and every difference is written to the `revisions` table:
  new           the source now has a year we do not have
  revised       the source changed a value we already have
  missing_live  we have a value the source no longer returns
Nothing in `observations` changes unless apply=True.
"""
import time
from datetime import datetime, timezone

from pipeline import collect

TOLERANCE = 1e-9


def compare(con, source_id, rows):
    live = {(c, y): v for c, y, v in rows if v is not None}
    db = {(c, y): v for c, y, v in con.execute(
        "SELECT country, year, value FROM observations WHERE source_id=?", (source_id,))}
    changes = []
    for key, v in sorted(live.items()):
        if key not in db:
            changes.append(("new", key, None, v))
        elif abs(db[key] - v) > TOLERANCE:
            changes.append(("revised", key, db[key], v))
    for key, v in sorted(db.items()):
        if key not in live:
            changes.append(("missing_live", key, v, None))
    return changes


def run(con, config, session=None, max_workers=4, apply=False):
    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.perf_counter()
    results = collect.fetch_many(config, session, max_workers)
    wall = time.perf_counter() - t0
    summary = []
    for src in config["sources"]:
        res, err, secs = results[src["id"]]
        if err:
            con.execute("INSERT INTO recheck_log VALUES (?,?,?,?,?,?,?,?)",
                        (run_ts, src["id"], "error", 0, 0, 0, secs, str(err)[:300]))
            summary.append({"source_id": src["id"], "status": "error", "message": str(err)[:120]})
            continue
        rows, _, _ = res
        changes = compare(con, src["id"], rows)
        con.executemany("INSERT INTO revisions VALUES (?,?,?,?,?,?,?)",
                        [(run_ts, src["id"], k[0], k[1], kind, old, new)
                         for kind, k, old, new in changes])
        counts = {kind: sum(1 for c in changes if c[0] == kind)
                  for kind in ("new", "revised", "missing_live")}
        con.execute("INSERT INTO recheck_log VALUES (?,?,?,?,?,?,?,?)",
                    (run_ts, src["id"], "ok", counts["new"], counts["revised"],
                     counts["missing_live"], secs, ""))
        if apply and changes:
            collect.load(con, src["id"], rows)
        summary.append({"source_id": src["id"], "status": "ok", **counts})
        con.commit()
    con.commit()
    total_sequential = sum(r[2] for r in results.values())
    return {"sources": summary, "wall_seconds": wall, "sum_of_source_seconds": total_sequential}
