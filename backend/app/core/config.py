from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # Control Plane metadata database — never customer databases (cf. Règle 19).
    database_url: str = "sqlite+aiosqlite:///./control_plane_dev.db"

    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Fernet key encrypting database credentials at rest (cf. Règle 15 — no plaintext
    # secrets). Dev-only default below; override in any real deployment, exactly like
    # jwt_secret_key. A real deployment should back this with a KMS-managed key.
    secret_encryption_key: str = "08u_J80OTnrWkefxT-D4WVGWAnX-CJynJWy-T-SCvXQ="

    # Resend (transactional email) — cf. app/services/email_service.py. "console"
    # prints instead of calling out, so dev/tests never need a real API key.
    email_backend: str = "console"  # "console" | "resend"
    email_from: str = "no-reply@eminidatabase.dev"
    resend_api_key: str = ""

    # NOWPayments (crypto payments) — cf. app/services/payment_providers/nowpayments.py.
    nowpayments_api_key: str = ""
    nowpayments_ipn_secret: str = ""
    nowpayments_sandbox: bool = True
    # This API's own publicly reachable base URL, so NOWPayments knows where to POST
    # the IPN callback (self-referential — this isn't NOWPayments' URL).
    nowpayments_public_api_url: str = "http://localhost:8000"
    nowpayments_default_pay_currency: str = "usdtbsc"
    nowpayments_payment_window_hours: float = 3.0
    # Crypto network fees can shave a fraction of a cent off what actually
    # arrives — a "partially_paid" status within this tolerance still counts
    # as settled, rather than leaving the invoice stuck unpaid over dust.
    nowpayments_tolerance_usd: float = 0.50

    # FedaPay (mobile money, West Africa) — cf.
    # app/services/payment_providers/fedapay.py docstring for why this is raw REST
    # via httpx rather than a package: FedaPay has no official Python SDK, and the
    # direct (non-redirect) mobile-money "collect" endpoints aren't wrapped by any
    # of its official SDKs (PHP/Node/Ruby) either — they're called the same way
    # here as everywhere else in this codebase (webhook delivery, NOWPayments).
    fedapay_environment: str = "sandbox"  # "sandbox" | "live"
    fedapay_secret_key: str = ""
    fedapay_webhook_secret: str = ""

    # OAuth sign-up/sign-in (Google, GitHub) — cf. app/services/oauth_service.py.
    # This API's own publicly reachable base URL, so the provider knows where to
    # redirect back with the authorization code (self-referential, same pattern
    # as nowpayments_public_api_url).
    oauth_redirect_base_url: str = "http://localhost:8000"
    # Where the OAuth callback hands the session off to once it succeeds/fails —
    # the frontend's own origin, not this API's (cf. frontend/app/auth/callback).
    frontend_oauth_redirect_url: str = "http://localhost:3000"
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
