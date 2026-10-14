"""Helpers shared by the routers: flight status, fixed role holders, serialisation."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Flight, RosterEntry, Staff

ROLE_ORDER = {"Driver": 0, "Toilet": 1, "Truck": 2}
STATUS_LABEL = {"sched": "Scheduled", "landed": "Landed", "cleaning": "Cleaning", "done": "Done", "cancelled": "Cancelled"}
SHIFT_ORDER = {"early": 0, "late": 1, "all": 2}
SHIFT_TYPE_LABEL = {"early": "Early", "late": "Late", "all": "All day"}
DEFAULT_ROLES = ["Business", "Vacuum", "Economy - Front", "Economy - Mid", "Economy - Rear"]


def to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def flight_status(f: Flight) -> str:
    if f.cancelled:
        return "cancelled"
    if f.finished_at:
        return "done"
    if f.started_at:
        return "cleaning"
    if f.landed:
        return "landed"
    return "sched"


def flight_minutes(f: Flight) -> Optional[int]:
    if f.started_at and f.finished_at:
        return max(0, round((f.finished_at - f.started_at).total_seconds() / 60))
    return None


def fixed_holders(db: Session, work_date: date, shift: str) -> list[dict]:
    """People on duty who hold a fixed role (Driver, Toilet, Truck) for the day."""
    rows = db.execute(
        select(RosterEntry, Staff)
        .join(Staff, Staff.id == RosterEntry.staff_id)
        .where(
            RosterEntry.work_date == work_date,
            RosterEntry.shift == shift,
            RosterEntry.shift_type.is_not(None),
            RosterEntry.role.is_not(None),
        )
    ).all()
    holders = [{"role": e.role, "staff_id": s.id, "staff_name": s.name} for e, s in rows]
    holders.sort(key=lambda h: (ROLE_ORDER.get(h["role"], 9), h["staff_name"].lower()))
    return holders


def fixed_for(db: Session, f: Flight, live: Optional[list[dict]] = None) -> list[dict]:
    """Snapshot taken when cleaning started, else the current holders (pass `live` to avoid a query per flight)."""
    if f.fixed is not None:
        return f.fixed
    return live if live is not None else fixed_holders(db, f.work_date, f.shift)


def crew_of(db: Session, f: Flight, live: Optional[list[dict]] = None) -> list[dict]:
    """Everyone recorded on the flight: the fixed role holders plus the per aircraft assignments."""
    crew = list(fixed_for(db, f, live))
    for a in f.assignments:
        if a.staff_id:
            crew.append({"role": a.role, "staff_id": a.staff_id, "staff_name": a.staff.name if a.staff else ""})
    return crew


def build_flight_out(db: Session, f: Flight, detail: bool = False, live: Optional[list[dict]] = None) -> dict:
    fixed = fixed_for(db, f, live)
    assignments = [
        {"role": a.role, "staff_id": a.staff_id, "staff_name": a.staff.name if a.staff else ""} for a in f.assignments
    ]
    data = {
        "id": f.id,
        "work_date": f.work_date,
        "shift": f.shift,
        "flight_no": f.flight_no,
        "airline": f.airline,
        "rego": f.rego,
        "gate": f.gate,
        "origin": f.origin,
        "international": f.international,
        "sched": f.sched,
        "eta": f.eta,
        "delay_minutes": to_minutes(f.eta) - to_minutes(f.sched),
        "landed": f.landed,
        "cancelled": f.cancelled,
        "status": flight_status(f),
        "started_at": f.started_at,
        "finished_at": f.finished_at,
        "minutes": flight_minutes(f),
        "notes": f.notes,
        "fixed": fixed,
        "assignments": assignments,
        "crew_count": len(fixed) + sum(1 for a in assignments if a["staff_id"]),
        "has_signature": bool(f.sig_image),
        "sig_name": f.sig_name,
        "signed_at": f.signed_at,
    }
    if detail:
        data["sig_image"] = f.sig_image
    return data
