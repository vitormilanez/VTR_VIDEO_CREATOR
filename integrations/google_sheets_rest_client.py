"""Cliente Google Sheets REST sem SDK pesado do Google."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class GoogleSheetsRestClient:
    def __init__(self) -> None:
        load_dotenv()
        self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        self.token_file = Path(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", ".google_sheets_token.json"))
        if not self.spreadsheet_id:
            raise RuntimeError("Defina GOOGLE_SHEETS_SPREADSHEET_ID.")
        if not self.token_file.exists():
            raise RuntimeError("Token OAuth nao encontrado. Rode primeiro o fluxo OAuth do Google Sheets.")

    def _read_token(self) -> dict[str, Any]:
        return json.loads(self.token_file.read_text(encoding="utf-8"))

    def _write_token(self, token: dict[str, Any]) -> None:
        self.token_file.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")

    def _is_expired(self, token: dict[str, Any]) -> bool:
        expiry = token.get("expiry")
        if not expiry:
            return False
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        return expiry_dt <= datetime.now(timezone.utc) + timedelta(minutes=2)

    def _refresh_token(self, token: dict[str, Any]) -> dict[str, Any]:
        refresh_token = token.get("refresh_token")
        client_id = token.get("client_id")
        client_secret = token.get("client_secret")
        token_uri = token.get("token_uri", "https://oauth2.googleapis.com/token")
        if not refresh_token or not client_id or not client_secret:
            raise RuntimeError("Token OAuth sem refresh_token/client_id/client_secret.")

        body = urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        request = Request(
            token_uri,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        payload = self._open_json(request)
        token["token"] = payload["access_token"]
        token["expiry"] = (
            datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 3600)))
        ).isoformat()
        self._write_token(token)
        return token

    def access_token(self) -> str:
        token = self._read_token()
        if self._is_expired(token):
            token = self._refresh_token(token)
        return token["token"]

    def _open_json(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise RuntimeError(f"Google Sheets REST erro {exc.code}: {detail}") from exc

    def get_values(self, range_name: str) -> list[list[str]]:
        encoded_range = quote(range_name, safe="")
        url = f"{SHEETS_API}/{self.spreadsheet_id}/values/{encoded_range}"
        request = Request(url, headers={"Authorization": f"Bearer {self.access_token()}"})
        payload = self._open_json(request)
        return payload.get("values", [])

    def append_rows(self, range_name: str, rows: list[list[object]]) -> dict[str, Any]:
        encoded_range = quote(range_name, safe="")
        query = urlencode({"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"})
        url = f"{SHEETS_API}/{self.spreadsheet_id}/values/{encoded_range}:append?{query}"
        body = json.dumps({"values": rows}, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.access_token()}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        return self._open_json(request)

    def update_values(self, range_name: str, rows: list[list[object]]) -> dict[str, Any]:
        encoded_range = quote(range_name, safe="")
        query = urlencode({"valueInputOption": "USER_ENTERED"})
        url = f"{SHEETS_API}/{self.spreadsheet_id}/values/{encoded_range}?{query}"
        body = json.dumps({"values": rows}, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.access_token()}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="PUT",
        )
        return self._open_json(request)

    def delete_row(self, sheet_title: str, row_number: int) -> dict[str, Any]:
        """Remove uma linha inteira sem deixar um registro vazio na planilha."""
        if row_number < 2:
            raise ValueError("A linha de cabecalho nao pode ser removida.")

        fields = urlencode({"fields": "sheets.properties(sheetId,title)"})
        metadata_request = Request(
            f"{SHEETS_API}/{self.spreadsheet_id}?{fields}",
            headers={"Authorization": f"Bearer {self.access_token()}"},
        )
        metadata = self._open_json(metadata_request)
        sheet_id = next(
            (
                sheet.get("properties", {}).get("sheetId")
                for sheet in metadata.get("sheets", [])
                if sheet.get("properties", {}).get("title") == sheet_title
            ),
            None,
        )
        if sheet_id is None:
            raise RuntimeError(f"Aba '{sheet_title}' nao encontrada no Google Sheets.")

        body = json.dumps(
            {
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": row_number - 1,
                                "endIndex": row_number,
                            }
                        }
                    }
                ]
            },
            ensure_ascii=False,
        ).encode("utf-8")
        delete_request = Request(
            f"{SHEETS_API}/{self.spreadsheet_id}:batchUpdate",
            data=body,
            headers={
                "Authorization": f"Bearer {self.access_token()}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        return self._open_json(delete_request)
