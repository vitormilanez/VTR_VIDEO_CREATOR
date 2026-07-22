# Setup - Google Sheets API

Use este modo para a automacao escrever na planilha.

## Planilha alvo

```text
https://docs.google.com/spreadsheets/d/1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ/edit
```

Spreadsheet ID:

```text
1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ
```

Conta operacional:

```text
vtrconsultingbr@gmail.com
```

## Opcao recomendada agora - OAuth Desktop App

Use esta opcao se o Google mostrar:

```text
Service account key creation is disabled
```

Esse e o caso do projeto atual. O script abre uma tela de autorizacao no navegador na primeira execucao e salva um token local.

### Passos no Google Cloud

1. Va em `APIs & Services` > `Library`.
2. Pesquise e ative a `Google Sheets API`.
3. Va em `APIs & Services` > `OAuth consent screen`.
4. Configure o app. Se aparecer a escolha, use `External`.
5. Nome do app: `AI Video Creator`.
6. Email de suporte: `vtrconsultingbr@gmail.com`.
7. Em `Test users`, adicione `vtrconsultingbr@gmail.com`.
8. Va em `APIs & Services` > `Credentials`.
9. Clique em `Create Credentials` > `OAuth client ID`.
10. Em `Application type`, escolha `Desktop app`.
11. Nome: `AI Video Creator Local`.
12. Clique em `Create`.
13. Baixe o JSON do OAuth client.

### Configuracao local com OAuth

Crie um `.env` a partir do `.env.example` ou exporte no terminal:

```bash
export GOOGLE_SHEETS_SPREADSHEET_ID="1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ"
export GOOGLE_OAUTH_CLIENT_SECRETS="/caminho/seguro/client_secret.json"
export GOOGLE_OAUTH_TOKEN_FILE=".google_sheets_token.json"
```

Na primeira execucao, o navegador vai abrir para autorizar acesso ao Google Sheets.

## Opcao alternativa - Service Account

Use apenas se o Google permitir criar chave JSON para service account.

### Passos no Google Cloud

1. Acesse Google Cloud com a conta operacional.
2. Crie um projeto para o AI Video Creator.
3. Ative a `Google Sheets API`.
4. Crie uma `Service Account`.
5. Gere uma chave JSON para essa service account.
6. Baixe o arquivo JSON para um local seguro fora do git.
7. Copie o email da service account.
8. No Google Sheets, compartilhe a planilha com esse email como `Editor`.

### Configuracao local com service account

Crie um `.env` a partir do `.env.example` ou exporte no terminal:

```bash
export GOOGLE_SHEETS_SPREADSHEET_ID="1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ"
export GOOGLE_APPLICATION_CREDENTIALS="/caminho/seguro/service-account.json"
```

## Instalar dependencias

```bash
.venv/bin/python -m pip install -r trend_hunter/requirements.txt
```

## Enviar tendencias para o Google Sheets

Depois de rodar o Trend Hunter:

```bash
.venv/bin/python sync_trends_to_sheets.py --limit 20
```

Com o ambiente OAuth criado neste projeto, use:

```bash
.venv_sheets/bin/python sync_trends_to_sheets.py --limit 20
```

O script usa o CSV mais recente em:

```text
trend_hunter/output/trends_*.csv
```

E adiciona linhas novas na aba:

```text
Radar Tendencias
```

## Campos preenchidos

- `Data`
- `Tema`
- `Subtema`
- `Fonte`
- `Link referencia`
- `Sinal de tendencia`
- `Dor do publico`
- `Potencial Viral`
- `Prioridade`
- `Status`
- `Observacoes`

## Gerar ideias a partir do Radar

```bash
.venv_sheets/bin/python generate_ideas_from_radar.py --limit 10 --include-media
```

O script le `Radar Tendencias`, adiciona ideias na aba `Ideias` e marca as linhas processadas como `Ideia gerada`.

## Segurança

- Nao salvar o JSON da service account dentro do repositorio.
- Nao publicar a chave em prints, WhatsApp ou docs compartilhados.
- Se uma senha ja foi compartilhada em conversa, troque depois do setup.
- A automacao so deve publicar ou gastar creditos depois de status de aprovacao explicito.
