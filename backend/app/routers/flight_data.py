"""Pull the day's arrivals from the flight data provider (FlightAware AeroAPI)."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import FlightSyncLog, utcnow
from ..schemas import FlightDataStatus, SyncIn, SyncOut
from ..services.flight_data import (
    AeroApiClient,
    FlightDataError,
    build_client,
    parse_window,
    rules_from_settings,
    window_bounds,
)
from ..services.flight_sync import sync_shift

router = APIRouter(prefix="/api/flight-data", tags=["flight data"], dependencies=[Depends(get_current_user)])


def get_flight_client() -> AeroApiClient:
    """Dependency so tests can swap in a fake client."""
    try:
        return build_client(settings)
    except FlightDataError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _window(shift: str):
    return parse_window(settings.morning_window if shift == "morning" else settings.night_window)


def _calls_this_month(db: Session) -> int:
    now = utcnow()
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(db.scalar(select(func.coalesce(func.sum(FlightSyncLog.pages), 0)).where(FlightSyncLog.created_at >= first)) or 0)


@router.get("/status", response_model=FlightDataStatus)
def status(db: Session = Depends(get_db)):
    last = db.scalar(select(FlightSyncLog).order_by(FlightSyncLog.id.desc()).limit(1))
    return {
        "configured": bool(settings.flight_api_key),
        "provider": "FlightAware AeroAPI",
        "airport": settings.airport_icao,
        "filter_text": rules_from_settings(settings).describe(),
        "last_sync_at": last.created_at if last else None,
        "last_ok": last.ok if last else None,
        "last_message": last.message if last else "",
        "calls_this_month": _calls_this_month(db),
        "monthly_limit": settings.monthly_call_limit,
    }


@router.post("/sync", response_model=SyncOut)
def sync(body: SyncIn, db: Session = Depends(get_db), client: AeroApiClient = Depends(get_flight_client)):
    now = utcnow()
    last_ok = db.scalar(select(FlightSyncLog).where(FlightSyncLog.ok.is_(True)).order_by(FlightSyncLog.id.desc()).limit(1))
    if last_ok is not None and settings.sync_min_interval > 0:
        wait = settings.sync_min_interval - (now - last_ok.created_at).total_seconds()
        if wait > 0:
            raise HTTPException(status_code=429, detail=f"Flights were updated just now. Try again in {int(wait) + 1} seconds.")

    used = _calls_this_month(db)
    reserve = client.max_pages * (2 if client.include_arrived else 1)
    if settings.monthly_call_limit and used + reserve > settings.monthly_call_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly limit reached ({used} of {settings.monthly_call_limit} result sets used). "
            "Raise FLIGHT_MONTHLY_CALL_LIMIT if your plan allows more.",
        )

    tz = ZoneInfo(settings.airport_tz)
    window = _window(body.shift)
    start, end = window_bounds(body.date, window, tz)
    # A little slack either side: a flight can be scheduled inside the window and estimated just outside it.
    try:
        provider_flights = client.arrivals(settings.airport_icao, start - timedelta(minutes=30), end + timedelta(minutes=30), tz)
    except FlightDataError as error:
        db.add(FlightSyncLog(work_date=body.date, shift=body.shift, pages=client.last_pages, ok=False, message=str(error)))
        db.commit()
        raise HTTPException(status_code=502, detail=str(error)) from error

    result = sync_shift(
        db,
        flights=provider_flights,
        rules=rules_from_settings(settings),
        work_date=body.date,
        shift=body.shift,
        window=window,
    )
    db.add(
        FlightSyncLog(
            work_date=body.date,
            shift=body.shift,
            pages=client.last_pages,
            ok=True,
            fetched=result.fetched,
            created=result.created,
            updated=result.updated,
            message=f"{result.kept} kept of {result.fetched}",
        )
    )
    db.commit()
    return {
        "fetched": result.fetched,
        "kept": result.kept,
        "created": result.created,
        "updated": result.updated,
        "skipped_started": result.skipped_started,
        "pages": client.last_pages,
        "calls_this_month": used + client.last_pages,
    }
