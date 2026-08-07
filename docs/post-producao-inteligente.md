# Pós-produção inteligente — Fase 1

## Escopo

A Fase 1 adiciona edição automática sobre um vídeo já pronto, sem modificar o arquivo original e sem fazer novos cortes na fala. O fluxo transcreve localmente, planeja interações por índices estáveis de palavras, executa preflight e gera uma prévia vertical 1080 × 1920 com o áudio original.

O botão **Editar automaticamente** aparece em `/producao/:id` somente quando o vídeo está pronto. A tela permite revisar a transcrição, ativar/desativar eventos, editar o texto visual, repetir o preflight, gerar a prévia, comparar original e prévia e baixar o MP4 resultante.

## Contratos e versões

- `Transcript`: idioma, duração real, texto, segmentos, palavras indexadas, fingerprint SHA-256 do vídeo, versão do schema, modelo e conteúdo.
- `SemanticSegment`: intervalo de palavras, fala, motivo e confiança.
- `VisualPlan`: saída fechada do planner. Contém índices de palavras; não aceita timestamps do modelo.
- `VisualTimeline`: deriva `startMs`/`endMs` no backend e registra versões de vídeo/transcrição.
- `PostProductionJob`: job operacional independente (`kind=post_production`).

Taxonomia fechada: `none`, `caption_emphasis`, `kinetic_text`, `progressive_list`, `supporting_visual` e `cta_card`. Estatísticas não são criadas automaticamente.

O planner local determinístico está sempre disponível e não consome créditos. O Claude só é habilitado quando existem credenciais e `POST_PRODUCTION_USE_CLAUDE=1`; a resposta usa JSON Schema e é validada novamente. Texto visual que acrescente palavras fora da fala selecionada é substituído por texto derivado da própria fala.

## Estados

`queued → transcribing → planning → preflight → needs_review → rendering_preview → preview_ready`

Estados terminais ou de intervenção: `failed`, `cancelled`, `stale` e `needs_review`. Jobs interrompidos durante análise/renderização são retomados no startup quando o vídeo original ainda existe; caso contrário são marcados como falha segura.

## Preflight

Achados são classificados como `BLOCKER`, `WARNING` ou `INFO`. Um blocker impede renderização. As verificações cobrem:

- arquivo e streams de vídeo/áudio, duração e fingerprint;
- contrato da transcrição/timeline, índices, derivação dos tempos e limites;
- stale por versão do vídeo/transcrição;
- ordenação, sobreposição e densidade visual;
- comprimento dos textos, assets/fallback e CTA;
- área segura de legenda e revisão de segurança médica;
- disponibilidade de FFmpeg, FFprobe e Playwright.

## Persistência e arquivos

Jobs ficam em `data/operations.db`. A migração recria com segurança o `CHECK` de `operational_jobs.kind`, preservando jobs antigos de vídeo, avatar e cortes.

Artefatos ficam em `data/post_production/<job-id>/`:

- `source.mp4` (cópia de trabalho; o original permanece intacto);
- `transcript.json`, `visual-plan.json`, `timeline.json` e `preflight.json`;
- `overlays/*.png` e `captions.srt`;
- `preview.mp4` e `manifest.json`.

A chave de idempotência combina fingerprint do vídeo, versão da transcrição, versão da timeline, configuração de render e versão do design.

## API

- `POST /api/post-production` — cria ou devolve job idempotente para um vídeo pronto.
- `GET /api/post-production/{id}` — estado/progresso.
- `GET /api/post-production/{id}/artifacts` — transcrição e timeline.
- `PATCH /api/post-production/{id}/events` — habilita/desabilita e edita texto/revisão.
- `POST /api/post-production/{id}/preflight` — refaz as validações.
- `POST /api/post-production/{id}/render` — inicia a prévia se não houver blockers.
- `POST /api/post-production/{id}/replan` — regenera o plano, reaproveitando transcrição/cache válidos.
- `POST /api/post-production/{id}/cancel` — cancela de forma segura.
- `GET /api/post-production/{id}/preview[?download=true]` — reproduz ou baixa a prévia.

## Operação local

Dependências: FFmpeg/FFprobe no `PATH`, Playwright com Chromium e `faster-whisper`. A transcrição usa o modelo local `small` por padrão. Testes e fallback não chamam APIs pagas.

## Fase 2

A Fase 2 deve processar um lote controlado de **3 vídeos por execução**, reaproveitando os mesmos contratos, idempotência, preflight e manifestos. Ela não faz parte da Fase 1 e não deve ser habilitada implicitamente.
