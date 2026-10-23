"""A daily panel of every Iranian mutual fund from FIPIRAN.

For each day, FIPIRAN's ``fundcompare`` endpoint returns a snapshot of all funds: size, NAVs,
returns, asset mix and the firms behind each fund. Stacking these snapshots gives a fund x day
panel. Optionally each fund-day is enriched with ``getfund`` details (licences, investor
breakdown) and the TSETMC market index return is added for benchmarking.

This replaces the older notebooks in the `Fipiran-Web-Scraping-Iran-mutual-fund-Market`
repository, fixing these problems:

* details were requested for every fund on every date (also pairs that do not exist);
  now only funds present on a date are requested;
* missing numbers were written as the text "nan" when formatting large numbers;
* percentages were rescaled at a different step from where they were renamed, through
  several temporary Excel files; everything now happens in memory, once;
* the update notebook expected an Excel file the repository did not contain.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .fipiran import FipiranClient, flatten_funds
from .text import clean_firm_name
from .tsetmc import TsetmcClient

log = logging.getLogger(__name__)

TEDPIX = "32097828799138957"      # TSETMC code of the main Tehran exchange index
FIRM_COLUMNS = ("manager", "guarantor", "custodian", "auditor")
# columns FIPIRAN reports in percent; converted to fractions (5.2 -> 0.052)
PERCENT_COLUMNS = (
    "daily_return", "weekly_return", "monthly_return", "quarterly_return", "six_month_return",
    "annual_return", "cumulative_return", "fiveBest", "stock", "bond", "other", "cash",
    "deposit", "fundUnit", "commodity", "insInvPercent", "legalPercent", "naturalPercent",
    "retInvPercent",
)
RENAME = {
    "dailyEfficiency": "daily_return", "weeklyEfficiency": "weekly_return",
    "monthlyEfficiency": "monthly_return", "quarterlyEfficiency": "quarterly_return",
    "sixMonthEfficiency": "six_month_return", "annualEfficiency": "annual_return",
    "efficiency": "cumulative_return", "prosoectusLink": "prospectusLink",
}


def _dates(start, end) -> list[date]:
    start, end = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _code(value) -> str | None:
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value) if not isinstance(value, float) else str(int(value))


def tidy_snapshot(items, on: date) -> pd.DataFrame:
    """Clean one day's ``fundcompare`` items."""
    df = flatten_funds(items)
    if df.empty:
        return df
    df = df.rename(columns=RENAME)
    df["date"] = pd.Timestamp(on)
    for col in FIRM_COLUMNS:
        if col in df:
            df[col] = df[col].map(clean_firm_name)
    if "websiteAddress" in df:
        df["websiteAddress"] = df["websiteAddress"].astype(str).str.strip("[]'\" ").replace({"": None, "None": None, "nan": None})
    for col in PERCENT_COLUMNS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce") / 100
    for col in ("fundSize", "netAsset", "statisticalNav", "cancelNav", "issueNav"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "insCode" in df:
        # 17-digit codes exceed float precision; read them from the raw JSON (exact Python ints)
        # because a DataFrame column mixing ints and blanks is stored as floats and rounded
        df["insCode"] = [_code(i.get("insCode")) for i in items]
    return df


def flatten_details(item: dict) -> dict:
    """``getfund`` item -> flat dict; the licence list is reduced to its first entry."""
    out = {k: v for k, v in item.items() if not isinstance(v, (list, dict)) and k != "name"}
    licences = item.get("mutualFundLicenses") or []
    if licences and isinstance(licences[0], dict):
        out.update({f"license_{k}": v for k, v in licences[0].items() if k != "regNo"})
    return out


class FundPanelBuilder:
    def __init__(self, fipiran: FipiranClient | None = None, tsetmc: TsetmcClient | None = None):
        self.fipiran = fipiran or FipiranClient()
        self.tsetmc = tsetmc or TsetmcClient(self.fipiran.http)

    def fund_types(self) -> pd.DataFrame:
        data = self.fipiran.http.get_json(f"{self.fipiran.base}/fundtype")
        types = pd.json_normalize(data.get("items", []))
        if types.empty:
            return types
        types = types[["fundType", "name"]].rename(columns={"name": "fund_type_name"})
        types["fund_type_name"] = types["fund_type_name"].str.replace(r"^در\s*", "", regex=True)
        return types

    def snapshot(self, on: date) -> pd.DataFrame:
        data = self.fipiran.http.get_json(f"{self.fipiran.base}/fundcompare", params={"date": on.isoformat()})
        return tidy_snapshot(data.get("items", []), on)

    def details(self, reg_no, on: date) -> dict | None:
        data = self.fipiran.http.get_json(f"{self.fipiran.base}/getfund",
                                          params={"regno": reg_no, "date": on.isoformat()})
        item = (data or {}).get("item")
        return flatten_details(item) if item else None

    def index_returns(self, code: str = TEDPIX) -> pd.DataFrame:
        data = self.tsetmc.http.get_json(f"{self.tsetmc.base}/Index/GetIndexB2History/{code}")
        idx = pd.DataFrame(data.get("indexB2", []))
        if idx.empty:
            return pd.DataFrame(columns=["date", "index_close", "index_return"])
        idx["date"] = pd.to_datetime(idx["dEven"].astype(str), format="%Y%m%d")
        idx = idx.sort_values("date").groupby("date", as_index=False)["xNivInuClMresIbs"].last()
        idx = idx.rename(columns={"xNivInuClMresIbs": "index_close"})
        idx["index_return"] = idx["index_close"].pct_change()
        return idx

    def build(self, start, end, details: bool = False, index: bool = True) -> pd.DataFrame:
        """Fund x day panel from ``start`` to ``end`` (inclusive). Days that fail are logged and skipped."""
        frames = []
        for day in _dates(start, end):
            try:
                snap = self.snapshot(day)
            except Exception as exc:  # noqa: BLE001 - one bad day should not stop the run
                log.warning("snapshot %s failed: %s", day, exc)
                continue
            if snap.empty:
                continue
            if details:
                rows = []
                for reg_no in snap["regNo"].dropna().unique():   # only funds that exist on this day
                    try:
                        d = self.details(reg_no, day)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("details %s %s failed: %s", reg_no, day, exc)
                        continue
                    if d:
                        rows.append({**d, "regNo": reg_no})
                if rows:
                    extra = pd.DataFrame(rows)
                    new_cols = ["regNo"] + [c for c in extra.columns if c not in snap.columns]
                    snap = snap.merge(extra[new_cols], on="regNo", how="left")
            frames.append(snap)
        if not frames:
            return pd.DataFrame()
        panel = pd.concat(frames, ignore_index=True)
        types = self.fund_types()
        if not types.empty and "fundType" in panel:
            panel = panel.merge(types, on="fundType", how="left")
        if index:
            panel = panel.merge(self.index_returns()[["date", "index_return"]], on="date", how="left")
        return panel.sort_values(["date", "regNo"]).reset_index(drop=True)


def read_panel(path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, dtype={"insCode": str})
    df["date"] = pd.to_datetime(df["date"])
    return df


def write_panel(df: pd.DataFrame, path) -> None:
    path = Path(path)
    if path.suffix == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")


def update_panel(path, builder: FundPanelBuilder | None = None, end=None, **kwargs) -> pd.DataFrame:
    """Append the days after the last date in an existing panel file, then save it."""
    builder = builder or FundPanelBuilder()
    old = read_panel(path)
    start = old["date"].max() + timedelta(days=1)
    end = pd.Timestamp(end or datetime.today())
    if start > end:
        log.info("panel already up to date (%s)", old["date"].max().date())
        return old
    new = builder.build(start, end, **kwargs)
    panel = pd.concat([old, new], ignore_index=True).drop_duplicates(["date", "regNo"], keep="last")
    panel = panel.sort_values(["date", "regNo"]).reset_index(drop=True)
    write_panel(panel, path)
    return panel
