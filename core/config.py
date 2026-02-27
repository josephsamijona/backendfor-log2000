from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory (works both locally and on Railway)
BACKEND_DIR = Path(__file__).parent.parent
MAIN_PY = BACKEND_DIR / "main.py"
CSV_DIR = BACKEND_DIR

class Settings(BaseSettings):
    dburl: str
    secret_key: str = "super_secret_jwt_key_please_change_in_production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    # Comma-separated origins, e.g.: http://localhost:5173,https://myapp.com
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
