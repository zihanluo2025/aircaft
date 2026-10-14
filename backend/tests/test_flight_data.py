from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.services.flight_data import (
    AeroApiClient,
    FlightDataError,
    FlightFilter,
    ProviderFlight,
    apply_filter,
    in_window,
    is_international,
    parse_aeroapi_flights,
    parse_window,
    window_bounds,
)

TZ = ZoneInfo("Australia/Adelaide")  # UTC+10:30 in October (daylight saving)


def record(**over):
    base = {
        "fa_flight_id": "JST123-1",
        "ident": "JST123",
        "ident_iata": "JQ123",
        "operator": "JST",
        "operator_icao": "JST",
        "operator_iata": "JQ",
        "flight_number": "123",
        "registration": "vhvgx",
        "cancelled": False,
        "origin": {"code_icao": "YMML", "city": "Melbourne"},
        "gate_destination": "5",
        "scheduled_in": "2026-10-13T19:30:00Z",  # 06:00 Adelaide next day
        "estimated_in": "2026-10-13T19:45:00Z",
        "actual_on": None,
        "actual_in": None,
    }
    base.update(over)
    return base


def flight(**over):
    base = dict(
        external_id="x",
        flight_no="JQ 123",
        airline_code="JQ",
        airline="Jetstar",
        rego="",
        gate="",
        origin="YMML",
        origin_name="",
        international=False,
        sched=datetime(2026, 10, 14, 6, 0),
        eta=datetime(2026, 10, 14, 6, 0),
        landed=False,
        cancelled=False,
    )
    base.update(over)
    return ProviderFlight(**base)


def test_international_means_origin_not_australian():
    assert is_international("WSSS")
    assert is_international("NZAA")
    assert not is_international("YMML")
    assert not is_international("")


def test_parse_converts_to_airport_local_time():
    [f] = parse_aeroapi_flights({"scheduled_arrivals": [record()]}, TZ)
    assert f.flight_no == "JQ 123"
    assert f.airline == "Jetstar"
    assert f.sched == datetime(2026, 10, 14, 6, 0)
    assert f.eta == datetime(2026, 10, 14, 6, 15)
    assert f.rego == "VHVGX"
    assert f.gate == "5"
    assert f.origin == "YMML"
    assert not f.international and not f.landed


def test_parse_arrived_endpoint_uses_actual_gate_time_and_marks_landed():
    payload = {"arrivals": [record(actual_in="2026-10-13T19:40:00Z", actual_on="2026-10-13T19:35:00Z")]}
    [f] = parse_aeroapi_flights(payload, TZ)
    assert f.landed
    assert f.eta == datetime(2026, 10, 14, 6, 10)


def test_parse_falls_back_to_runway_time_and_skips_records_without_times():
    only_runway = record(scheduled_in=None, estimated_in=None, scheduled_on="2026-10-13T19:20:00Z")
    nothing = record(fa_flight_id="n", scheduled_in=None, estimated_in=None)
    result = parse_aeroapi_flights({"scheduled_arrivals": [only_runway, nothing]}, TZ)
    assert len(result) == 1
    assert result[0].sched == datetime(2026, 10, 14, 5, 50)


def test_parse_uses_icao_operator_when_iata_missing():
    rec = record(operator_iata=None, operator_icao="VOZ", ident_iata="VA55", flight_number="55")
    [f] = parse_aeroapi_flights({"scheduled_arrivals": [rec]}, TZ)
    assert f.airline_code == "VA"
    assert f.airline == "Virgin Australia"
    assert f.flight_no == "VA55"


def test_filter_any_keeps_international_or_listed_airline():
    rules = FlightFilter(airlines=["JQ", "VA"], international=True, mode="any")
    jq_domestic = flight()
    va_domestic = flight(airline_code="VA")
    qf_domestic = flight(airline_code="QF")
    qf_intl = flight(airline_code="QF", international=True)
    kept = apply_filter([jq_domestic, va_domestic, qf_domestic, qf_intl], rules)
    assert kept == [jq_domestic, va_domestic, qf_intl]


def test_filter_all_needs_both():
    rules = FlightFilter(airlines=["JQ"], international=True, mode="all")
    assert not rules.keeps(flight())
    assert rules.keeps(flight(international=True))
    assert not rules.keeps(flight(airline_code="QF", international=True))


def test_filter_without_rules_keeps_everything_and_describes_itself():
    assert FlightFilter(airlines=[], international=False).keeps(flight(airline_code="ZZ"))
    text = FlightFilter(airlines=["JQ", "VA"], international=True).describe()
    assert "international" in text and "Jetstar" in text and "Virgin Australia" in text


def test_window_bounds_cross_midnight_and_utc():
    start, end = window_bounds(datetime(2026, 10, 14).date(), parse_window("14:00-23:59"), TZ)
    assert start.utcoffset().total_seconds() == 10.5 * 3600
    assert (start.hour, end.hour, end.minute) == (14, 23, 59)
    assert parse_window("04:00-14:00") == (time(4, 0), time(14, 0))


class Recorder:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def __call__(self, url, headers):
        self.urls.append((url, headers))
        return self.pages[len(self.urls) - 1]


def test_client_follows_next_links_up_to_max_pages_and_sends_key():
    pages = [
        {"scheduled_arrivals": [record(fa_flight_id="a")], "links": {"next": "/airports/YPAD/flights/scheduled_arrivals?cursor=1"}},
        {"scheduled_arrivals": [record(fa_flight_id="b")], "links": {"next": "/airports/YPAD/flights/scheduled_arrivals?cursor=2"}},
        {"scheduled_arrivals": [record(fa_flight_id="c")]},
    ]
    http = Recorder(pages)
    client = AeroApiClient("KEY", max_pages=2, include_arrived=False, http_get=http)
    flights = client.arrivals("YPAD", datetime(2026, 10, 14, 4, tzinfo=TZ), datetime(2026, 10, 14, 14, tzinfo=TZ), TZ)
    assert [f.external_id for f in flights] == ["a", "b"]
    assert client.last_pages == 2
    assert http.urls[0][1]["x-apikey"] == "KEY"
    assert "type=Airline" in http.urls[0][0] and "start=2026-10-13T17%3A30%3A00Z" in http.urls[0][0]
    assert http.urls[1][0] == "https://aeroapi.flightaware.com/aeroapi/airports/YPAD/flights/scheduled_arrivals?cursor=1"


def test_client_merges_both_endpoints_and_dedupes():
    pages = [
        {"scheduled_arrivals": [record(fa_flight_id="a")]},
        {"arrivals": [record(fa_flight_id="a", actual_on="2026-10-13T19:35:00Z"), record(fa_flight_id="b")]},
    ]
    client = AeroApiClient("KEY", include_arrived=True, http_get=Recorder(pages))
    flights = client.arrivals("YPAD", datetime(2026, 10, 14, 4, tzinfo=TZ), datetime(2026, 10, 14, 14, tzinfo=TZ), TZ)
    assert sorted(f.external_id for f in flights) == ["a", "b"]
    assert next(f for f in flights if f.external_id == "a").landed  # the arrived copy wins
    assert client.last_pages == 2


def test_provider_errors_propagate():
    def boom(url, headers):
        raise FlightDataError("nope")

    client = AeroApiClient("KEY", http_get=boom)
    with pytest.raises(FlightDataError):
        client.arrivals("YPAD", datetime(2026, 10, 14, 4, tzinfo=TZ), datetime(2026, 10, 14, 14, tzinfo=TZ), TZ)


def test_default_shift_windows_are_morning_6_to_13_and_night_the_rest():
    from app.config import settings

    morning = parse_window(settings.morning_window)
    night = parse_window(settings.night_window)
    day = datetime(2026, 10, 14).date()
    assert morning == (time(6, 0), time(13, 0))
    assert in_window(datetime(2026, 10, 14, 6, 0), day, morning)
    assert in_window(datetime(2026, 10, 14, 12, 59), day, morning)
    assert not in_window(datetime(2026, 10, 14, 5, 59), day, morning)
    # night runs from 13:00 to 06:00 the next morning
    assert in_window(datetime(2026, 10, 14, 13, 30), day, night)
    assert in_window(datetime(2026, 10, 15, 2, 30), day, night)
    assert not in_window(datetime(2026, 10, 15, 6, 30), day, night)
    assert not in_window(datetime(2026, 10, 14, 10, 0), day, night)
