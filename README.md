# Economic Indicator Pipeline

A small project that collects macroeconomic data automatically, stores it, forecasts it, and shows it on a dashboard.

I built it to practise the work an economic research team does every week: pulling secondary data from a public source, keeping it clean and traceable, and turning it into something you can read and forecast.

## What problem it solves

Normally, someone downloads economic data by hand, pastes it into a spreadsheet, and forgets where it came from. This project does that automatically and keeps a record of every step:

- the data is downloaded by code, not by hand
- the original download is saved, so you can always check where a number came from
- every run is logged, so you can see when data was last updated and whether anything failed
- running it again never creates duplicate rows

## What data it uses

Three indicators from the World Bank API, for India, China, the US, the UK and Japan, from 2000 onwards:

| Indicator | World Bank code |
|---|---|
| GDP growth (annual %) | NY.GDP.MKTP.KD.ZG |
| Inflation, consumer prices (annual %) | FP.CPI.TOTL.ZG |
| Unemployment (% of labour force) | SL.UEM.TOTL.ZS |

The data is annual, so each country has about one value per year.

## How it works

The pipeline has three steps. Each one is a file in the `pipeline/` folder.

1. **Collect** (`collect.py`): asks the World Bank API for each indicator, retries if the connection fails, and follows the API's pages until it has everything. It saves the raw response in `data/raw/` with a SHA-256 hash, then loads the values into SQLite. If one source fails, the others still run, and the failure is written to the log.
2. **Forecast** (`forecast.py`): for each country and indicator with at least 12 years of data, it fits an ARIMA(1,1,1) model and forecasts the next 3 years with an 80% range. If ARIMA fails on a series, it falls back to a simpler damped-trend smoothing model. The model used is saved next to each forecast.
3. **Track** (`tracker.py`): writes `data/resource_tracker.csv`, a list of every source with its URL, indicator code, how often it updates, the date the World Bank last updated it, and the date I last pulled it successfully.

`dashboard.py` is separate. It only reads what the three steps have already stored.

## Folder structure

```
econ-indicator-pipeline/
├── run.py               runs the steps
├── dashboard.py         the Streamlit dashboard
├── sources.yaml         which countries and indicators to pull
├── requirements.txt
├── docker-compose.yml   Postgres and Airflow
├── airflow/             the DAG and the Airflow image
├── dbt_project/         dbt models, seeds and tests
├── pipeline/
│   ├── db.py            creates the database tables
│   ├── collect.py       step 1
│   ├── forecast.py      step 2
│   └── tracker.py       step 3
├── tests/               automated tests
├── data/                created when you run it
│   ├── indicators.db    the SQLite database
│   ├── resource_tracker.csv
│   └── raw/             untouched API responses
└── .github/workflows/tests.yml     runs the tests on every push
```

## Rechecking against the internet

`python run.py recheck` downloads every source again, all at the same time, and compares the live data with what is stored. It does not change your data. It reports three kinds of difference:

- **new**: the source now has a year I don't have yet
- **revised**: the source changed a value I already have (the World Bank does this when it revises past years)
- **missing_live**: I have a value the source no longer returns

Every difference is saved in the `revisions` table, and each check is saved in `recheck_log`. The command also prints how long the check took compared with fetching the sources one after another. Run `python run.py recheck apply` if you also want the stored data updated to the live values.

The sources are fetched at the same time with a thread pool, because most of the time is spent waiting for the network. Each thread has its own connection, and the database is only written to one step at a time, so there are no write clashes. The `collect` step uses the same concurrent fetching.

## What is in the database

`data/indicators.db` has these tables:

- **observations**: the actual data. One row per indicator, country and year.
- **forecasts**: the predicted values, with the lower and upper range and the model used.
- **ingest_log**: one row per source per run, with the status (`ok` or `error`), number of rows loaded, the raw file name and hash, and the World Bank's last-updated date.
- **recheck_log** and **revisions**: the results of each recheck and every difference it found.

## How to run it

These are PowerShell commands. Run them from the project folder.

```powershell
pip install -r requirements.txt
python run.py all
```

`python run.py all` collects, forecasts and builds the tracker. It prints nothing when it works. To run one step on its own, type one word instead of `all`: `collect`, `forecast`, `tracker` or `recheck`.

## How to see the results

Start the dashboard:

```powershell
python -m streamlit run dashboard.py
```

It opens in your browser with a welcome note for researchers and five tabs:

- **Indicators & forecasts**: choose an indicator and countries to see the actual values and the forecast on one chart, plus the latest values and the forecast table.
- **Resource tracker**: each source with its URL and last pull.
- **Run log**: every run, with its status and row counts.
- **Recheck**: the results of each recheck and any differences found.
- **News**: recent headlines for the indicator and countries you picked (click "Load headlines").

If a number looks wrong, the log tells you which raw file it came from.

## Notes for researchers and headlines

The dashboard opens with a short welcome note that says what to keep in mind: the data is annual and lags the present, past values get revised, forecasts are simple, AI readings need checking, and headlines are context rather than evidence. Each indicator also has its own "Keep in mind" note under the chart (for example, base effects for inflation and growth, or different definitions of unemployment across countries). The text lives in `pipeline/notes.py`, so you can edit it.

Headlines come from Google News RSS, which needs no API key. For each country, the code searches the last 30 days for the country and the indicator's topic, removes duplicates, and shows the newest few. Countries are searched at the same time. The headlines are not used anywhere else: they do not change the data, the forecasts or the AI reading. Links are limited to http and https, titles are cleaned, and the RSS is parsed with `defusedxml` because it comes from the internet.

## How to add another indicator

Add an entry to `sources.yaml` with a name, the World Bank indicator code, the page URL and the frequency, then run `python run.py all` again. No code changes are needed for other World Bank indicators.

## Running it automatically

The project has two ways to run:

- **Simple mode (SQLite).** `python run.py all` and the Streamlit dashboard. This is what the Streamlit Community Cloud demo uses, because the dashboard builds its own database on first start.
- **Warehouse mode (Airflow, Postgres and dbt).** The version described in the next section. Airflow runs the pipeline every Monday, and GitHub Actions now only runs the tests.

## Warehouse mode: Airflow, Postgres and dbt

This is the part that makes the project look like a data engineering project. Airflow runs a weekly DAG, the data lands in Postgres, and dbt turns it into clean tables with tests.

```
load_raw  ->  dbt_staging_checks  ->  dbt_marts  ->  forecast  ->  dbt_reporting
```

1. **load_raw** (Python): downloads all sources at the same time and appends them to `raw.world_bank_observations`. Nothing is overwritten, so every load is kept, with a `run_id` and a load time. It also logs each source in `raw.ingest_runs`. Re-running the same run_id replaces only that run's rows, so a retry never creates duplicates. If a source fails, the other sources are still loaded and the task is marked failed so Airflow retries it.
2. **dbt_staging_checks**: builds `stg_world_bank_observations`, which keeps the latest value for each indicator, country and year, using a window function. It then runs the data quality tests. If any test fails, the run stops here, so bad data never reaches the final tables.
3. **dbt_marts**: builds the dimension and fact tables: `dim_country`, `dim_indicator`, `fct_indicator_yearly` (year-on-year change and 5-year average, using window functions) and `fct_indicator_revisions` (every time the source changed a value we already had).
4. **forecast** (Python): fits ARIMA on `fct_indicator_yearly` and stores 3-year forecasts in `forecasts.indicator_forecasts`.
5. **dbt_reporting**: builds `reporting.rpt_latest_indicators`, the final table: one row per indicator and country with the latest value, change, 5-year average, rank and next-year forecast.

### Layers

| Schema | Written by | What it holds |
|---|---|---|
| `raw` | Python | Every load, untouched, with run_id and load time |
| `staging` | dbt | One cleaned row per indicator, country and year |
| `marts` | dbt | Dimension and fact tables |
| `reporting` | dbt | The final table the dashboard reads |
| `forecasts` | Python | Forecasts per run |

### Data quality tests

| Test | What it checks | If it fails |
|---|---|---|
| `not_null` | source, country, year and value are always filled | run stops |
| `unique_combination` | one row per indicator, country and year | run stops |
| `accepted_values` | only known indicators | run stops |
| `relationships` | every country and indicator exists in its dimension table | run stops |
| `assert_values_within_expected_range` | values sit inside the ranges in `seeds/indicator_ranges.csv` | run stops |
| `assert_enough_history_for_forecast` | at least 12 years per series | warning |
| `assert_no_gaps_in_years` | no missing years inside a series | warning |
| `assert_forecast_interval_is_ordered` | lower bound is below the forecast, which is below the upper bound | run stops |

The ranges in `indicator_ranges.csv` are my own guard-rails (GDP growth -50 to 50, inflation -10 to 100, unemployment 0 to 40). They catch obvious errors, not subtle ones. Change them if your data needs it.

### Run it

You need Docker Desktop.

```powershell
docker compose up --build
```

Then open http://localhost:8080 and sign in with `admin` / `admin` (local use only). Unpause `econ_indicators_weekly` and click Trigger DAG. The warehouse is on `localhost:5433` (user, password and database are all `econ`).

To see the result in the dashboard, point it at the warehouse:

```powershell
$env:WAREHOUSE_URL = "postgresql+psycopg2://econ:econ@localhost:5433/econ"
python -m streamlit run dashboard.py
```

The dashboard then reads the dbt tables, shows the reporting table, and the Recheck tab lists the revisions found between loads. Without `WAREHOUSE_URL` it uses SQLite as before.

To run dbt by hand, set `DBT_HOST=localhost`, `DBT_PORT=5433`, `DBT_USER=econ`, `DBT_PASSWORD=econ` and `DBT_DBNAME=econ`, then run `dbt build --select tag:staging --profiles-dir .` from the `dbt_project` folder.

### Design choices

- **Why the raw layer only appends:** overwriting would lose the history, and the history is how revisions are found.
- **Why dbt is in its own virtual environment inside the Airflow image:** dbt and Airflow need different versions of some packages, and separate environments avoid the clash.
- **Why the dbt steps are split in three:** a failed test in the first step stops the DAG before the marts and the forecast run.
- **Why the data is loaded with threads:** most of the time is spent waiting on the network, while the database writes happen one source at a time.

## Tests

```powershell
pytest
```

The tests use fake API responses, so they run without internet. The warehouse tests start a small embedded Postgres (`pip install -r requirements-dev.txt` installs it), or you can set `TEST_WAREHOUSE_URL` to use your own. The DAG test only runs if Airflow is installed. They check that paging works, that missing values are skipped, that re-running does not duplicate data, that a failing source is logged without stopping the run, and that forecasts and the tracker are produced.

## Limits

- The forecasts come from a simple model fitted to about 25 yearly points per series. They show the basic trend, not a serious economic forecast.
- Annual data cannot capture fast changes. A monthly source would need a different model setup.
- Headlines are a keyword search, so some results will be off-topic. Read the title and source before you use one.
- It only reads from the World Bank API for data. A different provider would need a new collector.
- The World Bank revises past values, which the loader handles by updating existing rows, but it does not keep a history of those revisions.

## Built with

Python, pandas, requests, statsmodels, Postgres, dbt, Apache Airflow, Docker, SQLAlchemy, SQLite, Streamlit, defusedxml, Groq, pytest, GitHub Actions (tests).
