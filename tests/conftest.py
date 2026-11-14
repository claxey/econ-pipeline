import os

import pytest


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    """A Postgres to test against: TEST_WAREHOUSE_URL if set, otherwise an embedded one from pgserver."""
    url = os.environ.get("TEST_WAREHOUSE_URL")
    if url:
        yield url
        return
    pgserver = pytest.importorskip("pgserver")
    srv = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    yield srv.get_uri().replace("postgresql://", "postgresql+psycopg2://")
    srv.cleanup()
