from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from api.routers import dialogs as dialogs_router
from api.routers import messages as messages_router
from api.routers import n8n_bridge as n8n_bridge_router
from api.routers import ocr as ocr_router
from api.routers import post_message as post_message_router
from api.routers import telegram_bot_commands as telegram_bot_commands_router
from api.routers import telegram_trigger as telegram_trigger_router
from api.routers import ai_text as ai_text_router
from api.telegram_bot_command_runtime import telegram_bot_command_runtime
from api.telegram_trigger_runtime import telegram_trigger_runtime


logger = logging.getLogger(__name__)


health_router = APIRouter()


@health_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run migrations on startup
    from services.shared.db.migrations.apply import apply_migrations
    apply_migrations()

    try:
        telegram_trigger_runtime.load_from_db()
        telegram_trigger_runtime.start()
    except Exception:
        logger.exception("Telegram trigger runtime startup failed")

    try:
        telegram_bot_command_runtime.load_from_db()
        telegram_bot_command_runtime.refresh_webhooks()
    except Exception:
        logger.exception("Telegram bot command runtime startup failed")

    yield

    telegram_trigger_runtime.stop()
    telegram_bot_command_runtime.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="TG-Dog API", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(dialogs_router.router)
    app.include_router(messages_router.router)
    app.include_router(ai_text_router.router)
    app.include_router(n8n_bridge_router.router)
    app.include_router(ocr_router.router)
    app.include_router(post_message_router.router)
    app.include_router(telegram_trigger_router.router)
    app.include_router(telegram_bot_commands_router.router)
    return app


app = create_app()
