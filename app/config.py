from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://router:router@localhost:5432/router"
    redis_url: str = "redis://localhost:6379/0"
    model_dir: str = "artifacts/robustness/deployed"
    auto_routing_enabled: bool = False
    demo_mode: bool = False
    demo_ticket_limit: int = 500
    routing_path: str = "config/routing.json"
    frontend_dir: str = "frontend/dist"
    lease_seconds: int = 90
    job_timeout: int = 60
    max_attempts: int = 3
    retry_base_seconds: int = 5

    @field_validator('database_url')
    @classmethod
    def postgres_driver(cls,value):
        if value.startswith('postgres://'):
            return 'postgresql+psycopg://'+value[len('postgres://'):]
        if value.startswith('postgresql://'):
            return 'postgresql+psycopg://'+value[len('postgresql://'):]
        return value


@lru_cache
def settings():
    return Settings()
