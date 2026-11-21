"""Download and cache day-ahead prices and generation by source from the Energy-Charts API.

Source: Energy-Charts (Fraunhofer ISE), https://api.energy-charts.info — data under CC BY 4.0
(prices from Bundesnetzagentur / SMARD.de and ENTSO-E).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

API = "https://api.energy-charts.info"
CACHE = Path(__file__).resolve().parent.parent / "data"
ZONES = {"DE": {"bzn": "DE-LU", "country": "de"}, "FR": {"bzn": "FR", "country": "fr"}}


def _get(url: str, retries: int = 6) -> dict:
    """GET with a raw-response cache (data/raw) and polite back-off on HTTP 429 (rate limit)."""
    raw = CACHE / "raw" / (url.split("/")[-1].replace("?", "_").replace("&", "_").replace("=", "-") + ".json")
    if raw.exists():
        return json.loads(raw.read_text())
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eu-power-capture-prices/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_bytes(body)
            time.sleep(1.5)  # be gentle with the public API
            return json.loads(body)
        except urllib.error.HTTPError as e:
            if attempt == retries - 1:
                raise
            time.sleep(30 * (attempt + 1) if e.code == 429 else 3)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def _years(start: str, end: str):
    for y in range(int(start[:4]), int(end[:4]) + 1):
        a, b = max(f"{y}-01-01", start), min(f"{y + 1}-01-01", end)
        if a < b:
            yield pd.Timestamp(a), pd.Timestamp(b)


def _to_index(seconds) -> pd.DatetimeIndex:
    return pd.to_datetime(seconds, unit="s", utc=True).tz_convert("Europe/Berlin")


def load_prices(zone: str, start: str = "2019-01-01", end: str | None = None) -> pd.Series:
    """Day-ahead price (EUR/MWh), hourly or 15-min depending on the period."""
    end = end or pd.Timestamp.today().strftime("%Y-%m-01")
    path = CACHE / f"prices_{zone}.csv.gz"
    if path.exists():
        s = pd.read_csv(path, index_col=0).iloc[:, 0]
        s.index = pd.to_datetime(s.index, utc=True).tz_convert("Europe/Berlin")
        return s
    parts = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        a, b = max(f"{y}-01-01", start), min(f"{y + 1}-01-01", end)
        j = _get(f"{API}/price?bzn={ZONES[zone]['bzn']}&start={a}&end={b}")
        parts.append(pd.Series(j["price"], index=_to_index(j["unix_seconds"]), name="price"))
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated()]
    CACHE.mkdir(exist_ok=True)
    s.to_csv(path)
    return s


def load_generation(zone: str, start: str = "2019-01-01", end: str | None = None) -> pd.DataFrame:
    """Public net generation by source and load (MW)."""
    end = end or pd.Timestamp.today().strftime("%Y-%m-01")
    path = CACHE / f"generation_{zone}.csv.gz"
    if path.exists():
        df = pd.read_csv(path, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert("Europe/Berlin")
        return df
    parts = []
    for a, b in _years(start, end):  # one request per year keeps us well under the rate limit
        j = _get(f"{API}/public_power?country={ZONES[zone]['country']}"
                 f"&start={a:%Y-%m-%d}&end={b:%Y-%m-%d}")
        cols = {p["name"]: p["data"] for p in j["production_types"]}
        parts.append(pd.DataFrame(cols, index=_to_index(j["unix_seconds"])))
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated()]
    CACHE.mkdir(exist_ok=True)
    df.to_csv(path)
    return df


def hourly(zone: str) -> pd.DataFrame:
    """Hourly table: price, load, solar, wind onshore, wind offshore (MW)."""
    price = load_prices(zone).resample("h").mean()
    gen = load_generation(zone)
    pick = {
        "load": "Load",
        "solar": "Solar",
        "wind_on": "Wind onshore",
        "wind_off": "Wind offshore",
    }
    g = pd.DataFrame({k: gen[v] for k, v in pick.items() if v in gen.columns}).resample("h").mean()
    df = pd.concat([price.rename("price"), g], axis=1).dropna(subset=["price"])
    return df
