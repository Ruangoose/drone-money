"""Rerun the study from a clean clone: screens, baskets, history, attribution, catalysts and valuation, the
checks on the screen's reach and on drone spending outside product code 1550, then the web page's figures
(site.py). Outputs go to output/; the series built from Alpaca's prices stay out of git (see .gitignore).

    python run.py            # reruns from the screens in data/screen/ and the download cache
    python run.py --refresh  # reruns the EDGAR and USAspending screens too
"""
import pandas as pd

from drones import reach, primes, screen, site, spending, study, valuation
from drones.http import ROOT

OUT = ROOT / "output"


def valuation_tables(mem, raw):
    """EV/sales and other measures month by month for every name, and their medians across the names each
    basket held that month."""
    rawc = raw.pivot(index="date", columns="symbol", values="close")
    per = []
    for s in sorted(mem.symbol.unique()):
        if s in study.CIKS and s in rawc:
            per.append(valuation.monthly(s, study.CIKS[s], rawc[s]))
    per = pd.concat(per, ignore_index=True)
    reb = pd.read_csv(OUT / "rebalances.csv", parse_dates=["date"])
    held = (reb.assign(symbol=reb["names"].fillna("").str.split(",")).explode("symbol")
            .query("symbol != ''")[["date", "basket", "symbol"]])
    held["ym"] = held["date"].dt.to_period("M")
    per["ym"] = per["date"].dt.to_period("M")
    m = per.merge(held[["ym", "basket", "symbol"]], on=["ym", "symbol"])
    cols = ["ev_sales", "rev_growth", "gross_margin", "op_margin", "shares_yoy", "backlog_to_sales"]
    med = m.groupby(["basket", "date"])[cols].median().reset_index()
    per.to_csv(OUT / "valuation-by-name.csv", index=False)
    med.to_csv(OUT / "valuation-by-basket.csv", index=False)
    return per, med


def main(refresh_screens=False):
    if refresh_screens or not (ROOT / "data" / "screen" / "drone-10k-intensity.csv").exists():
        screen.run()
    if refresh_screens or not (ROOT / "data" / "screen" / "dod-top-parents.csv").exists():
        primes.run()
    spending.run()
    spending.wider()  # with loitering munitions and counter-drone added
    mem, series, liq, raw, closes, f = study.run()
    # The screen's reach: companies that stopped filing, and every candidate's rule outcome.
    if refresh_screens or not (ROOT / "data" / "screen" / "broad-new-scored.csv").exists():
        reach.run()
    reach.candidates()
    per, med = valuation_tables(mem, raw)
    site.write(series, closes, per, med)


if __name__ == "__main__":
    import sys
    main(refresh_screens="--refresh" in sys.argv)
