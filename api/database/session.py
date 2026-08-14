from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from api.database.config import DatabaseSettings
from api.database.tenant import TenantContext


@dataclass(frozen=True, slots=True)
class Database:
    engine: Engine
    sessions: sessionmaker[Session]

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.sessions() as session:
            yield session

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self.sessions.begin() as session:
            yield session

    @contextmanager
    def tenant_transaction(self, tenant: TenantContext) -> Iterator[Session]:
        """Abre transação e injeta o contexto consumido pelas policies RLS."""

        with self.sessions.begin() as session:
            session.execute(
                text("SELECT set_config('app.user_id', :user_id, true)"),
                {"user_id": str(tenant.user_id)},
            )
            session.execute(
                text("SELECT set_config('app.organization_id', :organization_id, true)"),
                {"organization_id": str(tenant.organization_id)},
            )
            yield session

    def dispose(self) -> None:
        self.engine.dispose()


def create_database(settings: DatabaseSettings) -> Database:
    connect_args = {
        "application_name": settings.application_name,
        "options": f"-c statement_timeout={settings.statement_timeout_ms}",
    }
    engine = create_engine(
        settings.url,
        pool_pre_ping=True,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
        connect_args=connect_args,
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    return Database(engine=engine, sessions=sessions)
