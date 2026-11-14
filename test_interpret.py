import pandas as pd

from pipeline.interpret import build_facts, interpret


def data():
    obs = pd.DataFrame({"country": ["IND"] * 8, "year": range(2016, 2024),
                        "value": [8.0, 6.5, 6.5, 3.9, -5.8, 9.7, 7.0, 8.2]})
    fc = pd.DataFrame({"country": ["IND"], "year": [2024], "forecast": [7.1],
                       "lower": [5.0], "upper": [9.0], "model": ["ARIMA(1,1,1)"]})
    return obs, fc


def test_facts_have_the_right_numbers():
    obs, fc = data()
    t = build_facts("GDP growth", obs, fc)
    assert "latest 8.20 (2023)" in t and "highest 9.70 (2021)" in t
    assert "lowest -5.80 (2020)" in t and "2024: 7.10 (80% range 5.00 to 9.00)" in t


def test_interpret_sends_only_the_facts():
    class Msg: content = " reading "
    class Choice: message = Msg()
    class Resp: choices = [Choice()]
    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    Client.kw = kw
                    return Resp()
    obs, fc = data()
    out = interpret(build_facts("GDP", obs, fc), client=Client())
    msgs = Client.kw["messages"]
    assert out == "reading" and "latest 8.20" in msgs[1]["content"]
    assert msgs[0]["role"] == "system" and "do not invent" in msgs[0]["content"]
