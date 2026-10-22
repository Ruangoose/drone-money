"""Who wins DoD's drone money: contract obligations under product code 1550 (unmanned aircraft) by fiscal
year, as a share of all DoD contract obligations, and split by recipient group (the drone basket's
companies, the primes, other listed firms, private firms).

Code 1550 understates the theme: loitering munitions and counter-drone systems are usually booked under
other product codes (guided missiles, fire control, communications). It is a clean, comparable series all the
same. Fiscal 2026 ended on 30 September 2026; DoD's contract data reaches USAspending with up to 90 days'
delay, so its last quarter is incomplete.

`wider` adds what code 1550 misses, two ways. (1) Code 1425 (guided missile systems, complete), where most
Switchblade and LASSO loitering-munition money sits, added whole, and then 1410 (guided missiles) as well: they
also carry the primes' missiles.
(2) Only the contract actions outside 1550 whose descriptions name loitering munitions or counter-drone
systems (LOITERING, COUNTER_DRONE, programme names included), plus Coyote, the counter-drone interceptor,
under the guided-missile and defense R&D codes. Descriptions that name a programme only by a generic phrase
("all up rounds") are missed, so this version understates both. Counter-drone work has no product code of its own: it is spread over R&D, electronics
modification, engineering services, electronic countermeasures and guided-missile codes.
"""
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import companies
from .http import ROOT, post_json
from .primes import API, _filters, parent_of

FYS = range(2016, 2027)
OUT = ROOT / "data" / "screen"
# Names and programmes as contracting officers write them (LASSO is the Army's Low Altitude Stalking and Strike
# Ordnance; OPF-L is the Marines' Organic Precision Fires-Light; SB300 is Switchblade 300).
LOITERING = ["switchblade", "SB300", "SB600", "loitering munition", "loitering munitions", "loitered munition",
             "loitered munitions", "LASSO", "low altitude stalking", "organic precision fires", "OPF-L", "LMAMS",
             "lethal miniature aerial"]
COUNTER_DRONE = ["counter-UAS", "C-UAS", "CUAS", "counter-sUAS", "C-sUAS", "counter unmanned", "counter-drone",
                 "counter drone", "counter small unmanned", "counter-small unmanned", "M-LIDS", "FS-LIDS"]
# "Coyote" also names a uniform colour and other kit, so it counts only under these codes.
COYOTE_CODES = ("14", "AC")
# USAspending's keyword search is fuzzy ("CUAS" also finds "Rio Cuarto"), so an action counts only when its own
# description names one of the terms.
NAMED = re.compile(r"counter|c[- ]?s?uas|cuxs|lids|loiter|switchblade|lasso|stalking|precision fires|opf|sb[36]00|"
                   r"lmams|lethal miniature|coyote|drone ?buster", re.I)
TXN_FIELDS = ["Award ID", "Mod", "Recipient Name", "Action Date", "Transaction Amount", "Transaction Description",
              "product_or_service_code", "internal_id", "recipient_id"]


def total_by_fy(extra=None):
    body = {"group": "fiscal_year", "filters": _filters(FYS[0], **(extra or {}))}
    body["filters"]["time_period"] = [{"start_date": f"{FYS[0] - 1}-10-01", "end_date": f"{FYS[-1]}-09-30"}]
    r = post_json(f"{API}/search/spending_over_time/", body)
    return {int(x["time_period"]["fiscal_year"]): x["aggregated_amount"] for x in r["results"]}


def _grouped(rows):
    """Add each recipient's company and group (companies.py), looking parents up in parallel."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        parents = list(pool.map(lambda c: parent_of(c["recipient_id"], c["recipient"]), rows))
    for c, (_, pname) in zip(rows, parents):
        c["parent"] = pname
        c["company"] = companies.company(c["recipient"], c["fy"], pname)
        c["group"] = companies.group(c["company"])
    return pd.DataFrame(rows)


def split(extra):
    """The top 200 recipients' obligations each fiscal year under the filter `extra`, with their groups."""
    rows = []
    for fy in FYS:
        for page in (1, 2):
            r = post_json(f"{API}/search/spending_by_category/recipient/",
                          {"filters": _filters(fy, **extra), "category": "recipient", "limit": 100, "page": page})
            rows += [{"fy": fy, "recipient": c["name"], "recipient_id": c["recipient_id"], "amount": c["amount"]}
                     for c in r["results"]]
            if not r["page_metadata"].get("hasNext"):
                break
    return _grouped(rows)


def run():
    total = total_by_fy()
    drones = total_by_fy({"psc_codes": ["1550"]})
    rec = split({"psc_codes": ["1550"]})
    rec[["fy", "recipient", "parent", "company", "amount", "group"]].to_csv(
        OUT / "dod-drone-psc1550-recipients.csv", index=False)
    by = rec.pivot_table(index="fy", columns="group", values="amount", aggfunc="sum").fillna(0.0)
    by["top_recipients_sum"] = by.sum(axis=1)
    by["psc1550_total"] = pd.Series(drones)
    by["dod_total"] = pd.Series(total)
    by["psc1550_share_of_dod"] = by["psc1550_total"] / by["dod_total"]
    by.to_csv(OUT / "dod-drone-psc1550-by-fy.csv")
    return by


def transactions(fy, keywords):
    """Every DoD contract action in fiscal year `fy` whose record matches any of `keywords`."""
    rows, page = [], 1
    while True:
        r = post_json(f"{API}/search/spending_by_transaction/",
                      {"filters": _filters(fy, keywords=keywords), "fields": TXN_FIELDS, "limit": 100,
                       "page": page, "sort": "Transaction Amount", "order": "desc"})
        rows += r["results"]
        if not r["page_metadata"].get("hasNext"):
            break
        page += 1
    return rows


def shares(name, total, rec):
    """Each group's share of `total` (by fiscal year), and AeroVironment's and Kratos's."""
    by = rec.pivot_table(index="fy", columns="group", values="amount", aggfunc="sum").reindex(FYS).fillna(0.0)
    out = by.div(pd.Series(total), axis=0).add_prefix("share_")
    for comp in ("AeroVironment", "Kratos"):
        out[f"share_{comp}"] = rec[rec.company == comp].groupby("fy")["amount"].sum().reindex(FYS).fillna(0.0) / \
            pd.Series(total)
    return out.assign(variant=name, total=pd.Series(total)).rename_axis("fy").reset_index()


def wider():
    base = pd.read_csv(OUT / "dod-drone-psc1550-recipients.csv")
    t1550 = pd.Series(total_by_fy({"psc_codes": ["1550"]}))

    # (1) Code 1425 added whole, then 1410 (guided missiles), which holds a little Switchblade money too.
    w1425, t1425 = split({"psc_codes": ["1425"]}), pd.Series(total_by_fy({"psc_codes": ["1425"]}))
    w1410, t1410 = split({"psc_codes": ["1410"]}), pd.Series(total_by_fy({"psc_codes": ["1410"]}))

    # (2) Contract actions outside 1550 that name loitering munitions or counter-drone systems.
    acts = []
    for fy in FYS:
        for kind, kws, codes in (("loitering munitions", LOITERING, None), ("counter-drone", COUNTER_DRONE, None),
                                 ("coyote", ["coyote"], COYOTE_CODES)):
            for t in transactions(fy, kws):
                psc = t.get("product_or_service_code") or ""
                if psc == "1550" or (codes and not psc.startswith(codes)) or \
                        not NAMED.search(t["Transaction Description"] or ""):
                    continue
                acts.append({"fy": fy, "id": t["internal_id"], "award": t["Award ID"], "mod": t["Mod"],
                             "date": t["Action Date"], "recipient": t["Recipient Name"],
                             "recipient_id": t["recipient_id"], "psc": psc, "amount": t["Transaction Amount"] or 0.0,
                             "description": t["Transaction Description"], "matched": kind})
    acts = _grouped(pd.DataFrame(acts).drop_duplicates("id").to_dict("records"))
    acts.to_csv(OUT / "dod-drone-keyword-actions.csv", index=False)
    t_acts = acts.groupby("fy")["amount"].sum().reindex(FYS).fillna(0.0)

    out = pd.concat([
        shares("1550", t1550, base),
        shares("1550 + 1425", t1550 + t1425, pd.concat([base, w1425[base.columns]])),
        shares("1550 + 1425 + 1410", t1550 + t1425 + t1410,
               pd.concat([base, w1425[base.columns], w1410[base.columns]])),
        shares("1550 + named actions", t1550 + t_acts, pd.concat([base, acts[base.columns]])),
    ], ignore_index=True)
    out.to_csv(OUT / "dod-drone-wider-by-fy.csv", index=False)
    return out, acts


if __name__ == "__main__":
    with pd.option_context("display.width", 200):
        by = run()
        share = by.pop("psc1550_share_of_dod")
        print((by / 1e6).round(1).assign(share_pct=(share * 100).round(3)))
