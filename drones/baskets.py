"""Basket returns from daily prices and a membership table.

Equal-weighted baskets are rebalanced at each month's first trading day and drift within the month, so small,
volatile names don't earn the artificial rebalancing gains of daily equal weights. A name joins or leaves at
the first rebalance on or after its membership dates.
"""
import numpy as np
import pandas as pd


def daily_returns(closes):
    return closes.pct_change(fill_method=None)


def month_starts(index):
    s = pd.Series(index, index=index)
    return set(s.groupby([index.year, index.month]).min())


def members_on(membership, basket, day):
    m = membership[(membership.basket == basket) & (membership.start <= day) &
                   ((membership.end.isna()) | (membership.end > day))]
    return sorted(m.symbol.unique())


def basket_returns(rets, membership, basket, liquid=None, caps=None):
    """Daily returns of a monthly-rebalanced basket, and the weights at each rebalance. Equal weights, or
    market-value weights when `caps` (date x symbol market values) is given, using the last value before the
    rebalance. `liquid` (date x symbol, True where the name passes the liquidity test using data to the
    previous day) filters members at each rebalance."""
    starts = month_starts(rets.index)
    out, held, w, log = [], [], None, []
    for day in rets.index:
        if day in starts or w is None:
            held = [s for s in members_on(membership, basket, day) if s in rets.columns]
            if liquid is not None:
                held = [s for s in held if s in liquid.columns and bool(liquid.at[day, s])]
            # A name needs a return today to be bought today (it has traded at least one day).
            held = [s for s in held if not np.isnan(rets.at[day, s])]
            if caps is not None and held:
                last = caps[caps.index < day].reindex(columns=held)
                mv = last.ffill().iloc[-1] if len(last) else pd.Series(np.nan, index=held)
                mv = mv.fillna(mv.median() if mv.notna().any() else 1.0)
                w = mv / mv.sum()
            else:
                w = pd.Series(1.0 / len(held), index=held) if held else pd.Series(dtype=float)
            log.append({"date": day, "basket": basket, "n": len(held), "names": ",".join(held)})
        if w.empty:
            out.append(np.nan)
            continue
        r = rets.loc[day, w.index].fillna(0.0)
        port = float((w * r).sum())
        out.append(port)
        w = w * (1 + r) / (1 + port)
    return pd.Series(out, index=rets.index, name=basket), pd.DataFrame(log)


def ols_beta(y, x):
    ok = y.notna() & x.notna()
    if ok.sum() < 60:
        return np.nan
    x_, y_ = x[ok] - x[ok].mean(), y[ok] - y[ok].mean()
    return float((x_ * y_).sum() / (x_ * x_).sum())


def hedged_pair(long, short, mkt, method="beta", window=252):
    """Long one unit of the long basket and short h units of the short basket, with h reset monthly from
    the trailing window (data to the previous day only): the ratio of market betas, or of volatilities."""
    starts = month_starts(long.index)
    h, hs = np.nan, []
    for i, day in enumerate(long.index):
        if day in starts or np.isnan(h):
            past = slice(max(0, i - window), i)
            l, s, m = long.iloc[past], short.iloc[past], mkt.reindex(long.index).iloc[past]
            if method == "beta":
                bl, bs = ols_beta(l, m), ols_beta(s, m)
                h = bl / bs if bs and not np.isnan(bs) else np.nan
            else:
                h = l.std() / s.std() if s.std() else np.nan
        hs.append(h)
    hs = pd.Series(hs, index=long.index, name="hedge_ratio")
    return (long - hs * short).rename(f"pair_{method}"), hs


def stats(r, periods=252):
    r = r.dropna()
    if r.empty:
        return {}
    growth = (1 + r).cumprod()
    years = len(r) / periods
    dd = growth / growth.cummax() - 1
    vol = r.std() * np.sqrt(periods)
    ann = growth.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan
    return {"start": r.index[0].date(), "end": r.index[-1].date(), "ann_return": ann, "ann_vol": vol,
            "sharpe_like": (r.mean() * periods) / vol if vol else np.nan, "max_drawdown": dd.min(),
            "total": growth.iloc[-1] - 1}
