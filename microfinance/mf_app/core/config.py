from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # This service's OWN metadata database — never institution business data
    # (cf. docs/architecture/08-microfinance-et-billing.md §8.4).
    control_database_url: str = "sqlite+aiosqlite:///./microfinance_control_dev.db"

    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Fernet key encrypting institution DB credentials at rest — same scheme as
    # backend/app/core/config.py's secret_encryption_key, a separate key for a
    # separate deployable.
    secret_encryption_key: str = "08u_J80OTnrWkefxT-D4WVGWAnX-CJynJWy-T-SCvXQ="

    # This service is itself a client of the Control Plane (cf. §8.3) — every
    # institution is provisioned by calling this API via eminidatabase_sdk.
    platform_api_url: str = "http://127.0.0.1:8000/api/v1"

    # Gates POST /institutions (onboarding) — internal ops only, not self-service
    # (cf. §8.11). Argon2 hash, verified the same way as any other secret in this
    # codebase, never compared in plaintext.
    mf_operator_token_hash: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
