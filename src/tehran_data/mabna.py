"""Mabna Data Processing instrument database (paid API; requires your own token).

The token is read from the MABNA_TOKEN environment variable and never stored in code.
"""

from __future__ import annotations

import base64
import os

import pandas as pd
import requests

from .http import HttpClient

BASE = "https://v1.db.api.mabnadp.com"


class MabnaClient:
    def __init__(self, token: str | None = None, http: HttpClient | None = None, base: str = BASE):
        token = token or os.environ.get("MABNA_TOKEN")
        if not token:
            raise RuntimeError("set the MABNA_TOKEN environment variable or pass token=")
        self.http = http or HttpClient(pause=1.0)
        auth = base64.b64encode(f"{token}:".encode()).decode()
        self.http.session.headers["Authorization"] = f"Basic {auth}"
        self.base = base

    def instruments(self, page_size: int = 100, limit: int | None = None) -> pd.DataFrame:
        """All exchange instruments, fetched page by page."""
        rows, skip = [], 0
        while True:
            try:
                page = self.http.get_json(f"{self.base}/exchange/instruments",
                                          params={"_count": page_size, "_skip": skip}).get("data", [])
            except requests.HTTPError as exc:
                if getattr(exc.response, "status_code", None) == 401:
                    raise RuntimeError("Mabna rejected the token (HTTP 401)") from exc
                raise
            if not page:
                break
            rows.extend(page)
            skip += page_size
            if limit and len(rows) >= limit:
                rows = rows[:limit]
                break
        return pd.DataFrame(rows)
