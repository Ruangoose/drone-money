"""Checks on the drone screen's reach: does it miss companies that have since stopped filing, and does any
company that would pass the rules lack prices?

EDGAR full-text search covers every filing since 2001, including those of companies that were later
acquired, delisted or deregistered, so the screen is not limited to today's filers. What it can miss is a
company whose 10-Ks never use one of its possessive or product phrases. `run` searches 10-Ks for broader
terms ("drone", "UAV", "unmanned aerial" and so on), takes the companies the screen didn't find, and scores
the matching 10-Ks of those that filed no 10-K after BROAD_STOPPED (they have stopped filing) with the
screen's own intensity measure. Active companies are scored too when one 10-K matches several broad terms.

`candidates` takes every eligibility spell the intensity test opens, in the phrase screen's companies and the
broad check's, and records which rule each one passes: listing (the 10-K cover's Section 12(b) registration,
or Alpaca bars), liquidity (the 63-day median traded value at each month start, from Alpaca bars) and
materiality (config/drone-materiality.csv).
"""
import json
import re
import urllib.parse

import pandas as pd

from . import prices, rules
from .http import ROOT, sec_json, sec_text
from .screen import END, START, company_10ks, html_to_text, intensity

# The symbol each listed candidate traded under during its spells (Alpaca keys bars by symbol).
SYMBOLS = {1368622: "AVAV", 1069258: "KTOS", 748268: "RCAT", 8504: "UAVS", 1956955: "UMAC", 1646188: "ONDS",
           1819810: "RDW", 1178727: "COMS", 1855631: "AWIN", 1927958: "AIRO", 1529113: "XTIA", 1638911: "DUKR",
           2011208: "SPAI", 1563568: "EVTV", 1702924: "WRAP", 2038439: "VWAV", 354908: "FLIR", 1500435: "GPRO",
           1425287: "WKHS", 217346: "TXT", 1069183: "AXON", 1899287: "AMPX", 1378140: "OPTT", 1787518: "DFNS",
           1114925: "LTRX", 1826681: "PDYN",
           # found by the broad check only
           54381: "KAMN", 1280263: "AMBA", 1398805: "BEEM", 1414767: "NCPL", 1606698: "ALPP", 1818274: "ARAI",
           1865120: "BRAC"}
LISTED = re.compile(r"Nasdaq|NYSE|New York Stock Exchange", re.I)

BROAD = ['"drone"', '"drones"', '"UAV"', '"UAVs"', '"UAS"', '"unmanned aerial"', '"unmanned aircraft"',
         '"unmanned systems"', '"our UAV"', '"drone technology"', '"drone services"', '"drone delivery"',
         '"drone manufacturer"']
BROAD_STOPPED = "2025-10-21"  # no 10-K in the year to the screen's end date
MIN_TERMS_ACTIVE = 4  # an active company's 10-K is scored when it matches at least this many broad terms
OUT = ROOT / "data" / "screen"


def broad_hits():
    rows = []
    for phrase in BROAD:
        frm = 0
        while True:
            url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode({
                "q": phrase, "forms": "10-K", "dateRange": "custom", "startdt": START, "enddt": END, "from": frm})
            r = sec_json(url)
            hits = r["hits"]["hits"]
            for h in hits:
                s = h["_source"]
                rows.append({"phrase": phrase, "cik": int(s["ciks"][0]), "name": s["display_names"][0],
                             "adsh": s["adsh"], "file_date": s["file_date"]})
            frm += len(hits)
            if not hits or frm >= r["hits"]["total"]["value"]:
                break
    return pd.DataFrame(rows)


def run():
    known = set(pd.read_csv(OUT / "edgar-phrase-hits.csv")["cik"])
    hits = broad_hits()
    hits.to_csv(OUT / "broad-phrase-hits.csv", index=False)
    new = hits[~hits.cik.isin(known)]
    terms = new.groupby(["cik", "adsh"])["phrase"].nunique().rename("broad_terms").reset_index()
    rows = []
    for cik, g in terms.groupby("cik"):
        filings, meta = company_10ks(int(cik))
        if not filings:
            continue
        f = pd.DataFrame(filings)
        last = f["file_date"].max()
        stopped = last < BROAD_STOPPED
        pick = g if stopped else g[g.broad_terms >= MIN_TERMS_ACTIVE]
        for _, p in pick.iterrows():
            doc = f.loc[f.adsh == p.adsh, "doc"]
            if doc.empty:
                continue  # a 10-K before START, or one whose main document isn't listed
            words, n = intensity(int(cik), p.adsh, doc.iloc[0])
            filed = f.loc[f.adsh == p.adsh, "file_date"].iloc[0]
            later = f.loc[f["file_date"] > filed, "file_date"]
            rows.append({"cik": cik, "name": meta["name"], "tickers": meta["tickers"], "exchanges": meta["exchanges"],
                         "sic_desc": meta["sic_desc"], "last_10k": last, "stopped_filing": stopped, "adsh": p.adsh,
                         "doc": doc.iloc[0], "file_date": filed, "next_10k": later.min() if len(later) else None,
                         "broad_terms": p.broad_terms, "words": words, "drone_terms": n,
                         "per_10k_words": round(1e4 * n / max(words, 1), 1)})
    out = pd.DataFrame(rows)
    out["passes_intensity"] = out["per_10k_words"] >= rules.INTENSITY_MIN
    out.to_csv(OUT / "broad-new-scored.csv", index=False)
    summary = {"broad_10k_hits": hits.adsh.nunique(), "broad_companies": hits.cik.nunique(),
               "new_companies": new.cik.nunique(), "new_stopped": int(out.drop_duplicates("cik").stopped_filing.sum()),
               "scored_10ks": len(out), "passing": out[out.passes_intensity].cik.nunique()}
    (ROOT / "output" / "screen-check-summary.json").write_text(json.dumps(summary, indent=1))
    return summary, out


def listed_on_exchange(cik, adsh, doc):
    """True if the 10-K's cover registers a class of stock under Section 12(b) on Nasdaq or the NYSE."""
    text = re.sub(r"\s+", " ", html_to_text(sec_text(
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{doc}")))
    i = text.find("12(b)")
    j = text.find("12(g)", i)
    return bool(i >= 0 and LISTED.search(text[i:j if j > i else i + 600]))


def spells():
    """Every 10-K at or above the intensity threshold and the spell it opens (to the company's next 10-K), from
    the phrase screen and from the broad check."""
    k = pd.read_csv(OUT / "drone-10k-intensity.csv", parse_dates=["file_date"]).sort_values("file_date")
    k["until"] = k.groupby("cik")["file_date"].shift(-1)
    b = pd.read_csv(OUT / "broad-new-scored.csv", parse_dates=["file_date", "next_10k"])
    s = pd.concat([k.assign(source="phrase screen"),
                   b.rename(columns={"next_10k": "until"}).assign(source="broad check")], ignore_index=True)
    s = s[s.per_10k_words >= rules.INTENSITY_MIN].copy()
    s["until"] = s["until"].fillna(pd.Timestamp(END))
    return s[["cik", "name", "adsh", "doc", "file_date", "until", "per_10k_words", "source"]]


def candidates():
    mat = pd.read_csv(ROOT / "config" / "drone-materiality.csv", parse_dates=["from", "to"])
    syms = sorted(set(SYMBOLS.values()))
    raw = prices.daily_bars(syms, start=START, end=END, adjustment="raw")
    val = (raw.assign(v=raw["vwap"].fillna(raw["close"]) * raw["volume"])
           .pivot(index="date", columns="symbol", values="v"))
    med = val.rolling(rules.LIQUIDITY_DAYS, min_periods=40).median().shift(1)
    rows = []
    for _, f in spells().iterrows():
        cik, end = f.cik, f.until
        listed = listed_on_exchange(cik, f.adsh, f.doc)
        sym = SYMBOLS.get(cik)
        m = med[sym].loc[f.file_date:end] if sym in med else pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        starts = m.groupby([m.index.year, m.index.month]).head(1)
        mm = mat[(mat.cik == cik) & (mat["from"] < end) & (mat["to"].isna() | (mat["to"] > f.file_date))]
        material = "yes" if (mm.material == "yes").any() else ("no" if len(mm) else "not reviewed")
        liquid = int((starts >= rules.LIQUIDITY_MIN).sum())
        days = int(val[sym].loc[f.file_date:end].notna().sum()) if sym in val else 0
        # Listed during the spell: on the 10-K's cover, or trading on an exchange later in it (Alpaca's
        # consolidated bars cover exchange-listed stocks only).
        outcome = ("fails listing" if not (listed or days) else "no prices" if not days else
                   "fails liquidity" if not liquid else "fails materiality" if material == "no" else
                   "member" if material == "yes" else "needs a materiality decision")
        rows.append({"source": f.source, "cik": cik, "name": f["name"], "filed": f.file_date.date(),
                     "until": end.date(), "per_10k_words": f.per_10k_words, "listed_on_cover": listed,
                     "symbol": sym, "price_days": days, "months": len(starts), "months_liquid": liquid,
                     "max_month_start_median_m": round(starts.max() / 1e6, 2) if starts.notna().any() else None,
                     "material": material, "outcome": outcome})
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "output" / "screen-candidates.csv", index=False)
    return out


if __name__ == "__main__":
    s, out = run()
    print(s)
    with pd.option_context("display.width", 220, "display.max_rows", 300):
        print(out.sort_values("per_10k_words", ascending=False).head(40).to_string(index=False))
