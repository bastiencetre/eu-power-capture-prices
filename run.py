"""Run the full analysis: download (cached), compute tables, save figures and a summary.

Usage:  python run.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.analysis import daily_profile, fit_line, monthly_cannibalisation, yearly_table
from src.data import hourly

OUT = Path(__file__).resolve().parent
FIG = OUT / "figures"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
COL = {"DE": "#1f4e79", "FR": "#c0392b"}


def year_labels(t):
    """Mark the current, incomplete year (e.g. '2026 (Jan-Sep)') so it is not read as a full year."""
    full = {y: 8784 if y % 4 == 0 else 8760 for y in t.index}
    last = t.index.max()
    out = [str(y) for y in t.index]
    if t.loc[last, "hours"] < full[last] - 24:
        months = round(t.loc[last, "hours"] / 730)
        out[-1] = f"{last}\n(Jan-{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][months - 1]})"
    return out


def main():
    tables, cann, data = {}, {}, {}
    for zone in ["DE", "FR"]:
        print(f"Loading {zone}…")
        df = hourly(zone)
        data[zone] = df
        tables[zone] = yearly_table(df)
        cann[zone] = monthly_cannibalisation(df)
        tables[zone].round(3).to_csv(OUT / f"results_yearly_{zone}.csv")

    # 1. Solar capture rate by year
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for z, t in tables.items():
        ax.plot(t.index, t["rate_solar"] * 100, marker="o", color=COL[z], label=f"Solar {z}")
        if "rate_wind_on" in t:
            ax.plot(t.index, t["rate_wind_on"] * 100, marker="s", ls="--", color=COL[z], alpha=.6, label=f"Wind onshore {z}")
    ax.axhline(100, color="grey", lw=.8)
    ax.set_xticks(t.index); ax.set_xticklabels(year_labels(t))
    ax.set_ylabel("Capture rate (% of baseload price)")
    ax.set_title("Capture rate: what solar and wind earn vs the average price")
    ax.legend(ncol=2, fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "capture_rates.png"); plt.close(fig)

    # 2. Negative-price hours
    fig, ax = plt.subplots(figsize=(7, 3.4))
    w = 0.38
    for i, (z, t) in enumerate(tables.items()):
        ax.bar(t.index + (i - .5) * w, t["neg_hours"], width=w, color=COL[z], label=z)
    ax.set_xticks(t.index); ax.set_xticklabels(year_labels(t))
    ax.set_ylabel("Hours with a negative day-ahead price")
    ax.set_title("Negative-price hours per year")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "negative_hours.png"); plt.close(fig)

    # 3. Cannibalisation curve (monthly)
    fig, ax = plt.subplots(figsize=(6, 4))
    fits = {}
    for z, c in cann.items():
        ax.scatter(c["solar_share"] * 100, c["solar_rate"] * 100, s=14, color=COL[z], alpha=.7, label=z)
        fits[z] = fit_line(c["solar_share"] * 100, c["solar_rate"] * 100)
        s, i, r2 = fits[z]
        xs = c["solar_share"].sort_values() * 100
        ax.plot(xs, s * xs + i, color=COL[z], lw=1.2)
    ax.set_xlabel("Solar generation / load in the month (%)")
    ax.set_ylabel("Solar capture rate (%)")
    ax.set_title("The more solar, the less each solar MWh is worth")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "cannibalisation.png"); plt.close(fig)

    # 4. Duck curve
    years = [y for y in [2019, 2022, 2024, 2026] if y in tables["DE"].index]
    prof = daily_profile(data["DE"], years)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for y in prof:
        ax.plot(prof.index, prof[y], marker=".", label=str(y))
    ax.set_xlabel("Hour of day"); ax.set_ylabel("EUR/MWh")
    ax.set_title("Germany, April-September: average day-ahead price by hour")
    ax.legend(frameon=False, ncol=4)
    fig.tight_layout(); fig.savefig(FIG / "duck_curve_DE.png"); plt.close(fig)

    # Summary
    lines = ["# Results summary", ""]
    for z, t in tables.items():
        lines.append(f"## {z}")
        cols = ["baseload", "capture_solar", "rate_solar", "neg_hours", "share_solar"]
        lines.append("| year | " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * (len(cols) + 1))
        for (y, r), lab in zip(t[cols].iterrows(), year_labels(t)):
            lines.append(f"| {lab.replace(chr(10), ' ')} | " + " | ".join(f"{r[c]:.3f}" if c != "neg_hours" else f"{int(r[c])}" for c in cols) + " |")
        s, i, r2 = fits[z]
        lines.append(f"\nCannibalisation fit: each +1 pt of monthly solar share -> {s:+.2f} pt of solar capture rate (R^2 = {r2:.2f}).\n")
    (OUT / "results_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
