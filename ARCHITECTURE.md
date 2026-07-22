# AI Video Creator — Video creator 3

Combina o **frontend do Lovable** (UI bonita) com o **backend Python** que ja
roda localmente. Rodando 100% local por enquanto — sem Supabase, sem deploy.

## Como funciona

```
web/ (React + TanStack Start, Vite)   http://localhost:8080
        │  fetch GET /api/state  (hidrata o store Zustand no carregamento)
        ▼
api/server.py (FastAPI)                http://127.0.0.1:8000
        │  le e normaliza
        ▼
data/sheets_snapshot.json  ◄── sync_sheets_snapshot.py ◄── Google Sheets (fonte de verdade)
```

- `api/server.py` le o snapshot local do Sheets e **converte as colunas PT-BR
  para os tipos que a UI espera** (`Trend`, `Idea`, `Script`, `CalendarPost`,
  `PerformanceMetric`). Endpoint principal: `GET /api/state`.
- No frontend, `web/src/routes/_app.tsx` chama `fetchState()` no mount e
  hidrata o store (`web/src/lib/store.ts` -> acao `hydrate`). Todas as telas
  leem do store, entao passam a mostrar dados reais automaticamente.
- Se a API estiver offline, o frontend cai de volta nos seeds mockados (nao quebra).

## Rodar

```bash
./dev.sh
```

Sobe API (:8000) + frontend (:8080). Abra http://localhost:8080.

> **Node:** o Vite 8 exige Node >= 20.19. O `dev.sh` usa automaticamente o
> `node@22` do Homebrew. Sem ele, `cd web && npm run dev` falha com
> `styleText`/`node:util`.

### Rodar separado

```bash
# API
.venv/bin/python -m uvicorn api.server:app --reload --port 8000

# Frontend (com node@22 no PATH)
cd web && npm run dev
```

## Atualizar dados do Sheets

O snapshot e a fonte que a API serve. Para puxar dados novos da planilha:

```bash
.venv/bin/python sync_sheets_snapshot.py      # regrava data/sheets_snapshot.json
```

Ou pela API (mesmo efeito): `POST http://127.0.0.1:8000/api/refresh`.

## Estado atual (o que ja funciona)

- [x] UI do Lovable rodando local
- [x] API local servindo dados reais das 5 abas (radar, ideias, roteiros, calendario, performance)
- [x] Frontend hidratando o store a partir da API
- [x] Fallback para seeds se a API cair

## Proximos passos sugeridos

- [ ] Endpoints de escrita: aprovar roteiro, mudar status -> gravar de volta no Sheets.
- [ ] Ligar `POST /api/videos` ao `integrations/heygen_client.py` (producao real).
- [ ] Ligar performance ao Instagram/Meta (`integrations/instagram_client.py`).
- [ ] Afinar o mapeamento `familia`/`risco` (heuristica por palavra-chave hoje).
- [ ] Ligar postId de performance aos posts do calendario (hoje sao ids sinteticos).
```
