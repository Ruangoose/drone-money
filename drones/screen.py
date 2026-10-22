"""The drone basket's text screen, from SEC EDGAR.

Stage 1: full-text search finds every 10-K filed since 2016 that describes the company's own drones,
unmanned systems or counter-drone systems (possessive phrases such as "our drones", plus the product terms
"loitering munition" and "counter-UAS"/"counter-drone").
Stage 2: for every company found, each of its 10-Ks since 2016 is scored by drone intensity: mentions of drone
terms per 10,000 words of the annual report's main document. A 10-K passing the threshold makes the company
eligible from that filing's date until the filing date of its next 10-K (when it is scored again).
Stage 3 (rules.py) adds the revenue-share test from segment disclosures and the liquidity test from prices.
"""
import html
import re
import urllib.parse
from html.parser import HTMLParser

import pandas as pd

from .http import ROOT, sec_json, sec_text

PHRASES = [
    '"our drones"', '"our drone"', '"our UAS"', '"our sUAS"', '"our unmanned"', '"our UAVs"',
    '"our C-UAS"', '"our counter-UAS"', '"our counter-drone"', '"loitering munition"',
    '"loitering munitions"', '"counter-UAS"', '"counter-drone"',
]
START, END = "2016-01-01", "2026-10-21"

# Terms counted for intensity. Word boundaries keep "UAS" from matching inside other words.
TERMS = re.compile(
    r"\b(drones?|unmanned|s?UAS|UAVs?|UxS|counter-UAS|C-UAS|counter-drones?|loitering munitions?)\b",
    re.IGNORECASE,
)

OUT = ROOT / "data" / "screen"


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw):
    # Inline XBRL hides its header in <ix:header>; drop it before parsing.
    raw = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", raw)
    p = _Text()
    p.feed(raw)
    return html.unescape(" ".join(p.parts))


def search_hits():
    rows = []
    for phrase in PHRASES:
        frm = 0
        while True:
            url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode({
                "q": phrase, "forms": "10-K", "dateRange": "custom", "startdt": START, "enddt": END,
                "from": frm})
            r = sec_json(url)
            hits = r["hits"]["hits"]
            for h in hits:
                s = h["_source"]
                rows.append({"phrase": phrase, "cik": int(s["ciks"][0]), "name": s["display_names"][0],
                             "adsh": s["adsh"], "file_date": s["file_date"], "sic": (s.get("sics") or [""])[0]})
            frm += len(hits)
            if not hits or frm >= r["hits"]["total"]["value"]:
                break
    return pd.DataFrame(rows)


def company_10ks(cik):
    """Every 10-K (not amendments) a company filed since START, with its main document."""
    sub = sec_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    blocks = [sub["filings"]["recent"]]
    for f in sub["filings"].get("files", []):
        blocks.append(sec_json("https://data.sec.gov/submissions/" + f["name"]))
    rows = []
    for b in blocks:
        for form, adsh, fdate, doc, period in zip(b["form"], b["accessionNumber"], b["filingDate"],
                                                  b["primaryDocument"], b["reportDate"]):
            if form == "10-K" and fdate >= START:
                rows.append({"cik": cik, "adsh": adsh, "file_date": fdate, "period": period, "doc": doc})
    meta = {"name": sub["name"], "tickers": ",".join(sub.get("tickers", [])),
            "exchanges": ",".join(x or "" for x in sub.get("exchanges", [])), "sic": sub.get("sic"),
            "sic_desc": sub.get("sicDescription")}
    return rows, meta


def intensity(cik, adsh, doc):
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{doc}"
    text = html_to_text(sec_text(url))
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    hits = len(TERMS.findall(text))
    return words, hits


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    hits = search_hits()
    hits.to_csv(OUT / "edgar-phrase-hits.csv", index=False)
    rows, metas = [], {}
    for cik in sorted(hits["cik"].unique()):
        filings, meta = company_10ks(int(cik))
        metas[cik] = meta
        for f in filings:
            words, n = intensity(f["cik"], f["adsh"], f["doc"])
            rows.append({**f, **meta, "words": words, "drone_terms": n,
                         "per_10k_words": round(1e4 * n / max(words, 1), 1)})
    df = pd.DataFrame(rows).sort_values(["cik", "file_date"])
    df.to_csv(OUT / "drone-10k-intensity.csv", index=False)
    return hits, df


if __name__ == "__main__":
    hits, df = run()
    print(len(hits), "phrase hits;", hits["cik"].nunique(), "companies;", len(df), "10-Ks scored")
