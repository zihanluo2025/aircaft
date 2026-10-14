from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .migrations import add_missing_columns
from .routers import auth, flight_data, flights, report, roster, staff


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine)  # older databases are missing the newer flight columns
    yield


app = FastAPI(title="Turnaround API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(staff.router)
app.include_router(roster.router)
app.include_router(flights.router)
app.include_router(flight_data.router)
app.include_router(report.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}
