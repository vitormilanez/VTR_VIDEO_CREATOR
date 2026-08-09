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

- Status: `not_started`

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
