"""Forecast each series with ARIMA(1,1,1), falling back to a damped-trend ETS model."""
import warnings
from datetime import datetime, timezone

import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing

MIN_POINTS = 12


def forecast_series(series, horizon=3):
    """series: pandas Series indexed by integer year. Returns DataFrame year/forecast/lower/upper/model."""
    series = series.sort_index().astype(float)
    years = range(int(series.index[-1]) + 1, int(series.index[-1]) + horizon + 1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res = ARIMA(series.values, order=(1, 1, 1)).fit()
            fc = res.get_forecast(horizon)
            ci = fc.conf_int(alpha=0.2)
            return pd.DataFrame({"year": list(years), "forecast": fc.predicted_mean,
                                 "lower": ci[:, 0], "upper": ci[:, 1], "model": "ARIMA(1,1,1)"})
        except Exception:
            res = ExponentialSmoothing(series.values, trend="add", damped_trend=True).fit()
            pred = res.forecast(horizon)
            return pd.DataFrame({"year": list(years), "forecast": pred,
                                 "lower": None, "upper": None, "model": "ETS damped"})


def run(con, horizon=3):
    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    df = pd.read_sql("SELECT source_id, country, year, value FROM observations", con)
    for (source_id, country), g in df.groupby(["source_id", "country"]):
        if len(g) < MIN_POINTS:
            continue
        out = forecast_series(g.set_index("year")["value"], horizon)
        con.executemany(
            "INSERT OR REPLACE INTO forecasts VALUES (?,?,?,?,?,?,?,?)",
            [(source_id, country, int(r.year), float(r.forecast),
              None if pd.isna(r.lower) else float(r.lower),
              None if pd.isna(r.upper) else float(r.upper), r.model, run_ts)
             for r in out.itertuples()])
    con.commit()
