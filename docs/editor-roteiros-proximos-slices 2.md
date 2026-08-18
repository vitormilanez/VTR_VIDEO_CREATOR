# Editor de roteiros — próximos slices

Este backlog começa após o fechamento da fase 1. Cada slice deve terminar com evidência de teste e atualização do relatório da fase.

## Slice 14A — Testes de interação do editor

Objetivo: cobrir a experiência React, não apenas o motor de regras.

Escopo:

- Configurar ambiente de testes de componentes com DOM.
- Testar presets 10/15/30/45/60 e as mensagens de ideal, warning e blocking.
- Confirmar `Salvar` habilitado nos três estados de duração quando houver alteração.
- Testar loading e bloqueio temporário dos dois botões de IA.
- Testar no-op, saída inválida, restauração da versão anterior e `Desfazer IA`.
- Testar título sugerido, manutenção do título atual e aprovação/reabertura médica.
- Testar persistência após remontagem da tela.

Aceite:

- Todos os fluxos acima automatizados sem rede real.
- Nenhum teste depende da ordem de execução.
- Testes falham se warning voltar a bloquear `Salvar` ou HeyGen.

Dependência: fase 1 concluída.

## Slice 14B — Testes dos entry points pagos

Objetivo: comprovar que todos os caminhos pagos consultam o mesmo gate antes de reservar ou chamar o provedor.

Escopo:

- Vídeo final Direct Avatar.
- Video Agent.
- Modo cinematic.
- Prévia técnica.
- Geração por cenas.
- Matriz de bloqueio: limite duro, IA em andamento, schema inválido, erro técnico, revisão médica obrigatória, roteiro não pronto, fala não salva e confirmação ausente.
- Matriz permitida: ideal e warning, inclusive 109 e 116 palavras em 45 segundos.
- Testes concorrentes e de idempotência em cada entrada relevante.

Aceite:

- Provedor e reserva nunca são chamados em estado bloqueado.
- Warning chega ao mock do provedor uma vez.
- Duplo clique/request idêntico não cria job ou custo duplicado.

Dependência: Slice 14A pode rodar em paralelo.

## Slice 15A — Homologação visual e acessibilidade

Objetivo: validar a tela real em dimensões e formas de navegação diferentes.

Escopo:

- Desktop largo, notebook e viewport estreito.
- Scroll da página e dos painéis laterais.
- Navegação por teclado, foco visível, labels e mensagens anunciáveis.
- Contraste dos estados verde, âmbar e vermelho.
- Textos longos, título longo e respostas extensas dos checks.
- Screenshot de cada estado crítico.

Aceite:

- Nenhum controle fica inacessível ou fora da tela.
- Fluxo principal pode ser concluído apenas com teclado.
- Evidências visuais anexadas ao relatório.

Dependência: Slice 14A.

## Slice 15B — Homologação controlada dos provedores

Objetivo: validar o contrato real sem risco de chamadas duplicadas.

Escopo:

- Uma execução real de `medical_rewrite` em roteiro de teste não sensível.
- Uma execução real de `fit_duration` fora da faixa.
- Confirmação de structured output, métricas, cache e retry.
- Repetição do mesmo request para confirmar cache/no-op.
- Envio ao HeyGen somente com autorização explícita e orçamento definido.

Aceite:

- Nenhum conteúdo clínico integral aparece nos logs.
- Contagem de chamadas e custo correspondem ao esperado.
- Falha do provedor mantém a fala anterior e não cria job pago órfão.

Dependências: Slice 14B; credenciais de homologação. A etapa HeyGen exige autorização explícita por consumir crédito.

## Slice 15C — Modularização da tela de roteiro

Objetivo: reduzir o risco de manutenção do arquivo de rota sem alterar o comportamento homologado.

Escopo:

- Extrair `DurationControl`, `MedicalReviewCard`, `TitleAlignmentCard`, `QualityChecks`, `AiEditorActions` e `GenerationGateSummary`.
- Isolar persistência/autosave e envio de IA em hooks testáveis.
- Manter cálculos determinísticos fora dos componentes.
- Evitar novos waterfalls e dependências instáveis em hooks.

Aceite:

- Mesma interface e mesmos contratos de API.
- Suítes 14A e 14B continuam verdes sem alteração de expectativas.
- Redução mensurável do tamanho e da complexidade da rota principal.

Dependência: homologação funcional dos Slices 14A e 15A.

## Slice 15D — Saneamento técnico global

Objetivo: obter uma linha de base limpa para o projeto inteiro.

Escopo:

- Corrigir erros de Prettier e avisos de hooks nas telas legadas.
- Resolver avisos FastAPI migrando `on_event` para lifespan.
- Revisar os quatro avisos de vulnerabilidade informados pelo npm sem atualização destrutiva.
- Adicionar `typecheck`, testes e lint ao fluxo de CI local.

Aceite:

- `pytest`, Vitest, TypeScript, build e ESLint globais passam.
- Nenhuma alteração visual ou funcional não planejada.
- Dependências atualizadas somente com testes de regressão verdes.

Dependência: pode começar após a fase 1, mas deve ser entregue separadamente da modularização.

## Ordem recomendada

1. Slice 14A — interação do editor.
2. Slice 14B — entry points pagos.
3. Slice 15A — homologação visual e acessibilidade.
4. Slice 15B — provedores reais com orçamento controlado.
5. Slice 15C — modularização após congelar o comportamento.
6. Slice 15D — saneamento global em mudança separada.
