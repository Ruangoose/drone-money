"""Quarterly fundamentals from SEC XBRL company facts: revenue, gross profit, operating income, backlog
(remaining performance obligations), cash, debt and shares outstanding.

Flows are rebuilt as quarters: 3-month facts where filed, and the fourth quarter as the fiscal year less the
first nine months. Trailing-twelve-month (TTM) values are the sum of the last four quarters. Balances (cash,
debt, backlog, shares) are point-in-time. Each value is dated by its filing date, not its period end, so a
valuation on any day uses only what had been published by then.
"""
import pandas as pd

from .http import sec_json

REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
           "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"]
FLOWS = {"revenue": REVENUE, "gross_profit": ["GrossProfit"], "cost_of_revenue":
         ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
         "operating_income": ["OperatingIncomeLoss"]}
STOCKS = {"cash": ["CashAndCashEquivalentsAtCarryingValue", "Cash",
                   "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
          "debt_long": ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations",
                        "ConvertibleNotesPayable"],
          "debt_current": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"],
          "backlog": ["RevenueRemainingPerformanceObligation"]}
SHARES = [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")]


def earnings_dates(cik, since="2016-01-01"):
    """Results announcements: 8-Ks with Item 2.02, and the first trading session that could react (the
    same day if accepted before 09:30 New York time, otherwise the next day)."""
    sub = sec_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    blocks = [sub["filings"]["recent"]]
    for f in sub["filings"].get("files", []):
        blocks.append(sec_json("https://data.sec.gov/submissions/" + f["name"]))
    rows = []
    for b in blocks:
        for form, items, acc in zip(b["form"], b["items"], b["acceptanceDateTime"]):
            if form.startswith("8-K") and "2.02" in (items or ""):
                ts = pd.Timestamp(acc).tz_convert("America/New_York")
                if ts.date().isoformat() >= since:
                    rows.append({"accepted": ts, "react_after_open": ts.hour * 60 + ts.minute >= 9 * 60 + 30})
    return pd.DataFrame(rows).drop_duplicates()


def company_facts(cik):
    return sec_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")


def _facts(cf, tag, ns="us-gaap", unit="USD"):
    try:
        rows = cf["facts"][ns][tag]["units"][unit]
    except KeyError:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[df["form"].str.startswith(("10-K", "10-Q", "20-F", "40-F"), na=False)]
    for c in ("start", "end", "filed"):
        if c in df:
            df[c] = pd.to_datetime(df[c])
    return df


def _quarters(cf, tags):
    """One revenue-type flow as quarters, from whichever tag covers each period (first tag wins)."""
    out = {}
    for tag in tags:
        df = _facts(cf, tag)
        if df.empty or "start" not in df:
            continue
        df["days"] = (df["end"] - df["start"]).dt.days
        df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="first")
        q = df[df.days.between(80, 100)]
        for _, r in q.iterrows():
            out.setdefault(r["end"], (r["val"], r["filed"]))
        # Fourth quarters: the year less the three quarters inside it.
        for _, y in df[df.days.between(350, 380)].iterrows():
            if y["end"] in out:
                continue
            inside = [(e, v) for e, v in out.items() if y["start"] < e < y["end"]]
            if len(inside) == 3:
                out[y["end"]] = (y["val"] - sum(v[0] for _, v in inside), y["filed"])
            nine = df[(df.start == y["start"]) & df.days.between(260, 285)]
            if y["end"] not in out and len(nine):
                out[y["end"]] = (y["val"] - nine.iloc[0]["val"], y["filed"])
    if not out:
        return pd.DataFrame(columns=["end", "val", "filed"])
    return (pd.DataFrame([(e, v, f) for e, (v, f) in out.items()], columns=["end", "val", "filed"])
            .sort_values("end").reset_index(drop=True))


def _balances(cf, tags, ns="us-gaap", unit="USD"):
    frames = []
    for tag in tags:
        df = _facts(cf, tag, ns, unit)
        if df.empty:
            continue
        frames.append(df[["end", "val", "filed"]].assign(tag=tag))
    if not frames:
        return pd.DataFrame(columns=["end", "val", "filed"])
    df = pd.concat(frames)
    # Prefer the earlier-listed tag for the same date, and the first filing of each value.
    df["pri"] = df["tag"].map({t: i for i, t in enumerate(tags)})
    df = df.sort_values(["end", "pri", "filed"]).drop_duplicates("end", keep="first")
    return df[["end", "val", "filed"]].reset_index(drop=True)


def quarterly(cik):
    """A frame indexed by quarter end, with each item and the date it was first filed."""
    cf = company_facts(cik)
    cols = {}
    for name, tags in FLOWS.items():
        q = _quarters(cf, tags)
        cols[name] = q.set_index("end")["val"]
        cols[name + "_filed"] = q.set_index("end")["filed"]
    df = pd.DataFrame(cols)
    if "revenue" in df:
        df["revenue_ttm"] = df["revenue"].rolling(4, min_periods=4).sum()
        if df["gross_profit"].notna().any():
            gp = df["gross_profit"]
        else:
            gp = df["revenue"] - df["cost_of_revenue"]
        df["gross_margin_ttm"] = gp.rolling(4, min_periods=4).sum() / df["revenue_ttm"]
        df["operating_margin_ttm"] = df["operating_income"].rolling(4, min_periods=4).sum() / df["revenue_ttm"]
        df["revenue_growth_yoy"] = df["revenue_ttm"] / df["revenue_ttm"].shift(4) - 1
    for name, tags in STOCKS.items():
        b = _balances(cf, tags)
        df = df.join(b.set_index("end")["val"].rename(name), how="outer")
    sh = pd.concat([_balances(cf, [t], ns, "shares") for ns, t in SHARES])
    sh = sh.sort_values("filed").drop_duplicates("end", keep="first").set_index("end")
    return df.sort_index(), sh.rename(columns={"val": "shares"})
