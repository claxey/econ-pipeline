"""Turn the numbers behind a chart into a written reading.

The facts are computed in plain pandas first. The AI only gets those facts, so it
explains numbers we checked instead of guessing from a picture of a chart.
"""
import os

import pandas as pd

# Groq retires and adds models; if this one stops working, set GROQ_MODEL to one from console.groq.com
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

SYSTEM = (
    "You are a careful economic research analyst. Write a short reading of the data you are given. "
    "Rules: use only the numbers provided and quote them exactly; do not invent events, causes or "
    "numbers; if you mention a possible cause, say it is general context and not shown by this data; "
    "state that the forecast comes from a simple ARIMA model on annual data and is uncertain; "
    "write 120 to 180 words in plain English, as short paragraphs with no headings."
)


def build_facts(source_name, obs, fc):
    """obs: columns country, year, value. fc: columns country, year, forecast, lower, upper, model."""
    lines = [f"Indicator: {source_name}"]
    for country, g in obs.sort_values("year").groupby("country"):
        g = g.dropna(subset=["value"])
        if g.empty:
            continue
        last = g.iloc[-1]
        peak, low = g.loc[g["value"].idxmax()], g.loc[g["value"].idxmin()]
        recent = g.tail(5)
        line = (f"{country}: latest {last['value']:.2f} ({int(last['year'])}); "
                f"last 5 years average {recent['value'].mean():.2f}; "
                f"highest {peak['value']:.2f} ({int(peak['year'])}); "
                f"lowest {low['value']:.2f} ({int(low['year'])}); "
                f"first year in data {int(g['year'].min())}")
        if len(g) > 5:
            before = g.iloc[-6]
            line += f"; change vs {int(before['year'])}: {last['value'] - before['value']:+.2f}"
        f = fc[fc["country"] == country].sort_values("year") if not fc.empty else fc
        if not f.empty:
            parts = []
            for r in f.itertuples():
                rng = "" if pd.isna(r.lower) else f" (80% range {r.lower:.2f} to {r.upper:.2f})"
                parts.append(f"{int(r.year)}: {r.forecast:.2f}{rng}")
            line += f"; forecast {', '.join(parts)} using {f.iloc[0]['model']}"
        lines.append(line)
    return "\n".join(lines)


SKIP = ("whisper", "guard", "tts", "orpheus", "playai", "embed", "compound", "safeguard", "vision")
PREFER = ("llama-3.3", "llama-3.1", "gpt-oss", "llama", "qwen", "kimi")


def pick_model(client):
    """Ask Groq which models this key can use and pick a general chat model."""
    ids = [m.id for m in client.models.list().data]
    chat = [i for i in ids if not any(x in i.lower() for x in SKIP)]
    for p in PREFER:
        for i in chat:
            if p in i.lower():
                return i
    if chat:
        return chat[0]
    raise RuntimeError("No chat models available for this Groq key")


def _ask(client, model, facts):
    resp = client.chat.completions.create(
        model=model, max_tokens=600, temperature=0.2,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": facts}])
    return resp.choices[0].message.content.strip()


def interpret(facts, api_key=None, client=None):
    """Return the AI reading of the facts using Groq. Falls back to an available model if MODEL is gone."""
    if client is None:
        from groq import Groq
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("No GROQ_API_KEY set")
        client = Groq(api_key=key)
    try:
        return _ask(client, MODEL, facts)
    except Exception as exc:
        if "model_not_found" not in str(exc) and "does not exist" not in str(exc):
            raise
        return _ask(client, pick_model(client), facts)
