"""Settings read from environment variables (see .env.example and backend/.env.example)."""
import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load backend/.env into the environment without overriding variables that are already set."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _number(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _text(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip()
    return raw or default


class Settings:
    def __init__(self) -> None:
        self.env = os.getenv("ENV", "development")
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./turnaround.db")
        self.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
        self.access_token_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "720"))
        self.cors_origins = _split(os.getenv("CORS_ORIGINS", "http://localhost:5173"))

        # ---- flight data (FlightAware AeroAPI) ----
        self.flight_api_key = os.getenv("FLIGHT_API_KEY", "").strip()
        self.flight_api_base_url = _text("FLIGHT_API_BASE_URL", "https://aeroapi.flightaware.com/aeroapi").rstrip("/")
        self.airport_icao = _text("AIRPORT_ICAO", "YPAD").upper()
        self.airport_tz = _text("AIRPORT_TZ", "Australia/Adelaide")
        # Keep a flight when its airline is listed here (IATA codes: JQ = Jetstar, VA = Virgin Australia)...
        self.flight_airlines = [c.upper() for c in _split(os.getenv("FLIGHT_AIRLINES", "JQ,VA"))]
        # ...or when it comes from overseas. "any" keeps either kind, "all" needs both.
        self.flight_international = _flag("FLIGHT_INTERNATIONAL", True)
        self.flight_filter_mode = _text("FLIGHT_FILTER_MODE", "any").lower()
        self.flight_max_pages = max(1, _number("FLIGHT_MAX_PAGES", 3))
        self.flight_include_arrived = _flag("FLIGHT_INCLUDE_ARRIVED", True)
        self.morning_window = _text("MORNING_WINDOW", "06:00-13:00")
        self.night_window = _text("NIGHT_WINDOW", "13:00-06:00")
        self.sync_min_interval = _number("FLIGHT_SYNC_MIN_INTERVAL_SECONDS", 300)
        self.monthly_call_limit = _number("FLIGHT_MONTHLY_CALL_LIMIT", 100)

        if self.env == "production" and self.secret_key == "dev-secret-change-me":
            raise RuntimeError("Set SECRET_KEY to a long random value when ENV=production")


settings = Settings()
