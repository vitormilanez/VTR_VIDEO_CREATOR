"""Infraestrutura PostgreSQL multi-tenant do AI Video Creator.

Os módulos são importáveis sem abrir conexão. A aplicação atual continua
usando Sheets/SQLite até que o backend PostgreSQL seja ativado explicitamente.
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
