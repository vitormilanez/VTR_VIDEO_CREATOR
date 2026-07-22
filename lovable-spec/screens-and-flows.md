# Telas e Fluxos

## Navegacao

Use uma navegacao principal com estas areas:

- Dashboard
- Radar
- Ideias
- Roteiros
- Videos
- Calendario
- Performance
- Configuracoes

## Dashboard

Objetivo: mostrar o estado da esteira.

Metricas:

- tendencias coletadas;
- ideias geradas;
- roteiros em validacao;
- roteiros aprovados para video;
- videos solicitados;
- videos prontos;
- posts agendados;
- posts publicados;
- views totais;
- leads totais.

Listas:

- ultimas tendencias de alta prioridade;
- roteiros aguardando validacao medica;
- videos com erro ou pendentes;
- proximas publicacoes.

## Radar de Tendencias

Tabela com:

- data;
- tema;
- subtema;
- fonte;
- link de referencia;
- sinal de tendencia;
- dor do publico;
- potencial viral;
- prioridade;
- status;
- observacoes.

Acoes:

- criar tendencia manual;
- importar tendencias;
- gerar ideias das tendencias selecionadas;
- marcar como descartada;
- abrir link de referencia.

Filtros:

- prioridade;
- status;
- tema;
- fonte.

## Ideias

Tabela com:

- tema;
- hook;
- angulo;
- tipo;
- publico/dor;
- CTA;
- prioridade;
- status;
- link origem;
- observacoes.

Acoes:

- gerar ideias a partir do radar;
- editar ideia;
- aprovar para roteiro;
- gerar roteiro;
- rejeitar.

Status sugeridos:

- Ideia gerada
- Em revisao
- Aprovada para roteiro
- Roteiro gerado
- Rejeitada

## Roteiros

Tabela com:

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
- status;
- aprovador;
- data aprovacao;
- link doc/video.

View detalhada:

- editor do roteiro;
- painel de compliance;
- historico de status;
- botao aprovar;
- botao rejeitar;
- botao enviar para producao de video.

Status sugeridos:

- Aguardando validacao medica
- Ajustes solicitados
- Aprovado para video
- Video solicitado
- Video pronto
- Video aprovado
- Rejeitado

## Producao de Videos

Objetivo: acompanhar jobs de video.

Tabela com:

- video_id;
- roteiro;
- titulo;
- avatar;
- voz;
- status;
- criado em;
- atualizado em;
- duracao;
- video_url;
- thumbnail_url;
- erro.

Acoes:

- criar video a partir de roteiro selecionado;
- atualizar status do job;
- abrir video;
- baixar legenda quando disponivel;
- marcar video aprovado.

Observacao: chamadas HeyGen devem ser feitas por backend seguro.

## Calendario

Tabela ou calendario mensal com:

- data publicacao;
- canal;
- tema;
- formato;
- titulo/hook;
- responsavel;
- asset pronto;
- status;
- link post;
- observacoes.

Acoes:

- criar agendamento;
- vincular video aprovado;
- marcar como publicado;
- registrar link do post.

## Performance

Tabela com:

- data;
- canal;
- tema;
- views;
- retencao percentual;
- comentarios;
- salvamentos;
- compartilhamentos;
- novos seguidores;
- cliques;
- leads;
- nota;
- aprendizado;
- link post.

Graficos:

- views por tema;
- leads por tema;
- retencao media;
- salvamentos/compartilhamentos por post;
- top 5 conteudos.

## Configuracoes

Campos:

- avatar padrao HeyGen;
- voz padrao HeyGen;
- spreadsheet id opcional;
- canal principal;
- responsavel padrao;
- palavras-chave monitoradas;
- thresholds de prioridade.

Nunca mostrar valores completos de chaves secretas no frontend.
