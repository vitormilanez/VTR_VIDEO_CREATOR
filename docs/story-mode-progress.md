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
- testes sem criação de sessões ou vídeos.
- o snapshot de capabilities é congelado na reserva e obrigatório no envio, evitando
  que um job mude de contrato por diferenças de ambiente ou atualização do CLI.

Evidência do ambiente em 9 de agosto de 2026:

- CLI: `heygen 0.5.0`;
- Video Agent: estilos, Brand Kit, modo chat, anexos e 9:16/16:9 confirmados;
- Direct Video: contrato obtido via `--request-schema`, sem chamada de geração.
- validação local completa: 35 testes web e 247 testes Python aprovados; 2 smoke
  tests de providers reais permaneceram ignorados.

## Próximos slices

- 16B — Story Contract e Narrative Director;
- 16C — Story Critic e orçamento;
- 16D — Storyboard na interface;
- 16E — Orquestrador por shot e Asset Store;
- 16F — B-roll em vídeo no compositor;
- 16G — Claude Visual QC;
- 16H — preparação do piloto medieval controlado.
