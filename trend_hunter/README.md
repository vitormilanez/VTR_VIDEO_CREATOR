# AI VIDEO CREATOR - Trend Hunter

Ferramenta para encontrar tendencias de conteudo sobre obesidade, emagrecimento, GLP-1, Mounjaro, Ozempic, Wegovy, dieta, metabolismo e saude metabolica.

O objetivo e ajudar o Dr. Guilherme a transformar noticias e buscas recentes em ideias de Reels com gancho, angulo educativo e cuidado de compliance medico.

## Como rodar

Na raiz do projeto:

```bash
cd trend_hunter
python3 -m venv ../.venv
../.venv/bin/python -m pip install -r requirements.txt
../.venv/bin/python trend_hunter.py
```

Os resultados saem em:

```text
trend_hunter/output/trends_AAAA-MM-DD.csv
trend_hunter/output/trends_AAAA-MM-DD.json
```

## Fontes

Por padrao, o script busca em fontes gratuitas e tolerantes a falha:

- Google News RSS: noticias brasileiras recentes.
- GDELT: cobertura global e alto volume de noticias.
- PubMed: estudos cientificos recentes.
- Reddit: duvidas reais do publico.
- Google Trends via SerpAPI: opcional, apenas se houver `SERPAPI_KEY`.

As fontes podem ser ligadas/desligadas na tela `Configuracoes > Radar de tendencias`.
Tambem e possivel rodar manualmente:

```bash
../.venv/bin/python trend_hunter.py \
  --query "GLP-1" \
  --source google_news \
  --source gdelt \
  --source pubmed \
  --source reddit
```

Opcionalmente, se houver uma chave `SERPAPI_KEY`, ele tambem tenta buscar dados de Google Trends via SerpAPI:

```bash
export SERPAPI_KEY="sua_chave"
../.venv/bin/python trend_hunter.py
```

## Google Sheets

A planilha operacional do projeto fica em:

```text
https://docs.google.com/spreadsheets/d/1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ/edit
```

Spreadsheet ID:

```text
1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ
```

Para integracao automatica, copie `.env.example` para `.env` e configure uma credencial da Google Sheets API. Nao salve chaves reais no git.

Para enviar tendencias do CSV mais recente para a aba `Radar Tendencias`:

```bash
../.venv/bin/python ../sync_trends_to_sheets.py --limit 20
```

## Campos gerados

- `periodo`: dia, semana, quinzena ou mes.
- `fonte`: origem do sinal, como Google News RSS, GDELT, PubMed, Reddit ou SerpAPI Google Trends.
- `tipo`: noticia, noticia global, estudo cientifico, duvida do publico ou busca em alta.
- `trend`: titulo ou termo encontrado.
- `score`: pontuacao de relevancia editorial.
- `termos_encontrados`: termos de interesse encontrados no texto.
- `angulo_de_conteudo`: sugestao de abordagem para Reel.
- `cuidado_medico_compliance`: lembretes para evitar risco medico/publicitario.
- `link_da_fonte`: URL de referencia.
- `publicado_em`: data da noticia quando disponivel.

## Fluxo editorial

1. Rodar o Trend Hunter.
2. Abrir o CSV/JSON em `trend_hunter/output`.
3. Escolher tendencias com bom score.
4. Transformar em ideias de Reels.
5. Criar hook, conflito, explicacao simples, virada e CTA.
6. Validar a parte medica com Dr. Guilherme antes de publicar.

## Cuidados

- Nao prescrever medicamentos.
- Nao citar doses.
- Nao prometer resultado.
- Nao fazer sensacionalismo medico.
- Nao usar IA como fonte medica final.
- Validar informacao medica antes de gravar/publicar.
