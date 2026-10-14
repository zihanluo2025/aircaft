"""Fill the database with fictional staff, a roster with same-day changes, and a day of flights.

    python -m scripts.seed_demo                 # today
    python -m scripts.seed_demo --date 2026-10-13

Safe to run twice: a day that already has flights for a shift is left alone.
"""
import argparse
from datetime import date, timedelta

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Assignment, Flight, RosterEntry, Staff, utcnow

TEAMS = {
    "morning": ["Alex K", "Priya S", "Tom W", "Mei L", "Sam R", "Jordan P", "Lina H", "Ben T", "Noor A", "Chris D"],
    "night": ["Dan M", "Eva C", "Raj N", "Yuki T", "Omar B", "Tess G", "Leo F", "Hana J", "Pete V", "Zoe Q"],
}
PLAN = ["all", "early", "early", "late", "all", "early", "late", "late", "early", None]
QUALS = {0: ["Driver", "Truck"], 1: ["Truck"], 2: ["Driver"], 4: ["Truck", "Driver"], 7: ["Driver"], 8: ["Driver"]}
ROLES = {0: "Driver", 1: "Toilet", 4: "Truck"}
CHANGES = {2: "all", 6: "early"}  # moved on the day because of flight changes
CALL_IN = 7  # not on the plan, phoned in at short notice

FLIGHTS = {
    "morning": [
        ("05:50", "05:50", "QF 705", "Qantas", "VH-VXA", "Bay 3"),
        ("06:25", "06:40", "VA 1252", "Virgin Australia", "VH-YIA", "Bay 5"),
        ("07:05", "07:05", "CZ 664", "China Southern", "B-1385", "Bay 2"),
        ("07:20", "07:20", "JQ 744", "Jetstar", "VH-VFB", "Bay 6"),
        ("08:40", "08:25", "MU 782", "China Eastern", "B-306A", "Bay 1"),
        ("09:30", "09:30", "CX 174", "Cathay Pacific", "B-LRA", "Bay 2"),
        ("10:15", "10:35", "SQ 278", "Singapore Airlines", "9V-SMA", "Bay 4"),
        ("11:05", "11:05", "QF 717", "Qantas", "VH-VZA", "Bay 3"),
    ],
    "night": [
        ("17:30", "17:30", "QF 718", "Qantas", "VH-VZB", "Bay 3"),
        ("18:15", "18:40", "VA 1253", "Virgin Australia", "VH-YIB", "Bay 5"),
        ("19:05", "19:05", "CZ 663", "China Southern", "B-1386", "Bay 2"),
        ("19:50", "19:50", "JQ 745", "Jetstar", "VH-VFC", "Bay 6"),
        ("21:10", "20:55", "MU 781", "China Eastern", "B-306B", "Bay 1"),
        ("22:30", "22:30", "CX 173", "Cathay Pacific", "B-LRB", "Bay 2"),
    ],
}
DEFAULT_ROLES = ["Business", "Vacuum", "Economy - Front", "Economy - Mid", "Economy - Rear"]


def seed(db, work_date: date) -> None:
    for shift, names in TEAMS.items():
        existing = {s.name: s for s in db.scalars(select(Staff).where(Staff.team == shift))}
        for index, name in enumerate(names):
            staff = existing.get(name)
            if staff is None:
                staff = Staff(name=name, team=shift, quals=QUALS.get(index, []))
                db.add(staff)
                db.flush()
            planned = None if index == CALL_IN else PLAN[index]
            current = CHANGES.get(index, planned if index != CALL_IN else "late")
            has_entry = db.scalar(
                select(RosterEntry.id).where(
                    RosterEntry.work_date == work_date, RosterEntry.shift == shift, RosterEntry.staff_id == staff.id
                )
            )
            if has_entry or (planned is None and current is None):
                continue
            db.add(
                RosterEntry(
                    work_date=work_date,
                    shift=shift,
                    staff_id=staff.id,
                    planned_type=planned,
                    shift_type=current,
                    role=ROLES.get(index) if current else None,
                    called_in_at=(utcnow() - timedelta(minutes=40)) if index == CALL_IN else None,
                )
            )
        has_flights = db.scalar(select(Flight.id).where(Flight.work_date == work_date, Flight.shift == shift))
        if has_flights:
            continue
        for sched, eta, number, airline, rego, gate in FLIGHTS[shift]:
            flight = Flight(
                work_date=work_date, shift=shift, flight_no=number, airline=airline, rego=rego, gate=gate,
                sched=sched, eta=eta,
            )
            flight.assignments = [Assignment(role=r, position=i) for i, r in enumerate(DEFAULT_ROLES)]
            db.add(flight)
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db, args.date)
    print(f"Seeded demo data for {args.date.isoformat()}")


if __name__ == "__main__":
    main()
