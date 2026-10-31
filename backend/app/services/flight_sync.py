"""Write provider flights into the flights table without touching anything the leading hand has recorded."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Assignment, Flight
from .domain import DEFAULT_ROLES
from .flight_data import FlightFilter, ProviderFlight, apply_filter, in_window


@dataclass
class SyncResult:
    fetched: int = 0
    kept: int = 0
    created: int = 0
    updated: int = 0
    skipped_started: int = 0
    removed: int = 0


def sync_shift(
    db: Session,
    *,
    flights: list[ProviderFlight],
    rules: FlightFilter,
    work_date: date,
    shift: str,
    window: tuple[time, time],
) -> SyncResult:
    """Create or update the day's flights.

    Flights that fall outside the shift window or the filter are ignored. A flight whose cleaning has already
    started is never changed, and crew, notes, times and signatures are never overwritten.
    """
    result = SyncResult(fetched=len(flights))
    wanted = [f for f in apply_filter(flights, rules) if in_window(f.sched, work_date, window)]
    result.kept = len(wanted)

    existing = {
        f.flight_no: f
        for f in db.scalars(select(Flight).where(Flight.work_date == work_date, Flight.shift == shift))
    }

    for pf in sorted(wanted, key=lambda f: f.sched):
        row = existing.get(pf.flight_no)
        if row is None:
            row = Flight(
                work_date=work_date,
                shift=shift,
                flight_no=pf.flight_no,
                sched=pf.sched.strftime("%H:%M"),
                eta=pf.eta.strftime("%H:%M"),
            )
            row.assignments = [Assignment(role=role, position=i) for i, role in enumerate(DEFAULT_ROLES)]
            _copy_details(row, pf)
            db.add(row)
            existing[pf.flight_no] = row
            result.created += 1
            continue
        if row.started_at is not None:
            result.skipped_started += 1
            continue
        before = (row.sched, row.eta, row.gate, row.rego, row.landed, row.cancelled, row.origin, row.airline)
        row.sched = pf.sched.strftime("%H:%M")
        row.eta = pf.eta.strftime("%H:%M")
        _copy_details(row, pf)
        if before != (row.sched, row.eta, row.gate, row.rego, row.landed, row.cancelled, row.origin, row.airline):
            result.updated += 1

    # Flights already here that the current rules no longer keep (synced before an airline was dropped)
    # go, but only if nobody has touched them -- recorded work is never deleted by a sync.
    for row in list(existing.values()):
        if not rules.keeps_airline(_airline_of(row.flight_no), bool(row.international)) and _untouched(row):
            db.delete(row)
            result.removed += 1

    db.commit()
    return result


def _airline_of(flight_no: str) -> str:
    return (flight_no or "").split(" ")[0][:2].upper()


def _untouched(row: Flight) -> bool:
    return (
        row.started_at is None
        and not row.notes
        and not row.sig_image
        and not row.photos
        and not any(a.staff_id for a in row.assignments)
    )


def _copy_details(row: Flight, pf: ProviderFlight) -> None:
    row.airline = pf.airline or row.airline or ""
    row.rego = pf.rego or row.rego or ""
    row.gate = pf.gate or row.gate or ""
    row.origin = pf.origin or row.origin or ""
    row.international = pf.international
    row.landed = pf.landed or bool(row.landed)  # a hand-marked landing is not undone by a late feed
    row.cancelled = pf.cancelled or bool(row.cancelled)
