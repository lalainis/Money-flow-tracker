import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
IS_RENDER = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"))
IS_PRODUCTION = (os.getenv("FLASK_ENV") or "").strip().lower() == "production"

load_dotenv()
if not IS_RENDER:
    load_dotenv(BASE_DIR / "finan.env")

UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{BASE_DIR / 'app.db'}"


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name, default, minimum=None):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


DB_POOL_PRE_PING = _env_bool("DB_POOL_PRE_PING", default=True)
DB_POOL_RECYCLE_SECONDS = _env_int("DB_POOL_RECYCLE_SECONDS", default=1800, minimum=30)
DB_POOL_TIMEOUT_SECONDS = _env_int("DB_POOL_TIMEOUT_SECONDS", default=30, minimum=1)
DB_POOL_SIZE = _env_int("DB_POOL_SIZE", default=5, minimum=1)
DB_MAX_OVERFLOW = _env_int("DB_MAX_OVERFLOW", default=10, minimum=0)
DB_CONNECT_TIMEOUT_SECONDS = _env_int("DB_CONNECT_TIMEOUT_SECONDS", default=10, minimum=1)
DB_KEEPALIVES_IDLE_SECONDS = _env_int("DB_KEEPALIVES_IDLE_SECONDS", default=30, minimum=1)
DB_KEEPALIVES_INTERVAL_SECONDS = _env_int("DB_KEEPALIVES_INTERVAL_SECONDS", default=10, minimum=1)
DB_KEEPALIVES_COUNT = _env_int("DB_KEEPALIVES_COUNT", default=5, minimum=1)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if IS_RENDER or IS_PRODUCTION:
        raise RuntimeError("SECRET_KEY is required in production")
    SECRET_KEY = "dev-only-secret-key-change-me"

_cors_origins = [item.strip() for item in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if item.strip()]
if _cors_origins:
    CORS_ALLOWED_ORIGINS = _cors_origins
else:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

AUTH_TOKEN_TTL_HOURS = max(1, int(os.getenv("AUTH_TOKEN_TTL_HOURS", "12")))
AUTH_MAX_FAILED_ATTEMPTS = max(3, int(os.getenv("AUTH_MAX_FAILED_ATTEMPTS", "5")))
AUTH_LOCKOUT_MINUTES = max(1, int(os.getenv("AUTH_LOCKOUT_MINUTES", "15")))

ROLES = {"cashier", "board", "auditor", "admin", "member"}
EXPENSE_CATEGORIES = [
    "Operating expenses",
    "Construction materials",
    "Feed",
    "Taxes",
    "Licenses",
    "Land payments",
    "Internet",
    "Electricity",
    "Insurance",
    "Mowing expenses",
    "Beaver monitoring expenses",
    "LMS membership fee",
    "Bank commission fee",
    "Other",
]
ALLOWED_ATTACHMENT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "txt", "doc", "docx", "xlsx"}
