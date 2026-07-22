# APIs e Integracoes

## Arquitetura recomendada

O frontend deve falar com funcoes de backend/Edge Functions. O frontend nunca deve chamar diretamente HeyGen, Meta Graph API ou Google APIs com chaves secretas.

## Endpoints internos sugeridos

### `POST /api/trends/search`

Busca tendencias e salva em `trends`.

Entrada:

```json
{
  "queries": ["GLP-1 obesidade emagrecimento"],
  "period": "7d",
  "limit": 20
}
```

Saida:

```json
{
  "created": 12,
  "skipped": 4
}
```

### `POST /api/ideas/generate`

Gera ideias a partir de tendencias selecionadas.

Entrada:

```json
{
  "trend_ids": ["uuid"],
  "limit": 10
}
```

### `POST /api/scripts/generate`

Gera roteiros a partir de ideias selecionadas.

Entrada:

```json
{
  "idea_ids": ["uuid"]
}
```

### `POST /api/videos/create`

Cria um job HeyGen a partir de um roteiro.

Entrada:

```json
{
  "script_id": "uuid",
  "avatar_id": "heygen_avatar_id",
  "voice_id": "heygen_voice_id",
  "caption": true
}
```

Importante: esse endpoint deve exigir clique explicito do usuario e registrar o job em `video_jobs`.

### `POST /api/videos/refresh`

Consulta status do HeyGen e atualiza `video_jobs`.

Entrada:

```json
{
  "video_job_id": "uuid"
}
```

## Google Sheets

No MVP Lovable, Supabase deve ser a fonte principal. Google Sheets pode ser opcional para importacao/exportacao.

Opcoes:

- importar CSV manual para popular tabelas;
- exportar tabelas para CSV;
- usar Google Sheets API via backend para sincronizacao.

Mapeamento das abas atuais:

- `Radar Tendencias` -> `trends`
- `Ideias` -> `ideas`
- `Roteiros` -> `scripts`
- `Calendario` -> `calendar_posts`
- `Performance` -> `performance_metrics`

## HeyGen

Referencia atual:

- `../integrations/heygen_client.py`
- `../heygen_create_video.py`
- `../heygen_get_video.py`

Endpoints HeyGen usados no projeto atual:

- `GET /v3/users/me`
- `GET /v3/avatars`
- `GET /v3/avatars/looks`
- `POST /v3/videos`
- `GET /v3/videos/{video_id}`

Variaveis:

```text
HEYGEN_API_KEY
HEYGEN_DEFAULT_AVATAR_ID
HEYGEN_DEFAULT_VOICE_ID
```

## Instagram / Meta

Referencia atual:

- `../integrations/instagram_client.py`

Campos necessarios:

```text
META_ACCESS_TOKEN
INSTAGRAM_BUSINESS_ACCOUNT_ID
```

Uso inicial:

- puxar perfil;
- listar midias recentes;
- registrar metricas basicas.

## Busca de tendencias

Referencia atual:

- `../trend_hunter/trend_hunter.py`

Fontes:

- Google News RSS;
- SerpAPI Google Trends opcional.

Variavel opcional:

```text
SERPAPI_KEY
```

## Segredos

Guardar como secrets/variaveis de ambiente do backend:

```text
HEYGEN_API_KEY
META_ACCESS_TOKEN
INSTAGRAM_BUSINESS_ACCOUNT_ID
SERPAPI_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REFRESH_TOKEN
```
