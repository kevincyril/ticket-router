from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://router:router@localhost:5432/router"
    redis_url: str = "redis://localhost:6379/0"
    model_dir: str = "artifacts/robustness/deployed"
    auto_routing_enabled: bool = False
    routing_path: str = "config/routing.json"
    frontend_dir: str = "frontend/dist"
    lease_seconds: int = 90
    job_timeout: int = 60
    max_attempts: int = 3
    retry_base_seconds: int = 5


@lru_cache
def settings():
    return Settings()
