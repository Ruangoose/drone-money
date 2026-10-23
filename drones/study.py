"""The study: baskets, the pair, attribution, catalysts and valuation.

Writes tables to output/; site.py turns them into the web page's figures. Prices end on END (the last full
trading day when the study was run).
"""
import json

import numpy as np
import pandas as pd

from . import attribution as att
from . import baskets as bk
from . import factors, prices, rules, valuation
from .http import ROOT

END = "2026-10-20"
OUT = ROOT / "output"
CIKS = {"AVAV": 1368622, "KTOS": 1069258, "RCAT": 748268, "UAVS": 8504, "UMAC": 1956955, "ONDS": 1646188,
        "RDW": 1819810, "LMT": 936468, "RTX": 101829, "UTX": 101829, "RTN": 1047122, "GD": 40533, "BA": 12927,
        "NOC": 1133421, "HII": 1501585, "LHX": 202058, "HRS": 202058, "LLL": 1056239, "AIRO": 1927958,
        "XTIA": 1529113}


def liquidity(raw, days=rules.LIQUIDITY_DAYS, floor=rules.LIQUIDITY_MIN):
    """True where the median daily traded value over the previous `days` sessions is at least `floor`."""
    df = raw.assign(value=raw["vwap"].fillna(raw["close"]) * raw["volume"])
    med = df.pivot(index="date", columns="symbol", values="value").rolling(days, min_periods=40).median()
    return med.shift(1) >= floor


def membership():
    return pd.concat([rules.drone_spells(rules.INTENSITY_MIN), rules.prime_spells()], ignore_index=True)


def load_prices(symbols):
    adj = prices.daily_bars(symbols, start="2016-01-01", end=END, adjustment="all")
    raw = prices.daily_bars(symbols, start="2016-01-01", end=END, adjustment="raw")
    return adj, raw


def carried(syms, adj, raw):
    """What holders of the merged names earned after they stopped trading (config/corporate-actions.csv). Names
    received that aren't basket members (Carrier, Otis) are fetched on their own and kept out of the price
    tables."""
    acts = bk.corporate_actions(ROOT / "config" / "corporate-actions.csv")
    new = sorted(set(acts.new) - set(syms))
    adj_n, raw_n = load_prices(new)
    return bk.carried_returns(prices.wide(pd.concat([adj, adj_n])), prices.wide(pd.concat([raw, raw_n])), acts)


def run():
    OUT.mkdir(exist_ok=True)
    mem = membership()
    mem.to_csv(OUT / "membership.csv", index=False)
    syms = sorted(mem.symbol.unique())
    adj, raw = load_prices(syms)
    closes = prices.wide(adj)
    rets = bk.daily_returns(closes)
    liq = liquidity(raw).reindex(rets.index).fillna(False)
    car = carried(syms, adj, raw)
    f = factors.daily()

    drones, dlog = bk.basket_returns(rets, mem, "drones", liquid=liq, carried=car)
    primes, plog = bk.basket_returns(rets, mem, "primes", liquid=liq, carried=car)
    pd.concat([dlog, plog]).to_csv(OUT / "rebalances.csv", index=False)
    # Sensitivity: market-value weights, so one small name's spike can't drive the basket.
    rawc = prices.wide(raw)
    caps = pd.DataFrame({s: valuation.monthly(s, CIKS[s], rawc[s]).set_index("date")["mcap"]
                         for s in syms if s in CIKS and s in rawc})
    drones_cw, _ = bk.basket_returns(rets, mem, "drones", liquid=liq, caps=caps, carried=car)
    primes_cw, _ = bk.basket_returns(rets, mem, "primes", liquid=liq, caps=caps, carried=car)
    mkt = f["MKT"] + f["RF"]
    pair_ew = (drones - primes).rename("pair_dollar")
    pair_cw = (drones_cw - primes_cw).rename("pair_capweighted")
    pair_beta, h_beta = bk.hedged_pair(drones, primes, mkt, "beta")
    pair_vol, h_vol = bk.hedged_pair(drones, primes, mkt, "vol")
    series = pd.concat([drones, primes, pair_ew, pair_beta, pair_vol, h_beta.rename("hedge_beta"),
                        h_vol.rename("hedge_vol"), drones_cw.rename("drones_capweighted"),
                        primes_cw.rename("primes_capweighted"), pair_cw], axis=1)
    series.to_csv(OUT / "daily-series.csv")

    # Performance by period.
    periods = {"all": ("2016-01-01", END), "2016-2021": ("2016-01-01", "2021-12-31"),
               "2022-2024": ("2022-01-01", "2024-12-31"), "2025": ("2025-01-01", "2025-12-31"),
               "2026 to date": ("2026-01-01", END)}
    perf = []
    for name, (a, b) in periods.items():
        for col in ["drones", "primes", "pair_dollar", "pair_beta", "pair_vol", "drones_capweighted",
                    "primes_capweighted", "pair_capweighted"]:
            perf.append({"period": name, "series": col, **bk.stats(series[col].loc[a:b])})
    pd.DataFrame(perf).to_csv(OUT / "performance.csv", index=False)

    # Factor attribution, full sample and since 2022.
    attr = {}
    for col in ["drones", "primes", "pair_dollar", "pair_beta"]:
        for label, a in (("all", "2016-01-01"), ("since 2022", "2022-01-01")):
            y = series[col].loc[a:]
            attr[f"{col} | {label}"] = att.regress(y, f, excess=not col.startswith("pair"))
    (OUT / "attribution.json").write_text(json.dumps(attr, indent=1, default=str))
    rb = {col: att.rolling_betas(series[col], f) for col in ["drones", "primes", "pair_dollar"]}
    pd.concat(rb, axis=1).to_csv(OUT / "rolling-betas.csv")

    # Catalyst windows.
    ev = pd.read_csv(ROOT / "config" / "events.csv", parse_dates=["day0"])
    rows = []
    for _, e in ev.iterrows():
        for after in (1, 5, 20):
            for col in ["pair_dollar", "drones", "primes"]:
                r = att.event_window(series[col], f, e.day0, before=1, after=after)
                if r:
                    rows.append({"day0": e.day0.date(), "event": e.event, "kind": e.kind, "series": col,
                                 "window": f"0..+{after}", **{k: v for k, v in r.items() if k != "day0"}})
    pd.DataFrame(rows).to_csv(OUT / "events.csv", index=False)
    return mem, series, liq, raw, closes, f


if __name__ == "__main__":
    run()
