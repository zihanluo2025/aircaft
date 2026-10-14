from datetime import datetime

import pytest

from app.main import app
from app.routers.flight_data import get_flight_client
from app.services.flight_data import AeroApiClient, FlightDataError

DAY = "2026-10-14"


def rec(fid, number, origin="YMML", iata="JQ", icao="JST", sched="2026-10-13T19:30:00Z", **over):
    base = {
        "fa_flight_id": fid,
        "operator_iata": iata,
        "operator_icao": icao,
        "flight_number": number,
        "registration": "VHXXX",
        "cancelled": False,
        "origin": {"code_icao": origin, "city": "X"},
        "gate_destination": "3",
        "scheduled_in": sched,
        "estimated_in": sched,
    }
    base.update(over)
    return base


class FakeHttp:
    def __init__(self, scheduled, arrived=()):
        self.scheduled, self.arrived, self.calls = list(scheduled), list(arrived), 0

    def __call__(self, url, headers):
        self.calls += 1
        if "/scheduled_arrivals" in url:
            return {"scheduled_arrivals": self.scheduled}
        return {"arrivals": self.arrived}


@pytest.fixture()
def fake(client):
    holder = {}

    def use(scheduled, arrived=()):
        http = FakeHttp(scheduled, arrived)
        holder["http"] = http
        holder["client"] = AeroApiClient("KEY", max_pages=1, http_get=http)
        app.dependency_overrides[get_flight_client] = lambda: holder["client"]
        return http

    return use


def flights(client):
    return client.get("/api/flights", params={"date": DAY, "shift": "morning"}).json()


def sync(client):
    return client.post("/api/flight-data/sync", json={"date": DAY, "shift": "morning"})


def test_sync_keeps_only_international_and_listed_airlines(client, fake):
    fake(
        [
            rec("1", "100"),  # Jetstar, domestic: kept
            rec("2", "200", iata="VA", icao="VOZ"),  # Virgin, domestic: kept
            rec("3", "300", iata="QF", icao="QFA"),  # Qantas domestic: dropped
            rec("4", "400", iata="SQ", icao="SIA", origin="WSSS"),  # international: kept
            rec("5", "500", iata="JQ", icao="JST", origin="NZAA"),  # Jetstar international: kept
        ]
    )
    response = sync(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["fetched"], body["kept"], body["created"]) == (5, 4, 4)
    rows = {f["flight_no"]: f for f in flights(client)}
    assert set(rows) == {"JQ 100", "VA 200", "SQ 400", "JQ 500"}
    assert rows["SQ 400"]["international"] and rows["SQ 400"]["origin"] == "WSSS"
    assert not rows["JQ 100"]["international"]
    assert rows["JQ 100"]["sched"] == "06:00" and rows["JQ 100"]["gate"] == "3"


def test_sync_ignores_flights_outside_the_shift_window(client, fake):
    # 14:30 local on the same day belongs to the night shift, 02:00 is before the morning window
    fake([rec("1", "100", sched="2026-10-14T04:00:00Z"), rec("2", "200", sched="2026-10-13T15:30:00Z")])
    assert sync(client).json()["kept"] == 0
    assert flights(client) == []


def test_sync_updates_times_but_never_a_flight_already_cleaning(client, fake):
    http = fake([rec("1", "100"), rec("2", "200", sched="2026-10-13T20:30:00Z")])
    sync(client)
    ids = {f["flight_no"]: f["id"] for f in flights(client)}
    assert client.post("/api/roster/import", json={"shift": "morning", "text": "Name,2026-10-14\nAlex K,Early\n"}).status_code == 200
    staff_id = client.get("/api/staff", params={"team": "morning"}).json()[0]["id"]
    client.put(f"/api/flights/{ids['JQ 100']}/assignments", json=[{"role": "Vacuum", "staff_id": staff_id}])
    assert client.post(f"/api/flights/{ids['JQ 100']}/start").status_code == 200
    client.patch(f"/api/flights/{ids['JQ 200']}", json={"notes": "check seat 4C"})

    http.scheduled = [
        rec("1", "100", estimated_in="2026-10-13T21:00:00Z", scheduled_in="2026-10-13T19:30:00Z"),
        rec("2", "200", sched="2026-10-13T20:30:00Z", estimated_in="2026-10-13T21:20:00Z"),
    ]
    # skip the throttle by clearing the log
    _clear_throttle(client)
    body = sync(client).json()
    assert body["skipped_started"] == 1 and body["updated"] == 1
    rows = {f["flight_no"]: f for f in flights(client)}
    assert rows["JQ 100"]["eta"] == "06:00"  # untouched, cleaning had started
    assert rows["JQ 200"]["eta"] == "07:50"  # updated
    assert rows["JQ 200"]["notes"] == "check seat 4C"  # notes survive


def _clear_throttle(client):
    from app.database import get_db
    from app.models import FlightSyncLog

    db = next(app.dependency_overrides[get_db]())
    try:
        for row in db.query(FlightSyncLog).all():
            row.created_at = datetime(2020, 1, 1)
        db.commit()
    finally:
        db.close()


def test_second_sync_inside_the_interval_is_refused(client, fake, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sync_min_interval", 300)
    fake([rec("1", "100")])
    assert sync(client).status_code == 200
    again = sync(client)
    assert again.status_code == 429 and "Try again" in again.json()["detail"]


def test_monthly_limit_blocks_the_call_before_any_request(client, fake, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "monthly_call_limit", 1)
    http = fake([rec("1", "100")])
    response = sync(client)
    assert response.status_code == 429 and "Monthly limit" in response.json()["detail"]
    assert http.calls == 0


def test_provider_failure_is_reported_and_logged(client):
    def boom(url, headers):
        raise FlightDataError("FlightAware rejected the API key. Check FLIGHT_API_KEY.")

    app.dependency_overrides[get_flight_client] = lambda: AeroApiClient("bad", max_pages=1, http_get=boom)
    response = sync(client)
    assert response.status_code == 502 and "API key" in response.json()["detail"]
    status = client.get("/api/flight-data/status").json()
    assert status["last_ok"] is False and "API key" in status["last_message"]


def test_missing_key_gives_503_and_status_says_not_configured(client):
    assert sync(client).status_code == 503
    status = client.get("/api/flight-data/status").json()
    assert status["configured"] is False
    assert "international" in status["filter_text"].lower()
    assert status["monthly_limit"] > 0


def test_flight_data_requires_login(client):
    from fastapi.testclient import TestClient

    anonymous = TestClient(app)
    assert anonymous.get("/api/flight-data/status").status_code == 401
