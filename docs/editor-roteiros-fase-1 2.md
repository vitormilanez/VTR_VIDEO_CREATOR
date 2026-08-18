# Editor de roteiros — fase 1 concluída

Data de fechamento: 9 de agosto de 2026.

## Resultado

Esta fase substituiu as regras divergentes de duração e envio por um contrato central. O editor agora trata separadamente duração, revisão médica, alinhamento de título, erro técnico e elegibilidade de geração.

A regra de 45 segundos ficou assim:

| Palavras | Estado | Salvar | Enviar ao HeyGen |
| --- | --- | --- | --- |
| até 108 | ideal | permitido | permitido se os demais gates estiverem válidos |
| 109–116 | warning | permitido | permitido se os demais gates estiverem válidos |
| 117 ou mais | blocking | permitido | bloqueado |

O mesmo cálculo atende aos presets de 10, 15, 30, 45 e 60 segundos, com 144 palavras por minuto, tolerância rígida de 7% e faixa de geração entre 88% e 94% da meta.

## Diagnóstico original

- O frontend e o backend consideravam 108 palavras como teto rígido para 45 segundos.
- O Video Agent tinha uma segunda régua, ainda mais conservadora.
- Duração, revisão médica e prontidão para geração apareciam como um único estado de “revisão necessária”.
- A edição manual de `Fala final` não participava corretamente do estado `dirty`, deixando `Salvar` desabilitado em alguns casos.
- A geração por cenas validava os campos estruturados antigos e não priorizava `textoFalado`.
- Solicitações simultâneas de IA podiam disputar a inicialização do cache SQLite.
- Um alerta médico obrigatório persistido pela IA podia ser recalculado apenas pelo risco e rebaixado indevidamente.

## Arquitetura entregue

- Contrato compartilhado em `shared/script_editor_contract.json`.
- Motor determinístico de duração, pós-validação e gate em `api/services/script_editor.py`.
- Espelho tipado para a interface em `web/src/lib/script-editor.ts`.
- Estado persistente do editor em SQLite, sem alterar o schema do Google Sheets.
- Endpoint de estado por roteiro e endpoint único para as duas operações de IA.
- Gate central aplicado antes de reservar jobs pagos de vídeo final, prévia e geração por cenas.
- Cache por conteúdo e contexto, deduplicação de requests simultâneos e no-op sem chamada de IA.
- Logs estruturados sem registrar o texto clínico integral.

## Situação por slice original

| Slice | Situação | Entrega |
| --- | --- | --- |
| 1 — Auditoria | concluído | Regras conflitantes e fontes de bloqueio mapeadas. |
| 2 — Duration Engine | concluído | Presets, perfil de fala, fórmulas, tokenização e limites centralizados. |
| 3 — UI e bloqueio | concluído | Estados verde/âmbar/vermelho, troca de preset e `Salvar` independente da duração. |
| 4 — Operações de IA | concluído | `medical_rewrite` e `fit_duration` separados, com rótulos neutros ao provedor. |
| 5 — Perfil editorial médico | concluído | Prompt médico v2, oralidade, autoridade, segurança e CTA. |
| 6 — Contexto e schema | concluído | Contexto completo, saída estruturada e validação de schema. |
| 7 — Pós-validação | concluído | Validação determinística, uma correção no máximo e preservação da versão anterior. |
| 8 — Título | concluído | Alerta independente e escolha explícita entre título atual e sugerido. |
| 9 — Checks explicáveis | concluído | Duração, segurança, sentido, claims, experiência clínica, título, gancho, CTA e revisão humana. |
| 10 — Custos | concluído | Cache, dedupe, no-op, retry único e histórico para desfazer IA. |
| 11 — Proteção HeyGen | concluído | Gate único e aviso de duração não bloqueante; limite duro e revisão obrigatória bloqueiam. |
| 12 — Observabilidade | concluído | Logs com operação, preset, contagens, status, versão, cache, retry e latência. |
| 13 — Persistência | concluído | Preset, aprovação médica, título, schema, erro e último resultado persistidos com fallback legado. |
| 14 — Testes completos | parcial avançado | Motor, API e políticas cobertos; falta ampliar testes de interação visual. |
| 15 — Validação final | parcial | Verificação manual principal feita sem chamadas pagas; falta a homologação integral descrita no plano seguinte. |

## Comportamentos confirmados

- Em 45 segundos, 108 é ideal, 109–116 é warning e 117+ bloqueia geração.
- Warning não bloqueia `Salvar` nem o gate de geração por duração.
- Blocking não impede salvar a fala.
- `Ajustar para Xs` não chama IA quando o texto já está na faixa de geração.
- Saída inválida conserva o texto anterior e faz no máximo uma tentativa corretiva.
- Requests idênticos simultâneos executam uma única operação.
- Alerta médico obrigatório persistido não pode ser rebaixado por um payload da interface.
- O título sugerido nunca é aplicado automaticamente.
- A geração por cenas usa `textoFalado` como fonte final, com fallback para os campos legados.
- Cliques duplicados são protegidos no frontend e por idempotência no backend.

## Validação executada

| Validação | Resultado |
| --- | --- |
| `python -m pytest -q` | 197 testes passaram; 4 avisos de depreciação FastAPI já conhecidos. |
| `npm run test` | 13 testes Vitest passaram. |
| `npx tsc --noEmit` | passou. |
| `npm run build` | passou. |
| ESLint dos arquivos do editor | passou sem erros e sem avisos. |
| Navegador local | preset 60s, warning, blocking, `Salvar` habilitado e persistência após reload confirmados. |

O lint global ainda possui dívida anterior em outras telas. Ela não é causada pelo editor e foi isolada como slice de saneamento no plano de continuidade.

## Arquivos centrais

- `shared/script_editor_contract.json`
- `api/services/script_editor.py`
- `api/services/script_performance.py`
- `api/server.py`
- `web/src/lib/script-editor.ts`
- `web/src/lib/script-quality.ts`
- `web/src/lib/api/local.ts`
- `web/src/routes/_app.roteiros.$id.tsx`
- `tests/test_script_editor.py`
- `web/src/lib/script-editor.test.ts`

## Limites desta fase

- Nenhuma geração real do HeyGen foi disparada durante a homologação, para evitar consumo de créditos.
- As chamadas reais de revisão médica também não foram usadas como critério de aceite; os contratos foram testados com respostas determinísticas e mocks.
- A tela de roteiro ainda é um componente grande e deve ser modularizada depois da homologação funcional, sem mudar comportamento.
