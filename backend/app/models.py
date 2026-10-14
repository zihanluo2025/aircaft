from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Naive UTC timestamp. Every datetime column stores UTC; the API adds the Z suffix."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    """A leading hand who can sign in."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(100), default="")
    default_shift: Mapped[str] = mapped_column(String(10), default="morning")


class Staff(Base):
    """A cleaner. Each person belongs to exactly one team: morning or night."""

    __tablename__ = "staff"
    __table_args__ = (UniqueConstraint("team", "name", name="uq_staff_team_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    team: Mapped[str] = mapped_column(String(10), index=True)
    quals: Mapped[list] = mapped_column(JSON, default=list)  # subset of ["Driver", "Truck"]
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RosterEntry(Base):
    """One person on one day of one shift.

    planned_type is the rostered shift imported from the manager's roster.
    shift_type is what is happening today. They differ when the leading hand changes someone.
    shift_type None means not working today.
    """

    __tablename__ = "roster_entries"
    __table_args__ = (UniqueConstraint("work_date", "shift", "staff_id", name="uq_roster_day_staff"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    shift_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # early | late | all
    planned_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # Driver | Toilet | Truck, fixed for the day
    called_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # The roster's actual Start / Indicative End for the day, HH:MM, "" when not recorded. shift_type
    # above is still what drives the Early/Late/All day grouping; these are the source of truth when
    # they came from an import or a manual correction.
    rstart: Mapped[str] = mapped_column(String(5), default="")
    rend: Mapped[str] = mapped_column(String(5), default="")

    staff: Mapped["Staff"] = relationship()


class Flight(Base):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[str] = mapped_column(String(10), index=True)
    flight_no: Mapped[str] = mapped_column(String(20))
    airline: Mapped[str] = mapped_column(String(100), default="")
    rego: Mapped[str] = mapped_column(String(20), default="")
    gate: Mapped[str] = mapped_column(String(20), default="")
    sched: Mapped[str] = mapped_column(String(5))  # HH:MM
    eta: Mapped[str] = mapped_column(String(5))  # HH:MM
    origin: Mapped[str] = mapped_column(String(10), default="")  # ICAO code of the airport it flew from
    international: Mapped[bool] = mapped_column(Boolean, default=False)
    landed: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Driver / Toilet / Truck holders captured when cleaning starts, so later roster edits do not rewrite history.
    fixed: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    sig_name: Mapped[str] = mapped_column(String(100), default="")
    sig_image: Mapped[str] = mapped_column(Text, default="")
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan", order_by="Assignment.position"
    )


class Assignment(Base):
    """A per-aircraft job (Business, Vacuum, Economy - Front, ...) and who does it."""

    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(60))
    staff_id: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    flight: Mapped["Flight"] = relationship(back_populates="assignments")
    staff: Mapped[Optional["Staff"]] = relationship()


class FlightSyncLog(Base):
    """One attempt to pull arrivals from the flight data provider. Used for throttling and the monthly quota."""

    __tablename__ = "flight_sync_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    work_date: Mapped[date] = mapped_column(Date)
    shift: Mapped[str] = mapped_column(String(10))
    pages: Mapped[int] = mapped_column(Integer, default=0)  # result sets requested; this is what the provider bills
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
