# Story Mode cinematográfico — relatório de progresso

Especificação de origem: `story-mode-cinematico-heygen-anthropic.md`, recebida em 9 de agosto de 2026.

Branch de implementação: `codex/intelligent-video-workflows`.

Regras permanentes desta fase:

- nenhuma chamada real Anthropic ou HeyGen durante os slices locais;
- `scriptRevision`, `finalSpeechHash`, revisão médica e confirmação explícita continuam obrigatórios;
- providers e campos são aceitos somente quando confirmados por capability registry;
- cada slice recebe testes e commit próprios;
- o piloto real do Slice 16H exige autorização e orçamento explícitos.

## Slice 16A — Capability Registry e transporte HeyGen

Status: concluído.

Implementado:

- inspeção local e sem custo dos schemas do CLI HeyGen;
- registro persistente versionado por hash dos schemas;
- detecção confirmada do CLI `0.5.0`;
- capabilities de Video Agent para `styleId`, `brandKitId`, chat, anexos e orientação;
- capabilities de Direct Video para tipos, engines, resoluções e proporções;
- `styleId`, `brandKitId` e modo do agente validados antes da reserva do job;
- transporte do Video Agent compilado somente com flags confirmadas;
- versão das capabilities incorporada ao fingerprint do job;
- endpoint local de leitura e refresh do registro;
- testes sem criação de sessões ou vídeos;
- o snapshot de capabilities é congelado na reserva e obrigatório no envio, evitando
  que um job mude de contrato por diferenças de ambiente ou atualização do CLI.

Evidência do ambiente em 9 de agosto de 2026:

- CLI: `heygen 0.5.0`;
- Video Agent: estilos, Brand Kit, modo chat, anexos e 9:16/16:9 confirmados;
- Direct Video: contrato obtido via `--request-schema`, sem chamada de geração;
- validação local completa: 35 testes web e 247 testes Python aprovados; 2 smoke
  tests de providers reais permaneceram ignorados.

## Slice 16B — Story Contract e Narrative Director

Status: concluído.

Implementado:

- contrato JSON estrito e compartilhado para Story Bible, Character Bible, Visual
  Bible e Shot Plan;
- Story Brief tipado com período, local, realismo, personagem, referências e limites
  de custo;
- cobertura integral da fala por índices de palavras, sem campo para fala livre nos
  shots;
- validação determinística de duração, ordem, lacunas, sobreposições, IDs, provider,
  referências, personagem, jobs e novos sinais médicos ou numéricos;
- prompt global do Narrative Director com schema e contexto estável preparados para
  prompt caching;
- modelo premium configurável e reparo explícito limitado a uma tentativa;
- cache persistente, deduplicação de requests simultâneos e registro de tokens;
- persistência versionada de projetos e planos, sem sobrescrever versões anteriores;
- invalidação do plano ativo quando fala, contrato, briefing ou capabilities mudam;
- endpoints para salvar o briefing, gerar o plano e ler o projeto ativo;
- confirmação explícita obrigatória antes da chamada Anthropic;
- nenhuma chamada ao HeyGen no fluxo de planejamento;
- validação local completa: 35 testes web e 258 testes Python aprovados; 2 smoke
  tests de providers reais permaneceram ignorados.

## Slice 16C — Story Critic, orçamento e aprovação

Status: concluído.

Implementado:

- contrato estruturado do Story Critic com códigos estáveis para narrativa,
  continuidade, história, medicina, redundância e provider;
- avaliação obrigatória de todos os shots, incluindo dificuldade, riscos e provider
  recomendado;
- orçamento recalculado localmente por estratégia, com custo inicial, pior caso,
  limite de jobs e limite de regenerações;
- taxas de job configuráveis, sem preços externos fixados silenciosamente no código;
- bloqueios estáveis para teto ausente, taxa ausente, jobs excedidos e custo acima do
  orçamento;
- cache, deduplicação, tokens e uma única correção de schema para a crítica;
- versionamento de críticas: refazer cria nova revisão e mantém o histórico;
- crítica inválida preserva integralmente a revisão válida anterior;
- aprovação humana vincula Story Hash, Critic Hash e Budget Hash;
- gate reutilizável que impede qualquer reserva de shot sem plano e orçamento
  aprovados;
- nenhuma chamada real a Anthropic ou HeyGen durante os testes;
- validação local completa: 35 testes web e 264 testes Python aprovados; 2 smoke
  tests de providers reais permaneceram ignorados.

## Próximos slices

- 16D — Storyboard na interface: concluído;
- 16E — Orquestrador por shot e Asset Store;
- 16F — B-roll em vídeo no compositor;
- 16G — Claude Visual QC;
- 16H — preparação do piloto medieval controlado.

## Slice 16D — Storyboard e aprovação por shot

Status: concluído.

Implementado:

- modo “História cinematográfica” separado dos fluxos Direct, Video Agent e
  Cinematic;
- Story Brief com objetivo, período, local, realismo, referências por hash e limites
  explícitos de jobs, regenerações e orçamento;
- Story Bible, storyboard editável, provider, duração e prompt adicional por shot;
- travas independentes de identidade, figurino e ambiente;
- aprovação humana da Bible e de cada shot antes da crítica;
- alterações salvas em nova revisão, preservando a anterior e com retry idempotente;
- crítica e aprovação vinculadas à revisão ativa; qualquer edição invalida o vínculo
  anterior;
- orçamento e pior cenário sempre visíveis antes da aprovação;
- proteção contra respostas assíncronas antigas e suporte a desfazer edições locais;
- botões antigos de prévia e vídeo final bloqueados no Story Mode;
- nenhum job HeyGen criado nesta fase;
- validação focada: 3 testes do reducer web e 18 testes Python de contrato,
  versionamento, crítica e orçamento aprovados.

## Slice MVP-1 — Storyboard funcional

Status: concluído.

- contrato narrativo atualizado para `story-contract-v2`;
- cada shot recebe do Claude uma estratégia MVP (`avatar_anchor`,
  `cinematic_broll` ou `local_transition`) e um `heygenPrompt` final;
- subject, período, figurino, atmosfera e continuidade passam pelo structured output;
- rotas de provider são determinísticas e limitadas às capabilities confirmadas;
- uma única função canônica fornece Character, Visual e Historical Bible para geração e QC;
- planos v1 ativos são invalidados em vez de reutilizados silenciosamente;
- editor permite revisar estratégia e prompt final antes de criar uma nova revisão;
- nenhuma chamada Anthropic ou HeyGen foi executada na validação local.

## Slice MVP-2 — Geração individual por shot

Status: concluído.

- cada card aprovado expõe somente “Gerar shot” ou “Refazer shot”, nunca geração em lote;
- a reserva revalida Story Hash, Prompt Hash, Budget Hash, aprovação, capability e teto
  de custo imediatamente antes do provider;
- `cinematic_broll` envia ao Video Agent exatamente o `heygenPrompt` aprovado;
- `avatar_anchor` usa Direct Video com apenas o trecho aprovado da fala e a identidade
  já selecionada;
- `local_transition` é renderizado com FFmpeg local e não consome job HeyGen;
- gerações têm revisão, chave idempotente, custo estimado, job remoto, arquivo local,
  thumbnail e estados persistentes;
- repetição da mesma chave não duplica provider, e submissão incerta bloqueia uma nova
  tentativa até verificação manual;
- refazer um shot preserva os arquivos e revisões dos demais;
- interface mostra status e preview por shot e mantém edição bloqueada somente depois
  da aprovação do plano;
- validação focada: 24 testes Python e typecheck do frontend aprovados, sem chamadas
  reais a Anthropic ou HeyGen.

## Próximos slices MVP

- MVP-3 — compositor final com vídeo por shot, narração contínua, legendas e música: concluído;
- MVP-4 — fixture medieval, testes P0 e validação final única da suíte completa.

## Slice MVP-3 — Composição final

Status: concluído.

- “Montar vídeo” só libera quando todos os shots da revisão aprovada têm MP4 local;
- o vídeo-base pronto mais recente do roteiro fornece uma única trilha contínua de narração;
- os shots são ordenados pelo plano e entram em tela cheia nos intervalos da fala;
- todos os áudios produzidos pelos shots, inclusive B-roll, são descartados na montagem;
- vídeos são normalizados para 1080×1920 e shots curtos congelam o último frame até o fim
  do intervalo, sem repetir o clipe;
- legendas do vídeo-base são preservadas; quando não há SRT, uma faixa sincronizada é
  criada deterministicamente a partir da fala aprovada;
- a música escolhida no perfil é aplicada pelo mixer local existente;
- composição, fontes, ordem, intervalos e política de áudio ficam no manifesto do job;
- o MP4 final pode ser assistido e baixado no próprio Story Mode;
- validação focada: 12 testes do orquestrador/compositor e typecheck aprovados, incluindo
  ordem visual e prova sintética de que o B-roll não substitui a narração.

## Slice MVP-4 — Validação e encerramento

Status: concluído.

- fixture principal em `tests/fixtures/story_medieval.py`: personagem atravessa um portal,
  chega à feira medieval, alterna três B-rolls com três avatar anchors e encerra na botica;
- os seis shots cobrem exatamente a fala aprovada, mantêm ordem, estratégia, identidade,
  figurino, época, anacronismos proibidos e prompts finais de produção;
- o Narrative Director aceita o plano completo em uma única chamada mockada;
- geração mockada acontece um shot por vez, sem alcançar o transporte real do HeyGen;
- um único teste P0 percorre Brief, plano Claude mockado, Story Bible, Shot Plan,
  edição e aprovação do shot, orçamento, seis gerações individuais mockadas,
  regeneração exclusiva do shot 03, composição local e MP4 final;
- a validação integrada corrigiu a autorização de produção para expor o Story Brief
  no formato usado pela reserva e pelo roteamento dos shots;
- os testes P0 cobrem vínculo com a fala, invalidação por edição, aprovação, budget,
  capabilities, idempotência, regeneração seletiva, ordem e narração sobre B-roll;
- nenhuma chamada real a Anthropic ou HeyGen foi feita nesta fase.

Teste focado principal:

```bash
.venv/bin/python -m pytest -q \
  tests/test_story_medieval_mvp.py::test_medieval_critical_path_with_mocks_outputs_final_mp4
```

Checkpoint final de 9 de agosto de 2026:

- Python: 280 testes aprovados e 2 smoke tests reais ignorados;
- Web: 39 testes aprovados;
- TypeScript: typecheck aprovado;
- ESLint: zero erros e quatro avisos não bloqueantes de Fast Refresh no editor;
- build Vite/Nitro de produção aprovado.

## Limite operacional consciente do MVP

A montagem usa como fonte de áudio o vídeo-base pronto mais recente do mesmo roteiro. Isso
preserva a voz e a sincronização sem criar jobs adicionais de voz. Se não existir vídeo-base,
o botão informa o pré-requisito e não inicia nenhuma chamada paga.

## Etapas que ainda usam créditos reais

- gerar o Story Plan e executar o Story Critic usam Anthropic quando operados pela interface;
- gerar ou refazer `avatar_anchor` e `cinematic_broll` usa um job HeyGen por ação;
- salvar o Brief, editar e aprovar shots, calcular o orçamento e compor o MP4 são locais;
- o teste P0 medieval substitui Anthropic e HeyGen por mocks e não consome créditos.

## Riscos conhecidos

- mocks não validam disponibilidade, latência, qualidade visual nem mudanças de contrato dos
  providers reais;
- custos são estimativas configuradas no ambiente, não uma cotação do provider em tempo real;
- a composição depende de um vídeo-base pronto do mesmo roteiro para fornecer a narração;
- a fixture comprova regeneração isolada do shot 03, mas não avalia continuidade visual real.

## Backlog explicitamente adiado

- polish visual avançado e cobertura de todos os breakpoints;
- Visual QC automático e loops Claude → HeyGen → Claude;
- análise opcional de thumbnail com Claude Vision;
- Avatar Shots e providers experimentais;
- efeitos cinematográficos além de corte seco/fade simples;
- analytics avançado, colaboração e histórico completo de versões;
- exportação da Story Bible e templates de histórias;
- criação de narração independente do vídeo-base;
- refatorações e abstrações sem impacto direto no MVP.
