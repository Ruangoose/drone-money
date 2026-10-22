"""The web page's figures (ruangoosen.co.za/projects/drones-vs-primes/), written to output/site/.

- summary.json: the headline figures: the screen and its checks, the baskets, the pair's returns by period, the
  factor loadings, the catalysts' averages by kind, valuation now against its history, the falls from the
  2026 high, and the background facts in config/background.csv. Single figures only.
- spending.json: DoD contract obligations for unmanned aircraft (product code 1550) by fiscal year and
  recipient group, and the same with the contracts that name loitering munitions or counter-drone systems
  added. Public data (USAspending.gov).
- baskets.json: the names each basket held at each monthly rebalance.
- shares.json: the series behind the page's three charts drawn from Alpaca's prices: the two baskets and the
  pair indexed to 100 (the last close of each week), the pair's move around each catalyst, and EV/sales at each
  month end for AeroVironment, Kratos and the primes' median. Alpaca agreed to the page charting these, with no
  data to download, so this file is git-ignored and the page publishes only the drawn charts.

Nothing here looks forward: every figure describes the past, to END.
"""
import json

import numpy as np
import pandas as pd

from . import baskets, reach, rules, screen
from .http import ROOT
from .study import END

OUT = ROOT / "output"
SITE = OUT / "site"
SCREEN = ROOT / "data" / "screen"
CONFIG = ROOT / "config"

NAMES = {"AVAV": "AeroVironment", "KTOS": "Kratos", "UAVS": "AgEagle", "RCAT": "Red Cat", "ONDS": "Ondas",
         "UMAC": "Unusual Machines", "RDW": "Redwire", "AIRO": "AIRO Group", "XTIA": "XTI Aerospace",
         "LMT": "Lockheed Martin", "RTX": "RTX", "RTN": "Raytheon", "UTX": "United Technologies",
         "GD": "General Dynamics", "BA": "Boeing", "NOC": "Northrop Grumman", "HII": "Huntington Ingalls"}
# Recipient groups (companies.py), as the page names them.
GROUPS = {"primes": "primes", "drone basket companies": "listed", "private": "private", "other": "other"}
KINDS = {"loitering munitions": "loitering", "counter-drone": "counter_drone", "coyote": "coyote"}
# The page shows the equal-weighted baskets and pair, and the market-value-weighted versions as a check.
SERIES = ["drones", "primes", "pair_dollar", "pair_capweighted", "drones_capweighted", "primes_capweighted"]
HISTORY = ("2019-01-01", "2024-12-31")  # the valuation history that "now" is set against


def _num(v, d=6):
    """A float rounded for JSON, or None where it's missing."""
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return None
    return round(float(v), d)


def _by_fy(s, d=6):
    return {str(int(k)): _num(v, d) for k, v in s.items()}


def _day(t):
    return pd.Timestamp(t).date().isoformat()


# ---- DoD's drone money (public data) -------------------------------------------------------------------
def spending():
    by = pd.read_csv(SCREEN / "dod-drone-psc1550-by-fy.csv", index_col="fy")
    wide = pd.read_csv(SCREEN / "dod-drone-wider-by-fy.csv")
    rec = pd.read_csv(SCREEN / "dod-drone-psc1550-recipients.csv")
    acts = pd.read_csv(SCREEN / "dod-drone-keyword-actions.csv")

    def variant(name):
        w = wide[wide.variant == name].set_index("fy")
        share = {GROUPS[g]: _by_fy(w[f"share_{g}"]) for g in GROUPS}
        share.update({c: _by_fy(w[f"share_{c}"]) for c in ("AeroVironment", "Kratos")})
        return {"total": _by_fy(w["total"], 0), "share": share}

    code = variant("1550")
    code["amount"] = {GROUPS[g]: _by_fy(by[g], 0) for g in GROUPS}
    code["dod_total"] = _by_fy(by["dod_total"], 0)
    code["share_of_dod"] = _by_fy(by["psc1550_share_of_dod"])
    full = by["psc1550_share_of_dod"].iloc[:-1]  # the last fiscal year is incomplete
    code["share_of_dod_range"] = {"min": {"fy": int(full.idxmin()), "value": _num(full.min())},
                                  "max": {"fy": int(full.idxmax()), "value": _num(full.max())}}
    # The largest recipients each year, by company.
    top = {}
    for fy, g in rec.groupby("fy"):
        c = g.groupby(["company", "group"])["amount"].sum().sort_values(ascending=False).head(8)
        top[str(fy)] = [{"company": k[0].replace(" (private)", "").replace(" (London-listed)", ""),
                         "group": GROUPS[k[1]], "amount": _num(v, 0), "share": _num(v / by.at[fy, "psc1550_total"])}
                        for k, v in c.items()]
    code["top"] = top

    named = variant("1550 + named actions")
    kinds = {}
    for kind, g in acts.groupby("matched"):
        groups = g.groupby("group")["amount"].sum()
        avav = g.loc[g.company == "AeroVironment", "amount"].sum()
        kinds[KINDS[kind]] = {"total": _num(g["amount"].sum(), 0), "actions": len(g),
                              "by_group": {GROUPS[k]: _num(v, 0) for k, v in groups.items()},
                              "AeroVironment": _num(avav, 0), "AeroVironment_share": _num(avav / g["amount"].sum())}
    named["actions"] = {"count": len(acts), "total": _num(acts["amount"].sum(), 0), "kinds": kinds}
    fys = [int(f) for f in by.index]
    return {"fys": fys, "last_full_fy": fys[-2], "partial_fy": fys[-1], "code1550": code, "named": named}


# ---- The screen and its checks ----------------------------------------------------------------------------
def screen_summary(held):
    hits = pd.read_csv(SCREEN / "edgar-phrase-hits.csv")
    k10 = pd.read_csv(SCREEN / "drone-10k-intensity.csv")
    broad = pd.read_csv(SCREEN / "broad-new-scored.csv")
    cand = pd.read_csv(OUT / "screen-candidates.csv")
    check = json.loads((OUT / "screen-check-summary.json").read_text())
    order = ["member", "fails materiality", "needs a materiality decision", "fails liquidity", "no prices",
             "fails listing"]
    # Each company's furthest step through the rules, over all its spells.
    best = (cand.assign(o=cand.outcome.map(order.index)).sort_values("o")
            .drop_duplicates(["source", "cik"]))
    outcomes = {src: {o.replace(" ", "_"): int(n) for o, n in g.outcome.value_counts().items()}
                for src, g in best.groupby("source")}
    passing = broad[broad.passes_intensity].drop_duplicates("cik")
    near = best[(best.source == "phrase screen") & (best.outcome == "fails liquidity")]
    near = near.sort_values("max_month_start_median_m", ascending=False).head(2)
    first_held = {}
    for month, names in held["drones"].items():
        for s in names:
            first_held.setdefault(s, month)
    return {
        "phrases": len(screen.PHRASES), "companies": int(hits.cik.nunique()), "tenks_scored": len(k10),
        "intensity_min": rules.INTENSITY_MIN, "liquidity_min_m": rules.LIQUIDITY_MIN / 1e6,
        "liquidity_days": rules.LIQUIDITY_DAYS, "n_primes": rules.N_PRIMES,
        "manufacturing_min": rules.MANUFACTURING_MIN,
        "passing_companies": int(best[best.source == "phrase screen"].cik.nunique()),
        "outcomes": {"phrase": outcomes.get("phrase screen", {}), "broad": outcomes.get("broad check", {})},
        "members": [{"symbol": s, "name": NAMES[s], "first_month": m} for s, m in first_held.items()],
        "near_misses": [{"name": NAMES.get(r.symbol, r["name"]), "max_median_m": _num(r.max_month_start_median_m, 2)}
                        for _, r in near.iterrows()],
        "broad": {"terms": len(reach.BROAD), "tenks": check["broad_10k_hits"], "companies": check["broad_companies"],
                  "new": check["new_companies"], "stopped": check["new_stopped"], "scored": check["scored_10ks"],
                  "passing": check["passing"], "passing_stopped": int(passing.stopped_filing.sum()),
                  "passing_active": int((~passing.stopped_filing).sum())},
    }


# ---- The baskets, month by month ------------------------------------------------------------------------
def holdings():
    reb = pd.read_csv(OUT / "rebalances.csv", parse_dates=["date"])
    reb["month"] = reb.date.dt.strftime("%Y-%m")
    out = {}
    for b, g in reb.groupby("basket"):
        g = g.drop_duplicates("month", keep="last")
        out[b] = {m: (n.split(",") if isinstance(n, str) and n else []) for m, n in zip(g.month, g.names)}
    return out


def baskets_summary(held):
    d = {m: v for m, v in held["drones"].items() if v}
    first = min(d)
    window = [m for m in d if m <= "2024-12"]
    only_two = [m for m in window if set(d[m]) <= {"AVAV", "KTOS"}]
    return {"drones_first_month": first, "drones_months_to_2024": len(window),
            "drones_months_only_avav_ktos": len(only_two), "drones_max_names": max(len(v) for v in d.values()),
            "drones_now": d[max(d)], "primes_now": held["primes"][max(held["primes"])],
            "primes_ever": sorted({s for v in held["primes"].values() for s in v})}


# ---- The pair, from Alpaca's prices -------------------------------------------------------------------------
def indexed(series):
    """The two baskets and the dollar-neutral pair, each 100 at the close before the drone basket's first day,
    sampled at the last close of each week."""
    first = series["drones"].first_valid_index()
    base = series.index[series.index.get_loc(first) - 1]
    r = series.loc[first:, ["drones", "primes", "pair_dollar"]].fillna(0.0)
    level = 100 * (1 + r).cumprod()
    level.loc[base] = 100.0
    level = level.sort_index()
    weekly = level.groupby(level.index.to_period("W-FRI")).tail(1)
    weekly = pd.concat([level.loc[[base]], weekly[weekly.index > base]])
    return level, {"base": _day(base), "dates": [_day(d) for d in weekly.index],
                   **{k: [_num(v, 2) for v in weekly[c]] for k, c in
                      (("drones", "drones"), ("primes", "primes"), ("pair", "pair_dollar"))}}


def performance(series):
    """Return, volatility and worst fall by period, every series over the same days: from the drone basket's
    first day (output/performance.csv starts the primes in April 2016, when they first pass the liquidity
    test)."""
    first = series["drones"].first_valid_index()
    windows = {"all": (first, END), "to_2021": (first, "2021-12-31"), "2022_24": ("2022-01-01", "2024-12-31"),
               "2025": ("2025-01-01", "2025-12-31"), "2026": ("2026-01-01", END)}
    out = {}
    for key, (a, b) in windows.items():
        for col in SERIES:
            st = baskets.stats(series[col].loc[a:b])
            out.setdefault(key, {})[col] = {"start": _day(st["start"]), "end": _day(st["end"]),
                                            **{k: _num(st[k]) for k in ("ann_return", "ann_vol", "max_drawdown",
                                                                        "total")}}
    return out


def attribution():
    a = json.loads((OUT / "attribution.json").read_text())
    out = {}
    for key, v in a.items():
        series, sample = [x.strip() for x in key.split("|")]
        if series not in SERIES:
            continue
        out.setdefault(series, {})["all" if sample == "all" else "since_2022"] = {
            "start": v["start"], "end": v["end"], "n": v["n"], "r2": _num(v["r2"]),
            "alpha_ann": _num(v["alpha_ann"]), "alpha_t": _num(v["alpha_t"]),
            "betas": {k: _num(x) for k, x in v["betas"].items()}, "t": {k: _num(x) for k, x in v["t"].items()}}
    return out


def catalysts():
    """Each catalyst's window for the pair (shares.json), and the averages by kind (summary.json)."""
    ev = pd.read_csv(OUT / "events.csv")
    cfg = pd.read_csv(CONFIG / "events.csv", dtype=str)
    ev = ev[ev.series == "pair_dollar"]
    events = []
    for _, c in cfg.iterrows():
        e = ev[ev.day0 == c.day0]
        win = {}
        for _, w in e.iterrows():
            win[w.window.split("+")[1]] = {"first": w["first"], "last": w["last"], "days": int(w.days),
                                           "raw": _num(w.raw), "abnormal": _num(w.abnormal),
                                           "percentile": _num(w.percentile, 4)}
        events.append({"day0": c.day0, "event": c.event, "kind": c.kind, "source": c.source, "windows": win})
    by_kind = {}
    five = ev[ev.window == "0..+5"]
    for kind, g in five.groupby("kind"):
        a = g.abnormal.dropna()
        by_kind[kind.replace(" ", "_")] = {"n": len(g), "n_abnormal": len(a), "mean": _num(a.mean()),
                                           "median": _num(a.median()), "positive": int((a > 0).sum())}
    return events, by_kind


def valuation(per, med):
    per = per.copy()
    per["date"] = pd.to_datetime(per["date"])
    med = med.copy()
    med["date"] = pd.to_datetime(med["date"])
    ev = per.pivot(index="date", columns="symbol", values="ev_sales")
    m = {b: g.set_index("date")["ev_sales"] for b, g in med.groupby("basket")}
    hist = slice(*HISTORY)
    out = {}
    for s in ("AVAV", "KTOS"):
        x = ev[s].dropna()
        out[s] = {"now": _num(x.iloc[-1], 4), "date": _day(x.index[-1]), "median_2019_24": _num(x.loc[hist].median(), 4)}
    for b in ("drones", "primes"):
        x = m[b].dropna()
        y26 = x.loc["2026-01-01":]
        out[b + "_median"] = {"now": _num(x.iloc[-1], 4), "median_2019_24": _num(x.loc[hist].median(), 4),
                              "high_2026": _num(y26.max(), 4), "high_2026_month": y26.idxmax().strftime("%Y-%m")}
    # EV now against each company's own adjusted EBITDA guidance (midpoint), from config/background.csv.
    bg = background()
    last = per.sort_values("date").groupby("symbol").tail(1).set_index("symbol")
    for s, (lo, hi) in {"AVAV": ("avav_fy27_ebitda_lo", "avav_fy27_ebitda_hi"),
                        "KTOS": ("ktos_2026_ebitda_lo", "ktos_2026_ebitda_hi")}.items():
        mid = (bg[lo]["value"] + bg[hi]["value"]) / 2 * 1e6
        out[s]["ev_to_guided_ebitda"] = _num(last.at[s, "ev"] / mid, 4)
    shares = {"dates": [d.strftime("%Y-%m-%d") for d in ev.loc[HISTORY[0]:].index],
              "AVAV": [_num(v, 3) for v in ev.loc[HISTORY[0]:, "AVAV"]],
              "KTOS": [_num(v, 3) for v in ev.loc[HISTORY[0]:, "KTOS"]],
              "primes_median": [_num(v, 3) for v in m["primes"].reindex(ev.loc[HISTORY[0]:].index)]}
    return out, shares


def falls(closes, level, held):
    """Each name's fall from its 2026 high to END (adjusted closes), and the baskets'."""
    names = held["drones"][max(held["drones"])] + held["primes"][max(held["primes"])]
    out = {}
    for s in names:
        px = closes[s].dropna().loc["2026-01-01":]
        out[s] = {"name": NAMES[s], "fall": _num(px.iloc[-1] / px.max() - 1, 4), "high": _day(px.idxmax())}
    for b, c in (("drones", "drones"), ("primes", "primes"), ("pair", "pair_dollar")):
        x = level[c].loc["2026-01-01":]
        out["basket_" + b] = {"fall": _num(x.iloc[-1] / x.max() - 1, 4), "high": _day(x.idxmax())}
    return out


def background():
    bg = pd.read_csv(CONFIG / "background.csv", dtype=str)
    out = {}
    for _, r in bg.iterrows():
        v = r["value"] if r["unit"] == "date" else float(r["value"])
        out[r.key] = {"value": v, "unit": r["unit"], "published": r["published"] if isinstance(r["published"], str)
                      else None, "source": r.source}
    a, b = out["avav_axs_revenue_q1fy27"]["value"], out["avav_axs_revenue_q1fy26"]["value"]
    out["avav_axs_growth"] = {"value": round(a / b - 1, 4), "unit": "share", "published": None,
                              "source": out["avav_axs_revenue_q1fy27"]["source"]}
    return out


def from_outputs():
    """Rewrites output/site/ from the study's saved output, without rerunning it: python -m drones.site"""
    from . import prices, study
    series = pd.read_csv(OUT / "daily-series.csv", index_col=0, parse_dates=True)
    mem = pd.read_csv(OUT / "membership.csv")
    adj, _ = study.load_prices(sorted(mem.symbol.unique()))
    per = pd.read_csv(OUT / "valuation-by-name.csv", parse_dates=["date"])
    med = pd.read_csv(OUT / "valuation-by-basket.csv", parse_dates=["date"])
    return write(series, prices.wide(adj), per, med)


def write(series, closes, per, med):
    SITE.mkdir(parents=True, exist_ok=True)
    held = holdings()
    level, idx = indexed(series)
    events, by_kind = catalysts()
    val, ev_sales = valuation(per, med)
    attr = attribution()
    summary = {
        "end": END, "factors_end": attr["drones"]["all"]["end"], "names": NAMES,
        "screen": screen_summary(held), "baskets": baskets_summary(held), "performance": performance(series),
        "attribution": attr, "catalysts": by_kind, "valuation": val, "falls": falls(closes, level, held),
        "background": background(),
    }
    files = {"summary.json": summary, "spending.json": spending(),
             "baskets.json": {"names": NAMES, **held},
             "shares.json": {"end": END, "indexed": idx, "events": events, "ev_sales": ev_sales}}
    for name, obj in files.items():
        (SITE / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    from_outputs()
