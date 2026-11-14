import importlib.util
import os
import subprocess
import sys
import tempfile

import pytest

if importlib.util.find_spec("airflow") is None:
    pytest.skip("apache-airflow is not installed", allow_module_level=True)

# Give Airflow a throwaway metadata database so loading the DAG does not touch a real one.
_home = tempfile.mkdtemp()
os.environ["AIRFLOW_HOME"] = _home
os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = f"sqlite:///{_home}/airflow.db"
try:
    subprocess.run([sys.executable, "-m", "airflow", "db", "migrate"], check=True, capture_output=True)
except Exception:   # Airflow missing, half-installed, or not supported on this OS (for example Windows)
    pytest.skip("Airflow could not start here, so the DAG test was skipped", allow_module_level=True)


def test_dag_loads_and_has_the_right_order():
    from airflow.models import DagBag
    folder = os.path.join(os.path.dirname(__file__), "..", "airflow", "dags")
    bag = DagBag(dag_folder=folder, include_examples=False)
    assert bag.import_errors == {}
    dag = bag.dags["econ_indicators_weekly"]
    order = ["load_raw", "dbt_staging_checks", "dbt_marts", "forecast", "dbt_reporting"]
    assert [t.task_id for t in dag.topological_sort()] == order
    assert dag.default_args["retries"] == 2 and dag.catchup is False
    assert "tag:staging" in dag.get_task("dbt_staging_checks").bash_command
