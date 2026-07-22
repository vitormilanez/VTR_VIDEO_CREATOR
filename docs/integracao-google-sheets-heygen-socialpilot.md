# Integracao - Google Sheets, HeyGen e SocialPilot

## Fonte de verdade

O Google Sheets pode ser a central operacional do projeto. A planilha analisada tem abas suficientes para controlar a esteira completa:

- URL da planilha:
  `https://docs.google.com/spreadsheets/d/1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ/edit`
- Spreadsheet ID:
  `1qI4NrKAXV8Tcf2LsmG3-UpoFpSuzbi-cQ0A5o3CSPJQ`

- Conta Google operacional:
  `vtrconsultingbr@gmail.com`

- `Dashboard`: visao geral de metricas.
- `Radar Tendencias`: entrada de temas e sinais de tendencia.
- `Ideias`: ideias editoriais geradas a partir do radar.
- `Roteiros`: roteiros prontos ou aguardando validacao.
- `Calendario`: planejamento de publicacao.
- `Performance`: resultados depois da publicacao.
- `Prompts`: prompts-base para geracao de ideias e roteiros.
- `Config`: listas de apoio, status, prioridade e tipos.

## Pipeline recomendado

1. `trend_hunter.py` coleta tendencias externas e gera CSV/JSON.
2. Um importador sincroniza as melhores tendencias com a aba `Radar Tendencias`.
3. Um gerador de ideias le a aba `Radar Tendencias` e preenche a aba `Ideias`.
4. Um gerador de roteiros le ideias aprovadas e preenche a aba `Roteiros`.
5. O time ou Dr. Guilherme revisa a aba `Roteiros`.
6. Apenas roteiros com status aprovado sao enviados para geracao de video.
7. O modulo HeyGen solicita a criacao do video.
8. O link do video gerado volta para `Roteiros` ou `Calendario`.
9. O time aprova o video final.
10. O modulo SocialPilot agenda/publica o conteudo aprovado.
11. Resultados entram na aba `Performance`.

## Estados sugeridos

Usar status explicitos para evitar automacao perigosa:

- `Pendente`
- `Em pesquisa`
- `Ideia gerada`
- `Roteiro gerado`
- `Aguardando validacao medica`
- `Aprovado para video`
- `Video solicitado`
- `Video pronto`
- `Video aprovado`
- `Agendado`
- `Publicado`
- `Rejeitado`

## Regras de seguranca

- Nao gerar video automaticamente sem status `Aprovado para video`.
- Nao publicar automaticamente sem status `Video aprovado`.
- Nao gravar credenciais na planilha nem no repositorio.
- Usar variaveis de ambiente para chaves:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="caminho/seguro/service-account.json"
export HEYGEN_API_KEY="..."
export SOCIALPILOT_API_KEY="..."
```

## Integracao com Google Sheets

Existem duas opcoes:

### Opcao 1 - Exportar XLSX manualmente

Mais simples para comecar.

Fluxo:

1. Baixar a planilha do Google Sheets como `.xlsx`.
2. Rodar scripts locais para ler o arquivo.
3. Gerar arquivos Markdown/CSV/JSON com ideias e roteiros.

Vantagem: rapido, sem configurar API.

Limite: nao atualiza o Google Sheets automaticamente.

### Opcao 1B - Google Sheets publico somente leitura

Boa para MVP.

Fluxo:

1. Configurar a planilha como `Qualquer pessoa com o link pode visualizar`.
2. Ler as abas via export CSV publico.
3. Gerar ideias, roteiros e arquivos locais.

Vantagem: nao precisa login, OAuth nem service account.

Limite: leitura apenas. Para escrever de volta na planilha, ainda precisa API.

### Opcao 2 - API do Google Sheets

Melhor para automacao completa.

Fluxo:

1. Criar projeto no Google Cloud.
2. Ativar Google Sheets API.
3. Criar service account.
4. Compartilhar a planilha com o email da service account.
5. Usar a API para ler e escrever nas abas.

Vantagem: fluxo automatizado de verdade.

Limite: exige setup inicial de credenciais.

## Integracao com HeyGen

Objetivo: transformar roteiros aprovados em videos.

Entrada esperada:

- titulo;
- roteiro;
- formato;
- avatar/template;
- idioma;
- CTA;
- instrucoes de tom.

Saida esperada:

- id do job;
- status;
- link do video;
- custo/credito consumido, se a API retornar.

O modulo deve ficar separado:

```text
integrations/heygen_client.py
```

Regra: o cliente HeyGen so deve ser chamado para linhas com status `Aprovado para video`.

## Integracao com SocialPilot

Objetivo: agendar ou publicar videos aprovados.

Entrada esperada:

- canal;
- data de publicacao;
- legenda;
- link ou arquivo de video;
- hashtags;
- status de aprovacao.

Saida esperada:

- id do post/agendamento;
- status;
- link do post quando publicado.

O modulo deve ficar separado:

```text
integrations/socialpilot_client.py
```

Regra: o cliente SocialPilot so deve ser chamado para linhas com status `Video aprovado`.

## Entregas praticas em ordem

### Fase 1 - Local e segura

- Ler o XLSX exportado.
- Transformar `Radar Tendencias` em ideias.
- Transformar `Ideias` em roteiros.
- Gerar Markdown para revisao.

### Fase 2 - Google Sheets API

- Ler/escrever direto no Google Sheets.
- Usar a planilha como painel de aprovacao.
- Atualizar status automaticamente.

Script inicial criado:

```text
sync_trends_to_sheets.py
```

Funcao:

- ler o CSV mais recente do Trend Hunter;
- deduplicar tendencias ja presentes na aba;
- enviar as melhores linhas para `Radar Tendencias`;
- manter status inicial como `Pendente`.

Script de ideias criado:

```text
generate_ideas_from_radar.py
```

Funcao:

- ler tendencias pendentes da aba `Radar Tendencias`;
- gerar ideias de Reels com hook, angulo, publico/dor, CTA e observacoes;
- preencher a aba `Ideias`;
- marcar as linhas processadas no Radar como `Ideia gerada`.

Setup detalhado:

```text
docs/setup-google-sheets-api.md
```

### Fase 3 - HeyGen

- Enviar roteiros aprovados para geracao de video.
- Buscar status do job.
- Salvar link do video na planilha.

### Fase 4 - SocialPilot

- Agendar videos aprovados.
- Atualizar calendario.
- Registrar link do post publicado.

### Fase 5 - Performance

- Importar metricas das redes ou preencher manualmente.
- Usar performance para melhorar ranking e prompts.
