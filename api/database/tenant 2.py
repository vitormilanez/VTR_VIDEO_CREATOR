from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


WRITE_ROLES = frozenset(
    {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.EDITOR,
    }
)


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: OrganizationRole

    def require_any(self, *roles: OrganizationRole) -> None:
        if self.role not in roles:
            allowed = ", ".join(role.value for role in roles)
            raise PermissionError(
                f"O papel '{self.role.value}' não possui esta permissão; esperado: {allowed}."
            )

    def require_write(self) -> None:
        if self.role not in WRITE_ROLES:
            raise PermissionError(f"O papel '{self.role.value}' possui acesso somente de revisão/leitura.")
