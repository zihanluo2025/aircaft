from datetime import date as Date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Assignment, Flight, RosterEntry, Staff, utcnow
from ..schemas import (
    ImportApplyOut,
    ImportIn,
    ImportPreviewOut,
    RosterEntryOut,
    RosterOut,
    RosterPatch,
    RosterPatchOut,
    Shift,
)
from ..services.domain import LICENCE_REQUIRED_ROLES, SHIFT_ORDER, title_case
from ..services.roster_import import QUAL_ROLES, ParsedRoster, parse_roster_text, parse_roster_xlsx

router = APIRouter(prefix="/api/roster", tags=["roster"], dependencies=[Depends(get_current_user)])


def _window(shift: str) -> tuple[str, str]:
    """The shift's configured Start-Indicative End window, as plain HH:MM strings (not the
    flight-sync `parse_window`, which returns `time` objects for a different purpose)."""
    text = settings.morning_window if shift == "morning" else settings.night_window
    start, _, end = text.partition("-")
    return start.strip(), end.strip()


def _entry_out(entry: RosterEntry, staff: Staff) -> RosterEntryOut:
    return RosterEntryOut(
        staff_id=staff.id,
        name=title_case(staff.name),
        quals=list(staff.quals or []),
        shift_type=entry.shift_type,
        planned_type=entry.planned_type,
        role=entry.role,
        called_in_at=entry.called_in_at,
        sick_at=entry.sick_at,
        rstart=entry.rstart,
        rend=entry.rend,
    )


@router.get("", response_model=RosterOut)
def get_roster(
    work_date: Date = Query(..., alias="date"),
    shift: Shift = Query(...),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(RosterEntry, Staff)
        .join(Staff, Staff.id == RosterEntry.staff_id)
        .where(RosterEntry.work_date == work_date, RosterEntry.shift == shift, Staff.active.is_(True))
    ).all()
    rows.sort(key=lambda r: (SHIFT_ORDER.get(r[0].shift_type, 3), r[1].name.lower()))
    return RosterOut(
        date=work_date,
        shift=shift,
        has_plan=any(e.planned_type for e, _ in rows),
        entries=[_entry_out(e, s) for e, s in rows],
    )


def _unassign(db: Session, work_date: Date, shift: str, staff_id: int) -> int:
    """Take a person off every unfinished flight of the day. Returns how many jobs were cleared."""
    unfinished = select(Flight.id).where(
        Flight.work_date == work_date, Flight.shift == shift, Flight.finished_at.is_(None)
    )
    result = db.execute(
        update(Assignment)
        .where(Assignment.staff_id == staff_id, Assignment.flight_id.in_(unfinished))
        .values(staff_id=None)
    )
    return result.rowcount or 0


@router.patch("/{staff_id}", response_model=RosterPatchOut)
def patch_entry(
    staff_id: int,
    body: RosterPatch,
    work_date: Date = Query(..., alias="date"),
    shift: Shift = Query(...),
    db: Session = Depends(get_db),
):
    staff = db.get(Staff, staff_id)
    if staff is None or not staff.active:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if staff.team != shift:
        raise HTTPException(status_code=400, detail=f"{title_case(staff.name)} belongs to the {staff.team} team")

    entry = db.scalar(
        select(RosterEntry).where(
            RosterEntry.work_date == work_date, RosterEntry.shift == shift, RosterEntry.staff_id == staff_id
        )
    )
    if entry is None:
        entry = RosterEntry(work_date=work_date, shift=shift, staff_id=staff_id)
        db.add(entry)

    fields = body.model_fields_set
    unassigned = 0

    if "shift_type" in fields:
        entry.shift_type = body.shift_type
        if body.shift_type is None:  # taken off the roster
            entry.role = None
            entry.called_in_at = None
            unassigned = _unassign(db, work_date, shift, staff_id)
        else:  # back on duty, so any earlier sick call no longer applies
            entry.sick_at = None

    if "role" in fields:
        if body.role is not None:
            if entry.shift_type is None:
                raise HTTPException(status_code=400, detail="Put the person on the roster before giving them a role")
            if body.role in LICENCE_REQUIRED_ROLES and body.role not in (staff.quals or []):
                raise HTTPException(status_code=400, detail=f"{title_case(staff.name)} is not qualified for {body.role}")
        entry.role = body.role

    if "called_in" in fields:
        if body.called_in:
            if entry.shift_type is None:
                raise HTTPException(status_code=400, detail="Put the person on the roster before marking a call in")
            entry.called_in_at = entry.called_in_at or utcnow()
        else:
            entry.called_in_at = None

    if "sick" in fields:
        if body.sick:
            entry.sick_at = entry.sick_at or utcnow()
            entry.shift_type = None
            entry.role = None
            entry.called_in_at = None
            unassigned = _unassign(db, work_date, shift, staff_id)
        else:
            entry.sick_at = None

    if "rstart" in fields and body.rstart is not None:
        entry.rstart = body.rstart
    if "rend" in fields and body.rend is not None:
        entry.rend = body.rend

    db.commit()
    return RosterPatchOut(entry=_entry_out(entry, staff), unassigned=unassigned)


def _preview_out(db: Session, parsed: ParsedRoster, shift: str) -> ImportPreviewOut:
    known = {s.name.lower() for s in db.scalars(select(Staff).where(Staff.team == shift))}
    return ImportPreviewOut(
        days=len(parsed.days),
        people=len(parsed.people),
        new_people=len([name for name in parsed.people if name not in known]),
        shifts=parsed.shifts,
        bad=parsed.bad[:20],
    )


def _apply_parsed(db: Session, parsed: ParsedRoster, shift: str) -> ImportApplyOut:
    """The new import fully replaces the previous version for the chosen shift's team:
    - every roster entry from the new roster's first date onward is cleared (dates the new file no
      longer covers included), then rebuilt from the file; earlier days stay as history for reports;
    - anyone in the team who is not in the new roster is made inactive, so the Off today list only
      shows the latest roster's people;
    - people no longer on duty are taken off unstarted flights from that date onward."""
    if not parsed.days:
        raise HTTPException(status_code=400, detail="No shifts found. Check the layout and try again.")

    first_day = min(Date.fromisoformat(day) for day in parsed.days)
    db.execute(delete(RosterEntry).where(RosterEntry.shift == shift, RosterEntry.work_date >= first_day))

    team = list(db.scalars(select(Staff).where(Staff.team == shift)))
    for staff in team:
        if staff.name.lower() not in parsed.people:
            staff.active = False
    by_name = {s.name.lower(): s for s in team}
    created = 0

    def ensure(name: str) -> Staff:
        nonlocal created
        staff = by_name.get(name.lower())
        if staff is None:
            staff = Staff(name=name.strip(), team=shift, quals=[])
            db.add(staff)
            db.flush()
            by_name[name.lower()] = staff
            created += 1
        elif not staff.active:
            staff.active = True
        return staff

    on_duty: set[tuple[Date, int]] = set()
    for day_str, cells in parsed.days.items():
        work_date = Date.fromisoformat(day_str)
        for name, cell in cells.items():
            staff = ensure(name)
            for role in cell["roles"]:
                if role in QUAL_ROLES and role not in (staff.quals or []):
                    staff.quals = [*(staff.quals or []), role]
            if cell["shift"]:
                db.add(
                    RosterEntry(
                        work_date=work_date,
                        shift=shift,
                        staff_id=staff.id,
                        shift_type=cell["shift"],
                        planned_type=cell["shift"],
                        rstart=cell["rstart"],
                        rend=cell["rend"],
                    )
                )
                on_duty.add((work_date, staff.id))

    # 已经开始清洁的航班不动，只清理还没开始的航班上已不在岗的人
    stale = db.execute(
        select(Assignment, Flight.work_date)
        .join(Flight, Flight.id == Assignment.flight_id)
        .where(
            Flight.shift == shift,
            Flight.work_date >= first_day,
            Flight.started_at.is_(None),
            Assignment.staff_id.is_not(None),
        )
    ).all()
    for assignment, work_date in stale:
        if (work_date, assignment.staff_id) not in on_duty:
            assignment.staff_id = None
    db.commit()
    return ImportApplyOut(days=len(parsed.days), created_staff=created, shifts=parsed.shifts)


def _read_xlsx(file: UploadFile, shift: str, today, window) -> ParsedRoster:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported.")
    try:
        return parse_roster_xlsx(file.file.read(), today, window)
    except Exception as error:  # noqa: BLE001 - any workbook-reading failure becomes one clear message
        raise HTTPException(status_code=400, detail="Could not read that spreadsheet. Is it a valid .xlsx file?") from error


@router.post("/import/preview", response_model=ImportPreviewOut)
def import_preview(body: ImportIn, db: Session = Depends(get_db)):
    parsed = parse_roster_text(body.text, window=_window(body.shift))
    return _preview_out(db, parsed, body.shift)


@router.post("/import", response_model=ImportApplyOut)
def import_apply(body: ImportIn, db: Session = Depends(get_db)):
    parsed = parse_roster_text(body.text, window=_window(body.shift))
    return _apply_parsed(db, parsed, body.shift)


@router.post("/import/preview/file", response_model=ImportPreviewOut)
def import_preview_file(shift: Shift = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    parsed = _read_xlsx(file, shift, None, _window(shift))
    return _preview_out(db, parsed, shift)


@router.post("/import/file", response_model=ImportApplyOut)
def import_apply_file(shift: Shift = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    parsed = _read_xlsx(file, shift, None, _window(shift))
    return _apply_parsed(db, parsed, shift)
