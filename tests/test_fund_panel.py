import pandas as pd
import pytest

from tehran_data import FipiranClient, FundPanelBuilder, HttpClient, TsetmcClient, clean_firm_name, update_panel
from tehran_data.fund_panel import flatten_details, tidy_snapshot

from .conftest import FakeResponse


@pytest.mark.parametrize("raw,expected", [
    ("مدیر (مشاور سرمایه گذاری آرمان آتی)", "مشاور سرمایه‌گذاری آرمان آتی"),
    ("سبد گردان نو ویرا (سهامی خاص)", "سبدگردان نوویرا"),
    ("كارگزاري بانك ملي ايران ، مدیر", "کارگزاری بانک ملی ایران"),
    ("بانک تجارت سهامی عام", "بانک تجارت"),
    ("مشاورسرمایه گذاری نیکی", "مشاور سرمایه‌گذاری نیکی"),
    ("نامشخص", None), ("", None), (None, None),
])
def test_clean_firm_name(raw, expected):
    assert clean_firm_name(raw) == expected


def test_spelling_variants_collapse_to_one_firm():
    variants = ["سرمایه گذاری الف", "سرمایه‌گذاری الف (سهامی خاص)", "مدیر (سرمايه گذاري الف)"]
    assert len({clean_firm_name(v) for v in variants}) == 1


SNAP = [{"regNo": "11", "name": "Fund A", "fundType": 4, "dailyEfficiency": 1.5, "efficiency": 120.0,
         "stock": 60.0, "bond": 30.0, "cash": 10.0, "fundSize": 1.2e13, "insCode": 65883838195688438,
         "manager": {"name": "مدیر (سبد گردان الف)"}, "websiteAddress": "['www.a.ir']",
         "prosoectusLink": "x"},
        {"regNo": "12", "name": "Fund B", "fundType": 6, "dailyEfficiency": None, "efficiency": 3.0,
         "fundSize": None, "insCode": None, "tempManagerName": "مشاور ب", "websiteAddress": None}]


def test_tidy_snapshot_scales_and_renames():
    df = tidy_snapshot(SNAP, pd.Timestamp("2025-03-02").date())
    a, b = df.iloc[0], df.iloc[1]
    assert a["daily_return"] == pytest.approx(0.015) and a["cumulative_return"] == pytest.approx(1.2)
    assert a["stock"] + a["bond"] + a["cash"] == pytest.approx(1.0)
    assert a["manager"] == "سبدگردان الف" and b["manager"] == "مشاور ب"
    assert a["insCode"] == "65883838195688438"          # not rounded, not scientific notation
    assert pd.isna(b["fundSize"]) and pd.isna(b["insCode"])   # missing stays missing, never the text "nan"
    assert a["websiteAddress"] == "www.a.ir" and "prospectusLink" in df


def test_flatten_details_takes_first_licence():
    d = flatten_details({"regNo": "11", "name": "x", "legalPercent": 40,
                         "mutualFundLicenses": [{"regNo": "11", "licenseNo": "L1", "isExpired": False}]})
    assert d == {"regNo": "11", "legalPercent": 40, "license_licenseNo": "L1", "license_isExpired": False}


def routes(fail_day=None, detail_calls=None):
    def compare(url, params):
        day = params["date"]
        if day == fail_day:
            return FakeResponse({}, 404)
        items = SNAP if day == "2025-03-02" else SNAP[:1]
        return {"items": [{**i, "regNo": i["regNo"]} for i in items]}

    def getfund(url, params):
        if detail_calls is not None:
            detail_calls.append((params["regno"], params["date"]))
        return {"item": {"regNo": params["regno"], "legalPercent": 25.0, "mutualFundLicenses": []}}

    return {
        "fundcompare": compare,
        "getfund": getfund,
        "fundtype": {"items": [{"fundType": 4, "name": "در سهام"}, {"fundType": 6, "name": "در اوراق با درآمد ثابت"}]},
        "GetIndexB2History": {"indexB2": [{"dEven": 20250301, "xNivInuClMresIbs": 100.0},
                                          {"dEven": 20250302, "xNivInuClMresIbs": 102.0},
                                          {"dEven": 20250303, "xNivInuClMresIbs": 101.0}]},
    }


def builder(fake_session, **kw):
    http = HttpClient(session=fake_session(routes(**kw)), pause=0, backoff=0, retries=1)
    return FundPanelBuilder(FipiranClient(http), TsetmcClient(http))


def test_build_panel_with_types_index_and_details(fake_session):
    calls = []
    panel = builder(fake_session, detail_calls=calls).build("2025-03-02", "2025-03-03", details=True)
    assert len(panel) == 3                                     # 2 funds on day 1, 1 fund on day 2
    assert set(calls) == {("11", "2025-03-02"), ("12", "2025-03-02"), ("11", "2025-03-03")}  # no non-existent pairs
    assert panel["fund_type_name"].iloc[0] == "سهام"            # "در" prefix removed
    day1 = panel[panel["date"] == "2025-03-02"]
    assert day1["index_return"].iloc[0] == pytest.approx(0.02)
    assert panel["legalPercent"].notna().all()


def test_failed_day_is_skipped(fake_session):
    panel = builder(fake_session, fail_day="2025-03-02").build("2025-03-02", "2025-03-03", index=False)
    assert panel["date"].dt.strftime("%Y-%m-%d").unique().tolist() == ["2025-03-03"]


def test_update_appends_only_new_days(fake_session, tmp_path):
    b = builder(fake_session)
    path = tmp_path / "panel.csv"
    b.build("2025-03-02", "2025-03-02").to_csv(path, index=False)
    panel = update_panel(path, b, end="2025-03-03")
    assert len(panel) == 3 and panel.duplicated(["date", "regNo"]).sum() == 0
    again = update_panel(path, b, end="2025-03-03")             # nothing new: unchanged
    assert len(again) == 3
    assert pd.read_csv(path, dtype={"insCode": str})["insCode"].dropna().iloc[0] == "65883838195688438"
