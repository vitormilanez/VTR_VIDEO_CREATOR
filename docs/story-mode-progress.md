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
