from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


class ConfigError(ValueError):
    pass


@dataclass(slots=True)
class AppConfig:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    app_master_key: str | None
    workspace_path: Path
    telegram_session_path: Path
    telegram_bot_token: str | None
    telegram_bot_webhook_base_url: str | None
    app_timezone: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def load_config(*, require_master_key: bool = False) -> AppConfig:
    required = [
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "WORKSPACE_PATH",
        "TELEGRAM_SESSION_PATH",
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise ConfigError(f"Missing required settings: {', '.join(missing)}")

    timezone = os.getenv("APP_TIMEZONE", "UTC")
    try:
        ZoneInfo(timezone)
    except Exception as exc:  # pragma: no cover
        raise ConfigError(f"Invalid timezone: {timezone}") from exc

    master_key = os.getenv("APP_MASTER_KEY")
    if require_master_key and not master_key:
        raise ConfigError("APP_MASTER_KEY is required for auth operations")

    workspace_path = Path(os.environ["WORKSPACE_PATH"]).resolve()
    session_path = Path(os.environ["TELEGRAM_SESSION_PATH"]).resolve()

    workspace_path.mkdir(parents=True, exist_ok=True)
    session_path.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        postgres_host=os.environ["POSTGRES_HOST"],
        postgres_port=int(os.environ["POSTGRES_PORT"]),
        postgres_db=os.environ["POSTGRES_DB"],
        postgres_user=os.environ["POSTGRES_USER"],
        postgres_password=os.environ["POSTGRES_PASSWORD"],
        app_master_key=master_key,
        workspace_path=workspace_path,
        telegram_session_path=session_path,
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_bot_webhook_base_url=os.getenv("TELEGRAM_BOT_WEBHOOK_BASE_URL"),
        app_timezone=timezone,
    )
