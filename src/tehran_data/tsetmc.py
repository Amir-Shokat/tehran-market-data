"""Tehran Stock Exchange market data (TSETMC public API).

Instruments are identified by their TSETMC *inscode* (a long integer). The exchange trades
Saturday to Wednesday, so Thursday and Friday are skipped when building date panels.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

import pandas as pd

from .http import HttpClient

log = logging.getLogger(__name__)
BASE = "https://cdn.tsetmc.com/api"


def tse_trading_days(start: str, end: str) -> list[str]:
    """YYYYMMDD strings from start to end, skipping Thursdays and Fridays."""
    d = datetime.strptime(start, "%Y%m%d").date()
    stop = datetime.strptime(end, "%Y%m%d").date()
    days = []
    while d <= stop:
        if d.weekday() not in (3, 4):        # Thursday=3, Friday=4
            days.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return days


class TsetmcClient:
    def __init__(self, http: HttpClient | None = None, base: str = BASE):
        self.http = http or HttpClient()
        self.base = base

    def closing_prices(self, inscode: str | int) -> pd.DataFrame:
        """Full daily price history (adjusted fields as provided by TSETMC)."""
        data = self.http.get_json(f"{self.base}/ClosingPrice/GetClosingPriceDailyList/{inscode}/0")
        df = pd.DataFrame(data.get("closingPriceDaily", []))
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["dEven"].astype(str), format="%Y%m%d")
        return df.set_index("date").sort_index()

    def instrument_history(self, inscode: str | int, on: str) -> dict:
        """Instrument characteristics on a date (YYYYMMDD), including the base volume."""
        data = self.http.get_json(f"{self.base}/Instrument/GetInstrumentHistory/{inscode}/{on}")
        return data.get("instrumentHistory") or {}

    def base_volume(self, inscode: str | int, on: str) -> float | None:
        value = self.instrument_history(inscode, on).get("baseVol")
        return float(value) if value is not None else None

    def shareholders(self, inscode: str | int, on: str) -> pd.DataFrame:
        """Major shareholders on a date. The API may also return the previous day; only the
        requested date is kept."""
        data = self.http.get_json(f"{self.base}/Shareholder/{inscode}/{on}")
        rows = [r for r in data.get("shareShareholder", []) if str(r.get("dEven")) == on]
        return pd.DataFrame(rows)

    def shareholder_panel(self, instruments: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        """Panel of major shareholders for many instruments and trading days.

        ``instruments`` needs columns ``inscode`` and ``symbol``; extra columns are carried
        through. Failed requests are logged and skipped so one bad day does not stop the run.
        """
        frames = []
        days = tse_trading_days(start, end)
        for _, ins in instruments.iterrows():
            for day in days:
                try:
                    df = self.shareholders(ins["inscode"], day)
                except Exception as exc:  # noqa: BLE001 - keep going, but record it
                    log.warning("%s %s: %s", ins["symbol"], day, exc)
                    continue
                if df.empty:
                    continue
                for col, value in ins.items():
                    df[col] = value
                df["symbol"] = re.sub(r"\d+$", "", str(ins["symbol"]))
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        panel = pd.concat(frames, ignore_index=True)
        panel["date"] = pd.to_datetime(panel["dEven"].astype(str), format="%Y%m%d")
        return panel.drop(columns="dEven").sort_values(["date", "inscode", "perOfShares"],
                                                      ascending=[True, True, False]).reset_index(drop=True)


def average_volume(prices: pd.DataFrame, as_of: date | str, days: int) -> float | None:
    """Mean of ``qTotTran5J`` (daily volume) over the last ``days`` trading days up to ``as_of``."""
    window = prices.loc[:pd.Timestamp(as_of)]
    window = window[window["qTotTran5J"] > 0].tail(days)
    return float(window["qTotTran5J"].mean()) if len(window) else None
