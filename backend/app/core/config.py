import os
from pathlib import Path

class Settings:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./dataready.db")
    jwt_secret = os.getenv("JWT_SECRET", "dev-only-change-me")
    upload_dir = Path(os.getenv("UPLOAD_DIR", "./private_uploads"))
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "50"))
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

settings = Settings()
