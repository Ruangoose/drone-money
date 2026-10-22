"""Basket membership from the screens, by the rules in the README.

Output: one row per eligibility spell (symbol, basket, start, end, reason). Liquidity is applied later, at
each monthly rebalance, because it needs prices (traded value), not returns.
"""
import pandas as pd

from .http import ROOT

CONFIG = ROOT / "config"
SCREEN = ROOT / "data" / "screen"
# Drone terms per 10,000 words: a relevance filter, set from the intensity distribution (pure plays score
# 20-60, Kratos 10-22, Redwire 6.7, incidental mentions 2-6) before any returns were computed. The
# materiality test does the real separation.
INTENSITY_MIN = 5.0
LIQUIDITY_MIN = 5e6
LIQUIDITY_DAYS = 63
N_PRIMES = 6
MANUFACTURING_MIN = 0.5


def drone_spells(intensity_min):
    """Eligibility from each passing 10-K's filing date to the next 10-K's filing date (or open-ended),
    kept only where config/drone-materiality.csv confirms a drone segment or principal business."""
    k = pd.read_csv(SCREEN / "drone-10k-intensity.csv", parse_dates=["file_date"])
    mat = pd.read_csv(CONFIG / "drone-materiality.csv", parse_dates=["from", "to"])
    rows = []
    for cik, g in k.sort_values("file_date").groupby("cik"):
        g = g.reset_index(drop=True)
        for i, f in g.iterrows():
            if f.per_10k_words < intensity_min:
                continue
            end = g.file_date.iloc[i + 1] if i + 1 < len(g) else pd.NaT
            rows.append({"cik": cik, "start": f.file_date, "end": end, "adsh": f.adsh,
                         "per_10k_words": f.per_10k_words})
    spells = pd.DataFrame(rows)
    out = []
    for _, s in spells.iterrows():
        m = mat[(mat.cik == s.cik) & (mat.material == "yes")]
        for _, mm in m.iterrows():
            start = max(s.start, mm["from"])
            end = min(x for x in (s.end, mm["to"]) if pd.notna(x)) if pd.notna(s.end) or pd.notna(mm["to"]) else pd.NaT
            if pd.isna(end) or start < end:
                out.append({"symbol": mm.symbol, "basket": "drones", "start": start, "end": end,
                            "reason": f"10-K {s.adsh} ({s.per_10k_words}/10k words); {mm.basis}"})
    return merge_spells(pd.DataFrame(out))


def merge_spells(df):
    if df.empty:
        return df
    df = df.sort_values(["symbol", "start"])
    out = []
    for sym, g in df.groupby("symbol"):
        cur = None
        for _, r in g.iterrows():
            if cur is not None and (pd.isna(cur["end"]) or r.start <= cur["end"]):
                if pd.isna(r.end) or (pd.notna(cur["end"]) and r.end > cur["end"]):
                    cur["end"] = r.end
                cur["reason"] += " | " + r.reason
            else:
                if cur is not None:
                    out.append(cur)
                cur = r.to_dict()
        out.append(cur)
    return pd.DataFrame(out)


def prime_spells():
    """The six largest US-listed defense manufacturers by DoD obligations in fiscal year t, held through
    calendar year t+1. config/prime-tickers.csv maps the companies (named as in companies.py) to listed
    securities by date."""
    top = pd.read_csv(SCREEN / "dod-top-parents.csv")
    tick = pd.read_csv(CONFIG / "prime-tickers.csv", parse_dates=["from", "to"]).dropna(subset=["symbol"])
    rows = []
    for fy, g in top.groupby("fy"):
        start, end = pd.Timestamp(f"{fy + 1}-01-01"), pd.Timestamp(f"{fy + 2}-01-01")
        g = g[g.defense_mfg_share >= MANUFACTURING_MIN].sort_values("obligations", ascending=False)
        picked, picked_syms = 0, set()
        for _, p in g.iterrows():
            t = tick[(tick.company == p.parent) & (tick["from"] < end) &
                     (tick["to"].isna() | (tick["to"] > start))]
            if t.empty:
                continue  # not US-listed (private, foreign or a non-listed subsidiary)
            if set(t.symbol) <= picked_syms:
                continue  # a parent that has merged into one already picked (e.g. Raytheon into RTX)
            picked_syms |= set(t.symbol)
            for _, tt in t.iterrows():
                s = max(start, tt["from"])
                e = min(end, tt["to"]) if pd.notna(tt["to"]) else end
                rows.append({"symbol": tt.symbol, "basket": "primes", "start": s, "end": e,
                             "reason": f"FY{fy} rank by DoD obligations: {p.parent} "
                                       f"(${p.obligations / 1e9:.1f}bn, {p.manufacturing_share:.0%} manufacturing)"})
            picked += 1
            if picked == N_PRIMES:
                break
    return merge_spells(pd.DataFrame(rows))
