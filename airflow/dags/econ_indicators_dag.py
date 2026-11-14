"""Weekly economic-indicator pipeline.

load_raw  ->  dbt_staging_checks  ->  dbt_marts  ->  forecast  ->  dbt_reporting

* load_raw             downloads every source at the same time and appends it to the raw layer in Postgres
* dbt_staging_checks   builds the cleaned staging view and runs the data quality tests on it (nulls,
                       unknown countries, impossible values). If any test fails, the run stops here.
* dbt_marts            builds the dimension and fact tables and tests them (unique keys, relationships)
* forecast             fits ARIMA models on the cleaned yearly table and stores the forecasts
* dbt_reporting        builds the final reporting table, joined with the latest forecast, and tests it
"""
import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/opt/airflow/project")
DBT_DIR = f"{PROJECT_DIR}/dbt_project"
DBT = os.environ.get("DBT_BIN", "dbt")
RAW_DIR = os.environ.get("RAW_DIR", "/opt/airflow/data/raw")

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


def load_raw_task(run_id):
    import yaml
    from pipeline import warehouse
    config = yaml.safe_load(open(f"{PROJECT_DIR}/sources.yaml"))
    return warehouse.load_raw(warehouse.get_engine(), config, run_id, raw_dir=RAW_DIR)


def forecast_task(run_id):
    from pipeline import forecast_pg, warehouse
    return forecast_pg.run(warehouse.get_engine(), run_id)


def dbt(select):
    return f"cd {DBT_DIR} && {DBT} build --select {select} --profiles-dir ."


with DAG(
    dag_id="econ_indicators_weekly",
    description="World Bank indicators: raw load, dbt models and tests, forecasts, reporting table",
    schedule="0 3 * * 1",              # every Monday at 03:00 UTC
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["economics", "dbt", "postgres"],
    doc_md=__doc__,
) as dag:
    load_raw = PythonOperator(task_id="load_raw", python_callable=load_raw_task)
    dbt_staging_checks = BashOperator(task_id="dbt_staging_checks", bash_command=dbt("tag:staging"))
    dbt_marts = BashOperator(task_id="dbt_marts", bash_command=dbt("tag:marts"))
    forecast = PythonOperator(task_id="forecast", python_callable=forecast_task)
    dbt_reporting = BashOperator(task_id="dbt_reporting", bash_command=dbt("tag:reporting"))

    load_raw >> dbt_staging_checks >> dbt_marts >> forecast >> dbt_reporting
