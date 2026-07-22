# Clientes Google Sheets

O projeto tem dois clientes para Google Sheets porque eles resolvem momentos diferentes do fluxo.

## `GoogleSheetsClient`

Arquivo:

```text
integrations/google_sheets_client.py
```

Usa o SDK oficial do Google:

- `google-api-python-client`
- `google-auth`
- `google-auth-oauthlib`

Use quando:

- precisar fazer o primeiro fluxo OAuth Desktop App;
- quiser usar service account;
- precisar de compatibilidade mais completa com o SDK oficial.

Esse cliente aceita tres formas de credencial:

- `GOOGLE_APPLICATION_CREDENTIALS`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_OAUTH_CLIENT_SECRETS`

## `GoogleSheetsRestClient`

Arquivo:

```text
integrations/google_sheets_rest_client.py
```

Usa chamadas REST diretas com `urllib`, sem depender do SDK oficial em tempo de execucao.

Use quando:

- o token OAuth local `.google_sheets_token.json` ja existir;
- quiser rodar scripts mais leves;
- estiver usando o dashboard local;
- estiver sincronizando tendencias, snapshot ou roteiros no fluxo diario.

Scripts que preferem esse cliente:

- `sync_trends_to_sheets.py`
- `sync_sheets_snapshot.py`
- `generate_scripts_from_ideas.py`
- `dashboard/app.py`

## Decisao pratica

Para setup inicial, use `GoogleSheetsClient`.

Para operacao diaria depois do OAuth configurado, use `GoogleSheetsRestClient`.

Essa separacao evita reabrir o fluxo OAuth sem necessidade e mantem o dashboard mais simples.
