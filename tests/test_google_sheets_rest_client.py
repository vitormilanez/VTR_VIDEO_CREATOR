from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from integrations.google_sheets_rest_client import GoogleSheetsRestClient


class GoogleSheetsRestClientTests(unittest.TestCase):
    def test_delete_row_uses_zero_based_delete_dimension_range(self) -> None:
        client = GoogleSheetsRestClient.__new__(GoogleSheetsRestClient)
        client.spreadsheet_id = "sheet-test"

        with (
            patch.object(client, "access_token", return_value="token"),
            patch.object(
                client,
                "_open_json",
                side_effect=[
                    {
                        "sheets": [
                            {"properties": {"sheetId": 42, "title": "Roteiros"}}
                        ]
                    },
                    {"replies": [{}]},
                ],
            ) as open_json,
        ):
            response = client.delete_row("Roteiros", 3)

        request = open_json.call_args_list[1].args[0]
        body = json.loads(request.data.decode("utf-8"))
        dimension = body["requests"][0]["deleteDimension"]["range"]
        self.assertEqual(
            dimension,
            {
                "sheetId": 42,
                "dimension": "ROWS",
                "startIndex": 2,
                "endIndex": 3,
            },
        )
        self.assertEqual(response, {"replies": [{}]})

    def test_delete_row_refuses_header(self) -> None:
        client = GoogleSheetsRestClient.__new__(GoogleSheetsRestClient)
        with self.assertRaises(ValueError):
            client.delete_row("Roteiros", 1)


if __name__ == "__main__":
    unittest.main()
