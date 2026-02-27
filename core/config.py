from pathlib import Path
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Paths
BASE_DIR = Path(__file__).parent.parent.parent  # locustest/
MAIN_PY = BASE_DIR / "main.py"
CSV_DIR = BASE_DIR / "backend"  # CSV output dir

class Settings(BaseSettings):
    dburl: str
    secret_key: str = "super_secret_jwt_key_please_change_in_production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    # Comma-separated origins in .env, e.g.: http://localhost:5173,https://myapp.com
    allowed_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
