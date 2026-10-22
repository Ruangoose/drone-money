"""Fundamentals against price, month by month, per name and per basket.

Market value is the raw (unadjusted) close times the shares outstanding last reported before that day.
Enterprise value adds debt and subtracts cash from the last balance sheet filed. EV/sales uses the latest
filed trailing-twelve-month revenue. Everything is as published by each month-end, so there's no hindsight.
"""
import numpy as np
import pandas as pd

from . import fundamentals
from .http import sec_json


def ticker_ciks():
    j = sec_json("https://www.sec.gov/files/company_tickers.json")
    return {v["ticker"]: int(v["cik_str"]) for v in j.values()}


def _asof(series_by_filed, day):
    """Latest value whose filing date is on or before `day`."""
    s = series_by_filed[series_by_filed.index <= day]
    return s.iloc[-1] if len(s) else np.nan


def monthly(symbol, cik, raw_close):
    q, sh = fundamentals.quarterly(cik)
    if q.empty:
        return pd.DataFrame()
    # Index each quarterly item by the date it was filed, so lookups use only published numbers.
    filed = q["revenue_filed"].fillna(q.index.to_series() + pd.Timedelta(days=45))
    by_filed = q.assign(filed=filed).sort_values("filed").set_index("filed")
    shares = sh.reset_index().sort_values(["filed", "end"]).set_index("filed")["shares"]
    px = raw_close.dropna()
    month_ends = px.groupby([px.index.year, px.index.month]).tail(1)
    rows = []
    for day, price in month_ends.items():
        shs = _asof(shares, day)
        rev = _asof(by_filed["revenue_ttm"].dropna(), day)
        cash = _asof(by_filed["cash"].dropna(), day)
        debt = np.nansum([_asof(by_filed["debt_long"].dropna(), day), _asof(by_filed["debt_current"].dropna(), day)])
        mcap = price * shs
        ev = mcap + debt - (0 if np.isnan(cash) else cash)
        rows.append({"date": day, "symbol": symbol, "mcap": mcap, "ev": ev, "revenue_ttm": rev,
                     "ev_sales": ev / rev if rev and rev > 0 else np.nan,
                     "rev_growth": _asof(by_filed["revenue_growth_yoy"].dropna(), day),
                     "gross_margin": _asof(by_filed["gross_margin_ttm"].dropna(), day),
                     "op_margin": _asof(by_filed["operating_margin_ttm"].dropna(), day),
                     "backlog": _asof(by_filed["backlog"].dropna(), day), "shares": shs})
    df = pd.DataFrame(rows)
    df["shares_yoy"] = df["shares"] / df["shares"].shift(12) - 1
    df["backlog_to_sales"] = df["backlog"] / df["revenue_ttm"]
    return df


def basket_medians(per_name, membership_by_month):
    """Median of each measure across the names held in each basket that month."""
    m = per_name.merge(membership_by_month, on=["date", "symbol"])
    cols = ["ev_sales", "rev_growth", "gross_margin", "op_margin", "shares_yoy", "backlog_to_sales"]
    return m.groupby(["basket", "date"])[cols].median().reset_index()
