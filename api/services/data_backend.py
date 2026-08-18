from __future__ import annotations

import os
import threading
import uuid
from typing import Any

from sqlalchemy import select

from api.database import Database, DatabaseSettings, OrganizationRole, TenantContext, create_database
from api.database.models import Organization, OrganizationMembership, UserProfile
from api.repositories.content import PostgresContentRepository


DEFAULT_ORGANIZATION_NAMESPACE = "ai-video-creator:organization:dr-guilherme"
DEFAULT_USER_NAMESPACE = "ai-video-creator:user:local-owner"

_LOCK = threading.Lock()
_DATABASE: Database | None = None
_REPOSITORY: PostgresContentRepository | None = None
_TENANT: TenantContext | None = None


def data_backend_name() -> str:
    value = os.getenv("DATA_BACKEND", "sheets").strip().lower()
    if value not in {"sheets", "postgres"}:
        raise RuntimeError("DATA_BACKEND deve ser 'sheets' ou 'postgres'.")
    return value


def postgres_enabled() -> bool:
    return data_backend_name() == "postgres"


def _configured_uuid(key: str, namespace: str) -> uuid.UUID:
    raw = os.getenv(key, "").strip()
    return uuid.UUID(raw) if raw else uuid.uuid5(uuid.NAMESPACE_URL, namespace)


def default_tenant_ids() -> tuple[uuid.UUID, uuid.UUID]:
    return (
        _configured_uuid("DEFAULT_ORGANIZATION_ID", DEFAULT_ORGANIZATION_NAMESPACE),
        _configured_uuid("DEFAULT_USER_ID", DEFAULT_USER_NAMESPACE),
    )


def _bootstrap_default_tenant(database: Database) -> TenantContext:
    organization_id, user_id = default_tenant_ids()
    organization_name = os.getenv("DEFAULT_ORGANIZATION_NAME", "Instituto Vivance").strip()
    organization_slug = os.getenv("DEFAULT_ORGANIZATION_SLUG", "instituto-vivance").strip()
    owner_email = os.getenv("DEFAULT_USER_EMAIL", "owner@local.ai-video-creator").strip()
    owner_name = os.getenv("DEFAULT_USER_NAME", "Administrador local").strip()

    with database.transaction() as session:
        organization = session.get(Organization, organization_id)
        if organization is None:
            organization = Organization(
                id=organization_id,
                slug=organization_slug,
                name=organization_name,
                status="active",
            )
            session.add(organization)
        user = session.get(UserProfile, user_id)
        if user is None:
            user = UserProfile(id=user_id, email=owner_email, display_name=owner_name)
            session.add(user)
        # Sem relacionamentos ORM explícitos, garantimos a ordem das FKs antes
        # de criar a associação entre usuário e organização.
        session.flush()
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
        )
        if membership is None:
            session.add(
                OrganizationMembership(
                    organization_id=organization_id,
                    user_id=user_id,
                    role=OrganizationRole.OWNER.value,
                    status="active",
                )
            )
        else:
            membership.role = OrganizationRole.OWNER.value
            membership.status = "active"
    return TenantContext(
        organization_id=organization_id,
        user_id=user_id,
        role=OrganizationRole.OWNER,
    )


def content_repository() -> PostgresContentRepository:
    global _DATABASE, _REPOSITORY, _TENANT
    if not postgres_enabled():
        raise RuntimeError("O repositório PostgreSQL foi solicitado com DATA_BACKEND diferente de postgres.")
    if _REPOSITORY is not None:
        return _REPOSITORY
    with _LOCK:
        if _REPOSITORY is not None:
            return _REPOSITORY
        settings = DatabaseSettings.from_env(required=True)
        assert settings is not None
        _DATABASE = create_database(settings)
        _TENANT = _bootstrap_default_tenant(_DATABASE)
        _REPOSITORY = PostgresContentRepository(_DATABASE, _TENANT.organization_id)
        return _REPOSITORY


def initialize_data_backend() -> dict[str, Any]:
    if not postgres_enabled():
        return {"ok": True, "backend": "sheets"}
    return content_repository().health()


def data_backend_health() -> dict[str, Any]:
    if not postgres_enabled():
        return {"ok": True, "backend": "sheets", "configured": True}
    try:
        return {**content_repository().health(), "configured": True}
    except Exception as exc:
        return {"ok": False, "backend": "postgres", "configured": True, "error": str(exc)}


def close_data_backend() -> None:
    global _DATABASE, _REPOSITORY, _TENANT
    with _LOCK:
        if _DATABASE is not None:
            _DATABASE.dispose()
        _DATABASE = None
        _REPOSITORY = None
        _TENANT = None


def reset_data_backend_for_tests() -> None:
    close_data_backend()
