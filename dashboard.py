
import os
import sqlite3

import pandas as pd
import streamlit as st
import yaml

from pipeline.bootstrap import ensure_data
from pipeline.interpret import build_facts, interpret
from pipeline.readers import read_sqlite, read_warehouse
from pipeline.warehouse import get_engine
from pipeline.news import fetch_for
from pipeline.notes import INDICATOR_NOTES, WELCOME_POINTS

DB = os.environ.get("INDICATOR_DB", "data/indicators.db")
TRACKER = os.environ.get("INDICATOR_TRACKER", "data/resource_tracker.csv")

st.set_page_config(page_title="Economic Indicators", layout="wide")
st.title("Economic Indicator Pipeline")



def secret(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets[name]
    except Exception:
        return None


WAREHOUSE_URL = secret("WAREHOUSE_URL")


@st.cache_resource(show_spinner="First start: downloading data from the World Bank...")
def first_run(_bootstrap_revision):
    return ensure_data(DB, "sources.yaml", TRACKER)


@st.cache_resource
def warehouse_engine(url):
    return get_engine(url)


try:
    if WAREHOUSE_URL:
        data = read_warehouse(warehouse_engine(WAREHOUSE_URL))   
    else:
        first_run("retry-missing-indicators-v2")
        data = read_sqlite(DB, TRACKER)
except Exception as exc:
    st.error(f"Could not load the data: {exc}")
    st.stop()

obs, fc, log = data["obs"], data["fc"], data["log"]
rechecks, revisions, tracker, rpt = data["rechecks"], data["revisions"], data["tracker"], data["rpt"]
st.caption("Data source: " + ("Postgres warehouse (dbt models)" if data["mode"] == "warehouse" else "local SQLite database"))

if obs.empty:
    st.warning("There are no observations yet. Run the pipeline first.")
    st.stop()

if data["mode"] == "sqlite":
    with open("sources.yaml", encoding="utf-8") as source_file:
        expected_sources = {source["id"] for source in yaml.safe_load(source_file)["sources"]}
    missing_sources = expected_sources - set(obs["source_id"].dropna().unique())
    if missing_sources:
        st.warning(
            "Some indicators are not available yet: "
            + ", ".join(sorted(missing_sources))
            + ". Check the Run log for download errors. Reload the app later to retry."
        )

ok_runs = log[log["status"] == "ok"]
with st.expander("Welcome, researchers: read this first", expanded=True):
    if not ok_runs.empty:
        st.caption(f"Data last pulled: {ok_runs['run_ts'].max()} (UTC)")
    for point in WELCOME_POINTS:
        st.markdown(f"- {point}")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Indicators & forecasts", "Resource tracker", "Run log", "Recheck", "News"])

with tab1:
    c1, c2 = st.columns(2)
    source = c1.selectbox("Indicator", sorted(obs["source_id"].unique()))
    countries = c2.multiselect("Countries", sorted(obs["country"].unique()),
                               default=sorted(obs["country"].unique())[:2])
    sub = obs[(obs["source_id"] == source) & (obs["country"].isin(countries))]
    f = fc[(fc["source_id"] == source) & (fc["country"].isin(countries))]

    chart = sub.pivot(index="year", columns="country", values="value")
    if not f.empty:
        fpiv = f.pivot(index="year", columns="country", values="forecast")
        fpiv.columns = [f"{c} (forecast)" for c in fpiv.columns]
        chart = chart.join(fpiv, how="outer")
    st.line_chart(chart)
    st.info("**Keep in mind:** " + INDICATOR_NOTES.get(source, "Check the source definition before comparing countries."))

    if not rpt.empty:
        st.subheader("Reporting table (built by dbt)")
        st.dataframe(rpt[rpt["source_id"] == source].drop(columns=["source_id"]), hide_index=True)
    st.subheader("Latest values")
    latest = (sub.sort_values("year").groupby("country").tail(1)
              .rename(columns={"value": "latest value", "year": "latest year"})
              [["country", "latest year", "latest value"]])
    st.dataframe(latest, hide_index=True)

    if not f.empty:
        st.subheader("Forecast (80% interval)")
        st.dataframe(f[["country", "year", "forecast", "lower", "upper", "model"]]
                     .sort_values(["country", "year"]), hide_index=True)
    st.subheader("Reading of these curves")
    if sub.empty:
        st.info("Pick at least one country.")
    else:
        names = {"gdp_growth": "GDP growth (annual %)", "cpi_inflation": "Inflation, consumer prices (annual %)",
                 "unemployment": "Unemployment (% of labour force)"}
        facts = build_facts(names.get(source, source), sub, f)
        with st.expander("Numbers behind the chart"):
            st.text(facts)
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            try:
                key = st.secrets["GROQ_API_KEY"]
            except Exception:
                key = None
        if not key:
            st.info("Set GROQ_API_KEY to get a written AI reading. The numbers above work without it.")
        elif st.button("Explain these curves"):
            with st.spinner("Writing..."):
                try:
                    st.session_state["reading"] = (facts, interpret(facts, api_key=key))
                except Exception as exc:
                    st.error(f"Could not get a reading: {exc}")
        saved = st.session_state.get("reading")
        if saved and saved[0] == facts:
            st.write(saved[1])
            st.caption("AI-written from the numbers above. Check it against the chart before you use it.")
    st.subheader("All observations")
    st.dataframe(sub.sort_values(["country", "year"]), hide_index=True)

with tab2:
    if tracker.empty:
        st.info("No tracker yet. Run the pipeline first.")
    else:
        st.dataframe(tracker, hide_index=True)

with tab3:
    st.dataframe(log, hide_index=True)

with tab4:
    if data["mode"] == "warehouse":
        st.write("The warehouse keeps every load. A revision is a value the source changed between two loads.")
        if revisions.empty:
            st.success("No revisions yet: every load so far returned the same values.")
        else:
            st.dataframe(revisions, hide_index=True)
    elif rechecks.empty:
        st.info("No rechecks yet. Run `python run.py recheck`.")
    else:
        st.write("Each recheck downloads every source again, at the same time, and compares it with the stored data.")
        st.subheader("Recheck runs")
        st.dataframe(rechecks, hide_index=True)
        st.subheader("Differences found")
        if revisions.empty:
            st.success("The live data matched the stored data on every recheck.")
        else:
            st.dataframe(revisions, hide_index=True)

with tab5:
    st.write("Recent headlines for the indicator and countries you picked in the first tab.")
    st.caption("Headlines are context, not evidence. They do not feed the data or the forecasts. "
               "Links open other websites, so check the original article before you rely on it.")
    if not countries:
        st.info("Pick at least one country in the first tab.")
    elif st.button("Load headlines"):
        with st.spinner("Fetching headlines..."):
            arts, errs = fetch_for(source, countries)
        st.session_state["news"] = (source, tuple(countries), arts, errs)
    saved = st.session_state.get("news")
    if saved and saved[0] == source and saved[1] == tuple(countries):
        _, _, arts, errs = saved
        for c in countries:
            st.subheader(c)
            if c in errs:
                st.warning(f"Could not load headlines: {errs[c]}")
            elif not arts.get(c):
                st.write("No recent headlines found.")
            for a in arts.get(c, []):
                when = a["published"].strftime("%d %b %Y") if a["published"] else "date unknown"
                st.markdown(f"- [{a['title']}]({a['link']}) ({a['publisher'] or 'unknown source'}, {when})")
