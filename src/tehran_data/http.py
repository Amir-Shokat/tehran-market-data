"""A small HTTP helper with retries, back-off and polite rate limiting."""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)


class HttpClient:
    def __init__(self, session: requests.Session | None = None, pause: float = 0.2,
                 retries: int = 3, backoff: float = 2.0, timeout: float = 20.0):
        self.session = session or requests.Session()
        self.pause, self.retries, self.backoff, self.timeout = pause, retries, backoff, timeout
        self._last = 0.0

    def get_json(self, url: str, **kwargs):
        """GET a JSON document. Retries on connection errors and 5xx/429; raises on other 4xx."""
        for attempt in range(1, self.retries + 1):
            wait = self.pause - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.get(url, timeout=self.timeout, **kwargs)
                self._last = time.monotonic()
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and 400 <= status < 500 and status != 429:
                    raise
                if attempt == self.retries:
                    raise
                delay = self.backoff ** attempt
                log.warning("%s failed (%s); retry %d in %.0fs", url, exc, attempt, delay)
                time.sleep(delay)
