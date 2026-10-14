"""Try the FlightAware key from the command line, without touching the database.

    python -m scripts.check_flight_api --shift morning
    python -m scripts.check_flight_api --shift morning --raw     # also print the first raw record

Each run uses a few result sets from your FlightAware quota.
"""
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.services.flight_data import FlightDataError, build_client, parse_window, rules_from_settings, window_bounds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shift", choices=["morning", "night"], default="morning")
    parser.add_argument("--date", help="YYYY-MM-DD in airport time (default: today)")
    parser.add_argument("--raw", action="store_true", help="print the first raw record from the provider")
    args = parser.parse_args()

    tz = ZoneInfo(settings.airport_tz)
    day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(tz).date()
    window = parse_window(settings.morning_window if args.shift == "morning" else settings.night_window)
    start, end = window_bounds(day, window, tz)
    rules = rules_from_settings(settings)

    try:
        client = build_client(settings)
        if args.raw:
            pages = client.fetch_raw(settings.airport_icao, "scheduled_arrivals", start, end)
            records = (pages[0].get("scheduled_arrivals") or []) if pages else []
            print(json.dumps(records[0] if records else {"note": "no records in this window"}, indent=2))
            print(f"-- {client.last_pages} result set(s) used\n")
        client.last_pages = 0
        flights = client.arrivals(settings.airport_icao, start, end, tz)
    except FlightDataError as error:
        print(f"Failed: {error}")
        return 1

    kept = [f for f in flights if rules.keeps(f)]
    print(f"{settings.airport_icao} {args.shift} {day}  {window[0]:%H:%M}-{window[1]:%H:%M} ({settings.airport_tz})")
    print(f"{len(flights)} arrivals from FlightAware, {len(kept)} kept. {rules.describe()}.")
    print(f"{client.last_pages} result set(s) used in this run.\n")
    for f in sorted(kept, key=lambda x: x.sched):
        tag = "INTL" if f.international else "dom "
        late = int((f.eta - f.sched).total_seconds() // 60)
        print(f"  {f.eta:%H:%M} (sched {f.sched:%H:%M}, {late:+d}m)  {f.flight_no:<9} {f.airline:<18} from {f.origin or '?':<5} {tag}  {f.rego}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
