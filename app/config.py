from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-only secrets and process settings.

    The broker endpoint is intentionally not configurable. The adapter always constructs an
    Alpaca client with ``paper=True`` so a typo cannot silently enable live trading.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    dashboard_password: SecretStr = SecretStr("replace-with-a-long-password")
    session_secret: SecretStr = SecretStr("replace-with-at-least-32-random-characters")
    discord_webhook_url: SecretStr | None = None
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: Path = Path("data/trading_bot.db")

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return value

    @property
    def credentials_configured(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def secure_configuration(self) -> bool:
        password = self.dashboard_password.get_secret_value()
        secret = self.session_secret.get_secret_value()
        return (
            password != "replace-with-a-long-password"
            and len(password) >= 12
            and secret != "replace-with-at-least-32-random-characters"
            and len(secret) >= 32
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
