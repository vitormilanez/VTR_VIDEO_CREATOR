# Setup rapido - Google Sheets publico somente leitura

Use este modo para testar a automacao sem Google Cloud, OAuth ou service account.

## Planilha

URL:

```text
https://docs.google.com/spreadsheets/d/1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ/edit
```

Conta operacional:

```text
vtrconsultingbr@gmail.com
```

## Como liberar leitura publica

1. Abra a planilha no Google Sheets.
2. Clique em `Compartilhar`.
3. Em `Acesso geral`, escolha `Qualquer pessoa com o link`.
4. Selecione permissao `Leitor`.
5. Copie o link e confirme que o ID continua:

```text
1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ
```

## Como testar

Na raiz do projeto:

```bash
.venv/bin/python sheets_public_reader.py --gid 1596729829 --output output/google_sheet_export.csv
```

Se funcionar, o script vai gerar:

```text
output/google_sheet_export.csv
```

## Limite deste modo

Este modo le a planilha, mas nao escreve de volta.

Para preencher automaticamente as abas `Ideias`, `Roteiros` e `Calendario`, sera necessario configurar Google Sheets API com service account ou OAuth.

## Seguranca

Nao coloque senhas, chaves de API, dados de pacientes, leads ou informacoes sensiveis na planilha enquanto ela estiver publica.
