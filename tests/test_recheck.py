import threading
import time

from pipeline import collect, recheck
from pipeline.db import connect
from tests.test_pipeline import CONFIG, FakeSession, FakeResp, make_payload

TWO = {**CONFIG, "sources": [
    {"id": "a", "name": "A", "provider": "WB", "indicator": "A", "docs_url": "x", "frequency": "annual"},
    {"id": "b", "name": "B", "provider": "WB", "indicator": "B", "docs_url": "x", "frequency": "annual"}]}


def test_no_changes_when_data_matches(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    collect.run(con, TWO, FakeSession(), raw_dir=str(tmp_path / "raw"))
    out = recheck.run(con, TWO, FakeSession())
    assert all(s["new"] == 0 and s["revised"] == 0 and s["missing_live"] == 0 for s in out["sources"])


def test_detects_revised_new_and_missing(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    collect.run(con, TWO, FakeSession(), raw_dir=str(tmp_path / "raw"))
    con.execute("UPDATE observations SET value = value + 1 WHERE source_id='a' AND year=2015")   # revised
    con.execute("DELETE FROM observations WHERE source_id='a' AND year=2023")                      # new
    con.execute("INSERT INTO observations VALUES ('a','IND',1999,3.0)")                            # missing live
    con.commit()
    out = recheck.run(con, TWO, FakeSession())
    a = [s for s in out["sources"] if s["source_id"] == "a"][0]
    assert (a["new"], a["revised"], a["missing_live"]) == (1, 1, 1)
    kinds = {r[0] for r in con.execute("SELECT kind FROM revisions")}
    assert kinds == {"new", "revised", "missing_live"}
    # report only: stored value unchanged
    assert con.execute("SELECT value FROM observations WHERE source_id='a' AND year=2015").fetchone()[0] != 5.0 + 0.1 * 15
    recheck.run(con, TWO, FakeSession(), apply=True)
    assert abs(con.execute("SELECT value FROM observations WHERE source_id='a' AND year=2015").fetchone()[0] - 6.5) < 1e-9


def test_sources_are_fetched_at_the_same_time(tmp_path):
    active, peak, lock = [0], [0], threading.Lock()

    class Slow:
        def get(self, url, params=None, timeout=None):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.3)
            with lock:
                active[0] -= 1
            return FakeResp(make_payload(params["page"], 2))

    con = connect(str(tmp_path / "t.db"))
    out = recheck.run(con, TWO, Slow(), max_workers=2)
    assert peak[0] == 2
    assert out["wall_seconds"] < out["sum_of_source_seconds"]


def test_one_failing_source_does_not_stop_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(collect.time, "sleep", lambda s: None)

    class Mixed:
        def get(self, url, params=None, timeout=None):
            if url.endswith("/A"):
                raise ValueError("boom")
            return FakeResp(make_payload(params["page"], 2))

    con = connect(str(tmp_path / "t.db"))
    out = recheck.run(con, TWO, Mixed())
    status = {s["source_id"]: s["status"] for s in out["sources"]}
    assert status == {"a": "error", "b": "ok"}
