# AI Video Creator

Este projeto organiza uma esteira local para transformar tendencias sobre obesidade, emagrecimento, GLP-1, Mounjaro, Ozempic, dieta, metabolismo e saude metabolica em ideias, roteiros e videos curtos com revisao humana.

O foco atual e o conteudo do Dr. Guilherme. A automacao acelera pesquisa e producao editorial, mas nao substitui validacao medica.

## Fluxo principal

1. `trend_hunter/trend_hunter.py` busca tendencias no Google News RSS e, opcionalmente, no Google Trends via SerpAPI.
2. `sync_trends_to_sheets.py` envia as melhores tendencias para a aba `Radar Tendencias`.
3. `generate_ideas_from_radar.py` transforma tendencias pendentes em ideias na aba `Ideias`.
4. `generate_scripts_from_ideas.py` transforma ideias em roteiros na aba `Roteiros`.
5. O Dr. Guilherme ou o time revisa os roteiros antes de qualquer producao de video.
6. O dashboard local em `dashboard/app.py` acompanha pipeline, snapshot da planilha, roteiros, producao HeyGen e performance.

## Regras de seguranca editorial

- Nao prescrever medicamentos.
- Nao citar doses.
- Nao prometer resultado.
- Nao fazer sensacionalismo medico.
- Validar informacao medica antes de gravar ou publicar.
- Tratar obesidade como condicao multifatorial, com linguagem acolhedora.

## Setup

Crie um ambiente virtual e instale as dependencias:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r trend_hunter/requirements.txt
```

Copie o arquivo de exemplo de ambiente:

```bash
cp .env.example .env
```

Configure no `.env` as chaves necessarias para o fluxo que pretende usar. Para Google Sheets, veja `docs/setup-google-sheets-api.md`.

## Comandos de operacao

Buscar tendencias:

```bash
.venv/bin/python trend_hunter/trend_hunter.py
```

Enviar tendencias para a aba `Radar Tendencias`:

```bash
.venv/bin/python sync_trends_to_sheets.py --limit 20
```

Gerar ideias a partir do radar:

```bash
.venv/bin/python generate_ideas_from_radar.py --limit 10 --include-media
```

Gerar roteiros a partir das ideias:

```bash
.venv/bin/python generate_scripts_from_ideas.py --limit 10
```

Atualizar snapshot local do dashboard:

```bash
.venv/bin/python sync_sheets_snapshot.py
```

Rodar dashboard local:

```bash
.venv/bin/python dashboard/app.py
```

Abra:

```text
http://127.0.0.1:8501
```

## Google Sheets

A planilha e a fonte operacional do projeto. As abas principais sao:

- `Radar Tendencias`: entrada de sinais, tendencias e dores do publico.
- `Ideias`: hooks, angulos e CTAs gerados a partir do radar.
- `Roteiros`: roteiro estruturado para validacao medica e posterior video.
- `Calendario`: agendamento, reagendamento e publicacao persistidos na planilha.
- `Performance`: resultados manuais ou importados depois da publicacao.

Conta dona da planilha: `vtrconsultingbr@gmail.com`.

Antes de criar qualquer job pago no HeyGen, o backend valida o texto falado final.
Falas com doses, promessas proibidas ou instrucoes prescritivas sao bloqueadas,
independentemente do status atual do roteiro.

Jobs de video, avatar e cortes ficam em `data/operations.db` (SQLite em modo WAL). Na
primeira abertura, os arquivos legados `data/video_jobs.json` e
`data/avatar_jobs.json` sao importados automaticamente. Envios de video e
projetos de cortes usam chaves idempotentes persistentes: repetir a mesma
requisicao retorna o job ja registrado, sem iniciar outro processamento.

## Cortes inteligentes

A rota `/cortes` aceita um video local de ate 2 GB, um video pronto do HeyGen
ou um link publico do YouTube. Links do YouTube sao baixados localmente com
`yt-dlp`, sem playlists e com limite de 2 horas.
O processamento transcreve a fala, escolhe os melhores trechos com IA, cria
versoes verticais com fundo desfocado ou preenchimento, adiciona legendas e
entrega ranking, legenda editorial e download de cada MP4. Os projetos ficam no
SQLite e os arquivos gerados em `data/cuts/`.

Em `Duracao automatica`, cada corte termina em uma fronteira natural da fala.
Sem credenciais da Anthropic, o ranking local considera abertura, ideia
completa, fechamento, densidade de informacao e diversidade entre os trechos.

A transcricao usa o Python configurado em `CUTS_PYTHON`. Na instalacao local
atual, o projeto tambem detecta automaticamente o ambiente
`../Video Creator/.venv_caption/bin/python`.

Se aparecer a tela "You need access" no Google Sheets, peça acesso para essa conta. A conta pessoal `vitor.milanezz@gmail.com` pode nao ter permissao direta no navegador, mesmo quando o app local consegue acessar via token OAuth.

Existem dois clientes de Google Sheets em `integrations/`:

- `GoogleSheetsClient`: usa o SDK oficial do Google. E o caminho mais completo para service account e primeiro fluxo OAuth.
- `GoogleSheetsRestClient`: usa chamadas REST leves com token OAuth local. E o caminho preferido para scripts operacionais e dashboard depois que o token ja existe.

Mais detalhes em `docs/google-sheets-clients.md`.

## Avatares e voz

A rota `/avatares` consulta as identidades privadas da conta HeyGen conectada. Ela permite criar avatar por foto, digital twin por video ou apresentador por descricao, com clonagem opcional de voz.

Fotos, videos e audios nao sao gravados no Google Sheets nem no snapshot. Eles sao enviados ao HeyGen somente depois do clique confirmado em `Criar avatar`. O backend salva localmente apenas identificadores, status e URL de consentimento em `data/operations.db`.

O titular precisa confirmar a autorizacao na interface e concluir o consentimento oficial do HeyGen antes do avatar ser usado em producao.

## Publicacao no Instagram

O app publica videos prontos diretamente como Reel ou Story pela API oficial da Meta. As
credenciais ficam somente no backend. Configure `META_ACCESS_TOKEN` e
`INSTAGRAM_BUSINESS_ACCOUNT_ID` no `.env`, reinicie a API e use **Configuracoes > Testar
conexao**. Depois, abra um video com status `pronto` e clique em **Publicar no Instagram**.

A Meta precisa conseguir baixar o arquivo por uma URL HTTPS publica; URLs locais nao funcionam.
Stories via API exigem conta Business e nao incluem legenda ou stickers interativos. Veja o passo
a passo em `docs/setup-instagram-meta.md`.

## Arquivos locais ignorados

O `.gitignore` mantem fora do git credenciais, tokens OAuth, `.env`, ambientes virtuais, snapshots, logs, videos gerados e fotos pessoais usadas como referencia de avatar.

Arquivos como `trend_hunter/output/`, `edited_videos/` e `production_videos/` sao saidas operacionais locais.

## Exportar para Lovable

A pasta `lovable-spec/` contem um briefing para reconstruir este projeto como web app no Lovable, incluindo prompt principal, telas, modelo de dados Supabase, integracoes e regras de compliance.
