"""The primes basket's ranking, from USAspending.gov.

For each federal fiscal year (October to September), the Department of Defense's contract obligations (award
types A-D) of the top 150 recipients are summed by company, matched on the recipients' own names with mergers
applied by year (companies.py; USAspending's own parent links put old contracts under today's parents and
mislabel some). For each of the 20 largest companies, the share of obligations under defense
manufacturing industry codes (DEFENSE_NAICS) is computed from its subsidiaries' NAICS breakdowns. That
separates the platform and weapons makers from health insurers, drug distributors, vaccine makers and
services firms.

rules.py then keeps US-listed parents with a defense manufacturing share of at least 50% and takes the six
largest.
A fiscal year's ranking sets the basket for the following calendar year (DoD contract data on USAspending
lags by up to 90 days, so FY t is complete by about the end of December).
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import companies
from .http import ROOT, get_json, post_json

API = "https://api.usaspending.gov/api/v2"
FYS = range(2015, 2026)
N_CHILDREN, N_PARENTS = 150, 20
OUT = ROOT / "data" / "screen"


def _filters(fy, **extra):
    return {"agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Defense"}],
            "time_period": [{"start_date": f"{fy - 1}-10-01", "end_date": f"{fy}-09-30"}],
            "award_type_codes": ["A", "B", "C", "D"], **extra}


def top_children(fy):
    rows = []
    for page in (1, 2):
        r = post_json(f"{API}/search/spending_by_category/recipient/",
                      {"filters": _filters(fy), "category": "recipient", "limit": 100, "page": page})
        rows += r["results"]
    return rows[:N_CHILDREN]


def parent_of(rid, name):
    """The recipient's parent; a recipient whose profile won't load stands as its own parent."""
    if not rid:
        return None, name
    try:
        p = get_json(f"{API}/recipient/{rid}/", timeout=30, retries=2)
    except Exception:
        return rid, name
    return p.get("parent_id") or rid, p.get("parent_name") or p.get("name") or name


# Defense manufacturing: ordnance and ammunition, communications equipment, electronic components,
# navigation and guidance, aerospace products, ships, military armored vehicles. A plain "manufacturing" test
# (NAICS 31-33) would let in the vaccine makers whose Operation Warp Speed contracts ran through DoD.
DEFENSE_NAICS = ("3329", "3342", "3344", "3345", "3364", "3366", "336992")


def naics_split(fy, rid):
    r = post_json(f"{API}/search/spending_by_category/naics/",
                  {"filters": _filters(fy, recipient_id=rid), "category": "naics", "limit": 100, "page": 1})
    codes = [(x["code"] or "", x["amount"]) for x in r["results"]]
    tot = sum(a for _, a in codes)
    man = sum(a for c, a in codes if c[:2] in ("31", "32", "33"))
    dfn = sum(a for c, a in codes if c.startswith(DEFENSE_NAICS))
    return tot, man, dfn


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    children = [(fy, c) for fy in FYS for c in top_children(fy)]
    # Profiles are independent lookups: fetch them in parallel (USAspending answers each in 1-3 seconds).
    ids = sorted({(c["recipient_id"], c["name"]) for _, c in children}, key=str)
    with ThreadPoolExecutor(max_workers=8) as pool:
        parents = dict(zip(ids, pool.map(lambda x: parent_of(*x), ids)))
    child_rows = []
    for fy, c in children:
        pid, pname = parents[(c["recipient_id"], c["name"])]
        child_rows.append({"fy": fy, "child": c["name"], "child_id": c["recipient_id"],
                           "parent_id": pid, "parent": pname, "obligations": c["amount"]})
    kids = pd.DataFrame(child_rows)
    # Companies by the recipients' own names (see companies.py: USAspending's parent links are unreliable).
    kids["company"] = [companies.company(c, fy, p) for c, fy, p in zip(kids.child, kids.fy, kids.parent)]
    parents = (kids.groupby(["fy", "company"])["obligations"].sum()
               .reset_index().sort_values(["fy", "obligations"], ascending=[True, False]))
    parents["rank"] = parents.groupby("fy")["obligations"].rank(ascending=False, method="first").astype(int)
    top = parents[parents["rank"] <= N_PARENTS].rename(columns={"company": "parent"})
    jobs = sorted({(int(p.fy), rid) for _, p in top.iterrows()
                   for rid in kids[(kids.fy == p.fy) & (kids.company == p.parent)]["child_id"] if rid})
    with ThreadPoolExecutor(max_workers=8) as pool:
        splits = dict(zip(jobs, pool.map(lambda j: naics_split(*j), jobs)))
    shares, dshares = [], []
    for _, p in top.iterrows():
        sub = kids[(kids.fy == p.fy) & (kids.company == p.parent)]
        tot = man = dfn = 0.0
        for rid in sub["child_id"]:
            if rid:
                t, m, d = splits[(int(p.fy), rid)]
                tot, man, dfn = tot + t, man + m, dfn + d
        shares.append(man / tot if tot else float("nan"))
        dshares.append(dfn / tot if tot else float("nan"))
    top = top.assign(manufacturing_share=shares, defense_mfg_share=dshares)
    kids.to_csv(OUT / "dod-top-children.csv", index=False)
    top.to_csv(OUT / "dod-top-parents.csv", index=False)
    return top


if __name__ == "__main__":
    top = run()
    with pd.option_context("display.width", 200, "display.max_rows", 300):
        print(top.assign(bn=(top.obligations / 1e9).round(2))[
            ["fy", "rank", "parent", "bn", "manufacturing_share", "defense_mfg_share"]].round(3))
