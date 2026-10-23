import pytest


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload

    def raise_for_status(self):
        import requests
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeSession:
    """Returns canned payloads by URL substring and records every call."""

    def __init__(self, routes):
        self.routes, self.calls, self.headers = routes, [], {}

    def get(self, url, timeout=None, params=None):
        self.calls.append((url, params))
        for key, payload in self.routes.items():
            if key in url:
                value = payload(url, params) if callable(payload) else payload
                return value if isinstance(value, FakeResponse) else FakeResponse(value)
        return FakeResponse({}, 404)


@pytest.fixture
def fake_session():
    return FakeSession
