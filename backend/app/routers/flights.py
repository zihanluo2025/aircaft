from datetime import date as Date
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Assignment, Flight, FlightPhoto, RosterEntry, Staff, utcnow
from ..schemas import (
    AssignmentIn,
    FlightDetail,
    FlightOut,
    FlightPatch,
    PhotoIn,
    PhotoOut,
    PhotoRename,
    Shift,
    SignatureIn,
    TimesIn,
)
from ..services.domain import build_flight_out, fixed_holders, title_case

router = APIRouter(prefix="/api/flights", tags=["flights"], dependencies=[Depends(get_current_user)])

_WITH_CREW = (selectinload(Flight.assignments).selectinload(Assignment.staff),)


def _load(db: Session, flight_id: int) -> Flight:
    flight = db.scalar(select(Flight).options(*_WITH_CREW).where(Flight.id == flight_id))
    if flight is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return flight


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("", response_model=list[FlightOut])
def list_flights(
    work_date: Date = Query(..., alias="date"),
    shift: Shift = Query(...),
    db: Session = Depends(get_db),
):
    flights = db.scalars(
        select(Flight)
        .options(*_WITH_CREW)
        .where(Flight.work_date == work_date, Flight.shift == shift)
        .order_by(Flight.eta, Flight.id)
    ).all()
    live = fixed_holders(db, work_date, shift)
    return [build_flight_out(db, f, live=live) for f in flights]


@router.get("/{flight_id}", response_model=FlightDetail)
def get_flight(flight_id: int, db: Session = Depends(get_db)):
    return build_flight_out(db, _load(db, flight_id), detail=True)


@router.patch("/{flight_id}", response_model=FlightOut)
def patch_flight(flight_id: int, body: FlightPatch, db: Session = Depends(get_db)):
    flight = _load(db, flight_id)
    for name in body.model_fields_set:
        value = getattr(body, name)
        if value is None:
            continue
        setattr(flight, name, value)
    db.commit()
    return build_flight_out(db, flight)


@router.delete("/{flight_id}", status_code=204)
def delete_flight(flight_id: int, db: Session = Depends(get_db)):
    db.delete(_load(db, flight_id))
    db.commit()


@router.put("/{flight_id}/assignments", response_model=FlightOut)
def put_assignments(flight_id: int, items: list[AssignmentIn], db: Session = Depends(get_db)):
    """Replace the per aircraft jobs. People newly added must be on duty and not busy on another aircraft."""
    flight = _load(db, flight_id)

    seen: set[int] = set()
    for item in items:
        if item.staff_id is None:
            continue
        if item.staff_id in seen:
            staff = db.get(Staff, item.staff_id)
            name = title_case(staff.name) if staff else "This person"
            raise HTTPException(status_code=400, detail=f"{name} is assigned twice -- pick one position")
        seen.add(item.staff_id)

    current = {a.staff_id for a in flight.assignments if a.staff_id}
    new_ids = {i.staff_id for i in items if i.staff_id} - current

    if new_ids:
        staff_rows = {s.id: s for s in db.scalars(select(Staff).where(Staff.id.in_(list(new_ids))))}
        on_duty = set(
            db.scalars(
                select(RosterEntry.staff_id).where(
                    RosterEntry.work_date == flight.work_date,
                    RosterEntry.shift == flight.shift,
                    RosterEntry.shift_type.is_not(None),
                    RosterEntry.staff_id.in_(list(new_ids)),
                )
            )
        )
        for staff_id in new_ids:
            staff = staff_rows.get(staff_id)
            if staff is None or staff.team != flight.shift:
                raise HTTPException(status_code=400, detail="Unknown staff member")
            if staff_id not in on_duty:
                raise HTTPException(status_code=400, detail=f"{title_case(staff.name)} is not on today's roster")

        busy = db.execute(
            select(Assignment.staff_id, Flight.flight_no)
            .join(Flight, Flight.id == Assignment.flight_id)
            .where(
                Flight.work_date == flight.work_date,
                Flight.shift == flight.shift,
                Flight.id != flight.id,
                Flight.started_at.is_not(None),
                Flight.finished_at.is_(None),
                Flight.cancelled.is_(False),
                Assignment.staff_id.in_(list(new_ids)),
            )
        ).first()
        if busy is not None:
            raise HTTPException(
                status_code=409, detail=f"{title_case(staff_rows[busy[0]].name)} is cleaning {busy[1]} right now"
            )

    flight.assignments.clear()
    db.flush()
    for position, item in enumerate(items):
        flight.assignments.append(Assignment(role=item.role, staff_id=item.staff_id, position=position))
    db.commit()
    return build_flight_out(db, _load(db, flight_id))


@router.post("/{flight_id}/start", response_model=FlightOut)
def start_cleaning(flight_id: int, db: Session = Depends(get_db)):
    flight = _load(db, flight_id)
    if flight.cancelled:
        raise HTTPException(status_code=400, detail="This flight is cancelled")
    if flight.started_at:
        raise HTTPException(status_code=409, detail="Cleaning has already started")
    holders = fixed_holders(db, flight.work_date, flight.shift)
    if not holders and not any(a.staff_id for a in flight.assignments):
        raise HTTPException(status_code=400, detail="Assign at least one person first")
    flight.fixed = holders  # snapshot: later roster edits do not rewrite this record
    flight.started_at = utcnow()
    flight.finished_at = None
    flight.landed = True
    db.commit()
    return build_flight_out(db, flight)


@router.post("/{flight_id}/finish", response_model=FlightOut)
def finish_cleaning(flight_id: int, db: Session = Depends(get_db)):
    flight = _load(db, flight_id)
    if not flight.started_at or flight.finished_at:
        raise HTTPException(status_code=409, detail="This flight is not being cleaned")
    flight.finished_at = utcnow()
    db.commit()
    return build_flight_out(db, flight)


@router.post("/{flight_id}/reopen", response_model=FlightOut)
def reopen_cleaning(flight_id: int, db: Session = Depends(get_db)):
    flight = _load(db, flight_id)
    if not flight.finished_at:
        raise HTTPException(status_code=409, detail="This flight is not finished")
    flight.finished_at = None
    db.commit()
    return build_flight_out(db, flight)


@router.patch("/{flight_id}/times", response_model=FlightOut)
def set_times(flight_id: int, body: TimesIn, db: Session = Depends(get_db)):
    """Correct the start or finish time when the leading hand forgot to tap."""
    flight = _load(db, flight_id)
    if not flight.started_at:
        raise HTTPException(status_code=409, detail="Start cleaning first")
    fields = body.model_fields_set
    started: Optional[datetime] = flight.started_at
    finished: Optional[datetime] = flight.finished_at
    if "started_at" in fields and body.started_at is not None:
        started = _naive_utc(body.started_at)
    if "finished_at" in fields and body.finished_at is not None:
        if flight.finished_at is None:
            raise HTTPException(status_code=409, detail="Finish cleaning first")
        finished = _naive_utc(body.finished_at)
    if finished is not None and finished <= started:
        raise HTTPException(status_code=400, detail="Finish must be after start")
    flight.started_at, flight.finished_at = started, finished
    db.commit()
    return build_flight_out(db, flight)


@router.put("/{flight_id}/signature", response_model=FlightDetail)
def sign(flight_id: int, body: SignatureIn, db: Session = Depends(get_db)):
    flight = _load(db, flight_id)
    if not flight.finished_at:
        raise HTTPException(status_code=400, detail="Finish cleaning before the cabin crew signs")
    if not body.image.startswith("data:image/png;base64,"):
        raise HTTPException(status_code=400, detail="The signature must be a PNG image")
    flight.sig_name = body.name
    flight.sig_image = body.image
    flight.signed_at = utcnow()
    db.commit()
    return build_flight_out(db, flight, detail=True)


@router.delete("/{flight_id}/signature", response_model=FlightDetail)
def clear_signature(flight_id: int, db: Session = Depends(get_db)):
    flight = _load(db, flight_id)
    flight.sig_name = ""
    flight.sig_image = ""
    flight.signed_at = None
    db.commit()
    return build_flight_out(db, flight, detail=True)


def _get_flight(db: Session, flight_id: int) -> Flight:
    flight = db.get(Flight, flight_id)
    if flight is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return flight


def _get_photo(db: Session, flight_id: int, photo_id: int) -> FlightPhoto:
    photo = db.scalar(select(FlightPhoto).where(FlightPhoto.id == photo_id, FlightPhoto.flight_id == flight_id))
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo


@router.get("/{flight_id}/photos", response_model=list[PhotoOut])
def list_photos(flight_id: int, db: Session = Depends(get_db)):
    _get_flight(db, flight_id)
    return db.scalars(select(FlightPhoto).where(FlightPhoto.flight_id == flight_id).order_by(FlightPhoto.id)).all()


@router.post("/{flight_id}/photos", response_model=PhotoOut, status_code=201)
def add_photo(flight_id: int, body: PhotoIn, db: Session = Depends(get_db)):
    _get_flight(db, flight_id)
    if not body.image.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="The photo must be an image")
    photo = FlightPhoto(flight_id=flight_id, name=body.name, image=body.image)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


@router.patch("/{flight_id}/photos/{photo_id}", response_model=PhotoOut)
def rename_photo(flight_id: int, photo_id: int, body: PhotoRename, db: Session = Depends(get_db)):
    photo = _get_photo(db, flight_id, photo_id)
    photo.name = body.name
    db.commit()
    return photo


@router.delete("/{flight_id}/photos/{photo_id}", status_code=204)
def remove_photo(flight_id: int, photo_id: int, db: Session = Depends(get_db)):
    photo = _get_photo(db, flight_id, photo_id)
    db.delete(photo)
    db.commit()
