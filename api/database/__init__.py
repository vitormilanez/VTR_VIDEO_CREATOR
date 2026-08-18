"""Infraestrutura PostgreSQL multi-tenant do AI Video Creator.

Os módulos são importáveis sem abrir conexão. Com ``DATA_BACKEND=postgres``,
o PostgreSQL é a fonte principal dos domínios de conteúdo migrados.
"""

from api.database.config import DatabaseSettings
from api.database.session import Database, create_database
from api.database.tenant import OrganizationRole, TenantContext

__all__ = [
    "Database",
    "DatabaseSettings",
    "OrganizationRole",
    "TenantContext",
    "create_database",
]
