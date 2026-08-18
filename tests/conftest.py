from __future__ import annotations

import os


# A suíte legada usa snapshots temporários e clientes Sheets falsos. Os testes
# PostgreSQL instanciam o repositório diretamente com um banco efêmero.
os.environ["DATA_BACKEND"] = "sheets"
