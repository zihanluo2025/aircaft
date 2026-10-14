import os

os.environ.setdefault("SECRET_KEY", "test-secret")
# Tests never talk to the real flight service, and a developer's backend/.env must not leak in.
for _name in ("FLIGHT_API_KEY", "FLIGHT_AIRLINES", "FLIGHT_INTERNATIONAL", "FLIGHT_FILTER_MODE", "FLIGHT_MONTHLY_CALL_LIMIT", "FLIGHT_SYNC_MIN_INTERVAL_SECONDS", "MORNING_WINDOW", "NIGHT_WINDOW", "AIRPORT_TZ"):
    os.environ[_name] = ""
os.environ["FLIGHT_AIRLINES"] = "JQ,VA"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password


@pytest.fixture()
def client():
    """A signed-in test client backed by a fresh in-memory SQLite database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with Session() as db:
        db.add(User(username="lead", password_hash=hash_password("password123"), display_name="Lead"))
        db.commit()

    test_client = TestClient(app)  # not used as a context manager, so the startup hook is skipped
    token = test_client.post("/api/auth/login", json={"username": "lead", "password": "password123"}).json()[
        "access_token"
    ]
    test_client.headers.update({"Authorization": f"Bearer {token}"})
    # There is no "create a flight" endpoint (flights only ever come from the provider sync); tests that
    # need one go straight to the database with this, the same session factory the app itself uses.
    test_client.db_session_factory = Session
    yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
