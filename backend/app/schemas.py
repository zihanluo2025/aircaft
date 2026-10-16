from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

Shift = Literal["morning", "night"]
ShiftType = Literal["early", "late", "all"]
FixedRole = Literal["Driver", "Toilet", "Truck"]
QualRole = Literal["Driver", "Truck"]
HHMM = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


def _iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[datetime, PlainSerializer(_iso_z, return_type=str)]


# ---- auth ----
class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    default_shift: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- staff ----
class StaffIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    team: Shift
    quals: list[QualRole] = Field(default_factory=list)


class StaffPatch(BaseModel):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]] = None
    quals: Optional[list[QualRole]] = None


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    team: str
    quals: list[str]
    active: bool


# ---- roster ----
class RosterEntryOut(BaseModel):
    staff_id: int
    name: str
    quals: list[str]
    shift_type: Optional[ShiftType]
    planned_type: Optional[ShiftType]
    role: Optional[FixedRole]
    called_in_at: Optional[UtcDateTime]
    sick_at: Optional[UtcDateTime]
    rstart: str
    rend: str


class RosterOut(BaseModel):
    date: date
    shift: Shift
    has_plan: bool
    entries: list[RosterEntryOut]


class RosterPatch(BaseModel):
    """Partial update. Only fields present in the request body are applied."""

    shift_type: Optional[ShiftType] = None
    role: Optional[FixedRole] = None
    called_in: Optional[bool] = None
    sick: Optional[bool] = None
    rstart: Optional[HHMM] = None
    rend: Optional[HHMM] = None


class RosterPatchOut(BaseModel):
    entry: RosterEntryOut
    unassigned: int


class ImportIn(BaseModel):
    shift: Shift
    text: Annotated[str, StringConstraints(max_length=300_000)]


class ImportPreviewOut(BaseModel):
    days: int
    people: int
    new_people: int
    shifts: int
    bad: list[str]


class ImportApplyOut(BaseModel):
    days: int
    created_staff: int
    shifts: int


# ---- flights ----
class FlightPatch(BaseModel):
    flight_no: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]] = None
    airline: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = None
    rego: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]] = None
    gate: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]] = None
    sched: Optional[HHMM] = None
    eta: Optional[HHMM] = None
    landed: Optional[bool] = None
    cancelled: Optional[bool] = None
    notes: Optional[Annotated[str, StringConstraints(max_length=4000)]] = None


class AssignmentIn(BaseModel):
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    staff_id: Optional[int] = None


class TimesIn(BaseModel):
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class SignatureIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    image: Annotated[str, StringConstraints(max_length=400_000)]


class CrewMember(BaseModel):
    role: str
    staff_id: Optional[int] = None
    staff_name: str = ""


class FlightOut(BaseModel):
    id: int
    work_date: date
    shift: Shift
    flight_no: str
    airline: str
    rego: str
    gate: str
    origin: str
    international: bool
    sched: str
    eta: str
    delay_minutes: int
    landed: bool
    cancelled: bool
    status: Literal["sched", "landed", "cleaning", "done", "cancelled"]
    started_at: Optional[UtcDateTime]
    finished_at: Optional[UtcDateTime]
    minutes: Optional[int]
    notes: str
    fixed: list[CrewMember]
    assignments: list[CrewMember]
    crew_count: int
    has_signature: bool
    sig_name: str
    signed_at: Optional[UtcDateTime]


class FlightDetail(FlightOut):
    sig_image: str


# ---- report ----
class ReportFlight(BaseModel):
    id: int
    flight_no: str
    eta: str
    status: str
    started_at: Optional[UtcDateTime]
    finished_at: Optional[UtcDateTime]
    minutes: Optional[int]
    crew_count: int
    crew: list[CrewMember]
    signed: bool


class ReportPerson(BaseModel):
    staff_id: int
    name: str
    aircraft: int
    minutes: int


class ReportOut(BaseModel):
    date: date
    shift: Shift
    done: int
    total: int
    average_minutes: int
    signed: int
    flights: list[ReportFlight]
    people: list[ReportPerson]
    called_in: list[str]
    roster_changes: list[str]
    summary_text: str


# ---- flight data (provider sync) ----
class FlightDataStatus(BaseModel):
    configured: bool
    provider: str
    airport: str
    filter_text: str
    last_sync_at: Optional[UtcDateTime]
    last_ok: Optional[bool]
    last_message: str
    calls_this_month: int
    monthly_limit: int


class SyncIn(BaseModel):
    date: date
    shift: Shift


class SyncOut(BaseModel):
    fetched: int
    kept: int
    created: int
    updated: int
    skipped_started: int
    pages: int
    calls_this_month: int
