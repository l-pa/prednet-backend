import logging
from pathlib import Path

import sentry_sdk
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy import inspect
from sqlmodel import Session, select
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings
from app.core.db import engine, init_db
from app.models import SQLModel


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


logger = logging.getLogger(__name__)


def _verify_database_initialized() -> None:
    with Session(engine) as session:
        # Ensure DB is reachable
        session.exec(select(1))

        # Ensure required tables exist (migrations applied)
        inspector = inspect(engine)
        required_tables = ["alembic_version", "user", "item"]
        missing = [t for t in required_tables if not inspector.has_table(t)]
        if missing:
            logger.warning(
                "Missing tables detected (%s). Attempting to run Alembic migrations...",
                ", ".join(missing),
            )
            _run_migrations()
            inspector = inspect(engine)
            missing_after = [t for t in required_tables if not inspector.has_table(t)]
            if missing_after:
                logger.warning(
                    "Tables still missing after migrations (%s). Creating metadata...",
                    ", ".join(missing_after),
                )
                SQLModel.metadata.create_all(engine)

        # Ensure initial data (e.g., first superuser)
        init_db(session)


@app.on_event("startup")
def _on_startup() -> None:
    try:
        _verify_database_initialized()
        logger.info("Database initialization check passed")
    except Exception:
        logger.exception("Database initialization check failed")
        # Re-raise to fail fast instead of running a broken API
        raise


def _run_migrations() -> None:
    # Resolve absolute paths for Alembic
    # alembic.ini lives in the parent of this directory (backend/alembic.ini)
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    # migration scripts directory (backend/app/alembic)
    script_location = Path(__file__).resolve().parent / "alembic"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(script_location))
    cfg.set_main_option("sqlalchemy.url", str(settings.SQLALCHEMY_DATABASE_URI))
    command.upgrade(cfg, "head")
