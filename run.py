"""CLI: python run.py [collect|forecast|tracker|recheck|all]   (recheck apply = also update changed values)"""
import sys
import yaml

from pipeline import collect, forecast, recheck, tracker
from pipeline.db import connect


def main(step="all", apply=False):
    config = yaml.safe_load(open("sources.yaml"))
    con = connect()
    if step in ("collect", "all"):
        collect.run(con, config)
    if step in ("forecast", "all"):
        forecast.run(con)
    if step in ("tracker", "all"):
        tracker.build(con, config)
    if step == "recheck":
        out = recheck.run(con, config, apply=apply)
        for s in out["sources"]:
            print(s)
        print(f"checked {len(out['sources'])} sources in {out['wall_seconds']:.1f}s "
              f"(one after another would take about {out['sum_of_source_seconds']:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all", apply="apply" in sys.argv[2:])
