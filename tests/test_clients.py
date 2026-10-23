import pandas as pd
import pytest
import requests

from tehran_data import FipiranClient, flatten_funds, HttpClient, MabnaClient, TsetmcClient, fund_network, manager_concentration, tse_trading_days
from tehran_data.tsetmc import average_volume

from .conftest import FakeResponse


def http(session):
    return HttpClient(session=session, pause=0, backoff=0)


def test_trading_days_skip_thursday_and_friday():
    days = tse_trading_days("20250828", "20250903")      # Thu 28 Aug to Wed 3 Sep 2025
    assert days == ["20250830", "20250831", "20250901", "20250902", "20250903"]


def test_shareholders_keep_only_requested_date(fake_session):
    payload = {"shareShareholder": [
        {"shareHolderName": "A", "dEven": 20250831, "perOfShares": 5.0},
        {"shareHolderName": "B", "dEven": 20250830, "perOfShares": 4.0}]}
    client = TsetmcClient(http(fake_session({"Shareholder/": payload})))
    df = client.shareholders(123, "20250831")
    assert df["shareHolderName"].tolist() == ["A"]


def test_shareholder_panel_merges_metadata_and_skips_failures(fake_session):
    def route(url, params):
        inscode, day = url.split("/")[-2:]
        if inscode == "2":
            return FakeResponse({}, 404)             # this instrument always fails
        return {"shareShareholder": [{"shareHolderName": "X", "dEven": int(day), "perOfShares": 1.0}]}

    client = TsetmcClient(http(fake_session({"Shareholder/": route})))
    ins = pd.DataFrame({"inscode": ["1", "2"], "symbol": ["FUNDA1", "FUNDB1"], "sub_industry": ["equity", "bond"]})
    panel = client.shareholder_panel(ins, "20250830", "20250901")
    assert len(panel) == 3 and set(panel["symbol"]) == {"FUNDA"}
    assert "dEven" not in panel.columns and panel["date"].is_monotonic_increasing


def test_closing_prices_and_average_volume(fake_session):
    rows = [{"dEven": 20250800 + d, "pClosing": 100 + d, "qTotTran5J": 0 if d == 5 else 1000 * d} for d in range(1, 11)]
    client = TsetmcClient(http(fake_session({"ClosingPrice": {"closingPriceDaily": rows}})))
    prices = client.closing_prices(1)
    assert prices.index.is_monotonic_increasing and prices.index[0] == pd.Timestamp("2025-08-01")
    assert average_volume(prices, "2025-08-10", 3) == pytest.approx(9000)
    assert average_volume(prices, "2025-08-06", 3) == pytest.approx((3000 + 4000 + 6000) / 3)   # zero day skipped


def test_base_volume(fake_session):
    client = TsetmcClient(http(fake_session({"GetInstrumentHistory": {"instrumentHistory": {"baseVol": 500000}}})))
    assert client.base_volume(1, "20250621") == 500000


def test_retry_then_success(fake_session):
    attempts = []

    def flaky(url, params):
        attempts.append(1)
        return FakeResponse({}, 503) if len(attempts) < 3 else {"ok": True}

    assert http(fake_session({"x": flaky})).get_json("https://x") == {"ok": True}
    assert len(attempts) == 3


def test_client_error_is_not_retried(fake_session):
    s = fake_session({"x": FakeResponse({}, 404)})
    with pytest.raises(requests.HTTPError):
        http(s).get_json("https://x")
    assert len(s.calls) == 1


FUNDS = pd.DataFrame({
    "name": ["Fund 1", "Fund 2", "Fund 3", "Fund 4"],
    "manager": ["Manager A", "Manager A", "Manager B", "Manager C"],
    "guarantor": ["Bank X", "Bank X", "Bank Y", None],
    "custodian": ["Cust 1", "Cust 1", "Cust 1", "Cust 2"],
    "netAsset": [400.0, 100.0, 300.0, 200.0],
})


def test_fund_network_structure():
    g = fund_network(FUNDS, roles=("manager", "guarantor"))
    assert g.nodes["Fund 1"]["kind"] == "fund" and g.nodes["Manager A"]["kind"] == "firm"
    assert g.degree("Manager A") == 2
    assert not g.has_node(None) and g.degree("Fund 4") == 1


def test_manager_concentration_hhi():
    table, hhi = manager_concentration(FUNDS)
    assert table.loc["Manager A", "funds"] == 2
    assert table["share"].sum() == pytest.approx(1.0)
    assert hhi == pytest.approx(50**2 + 30**2 + 20**2)


def test_fipiran_funds(fake_session):
    client = FipiranClient(http(fake_session({"dependencygraph": {"items": FUNDS.to_dict("records")}})))
    assert len(client.funds()) == 4


def test_mabna_requires_token(monkeypatch):
    monkeypatch.delenv("MABNA_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        MabnaClient()


def test_mabna_paginates_and_sets_auth(fake_session, monkeypatch):
    monkeypatch.setenv("MABNA_TOKEN", "test-token")

    def pages(url, params):
        skip = params["_skip"]
        return {"data": [{"id": i} for i in range(skip, min(skip + 2, 5))]}

    s = fake_session({"instruments": pages})
    client = MabnaClient(http=http(s))
    df = client.instruments(page_size=2)
    assert df["id"].tolist() == [0, 1, 2, 3, 4]
    assert s.headers["Authorization"].startswith("Basic ")


def test_flatten_nested_and_temp_names():
    items = [{"name": "F1", "manager": {"name": "Manager A", "managerId": 1}, "tempGuarantorName": "Bank X"},
             {"name": "F2", "manager": None, "tempManagerName": "Manager B", "guarantor": None}]
    df = flatten_funds(items)
    assert df["manager"].tolist() == ["Manager A", "Manager B"]
    assert df.loc[0, "guarantor"] == "Bank X" and pd.isna(df.loc[1, "guarantor"])
