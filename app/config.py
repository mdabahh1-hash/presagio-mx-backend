from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/veredikt"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def fix_db_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v
    SECRET_KEY: str = "change-me-in-production-at-least-32-characters-long"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_not_default(cls, v: str) -> str:
        # Fail hard at boot if running with the known-default / weak key — a
        # forgeable key means anyone can mint tokens. Prod has a strong key set,
        # so this guard just prevents ever silently shipping a weak one again.
        if v == "change-me-in-production-at-least-32-characters-long" or len(v) < 32:
            raise ValueError(
                "SECRET_KEY is the default placeholder or too short (<32 chars). "
                "Set a strong SECRET_KEY env var — tokens are forgeable otherwise."
            )
        return v

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:5175"
    BACKEND_URL: str = "http://localhost:8000"

    @field_validator("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "FRONTEND_URL", "BACKEND_URL", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    NEW_USER_POINTS: int = 1000

    # Quote → execution price protection
    PRICE_TOLERANCE: float = 0.01     # max relative deviation of avg fill vs quoted before 409 PRICE_MOVED
    QUOTE_TTL_SECONDS: int = 10       # quote_expires_at horizon

    # Referral bonus (PT) granted to BOTH inviter and invitee after the
    # invitee's first trade.
    REFERRAL_BONUS: int = 200

    GMAIL_USER: str = ""
    GMAIL_APP_PASSWORD: str = ""

    RESEND_API_KEY: str = ""


settings = Settings()
