"""Plain-language text shown to researchers on the dashboard."""

COUNTRY_NAMES = {"IND": "India", "CHN": "China", "USA": "United States", "GBR": "United Kingdom", "JPN": "Japan"}

WELCOME_POINTS = [
    "**What this is:** a pipeline that downloads World Bank indicators, stores them with a record of every download, forecasts 3 years ahead, and shows everything here.",
    "**The data is annual and lags the present.** The newest year is often a year or more behind today, so it will not show recent shocks.",
    "**Past values get revised.** The Recheck tab compares stored data with the live source. Check it before you quote a number.",
    "**Forecasts are simple.** They come from an ARIMA model fitted to about 25 yearly points. Read them as a trend with a wide range, not a prediction to act on.",
    "**AI readings are drafts.** They are written from the computed numbers only. Check every figure against the numbers panel.",
    "**Headlines are context, not evidence.** They do not feed the data or the forecasts. Open the original article before you rely on it.",
    "**When you cite a number,** give the World Bank indicator code and the pull date from the Resource tracker tab.",
]

INDICATOR_NOTES = {
    "gdp_growth": "Real GDP growth, annual %. 2020 and 2021 swing sharply because of the pandemic, so growth in the years after partly reflects recovery from a low base. The latest year may be a preliminary estimate.",
    "cpi_inflation": "Annual consumer price inflation. Countries build their price baskets differently, so compare trends more than exact levels. A big move can come from a base effect (an unusual previous year). Headline inflation includes food and energy, which are volatile.",
    "unemployment": "Unemployment as a % of the labour force. Definitions and survey methods differ across countries, so levels are not strictly comparable. The World Bank series is a modelled ILO estimate, so it can miss short-term swings.",
}

TOPIC_QUERIES = {
    "gdp_growth": "GDP growth economy",
    "cpi_inflation": "inflation CPI",
    "unemployment": "unemployment rate jobs",
}
