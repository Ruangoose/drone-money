"""Factor attribution and catalyst windows.

Attribution regresses daily excess returns on the market, size, value, profitability, investment and
momentum factors (Kenneth French), with Newey-West standard errors. A basket's return then splits into each
factor's contribution (its beta times the factor's average return) and the unexplained part: the intercept,
which is what the theme itself earned beyond those exposures.

Catalyst windows compare the pair's return around an event with the return its factor exposures predict,
fitted on the year that ends 10 trading days before the event. The event's percentile is read against every
window of the same length in that year, so a three-day move is judged against the pair's ordinary three-day
moves.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

FACTORS = ["MKT", "SMB", "HML", "RMW", "CMA", "MOM"]


def regress(y, f, factors=FACTORS, lags=5, excess=True):
    df = pd.concat([y.rename("y"), f], axis=1, join="inner").dropna()
    yy = df["y"] - (df["RF"] if excess else 0.0)
    X = sm.add_constant(df[factors])
    res = sm.OLS(yy, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    contrib = {k: res.params[k] * df[k].mean() * 252 for k in factors}
    return {"n": len(df), "start": df.index[0].date(), "end": df.index[-1].date(), "r2": res.rsquared,
            "alpha_ann": res.params["const"] * 252, "alpha_t": res.tvalues["const"],
            "betas": res.params[factors].to_dict(), "t": res.tvalues[factors].to_dict(),
            "contrib_ann": contrib, "mean_excess_ann": yy.mean() * 252,
            "resid_vol_ann": res.resid.std() * np.sqrt(252)}


def rolling_betas(y, f, window=252, factors=("MKT", "SMB", "MOM")):
    df = pd.concat([y.rename("y"), f], axis=1, join="inner").dropna()
    out = []
    for i in range(window, len(df), 21):
        w = df.iloc[i - window:i]
        X = sm.add_constant(w[list(factors)])
        res = sm.OLS(w["y"] - w["RF"], X).fit()
        out.append({"date": df.index[i - 1], **{k: res.params[k] for k in factors}, "r2": res.rsquared})
    return pd.DataFrame(out).set_index("date")


def event_window(y, f, day, before=1, after=1, est=252, gap=10, factors=FACTORS):
    """Cumulative raw and abnormal return from the close `before` days ahead of `day` to the close `after`
    days after it (day 0 is the first trading day that could react)."""
    yi = y.dropna().index
    pos = yi.searchsorted(pd.Timestamp(day))
    if pos >= len(yi) or pos - before - gap - est < 0:
        return None
    win = yi[pos - before + 1: pos + after + 1]
    raw = float((1 + y.loc[win]).prod() - 1)
    base = {"first": win[0].date(), "last": win[-1].date(), "days": len(win), "raw": raw,
            "abnormal": np.nan, "percentile": np.nan, "typical_abs": np.nan}
    if not set(win) <= set(f.index):
        return base  # the factor files end before this window does: raw return only
    idx = yi.intersection(f.index)
    p = idx.searchsorted(win[0])
    est_idx = idx[max(0, p - gap - est): p - gap]
    df = pd.concat([y.rename("y"), f], axis=1).loc[est_idx].dropna()
    X = sm.add_constant(df[factors])
    res = sm.OLS(df["y"] - df["RF"], X).fit()
    fw = f.loc[win]
    pred = res.params["const"] + (fw[factors] * res.params[factors]).sum(axis=1) + fw["RF"]
    abn = float((y.loc[win] - pred).sum())
    # Same-length windows of residuals in the estimation year, for a percentile.
    sums = res.resid.rolling(len(win)).sum().dropna()
    base.update({"abnormal": abn, "percentile": float((sums < abn).mean()) if len(sums) else np.nan,
                 "typical_abs": float(sums.abs().median()) if len(sums) else np.nan})
    return base
