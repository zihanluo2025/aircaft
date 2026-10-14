"""FlightAware AeroAPI client, response parsing and the flight filter.

Only the standard library is used for HTTP, so there is nothing extra to install.

AeroAPI v4 (https://www.flightaware.com/aeroapi/portal/documentation):
  GET /airports/{id}/flights/scheduled_arrivals   flights that have not arrived yet   -> {"scheduled_arrivals": [...]}
  GET /airports/{id}/flights/arrivals             flights that have already arrived   -> {"arrivals": [...]}
Both take start / end (ISO 8601, UTC) and type=Airline, and answer in pages of up to 15 flights with
{"links": {"next": "..."}}. Billing is per page, so the number of pages is capped by the caller.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

AIRLINE_NAMES = {
    "JQ": "Jetstar",
    "JST": "Jetstar",
    "VA": "Virgin Australia",
    "VOZ": "Virgin Australia",
    "QF": "Qantas",
    "QFA": "Qantas",
    "NZ": "Air New Zealand",
    "ANZ": "Air New Zealand",
    "SQ": "Singapore Airlines",
    "SIA": "Singapore Airlines",
    "EK": "Emirates",
    "UAE": "Emirates",
    "QR": "Qatar Airways",
    "QTR": "Qatar Airways",
    "CX": "Cathay Pacific",
    "CPA": "Cathay Pacific",
    "MH": "Malaysia Airlines",
    "MAS": "Malaysia Airlines",
    "TR": "Scoot",
    "TGW": "Scoot",
    "AK": "AirAsia",
    "AXM": "AirAsia",
    "D7": "AirAsia X",
    "XAX": "AirAsia X",
    "FJ": "Fiji Airways",
    "FJI": "Fiji Airways",
}
# ICAO -> IATA, so a filter written with either kind of code works
ICAO_TO_IATA = {"JST": "JQ", "VOZ": "VA", "QFA": "QF", "ANZ": "NZ", "SIA": "SQ", "UAE": "EK", "QTR": "QR"}


class FlightDataError(Exception):
    """The provider could not be reached, refused the request, or returned something unexpected."""


@dataclass
class ProviderFlight:
    external_id: str
    flight_no: str
    airline_code: str  # IATA when known
    airline: str
    rego: str
    gate: str
    origin: str  # ICAO code of the origin airport
    origin_name: str
    international: bool
    sched: datetime  # airport local time, naive
    eta: datetime  # airport local time, naive
    landed: bool
    cancelled: bool


# ---------------------------------------------------------------- filter
@dataclass
class FlightFilter:
    airlines: list[str]
    international: bool
    mode: str = "any"  # "any": airline OR international, "all": airline AND international

    def describe(self) -> str:
        names = [AIRLINE_NAMES.get(a, a) for a in self.airlines]
        parts = []
        if self.international:
            parts.append("international flights")
        if names:
            parts.append(" and ".join(names) if len(names) < 3 else ", ".join(names))
        if not parts:
            return "all arrivals"
        joiner = " and " if self.mode == "all" else " plus "
        return "Showing " + joiner.join(parts)

    def keeps(self, flight: ProviderFlight) -> bool:
        checks = []
        if self.airlines:
            checks.append(flight.airline_code.upper() in {a.upper() for a in self.airlines})
        if self.international:
            checks.append(flight.international)
        if not checks:
            return True
        return all(checks) if self.mode == "all" else any(checks)


def apply_filter(flights: list[ProviderFlight], rules: FlightFilter) -> list[ProviderFlight]:
    return [f for f in flights if rules.keeps(f)]


def rules_from_settings(settings) -> FlightFilter:
    mode = settings.flight_filter_mode if settings.flight_filter_mode in {"any", "all"} else "any"
    return FlightFilter(airlines=list(settings.flight_airlines), international=settings.flight_international, mode=mode)


def is_international(origin_icao: str) -> bool:
    """Australian airports have ICAO codes starting with Y. Anything else, flown into Australia, is international."""
    code = (origin_icao or "").strip().upper()
    return bool(code) and not code.startswith("Y")


# ---------------------------------------------------------------- parsing
def _parse_utc(value: Optional[str], tz: ZoneInfo) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(tz).replace(tzinfo=None)


def _first(record: dict, *keys: str) -> Optional[str]:
    for key in keys:
        if record.get(key):
            return record[key]
    return None


def parse_aeroapi_flights(payload: dict, tz: ZoneInfo) -> list[ProviderFlight]:
    """Turn one AeroAPI response (either endpoint) into ProviderFlight rows. Records without a time are dropped."""
    records = payload.get("scheduled_arrivals") or payload.get("arrivals") or []
    out: list[ProviderFlight] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        # Gate times (in) are what matters to the cleaners; runway times (on) are the fallback.
        sched = _parse_utc(_first(rec, "scheduled_in", "scheduled_on"), tz)
        eta = _parse_utc(_first(rec, "actual_in", "estimated_in", "actual_on", "estimated_on"), tz) or sched
        if sched is None and eta is None:
            continue
        sched = sched or eta
        origin = rec.get("origin") or {}
        origin_icao = (origin.get("code_icao") or origin.get("code") or "").upper()
        iata = (rec.get("operator_iata") or "").upper()
        icao = (rec.get("operator_icao") or "").upper()
        code = iata or ICAO_TO_IATA.get(icao, icao)
        number = str(rec.get("flight_number") or "").strip()
        flight_no = f"{iata} {number}" if iata and number else (rec.get("ident_iata") or rec.get("ident") or "").strip()
        if not flight_no:
            continue
        out.append(
            ProviderFlight(
                external_id=str(rec.get("fa_flight_id") or ""),
                flight_no=flight_no,
                airline_code=code,
                airline=AIRLINE_NAMES.get(iata) or AIRLINE_NAMES.get(icao) or rec.get("operator") or code,
                rego=(rec.get("registration") or "").upper(),
                gate=rec.get("gate_destination") or "",
                origin=origin_icao,
                origin_name=origin.get("city") or origin.get("name") or "",
                international=is_international(origin_icao),
                sched=sched,
                eta=eta,
                landed=bool(rec.get("actual_on") or rec.get("actual_in")),
                cancelled=bool(rec.get("cancelled")),
            )
        )
    return out


# ---------------------------------------------------------------- shift windows
def parse_window(text: str) -> tuple[time, time]:
    start, _, end = text.partition("-")
    return time.fromisoformat(start.strip()), time.fromisoformat(end.strip())


def window_bounds(work_date: date, window: tuple[time, time], tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The shift window as aware datetimes in the airport time zone."""
    start = datetime.combine(work_date, window[0], tzinfo=tz)
    end = datetime.combine(work_date, window[1], tzinfo=tz)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def in_window(moment: datetime, work_date: date, window: tuple[time, time]) -> bool:
    """moment is naive airport local time."""
    start = datetime.combine(work_date, window[0])
    end = datetime.combine(work_date, window[1])
    if end <= start:
        end += timedelta(days=1)
    return start <= moment <= end


# ---------------------------------------------------------------- client
HttpGet = Callable[[str, dict], dict]


def _urllib_get(url: str, headers: dict) -> dict:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = json.loads(error.read().decode("utf-8")).get("title", "")
        except Exception:  # noqa: BLE001 - body is only used for a nicer message
            pass
        if error.code in (401, 403):
            raise FlightDataError("FlightAware rejected the API key. Check FLIGHT_API_KEY.") from error
        if error.code == 429:
            raise FlightDataError("FlightAware says too many requests. Wait a minute and try again.") from error
        raise FlightDataError(f"FlightAware returned {error.code}. {detail}".strip()) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise FlightDataError("Cannot reach FlightAware. Check the internet connection.") from error
    except ValueError as error:
        raise FlightDataError("FlightAware sent an answer that is not JSON.") from error


class AeroApiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://aeroapi.flightaware.com/aeroapi",
        *,
        max_pages: int = 3,
        include_arrived: bool = True,
        http_get: HttpGet = _urllib_get,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_pages = max(1, max_pages)
        self.include_arrived = include_arrived
        self._get = http_get
        self.last_pages = 0  # result sets requested by the latest call, for the quota

    def build_url(self, airport: str, endpoint: str, start: datetime, end: datetime) -> str:
        query = urllib.parse.urlencode(
            {"type": "Airline", "start": _utc_iso(start), "end": _utc_iso(end), "max_pages": 1}
        )
        return f"{self.base_url}/airports/{airport}/flights/{endpoint}?{query}"

    def _next_url(self, link: str) -> str:
        if link.startswith("http"):
            return link
        if link.startswith("/aeroapi"):
            link = link[len("/aeroapi") :]
        return self.base_url + link

    def fetch_raw(self, airport: str, endpoint: str, start: datetime, end: datetime) -> list[dict]:
        """Raw response pages for one endpoint, following links.next up to max_pages."""
        headers = {"x-apikey": self.api_key, "Accept": "application/json; charset=UTF-8"}
        url: Optional[str] = self.build_url(airport, endpoint, start, end)
        pages: list[dict] = []
        while url and len(pages) < self.max_pages:
            payload = self._get(url, headers)
            self.last_pages += 1
            pages.append(payload)
            link = (payload.get("links") or {}).get("next")
            url = self._next_url(link) if link else None
        return pages

    def arrivals(self, airport: str, start: datetime, end: datetime, tz: ZoneInfo) -> list[ProviderFlight]:
        """start and end are aware datetimes. Returns every arrival in the window, before filtering."""
        self.last_pages = 0
        endpoints = ["scheduled_arrivals"] + (["arrivals"] if self.include_arrived else [])
        seen: dict[str, ProviderFlight] = {}
        for endpoint in endpoints:
            for page in self.fetch_raw(airport, endpoint, start, end):
                for flight in parse_aeroapi_flights(page, tz):
                    seen[flight.external_id or f"{flight.flight_no}@{flight.sched.isoformat()}"] = flight
        return list(seen.values())


def _utc_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_client(settings) -> AeroApiClient:
    if not settings.flight_api_key:
        raise FlightDataError("No flight data key. Set FLIGHT_API_KEY in backend/.env.")
    return AeroApiClient(
        settings.flight_api_key,
        settings.flight_api_base_url,
        max_pages=settings.flight_max_pages,
        include_arrived=settings.flight_include_arrived,
    )
