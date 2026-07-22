# AI Video Creator — MVP frontend com mocks

App interno em portugues-BR para gerenciar a esteira de conteudo do Dr. Guilherme: tendencias → ideias → roteiros → producao → calendario → performance. Nesta fase, sem backend, sem auth, sem chamadas de IA reais. Toda "geracao" retorna dados pre-definidos localmente, sempre acionada por clique explicito.

## Estilo e design system

- Interface de operacao (dashboard denso), nao landing page. Sem hero, sem gradientes.
- Tokens em `src/styles.css` (oklch): fundo neutro claro, texto grafite, acentos semanticos:
  - `--status-info` (azul), `--status-success` (verde), `--status-warn` (amarelo), `--status-danger` (vermelho).
  - Mapeados como `bg-status-info`, `text-status-warn`, etc. via `@theme inline`.
- Tipografia: Inter (ja disponivel via Tailwind default) — carregada no `<link>` do `__root.tsx`.
- Componentes shadcn ja instalados: Table, Badge, Button, Dialog, Tabs, Select, Input, Card, Sheet, Tooltip, DropdownMenu.

## Arquitetura de rotas (TanStack Start)

Layout com sidebar fixa em `src/routes/_app.tsx` (pathless, renderiza `<Outlet />` dentro do shell). Rotas filhas:

```
src/routes/
  __root.tsx              (existe — atualizar head + fonte)
  _app.tsx                (sidebar + topbar + Outlet)
  _app.index.tsx          (/ — Dashboard)
  _app.radar.tsx          (/radar)
  _app.ideias.tsx         (/ideias)
  _app.roteiros.tsx       (/roteiros)
  _app.roteiros.$id.tsx   (/roteiros/:id — detalhe/edicao)
  _app.producao.tsx       (/producao)
  _app.calendario.tsx     (/calendario)
  _app.performance.tsx    (/performance)
  _app.configuracoes.tsx  (/configuracoes)
```

O `index.tsx` placeholder atual sera substituido por Dashboard em `_app.index.tsx` (movendo/reescrevendo). Cada rota define `head()` proprio com title/description/og em PT-BR.

## Camada de dados (mock)

`src/lib/mock-data.ts` exporta os tipos e seeds coerentes com o modelo do prompt:

- `Trend` — 1 seed sobre Mounjaro (fonte, volume, tema, risco).
- `Idea` — 1 seed educativa/provocativa vinculada a tendencia, com hook, angulo, CTA, obs. compliance, familia do tema.
- `Script` — 1 seed com todos os campos (categoria, tema, titulo, hook, dor, explicacao, virada, CTA, cuidados medicos, risco, formato) e status `Aguardando validacao medica`.
- `VideoJob` — vazio (produto so gera com clique).
- `CalendarPost` — 1 seed pendente.
- `PerformanceMetric` — array vazio / zerados.
- `AppSettings` — objeto default (temas prioritarios, palavras proibidas, integracoes desligadas).

Estado global: `src/lib/store.ts` usando **Zustand** com persist em `localStorage` (chave `avc-store`). Todas as telas leem/escrevem via hooks selectors. Nao ha Supabase nesta fase.

Enums de status compartilhados: `Novo`, `Em analise`, `Aprovado`, `Aguardando validacao medica`, `Aprovado clinicamente`, `Rejeitado`, `Publicado`, `Pendente`. Badge com cor semantica.

## Telas — comportamento resumido

- **Dashboard** (`/`): 4 cards de metrica (tendencias novas, ideias, roteiros aguardando validacao, posts pendentes), tabela "Proximas acoes" e lista dos ultimos 5 itens por status critico.
- **Radar** (`/radar`): tabela filtravel (tema, risco, fonte), botao "Nova tendencia" (modal), botao por linha "Gerar ideia" → cria `Idea` mock a partir da tendencia e navega para `/ideias`.
- **Ideias** (`/ideias`): tabela, filtros por familia e status, acao "Gerar roteiro" (mock) e "Descartar".
- **Roteiros** (`/roteiros`): tabela + rota de detalhe (`/roteiros/:id`) com formulario dos campos do roteiro, controle de status de validacao medica e botao "Enviar para producao" (habilitado so quando `Aprovado clinicamente`).
- **Producao** (`/producao`): fila de `VideoJob`, botao "Criar video no HeyGen" desabilitado com tooltip "Integracao nao configurada" (stub arquitetural).
- **Calendario** (`/calendario`): visao mensal simples (grid), lista lateral de posts pendentes, drag opcional adiado — por ora clique abre modal para reagendar.
- **Performance** (`/performance`): tabela por post com metricas zeradas + estado vazio explicando que exige integracao Meta.
- **Configuracoes** (`/configuracoes`): formulario para `AppSettings` (temas, palavras proibidas, toggles de integracao read-only marcados como "Nao conectado"). Persiste no store.

## Regras criticas na UI

- Nenhum botao dispara acao automatica: todos os "Gerar X" exigem clique e mostram confirmacao quando criam registros.
- Banner fixo no topo do shell com aviso de compliance ("Conteudo educativo, nao prescritivo. Sem doses, sem promessas.").
- Componente `<ComplianceHints />` renderizado nos formularios de ideia/roteiro listando as regras do `compliance-rules.md` (versao inline: nao prescrever, nao citar dose, nao prometer, sem sensacionalismo, reforcar avaliacao individual).
- Status `Aguardando validacao medica` bloqueia acoes de producao e agendamento.

## Preparacao para fase 2 (nao implementar agora)

- `src/lib/api/` com arquivos vazios `trends.ts`, `heygen.ts`, `meta.ts`, `sheets.ts` exportando funcoes stub que lancam `Error("nao implementado")` — deixa claro onde a integracao entra.
- Comentarios `// TODO(cloud):` nos pontos onde o store seria trocado por server functions + Supabase.

## Entregaveis desta iteracao

1. Novos arquivos de rota + `_app.tsx` shell (sidebar com icones lucide).
2. `src/lib/mock-data.ts`, `src/lib/store.ts`, `src/lib/status.ts` (helpers de badge).
3. Componentes: `AppShell`, `SidebarNav`, `TopBar`, `StatusBadge`, `ComplianceBanner`, `ComplianceHints`, `MetricCard`, `DataTable` (wrapper simples sobre shadcn Table).
4. Atualizacao do `__root.tsx` head (titulo "AI Video Creator", descricao PT-BR, sem "Lovable App").
5. Tokens semanticos de status em `src/styles.css`.
6. Sem instalacao pesada: apenas `bun add zustand` e `date-fns` para o calendario.

## Fora do escopo

- Lovable Cloud / Supabase / auth.
- Chamadas reais a Gemini/HeyGen/Meta/Sheets.
- Drag-and-drop no calendario, exportacao CSV, upload de video.
