FROM apache/airflow:2.10.5-python3.12

COPY requirements-airflow.txt /tmp/requirements-airflow.txt

# Python packages used by the load and forecast tasks, pinned to Airflow's tested versions.
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.12.txt"

# dbt lives in its own virtual environment so its dependencies cannot clash with Airflow's.
RUN python -m venv /opt/airflow/dbt-venv \
    && /opt/airflow/dbt-venv/bin/pip install --no-cache-dir "dbt-core>=1.9,<1.10" "dbt-postgres>=1.9,<1.10"

ENV DBT_BIN=/opt/airflow/dbt-venv/bin/dbt
