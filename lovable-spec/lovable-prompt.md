# Prompt Principal Para Lovable

Crie um web app chamado **AI Video Creator** para gerenciar uma esteira de conteudo medico em videos curtos.

O app deve apoiar a producao de Reels para um medico chamado Dr. Guilherme, com foco em obesidade, emagrecimento, GLP-1, Mounjaro, Ozempic, Wegovy, dieta, metabolismo, comportamento alimentar e saude metabolica.

## Produto

O app deve transformar tendencias em ideias, ideias em roteiros, roteiros em videos aprovados e videos em publicacoes acompanhadas por performance.

Fluxo principal:

1. Capturar tendencias em uma tela de Radar.
2. Gerar ideias editoriais a partir das tendencias.
3. Gerar roteiros estruturados a partir das ideias.
4. Manter roteiros em validacao medica.
5. Permitir producao de video apenas como acao explicita do usuario.
6. Controlar calendario de publicacao.
7. Registrar performance por post.

## Estilo visual

Crie uma interface de operacao, nao uma landing page.

Visual desejado:

- dashboard limpo, profissional e denso;
- layout com sidebar ou tabs;
- tabelas escaneaveis;
- filtros por status, prioridade, tema e risco;
- botoes com icones para acoes;
- cards apenas para metricas e itens repetidos;
- tons neutros com acentos em azul, verde, amarelo e vermelho para status;
- nada de hero, marketing page, gradientes exagerados ou textos explicando como usar.

## Telas

Crie as telas:

- Dashboard
- Radar de Tendencias
- Ideias
- Roteiros
- Producao de Videos
- Calendario
- Performance
- Configuracoes

Detalhes de telas e fluxos estao em `screens-and-flows.md`.

## Banco

Use Supabase/Postgres com tabelas para:

- trends
- ideas
- scripts
- video_jobs
- calendar_posts
- performance_metrics
- app_settings

O modelo sugerido esta em `data-model.md`.

## Regras criticas

Todas as geracoes devem ser assistidas por humano. O app pode sugerir, mas nao deve publicar ou gastar creditos sem clique explicito.

Compliance medico:

- nao prescrever medicamento;
- nao citar doses;
- nao prometer resultado;
- nao fazer sensacionalismo;
- reforcar avaliacao individual;
- manter status de validacao medica antes de video/publicacao.

Mais detalhes em `compliance-rules.md`.

## Integracoes

Preparar arquitetura para:

- Google Sheets import/export opcional;
- HeyGen para criar videos;
- Instagram/Meta Graph API para performance;
- busca de tendencias por endpoint backend.

As chaves de API devem ficar apenas no backend/Edge Functions. Nunca expor `HEYGEN_API_KEY`, `META_ACCESS_TOKEN` ou credenciais Google no frontend.

## Dados iniciais

Popular o app com dados de exemplo coerentes:

- uma tendencia sobre Mounjaro;
- uma ideia educativa/provocativa;
- um roteiro aguardando validacao medica;
- um post no calendario pendente;
- metricas de performance zeradas.

## Logica editorial

Ao gerar ideias:

- detectar familia do tema: medicamento, comportamento, metabolismo, obesidade ou educativo;
- criar hook curto;
- criar angulo educativo;
- criar CTA sem promessa;
- incluir observacao de compliance.

Ao gerar roteiros:

- categoria;
- tema;
- titulo;
- hook;
- dor/conflito;
- explicacao simples;
- virada/provocacao;
- CTA;
- cuidados medicos;
- risco;
- formato sugerido;
- status inicial `Aguardando validacao medica`.

Use linguagem em portugues do Brasil.
