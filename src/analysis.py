"""Capture prices, capture rates, negative prices and cannibalisation."""
from __future__ import annotations

import numpy as np
import pandas as pd

TECHS = {"solar": "Solar", "wind_on": "Wind onshore", "wind_off": "Wind offshore"}


def capture_price(price: pd.Series, gen: pd.Series) -> float:
    """Generation-weighted average price: what the asset actually earns per MWh on the spot market."""
    m = gen.notna() & price.notna() & (gen > 0)
    return float((price[m] * gen[m]).sum() / gen[m].sum()) if m.any() else np.nan


def yearly_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per year: baseload price, capture price and capture rate per technology,
    number of negative-price hours, renewable shares."""
    rows = []
    for year, d in df.groupby(df.index.year):
        row = {"year": year, "baseload": d["price"].mean(), "neg_hours": int((d["price"] < 0).sum()),
               "hours": len(d)}
        for k in TECHS:
            if k in d and d[k].sum() > 0:
                cp = capture_price(d["price"], d[k])
                row[f"capture_{k}"] = cp
                row[f"rate_{k}"] = cp / row["baseload"]
                row[f"share_{k}"] = d[k].sum() / d["load"].sum()
        rows.append(row)
    return pd.DataFrame(rows).set_index("year")


def monthly_cannibalisation(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly solar share of load vs solar capture rate: the cannibalisation curve."""
    rows = []
    for m, d in df.groupby(pd.Grouper(freq="MS")):
        if len(d) < 24 * 20 or d["solar"].sum() <= 0:
            continue
        base = d["price"].mean()
        rows.append({"month": m, "solar_share": d["solar"].sum() / d["load"].sum(),
                     "solar_rate": capture_price(d["price"], d["solar"]) / base, "baseload": base})
    return pd.DataFrame(rows).set_index("month")


def fit_line(x: pd.Series, y: pd.Series) -> tuple[float, float, float]:
    """Least-squares slope, intercept and R^2."""
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return float(slope), float(intercept), float(r2)


def daily_profile(df: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Average price by hour of day for selected years (April to September): the 'duck curve'."""
    d = df[(df.index.month >= 4) & (df.index.month <= 9)]
    out = {y: d[d.index.year == y].groupby(d[d.index.year == y].index.hour)["price"].mean() for y in years}
    return pd.DataFrame(out)
