# Dashboard local

Dashboard local para operar o AI Video Creator no Mac.

## O que mostra

- Pipeline de tendencias, ideias, roteiros e calendario.
- Aba `Tendências` para rodar nova busca e adicionar à planilha sem sobrescrever.
- Status dos roteiros e aprovacoes.
- Saldo e conta HeyGen.
- Avatares disponiveis na HeyGen.
- Performance manual a partir da aba `Performance`.
- Area preparada para Instagram Graph API.

## Rodar

```bash
.venv_sheets/bin/python dashboard/app.py
```

Abrir:

```text
http://127.0.0.1:8501
```

## Modos de dados

Por padrao, o dashboard roda em modo local rapido:

- le `data/sheets_snapshot.json` quando existir;
- se nao existir snapshot, le o CSV mais recente em `trend_hunter/output`;
- mostra resumo do pipeline sem depender da API do Google Sheets;
- mostra HeyGen com os dados ja validados no setup;
- usa a aba Performance somente quando estivermos em modo live.

Para atualizar o snapshot com dados reais da planilha:

```bash
.venv_sheets/bin/python sync_sheets_snapshot.py
```

## Buscar mais tendências pelo dashboard

Na aba `Tendências`, clique em:

```text
Buscar e adicionar à planilha
```

O dashboard roda:

1. `trend_hunter/trend_hunter.py`
2. `sync_trends_to_sheets.py --limit 20`
3. `sync_sheets_snapshot.py`

O sync usa append e deduplicacao por `Link referencia + Sinal de tendencia`, entao nao sobrescreve linhas existentes.

Para tentar dados ao vivo do Google Sheets:

```bash
DASHBOARD_LIVE_SHEETS=1 .venv_sheets/bin/python dashboard/app.py
```

Para tentar dados ao vivo da HeyGen:

```bash
DASHBOARD_LIVE_HEYGEN=1 .venv_sheets/bin/python dashboard/app.py
```

Use live quando precisar conferir dados em tempo real. Use local para operacao rapida e estavel.

## Instagram

Para metricas reais do Instagram, a conta precisa ser profissional e conectada a uma Pagina do Facebook. Depois sera necessario configurar:

```bash
META_ACCESS_TOKEN=
INSTAGRAM_BUSINESS_ACCOUNT_ID=
```

Enquanto isso, o dashboard usa a aba `Performance` da planilha para views, comentarios, salvamentos, compartilhamentos e leads.

## Regra de seguranca

O dashboard pode mostrar dados e apoiar aprovacoes, mas a geracao de video deve continuar travada por status:

```text
Aprovado para video
```

Nada deve gastar creditos da HeyGen sem aprovacao explicita.
