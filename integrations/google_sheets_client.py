"""Cliente pequeno para Google Sheets API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
GOOGLE_REQUEST_TIMEOUT_SECONDS = 15


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class SheetsConfig:
    spreadsheet_id: str
    credentials_file: str | None = None
    service_account_json: str | None = None
    oauth_client_secrets_file: str | None = None
    oauth_token_file: str = ".google_sheets_token.json"


def load_config() -> SheetsConfig:
    load_dotenv()
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError("Defina GOOGLE_SHEETS_SPREADSHEET_ID no ambiente.")

    return SheetsConfig(
        spreadsheet_id=spreadsheet_id,
        credentials_file=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"),
        oauth_client_secrets_file=os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS"),
        oauth_token_file=os.getenv("GOOGLE_OAUTH_TOKEN_FILE", ".google_sheets_token.json"),
    )


def load_credentials(config: SheetsConfig):
    if config.service_account_json:
        from google.oauth2 import service_account

        info = json.loads(config.service_account_json)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    if config.credentials_file:
        from google.oauth2 import service_account

        path = Path(config.credentials_file).expanduser()
        if not path.exists():
            raise RuntimeError(f"Credencial Google nao encontrada: {path}")
        return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)

    if config.oauth_client_secrets_file:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        class TimeoutRequest(Request):
            def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
                return super().__call__(
                    url,
                    method=method,
                    body=body,
                    headers=headers,
                    timeout=timeout or GOOGLE_REQUEST_TIMEOUT_SECONDS,
                    **kwargs,
                )

        client_secrets_path = Path(config.oauth_client_secrets_file).expanduser()
        if not client_secrets_path.exists():
            raise RuntimeError(f"OAuth client secrets nao encontrado: {client_secrets_path}")

        token_path = Path(config.oauth_token_file).expanduser()
        credentials = None

        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(TimeoutRequest())

        if not credentials or not credentials.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
            credentials = flow.run_local_server(port=0)
            token_path.write_text(credentials.to_json(), encoding="utf-8")

        return credentials

    raise RuntimeError(
        "Defina GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_SERVICE_ACCOUNT_JSON "
        "ou GOOGLE_OAUTH_CLIENT_SECRETS."
    )


class GoogleSheetsClient:
    def __init__(self, config: SheetsConfig | None = None) -> None:
        from googleapiclient.discovery import build

        self.config = config or load_config()
        credentials = load_credentials(self.config)
        self.service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def get_values(self, range_name: str) -> list[list[str]]:
        response = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.config.spreadsheet_id, range=range_name)
            .execute()
        )
        return response.get("values", [])

    def append_rows(self, range_name: str, rows: Sequence[Sequence[object]]) -> dict:
        body = {"values": [list(row) for row in rows]}
        return (
            self.service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.config.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )

    def update_values(self, range_name: str, rows: Sequence[Sequence[object]]) -> dict:
        body = {"values": [list(row) for row in rows]}
        return (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.config.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body=body,
            )
            .execute()
        )
