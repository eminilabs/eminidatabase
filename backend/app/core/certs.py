from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class CertSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    certs_dir: str = "./certs"
    ca_common_name: str = "eminidatabase Internal CA"
    control_plane_common_name: str = "control-plane"
    cert_validity_days: int = 825  # < 825 days, the common CA/Browser Forum ceiling


@lru_cache
def get_cert_settings() -> CertSettings:
    return CertSettings()
