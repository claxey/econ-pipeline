from pipeline import news

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>India GDP grows faster than expected - Reuters</title><link>https://example.com/a</link>
<pubDate>Wed, 29 Oct 2025 10:00:00 GMT</pubDate><source url="https://reuters.com">Reuters</source></item>
<item><title>[Breaking] Older story - Mint</title><link>https://example.com/b</link>
<pubDate>Mon, 20 Oct 2025 10:00:00 GMT</pubDate><source url="https://livemint.com">Mint</source></item>
<item><title>India GDP grows faster than expected - Reuters</title><link>https://example.com/dup</link>
<pubDate>Wed, 29 Oct 2025 11:00:00 GMT</pubDate><source url="https://reuters.com">Reuters</source></item>
<item><title>Bad link</title><link>javascript:alert(1)</link><pubDate>Wed, 29 Oct 2025 12:00:00 GMT</pubDate></item>
<item><title>No date story - Blog</title><link>https://example.com/c</link><source url="https://x.com">Blog</source></item>
</channel></rss>"""


def test_parse_cleans_dedupes_sorts_and_filters():
    items = news.parse_rss(RSS, limit=10)
    titles = [i["title"] for i in items]
    assert titles == ["India GDP grows faster than expected", "Breaking Older story", "No date story"]
    assert all(i["link"].startswith("https://") for i in items)
    assert items[0]["publisher"] == "Reuters"


def test_query_uses_country_name_and_topic():
    q = news.build_query("cpi_inflation", "IND")
    assert q.startswith("India inflation") and q.endswith("when:30d")


def test_rejects_xml_entity_bomb():
    import pytest
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><rss><channel><item><title>&b;</title></channel></rss>'
    with pytest.raises(Exception):
        news.parse_rss(bomb)


def test_fetch_for_runs_countries_and_isolates_errors():
    class Resp:
        def __init__(self, text): self.text = text
        def raise_for_status(self): pass
    class Session:
        def get(self, url, headers=None, timeout=None):
            if "China" in url:
                raise ValueError("boom")
            return Resp(RSS)
    arts, errs = news.fetch_for("gdp_growth", ["IND", "CHN"], session=Session())
    assert len(arts["IND"]) == 3 and arts["CHN"] == [] and "CHN" in errs and "IND" not in errs
