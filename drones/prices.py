"""Daily prices from Alpaca's free market data plan (Basic).

Bars are split- and dividend-adjusted (adjustment=all), so returns from adjusted closes include dividends.
Alpaca's terms allow personal, non-commercial use only and bar republishing, so prices and the series
derived from them stay out of git (see .gitignore): the repo keeps only summary figures computed from them.

Keys: the APCA_API_KEY_ID and APCA_API_SECRET_KEY environment variables. On Windows they are also read from
the user's registry environment, so a shell started before they were set still finds them.
"""
import json
import os

import pandas as pd

from .http import fetch

BARS = "https://data.alpaca.markets/v2/stocks/bars"


def _key(name):
    v = os.environ.get(name)
    if not v and os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = winreg.QueryValueEx(k, name)[0]
        except OSError:
            v = None
    if not v:
        raise RuntimeError(f"{name} is not set; see the README for Alpaca keys")
    return v


def _headers():
    return {"APCA-API-KEY-ID": _key("APCA_API_KEY_ID"), "APCA-API-SECRET-KEY": _key("APCA_API_SECRET_KEY")}


def daily_bars(symbols, start="2016-01-01", end=None, feed="sip", adjustment="all"):
    """Daily bars for several symbols: a long frame of date, symbol, close, volume, vwap. Adjusted ("all")
    closes give total returns; raw closes times shares outstanding give market values.

    Asked for a renamed company's old and new symbols together, Alpaca returns the old history under the new
    symbol only (United Technologies' UTX under RTX), so any symbol missing from the combined answer is asked
    for on its own."""
    df = _bars(symbols, start, end, feed, adjustment)
    missing = sorted(set(symbols) - set(df["symbol"] if len(df) else []))
    if len(symbols) > 1 and missing:
        df = pd.concat([df] + [_bars([s], start, end, feed, adjustment) for s in missing], ignore_index=True)
    if df.empty:
        return df
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def _bars(symbols, start, end, feed, adjustment):
    params = {"symbols": ",".join(sorted(set(symbols))), "timeframe": "1Day", "start": start,
              "adjustment": adjustment, "feed": feed, "limit": 10000, "sort": "asc"}
    if end:
        params["end"] = end
    rows, token = [], None
    headers = _headers()
    while True:
        q = dict(params, **({"page_token": token} if token else {}))
        url = BARS + "?" + "&".join(f"{k}={v}" for k, v in q.items())
        r = json.loads(fetch(url, headers=headers, min_gap=0.35))
        for sym, bars in (r.get("bars") or {}).items():
            for b in bars:
                rows.append({"date": b["t"][:10], "symbol": sym, "close": b["c"], "volume": b["v"],
                             "vwap": b.get("vw")})
        token = r.get("next_page_token")
        if not token:
            break
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def wide(df, field="close"):
    return df.pivot(index="date", columns="symbol", values=field).sort_index()
