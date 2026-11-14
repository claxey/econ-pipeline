import yaml

from pipeline.bootstrap import ensure_data
from pipeline.db import connect
from tests.test_pipeline import CONFIG, FakeSession


def test_builds_data_when_missing_then_skips(tmp_path):
    cfg = tmp_path / "sources.yaml"
    cfg.write_text(yaml.safe_dump(CONFIG))
    db = str(tmp_path / "newdir" / "t.db")      # folder does not exist yet
    tr = str(tmp_path / "newdir" / "tr.csv")
    assert ensure_data(db, str(cfg), tr, FakeSession()) is True
    con = connect(db)
    assert con.execute("SELECT COUNT(*) FROM observations").fetchone()[0] > 0
    assert con.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0] > 0
    assert ensure_data(db, str(cfg), tr, FakeSession()) is False
