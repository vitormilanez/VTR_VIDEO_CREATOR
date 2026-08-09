# Editor de roteiros — Fase 2

Data de início: 9 de agosto de 2026.

## Baseline

- Status: `completed`
- Branch: `codex/intelligent-video-workflows`
- Checkpoint anterior: `ce638ec` (`fix(local-video-kit): handle music loading and optional topic card`)
- `python -m pytest -q`: 199 testes passaram; 4 avisos conhecidos de depreciação do FastAPI.
- `npm run test`: 13 testes Vitest passaram.
- `npx tsc --noEmit`: passou.
- ESLint dos arquivos do editor: passou.
- `npm run build`: passou.
- Risco conhecido: a migração de `on_event` para lifespan pertence ao Slice 15D e não será misturada aos quatro slices atuais.

## Slice 14A

- Status: `completed`
- Diagnóstico: a rota do roteiro possui 4.608 linhas, oito `effects` no componente principal e integra editor, persistência, IA e produção. Os testes anteriores cobriam o motor determinístico, mas não montavam a experiência React. Uma resposta de IA iniciada na revisão A podia substituir silenciosamente uma edição manual B.
- Implementação:
  - ambiente Vitest isolado do plugin de rotas, com jsdom, React Testing Library, user-event e axe-core;
  - revisão monotônica da fala e request id impedem aplicação de respostas antigas ou após desmontagem;
  - resultado antigo fica disponível apenas para consulta e descarte;
  - loading da IA, erros e mudanças de duração possuem anúncios acessíveis;
  - o título passou a ter associação explícita entre label e input.
- Arquivos:
  - `web/vitest.config.ts`;
  - `web/src/routes/-_app.roteiros.$id.test.tsx`;
  - `web/src/routes/_app.roteiros.$id.tsx`;
  - `web/package.json` e `web/package-lock.json`.
- Testes:
  - 21 testes React: presets 10/15/30/45/60, limites ideal/warning/blocking, estado clean/dirty, salvar, remontagem, loading, concorrência incompatível, no-op, schema inválido, timeout, undo, título, revisão médica, resposta antiga e axe;
  - 13 testes determinísticos anteriores preservados;
  - `npm run test`: 34 testes passaram;
  - `npx tsc --noEmit`: passou;
  - ESLint dos arquivos do slice: passou.
- Evidências: axe sem violações críticas nos estados ideal, warning, blocking, erro, título desalinhado e revisão médica obrigatória.
- Pendências: nenhuma interna. Contraste e teclado em navegador real pertencem ao Slice 15A.

## Slice 14B

- Status: `completed`
- Entry points de vídeo pagos auditados:
  - `POST /api/videos`: Direct Avatar, Video Agent e Cinematic;
  - `POST /api/videos/preview`: prévia técnica Direct Avatar;
  - `POST /api/scripts/{scriptId}/scene-generation/submit`: um job HeyGen por cena.
- Outros egressos externos encontrados: criação/consulta de avatar HeyGen e ações Claude de geração, direção e edição. Eles não geram vídeo a partir de uma fala final e, portanto, não usam o gate de roteiro; os contratos, retries, cache e logs dos provedores são homologados no Slice 15B.
- Autoridade e contrato:
  - `shared/script_editor_contract.json` continua como fonte canônica e agora declara versão, statuses e códigos dos gates;
  - Python e TypeScript carregam o JSON; o teste de paridade falha com divergência de presets, WPM, tolerância, metas, statuses, gates ou versão;
  - o backend calcula `scriptRevision` monotônico e `finalSpeechHash` SHA-256 sobre texto NFKC com whitespace equivalente;
  - mudança de palavra, conclusão, claim numérico, CTA ou pontuação incrementa a revisão e reabre a aprovação; whitespace equivalente não reabre.
- Gate e concorrência:
  - os três entry points chamam `_authorize_paid_generation` sob lock por roteiro antes da reserva;
  - aprovação médica é vinculada à revisão/hash e os flags de aprovação/schema enviados pelo cliente não substituem o estado persistido;
  - versão/contrato antigos retornam `409` com código estável antes de criar job;
  - jobs recebem `requestFingerprint`; mesma key e mesmo payload deduplicam, enquanto mesma key com payload diferente retorna `IDEMPOTENCY_KEY_CONFLICT`;
  - SQLite usa `BEGIN IMMEDIATE` e constraint única; o lock não permanece aberto durante chamadas HeyGen;
  - falhas após reserva preservam um estado conhecido (`failed_safe` ou `submission_uncertain`) para diagnóstico e reconciliação.
- Política de novas keys: preservado o comportamento existente — uma nova geração final explícita exige `forceNewVersion`; prévias podem coexistir; cenas diferentes podem coexistir.
- Testes sem custo:
  - presets 10/15/30/45/60 e limites do provider mock;
  - 45s com 109 e 116 palavras chama o mock uma vez; 117 bloqueia antes da reserva;
  - aprovação antiga, revisão/hash/contrato, bypass do cliente, normalização, concorrência e conflito de idempotência;
  - duas requisições simultâneas iguais criam um job e uma chamada de provider.
- Validação: `218 passed` no pytest completo; `34 passed` no Vitest; TypeScript e lint dos arquivos alterados passam. O lint global ainda registra dívida de Prettier em telas legadas, reservada ao Slice 15D.

## Slice 15A

- Status: `completed`
- Acessibilidade: nomes e descrições do editor permanecem associados; alertas técnicos usam `role=alert`, recebem foco programático e entram no `aria-describedby` da fala; estados assíncronos continuam anunciados em região `aria-live`.
- Teclado e movimento: foco global visível foi confirmado no navegador e a folha de estilos agora respeita `prefers-reduced-motion` para animações, transições e scroll suave.
- Responsividade: o cabeçalho deixa de depender de altura fixa, quebra as ações em uma segunda linha quando necessário e reduz o padding em telas estreitas. O conteúdo permanece sem overflow horizontal na viewport real de 1280 px; as regras responsivas cobrem 375/768/1024/1440 e zoom de 200% pela mesma quebra fluida.
- Contraste: estados críticos mantêm texto + ícone/label, sem depender apenas de cor. Axe segue sem violações críticas nos estados ideal, warning, blocking, erro, desalinhamento de título e revisão médica.
- Evidências visuais locais: `artifacts/script-editor/phase-2/15A/desktop-responsive.png`, `desktop-blocking.png` e `desktop-ideal.png`. O navegador embarcado desta execução possui viewport fixa; por isso larguras adicionais foram cobertas por CSS responsivo, testes de componentes e ausência de overflow no navegador disponível.
- Validação: 21 testes React passaram; TypeScript, Prettier e ESLint dos arquivos alterados passaram.

## Slice 15B

- Status: `completed_with_external_step_pending`; smokes reais aguardam autorização externa
- Falhas do editor: timeout, HTTP 429, HTTP 500 e conexão interrompida são classificados sem copiar resposta bruta. Cada caso admite uma única correção/retry, para após a segunda falha e devolve resposta segura com a fala anterior, schema inválido e revisão humana obrigatória.
- Structured output e segurança: cobertura para JSON/schema sem `script`, `script` vazio, warning aceito, blocking rejeitado em `fit_duration`, percentuais, dose, prazo, contagem clínica e experiência profissional inventada. Claims novos pedem conferência da fonte; o sistema não os rotula automaticamente como falsos.
- Cache/concorrência/no-op: request repetido usa cache sem nova chamada; requests simultâneos continuam deduplicados; texto já confortável permanece no caminho determinístico local.
- Jobs pagos: final, prévia e cenas agora capturam também timeout, conexão e falhas inesperadas depois da reserva. O erro persistido é sanitizado e o job termina em `failed_safe` ou `submission_uncertain`, nunca em sucesso. A reconciliação local classifica reservas antigas como retry seguro e submissões interrompidas como incertas, sem consultar nem cobrar o provedor.
- Privacidade: testes confirmam que logs não incluem fala/fonte integrais, segredos de exceção, tokens ou nomes de chaves; registram somente operação, preset, contagens, status, modelo, cache, retry, latência e tipo/código de falha.
- Testes: 71 testes mockados do editor/gates/provedores passaram; 2 smokes reais foram corretamente pulados. Nenhuma chamada Anthropic real e nenhum job HeyGen foram executados.
- Smokes opt-in preparados em `tests/test_real_provider_smoke.py`. IA textual: `ALLOW_REAL_AI_SMOKE_TESTS=true MAX_REAL_AI_CALLS=3 .venv/bin/python -m pytest -q tests/test_real_provider_smoke.py::test_real_anthropic_editor_contract_and_cache`. HeyGen exige autorização separada, IDs explícitos e um único job: `ALLOW_REAL_HEYGEN_SMOKE_TEST=true MAX_REAL_HEYGEN_JOBS=1 REAL_HEYGEN_AVATAR_ID=... REAL_HEYGEN_VOICE_ID=... .venv/bin/python -m pytest -q tests/test_real_provider_smoke.py::test_real_heygen_single_job_is_idempotent`.

## Slice 15C

- Status: `completed`
- Antes: rota com 4.773 linhas, 40 ocorrências de `useState`, 15 de `useEffect` e 19 handlers assíncronos. O mesmo arquivo continha orquestração, feedback do editor, avatar sets, Scene Plan, direção visual e checklist de produção.
- Depois: rota com 2.671 linhas, 30 ocorrências de `useState`, 9 de `useEffect` e 8 handlers assíncronos. Regras determinísticas continuam em `web/src/lib/script-editor.ts`; nenhum endpoint ou payload mudou.
- Extrações:
  - `editor-feedback.tsx` e `editor-feedback-hooks.ts`: duração, erro/foco, resposta antiga, checks, título e revisão médica;
  - `avatar-studio.tsx`: seleção de avatar, Avatar Sets e diálogo de edição;
  - `scene-plan-editor.tsx`: direção, edição e persistência das cenas;
  - `visual-plan-director.tsx`: direção visual e previews locais;
  - `production-readiness.tsx`: avisos de crédito e gates/checklists;
  - `editor-options.ts`: opções tipadas compartilhadas, sem duplicar contrato.
- Comportamento preservado: mesma ordem do DOM, textos, acessibilidade, stale-response guard, dirty/save, autosave, revisão, gate e chamadas de API. As extrações não adicionam effects, fetches ou waterfalls.
- Validação: 21 testes React/axe passaram; TypeScript e ESLint dos arquivos do slice passaram sem warnings; build de produção passou. Regressão visual real permaneceu sem overflow horizontal e foi salva em `artifacts/script-editor/phase-2/15C/desktop-regression.png`.

## Slice 15D

- Status: `completed`
- Diagnóstico global: havia quatro vulnerabilidades npm transitivas, avisos FastAPI pelo uso de `on_event`, dívida de formatação em quatro rotas legadas, exports incompatíveis com `react-refresh/only-export-components` e um effect com dependências instáveis na produção. Nenhuma regra foi desabilitada.
- FastAPI lifespan:
  - os dois handlers legados de startup foram migrados para um único lifespan;
  - reconciliação de jobs de vídeo, retomada de cortes e retomada de pós-produção executam exatamente uma vez;
  - `tests/test_api_lifespan.py` caracteriza a ordem e impede inicialização duplicada;
  - os quatro avisos de depreciação anteriores desapareceram.
- ESLint e Prettier:
  - lint global passou com zero erros e zero warnings;
  - variantes de `Button` e `Toggle` foram separadas em módulos sem componentes para atender Fast Refresh sem silenciar a regra;
  - exports sem consumidores foram removidos de `badge`, `form`, `navigation-menu` e `sidebar`;
  - o polling de pós-produção usa dependências escalares estáveis (`postJobId` e `postJobStatus`), preservando a frequência e o encerramento do timer;
  - as quatro rotas legadas apontadas pelo check foram formatadas sem alteração intencional de comportamento.
- Dependências:
  - antes: `brace-expansion` (alta), `js-yaml` (alta), `nanoid` (alta) e `postcss` (moderada), todas transitivas e com correção não-major disponível;
  - `npm audit fix` atualizou somente transitivas compatíveis: `brace-expansion` 1.1.18/5.0.9, `js-yaml` 4.3.1, `nanoid` 3.3.18 e `postcss` 8.5.26;
  - depois: `npm audit --json` confirmou 0 vulnerabilidades em 643 dependências auditadas;
  - `web/.nvmrc` fixa Node 24.15.0, faixa suportada pelo `jsdom` atual. A runtime empacotada usada nesta execução era 24.14.0 e passou em toda a regressão.
- CI local: `npm run ci`, dentro de `web`, executa em sequência Prettier check, ESLint global, TypeScript, Vitest, build e pytest do ambiente virtual do repositório.
- Arquivos principais: `api/server.py`, `tests/test_api_lifespan.py`, `web/package.json`, `web/package-lock.json`, `web/.nvmrc`, componentes base em `web/src/components/ui/` e as quatro rotas legadas formatadas.
- Validação: `npm run ci` passou integralmente; 34 testes Vitest e 237 testes pytest passaram, com 2 smokes reais corretamente pulados.
- Nota de fornecedor: o build informa que `vite-tsconfig-paths` se tornou redundante no Vite 8. O plugin é injetado e exigido como peer pelo wrapper `@lovable.dev/vite-tanstack-config`, inclusive em sua versão atual; não foi removido nem mascarado para evitar divergir da configuração suportada pelo fornecedor.

## Validação final

- Status: `completed_with_external_step_pending`
- Comando reproduzível: `cd web && npm run ci`.
- Backend: 237 testes passaram, 2 smokes opt-in foram pulados, 0 falhas e 0 warnings, em aproximadamente 17 segundos.
- Frontend: 34 testes Vitest passaram; TypeScript, ESLint global, Prettier check e build de produção passaram.
- Auditoria: 0 vulnerabilidades npm (0 baixa, 0 moderada, 0 alta e 0 crítica).
- Interações: cobertura React preservada para presets, limites, dirty/save, loading, concorrência, timeout, undo, título, revisão médica, resposta antiga, acessibilidade e entry points pagos.
- Regressão visual: editor carregou no navegador real sem overflow horizontal após a modularização; evidência em `artifacts/script-editor/phase-2/15C/desktop-regression.png`.
- Resultado: os seis slices executáveis (14A, 14B e 15A–15D) foram concluídos. Apenas os smokes reais pagos permanecem opt-in e não impedem o uso local nem a homologação mockada.

## Riscos residuais

- Chamadas reais de IA e HeyGen exigem autorização e limites explícitos; credenciais presentes não serão tratadas como autorização.
- O aviso informativo de `vite-tsconfig-paths` será eliminável quando o wrapper Lovable deixar de injetar o plugin; removê-lo unilateralmente hoje quebraria o peer contract da configuração instalada.
- Ambientes locais devem respeitar `web/.nvmrc` (Node 24.15.0) antes de reinstalar dependências.
