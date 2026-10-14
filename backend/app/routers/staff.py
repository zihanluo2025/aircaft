from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Staff
from ..schemas import Shift, StaffIn, StaffOut, StaffPatch

router = APIRouter(prefix="/api/staff", tags=["staff"], dependencies=[Depends(get_current_user)])


def _get(db: Session, staff_id: int) -> Staff:
    staff = db.get(Staff, staff_id)
    if staff is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return staff


@router.get("", response_model=list[StaffOut])
def list_staff(team: Optional[Shift] = Query(None), db: Session = Depends(get_db)):
    query = select(Staff).where(Staff.active.is_(True)).order_by(Staff.name)
    if team:
        query = query.where(Staff.team == team)
    return db.scalars(query).all()


@router.post("", response_model=StaffOut, status_code=201)
def create_staff(body: StaffIn, db: Session = Depends(get_db)):
    existing = db.scalar(select(Staff).where(Staff.team == body.team, Staff.name == body.name))
    if existing is not None:
        if existing.active:
            raise HTTPException(status_code=409, detail=f"{body.name} is already in the {body.team} team")
        existing.active = True  # bring back someone who was removed earlier
        existing.quals = list(body.quals)
        db.commit()
        return existing
    staff = Staff(name=body.name, team=body.team, quals=list(body.quals))
    db.add(staff)
    db.commit()
    return staff


@router.patch("/{staff_id}", response_model=StaffOut)
def patch_staff(staff_id: int, body: StaffPatch, db: Session = Depends(get_db)):
    staff = _get(db, staff_id)
    if body.name is not None and body.name != staff.name:
        clash = db.scalar(select(Staff).where(Staff.team == staff.team, Staff.name == body.name))
        if clash is not None:
            raise HTTPException(status_code=409, detail=f"{body.name} is already in the {staff.team} team")
        staff.name = body.name
    if body.quals is not None:
        staff.quals = list(dict.fromkeys(body.quals))
    db.commit()
    return staff


@router.delete("/{staff_id}", status_code=204)
def remove_staff(staff_id: int, db: Session = Depends(get_db)):
    """Soft delete, so finished flights keep the names of the people who worked them."""
    staff = _get(db, staff_id)
    staff.active = False
    db.commit()
