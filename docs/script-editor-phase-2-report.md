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

- Status: `not_started`

## Slice 15B

- Status: `not_started`

## Slice 15C

- Status: `not_started`

## Slice 15D

- Status: `not_started`

## Validação final

- Status: `not_started`

## Riscos residuais

- Chamadas reais de IA e HeyGen exigem autorização e limites explícitos; credenciais presentes não serão tratadas como autorização.
