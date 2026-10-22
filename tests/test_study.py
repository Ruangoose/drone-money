"""Checks on the study's rules and arithmetic, on made-up data (no downloads)."""
import json

import numpy as np
import pandas as pd
import pytest

from drones import attribution, baskets, companies, rules
from drones.http import ROOT


def test_monthly_rebalance_lets_weights_drift():
    days = pd.bdate_range("2024-01-29", "2024-02-06")
    rets = pd.DataFrame({"A": 0.10, "B": 0.0}, index=days)
    mem = pd.DataFrame({"symbol": ["A", "B"], "basket": "x", "start": pd.Timestamp("2020-01-01"), "end": pd.NaT})
    r, log = baskets.basket_returns(rets, mem, "x")
    # Equal weights on the first day; A's weight grows within January; back to equal on 1 February.
    assert r.iloc[0] == pytest.approx(0.05)
    assert r.iloc[1] == pytest.approx(0.5 * 1.10 / 1.05 * 0.10)
    assert r.loc["2024-02-01"] == pytest.approx(0.05)
    assert list(log["n"]) == [2, 2]


def test_a_name_joins_at_the_first_rebalance_after_its_start():
    days = pd.bdate_range("2024-01-02", "2024-03-05")
    rets = pd.DataFrame({"A": 0.0, "B": 0.01}, index=days)
    mem = pd.DataFrame({"symbol": ["A", "B"], "basket": "x", "start": [pd.Timestamp("2020-01-01"),
                        pd.Timestamp("2024-01-15")], "end": pd.NaT})
    r, log = baskets.basket_returns(rets, mem, "x")
    assert r.loc["2024-01-31"] == 0.0  # B isn't held in January
    assert log.set_index("date").loc["2024-02-01", "names"] == "A,B"


def test_hedge_ratio_uses_only_past_data():
    days = pd.bdate_range("2020-01-01", periods=600)
    rng = np.random.default_rng(1)
    mkt = pd.Series(rng.normal(0, 0.01, len(days)), index=days)
    long, short = 2 * mkt, mkt.copy()
    _, h = baskets.hedged_pair(long, short, mkt, "beta")
    before = h.copy()
    long.iloc[-1] = 5.0  # a shock on the last day can't change any ratio already set
    _, h2 = baskets.hedged_pair(long, short, mkt, "beta")
    pd.testing.assert_series_equal(before, h2)
    assert h.dropna().iloc[-1] == pytest.approx(2.0)


def test_spells_merge_when_they_overlap():
    t = pd.Timestamp
    df = pd.DataFrame({"symbol": ["A", "A", "A"], "basket": "drones",
                       "start": [t("2020-01-01"), t("2020-06-01"), t("2023-01-01")],
                       "end": [t("2020-12-31"), t("2021-06-30"), pd.NaT], "reason": ["a", "b", "c"]})
    out = rules.merge_spells(df)
    assert len(out) == 2
    assert out.iloc[0]["end"] == t("2021-06-30") and pd.isna(out.iloc[1]["end"])


def test_recipients_follow_mergers_by_year():
    assert companies.company("RAYTHEON COMPANY", 2018) == "Raytheon"
    assert companies.company("RAYTHEON COMPANY", 2021) == "RTX"
    assert companies.company("ORBITAL ATK, INC.", 2017) == "Orbital ATK"
    assert companies.company("ORBITAL ATK, INC.", 2019) == "Northrop Grumman"
    assert companies.company("AEROJET ROCKETDYNE, INC.", 2025) == "L3Harris"
    assert companies.group("Teal Drones") == "other" and companies.group(companies.company("TEAL DRONES INC", 2025)) \
        == "drone basket companies"


def test_event_window_against_its_own_year():
    days = pd.bdate_range("2020-01-01", periods=400)
    rng = np.random.default_rng(2)
    f = pd.DataFrame({k: rng.normal(0, 0.01, len(days)) for k in attribution.FACTORS}, index=days)
    f["RF"] = 0.0
    y = f["MKT"] + rng.normal(0, 0.002, len(days))
    y.iloc[350] += 0.10  # a 10% surprise on day 0
    r = attribution.event_window(y, f, days[350], before=1, after=1)
    assert r["abnormal"] == pytest.approx(0.10, abs=0.01)
    assert r["percentile"] == 1.0


def test_published_site_files_hold_no_price_series():
    """Only shares.json (git-ignored) may hold series drawn from Alpaca's prices."""
    site = ROOT / "output" / "site"
    if not (site / "summary.json").exists():
        pytest.skip("run run.py first")
    for name in ("summary.json", "spending.json", "baskets.json"):
        text = (site / name).read_text(encoding="utf-8")

        def longest(o):
            if isinstance(o, list):
                nums = sum(isinstance(v, float) for v in o)
                return max([nums] + [longest(v) for v in o])
            if isinstance(o, dict):
                return max([0] + [longest(v) for v in o.values()])
            return 0
        assert longest(json.loads(text)) <= 20, name
