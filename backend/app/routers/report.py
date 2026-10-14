from datetime import date as Date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Assignment, Flight, RosterEntry, Staff
from ..schemas import ReportFlight, ReportOut, ReportPerson, Shift
from ..services.domain import (
    SHIFT_TYPE_LABEL,
    STATUS_LABEL,
    crew_of,
    fixed_holders,
    flight_minutes,
    flight_status,
)
from ..services.summary import build_summary_text

router = APIRouter(prefix="/api/report", tags=["report"], dependencies=[Depends(get_current_user)])

SHIFT_NAME = {"morning": "Morning", "night": "Night"}


@router.get("", response_model=ReportOut)
def get_report(
    work_date: Date = Query(..., alias="date"),
    shift: Shift = Query(...),
    db: Session = Depends(get_db),
):
    flights = db.scalars(
        select(Flight)
        .options(selectinload(Flight.assignments).selectinload(Assignment.staff))
        .where(Flight.work_date == work_date, Flight.shift == shift)
        .order_by(Flight.eta, Flight.id)
    ).all()
    live = fixed_holders(db, work_date, shift)
    entries = db.execute(
        select(RosterEntry, Staff)
        .join(Staff, Staff.id == RosterEntry.staff_id)
        .where(RosterEntry.work_date == work_date, RosterEntry.shift == shift)
    ).all()

    done = [f for f in flights if flight_status(f) == "done"]
    minutes = [flight_minutes(f) or 0 for f in done]
    average = round(sum(minutes) / len(minutes)) if minutes else 0
    signed = sum(1 for f in flights if f.sig_image)
    active_total = sum(1 for f in flights if not f.cancelled)

    people: dict[int, dict] = {}
    report_flights: list[ReportFlight] = []
    summary_flights: list[dict] = []
    for f in flights:
        crew = crew_of(db, f, live)
        status = flight_status(f)
        report_flights.append(
            ReportFlight(
                id=f.id,
                flight_no=f.flight_no,
                eta=f.eta,
                status=status,
                minutes=flight_minutes(f),
                crew_count=len(crew),
                signed=bool(f.sig_image),
            )
        )
        summary_flights.append(
            {
                "flight_no": f.flight_no,
                "eta": f.eta,
                "status_label": STATUS_LABEL[status],
                "minutes": flight_minutes(f),
                "crew": [f"{c['staff_name']} ({c['role']})" for c in crew],
                "signed_by": f.sig_name if f.sig_image else "",
                "notes": f.notes,
            }
        )
        if status == "done":
            for staff_id in {c["staff_id"] for c in crew if c["staff_id"]}:
                name = next(c["staff_name"] for c in crew if c["staff_id"] == staff_id)
                person = people.setdefault(staff_id, {"staff_id": staff_id, "name": name, "aircraft": 0, "minutes": 0})
                person["aircraft"] += 1
                person["minutes"] += flight_minutes(f) or 0

    has_plan = any(e.planned_type for e, _ in entries)
    called_in = sorted(s.name for e, s in entries if e.shift_type and e.called_in_at)
    changes: list[str] = []
    if has_plan:
        for e, s in sorted(entries, key=lambda r: r[1].name.lower()):
            planned, current = e.planned_type, e.shift_type
            if planned == current:
                continue
            if current and e.called_in_at and not planned:
                continue  # already listed under Called in
            changes.append(
                f"{s.name} ({SHIFT_TYPE_LABEL.get(planned, 'not planned')} to {SHIFT_TYPE_LABEL.get(current, 'off')})"
            )

    summary = build_summary_text(
        date_str=work_date.isoformat(),
        shift_name=SHIFT_NAME[shift],
        done=len(done),
        active_total=active_total,
        average_minutes=average,
        signed=signed,
        called_in=called_in,
        changes=changes,
        flights=summary_flights,
    )
    return ReportOut(
        date=work_date,
        shift=shift,
        done=len(done),
        total=len(flights),
        average_minutes=average,
        signed=signed,
        flights=report_flights,
        people=sorted((ReportPerson(**p) for p in people.values()), key=lambda p: (-p.aircraft, p.name.lower())),
        called_in=called_in,
        roster_changes=changes,
        summary_text=summary,
    )
