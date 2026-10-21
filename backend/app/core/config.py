import os
from urllib.parse import quote_plus
from pathlib import Path

def _secret(env_name: str, file_env_name: str | None = None, fallback: str = "") -> str:
    path=os.getenv(file_env_name or f"{env_name}_FILE")
    if path:
        try: return Path(path).read_text().strip()
        except OSError as exc: raise RuntimeError(f"Unable to read configured secret file for {env_name}") from exc
    return os.getenv(env_name, fallback)

class Settings:
    app_env = os.getenv("APP_ENV", "development")
    database_url = os.getenv("DATABASE_URL") or ("postgresql+psycopg://"+quote_plus(os.getenv("DB_USER","dataready"))+":"+quote_plus(_secret("DB_PASSWORD","DB_PASSWORD_FILE","dataready"))+"@"+os.getenv("DB_HOST","db")+":"+os.getenv("DB_PORT","5432")+"/"+os.getenv("DB_NAME","dataready") if os.getenv("DB_HOST") else "sqlite:///./dataready.db")
    jwt_secret = _secret("JWT_SECRET", fallback="dev-only-change-me")
    upload_dir = Path(os.getenv("UPLOAD_DIR", "./private_uploads"))
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "50"))
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cookie_secure = os.getenv("COOKIE_SECURE", "true" if app_env=="production" else "false").lower()=="true"
    allowed_origins = [x.strip().rstrip("/") for x in os.getenv("ALLOWED_ORIGINS","http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
    anthropic_api_key = _secret("ANTHROPIC_API_KEY", fallback="")
    max_expanded_upload_mb = int(os.getenv("MAX_EXPANDED_UPLOAD_MB","200"))
    if app_env=="production" and (jwt_secret=="dev-only-change-me" or len(jwt_secret)<32):
        raise RuntimeError("Set a unique JWT_SECRET_FILE or JWT_SECRET of at least 32 characters for production")

settings = Settings()
