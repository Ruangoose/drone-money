"""Daily factors from the Kenneth R. French Data Library: market, size, value, profitability, investment
(the five-factor 2x3 set) and momentum. Downloaded at run time; only derived results are reported."""
import io
import zipfile

import pandas as pd

from .http import fetch

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "mom": "F-F_Momentum_Factor_daily_CSV.zip"}


def _read(name):
    raw = fetch(BASE + FILES[name], binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    head = next(i for i, l in enumerate(lines) if l.strip() and l.split(",")[0].strip() == "" and "," in l)
    body = []
    for l in lines[head + 1:]:
        cells = [c.strip() for c in l.split(",")]
        if not cells[0].isdigit() or len(cells[0]) != 8:
            if body:
                break
            continue
        body.append(cells)
    cols = ["date"] + [c.strip() for c in lines[head].split(",")[1:]]
    df = pd.DataFrame(body, columns=cols)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    return df.set_index("date").astype(float) / 100.0


def daily():
    f = _read("ff5").join(_read("mom"), how="inner")
    f.columns = [c.replace("Mkt-RF", "MKT").replace("Mom", "MOM").strip() for c in f.columns]
    return f
