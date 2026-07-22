# Roadmap - Automacao de Videos com IA

## Visao do produto

Criar uma automacao vendavel para profissionais que precisam transformar tendencias em videos curtos, com revisao humana antes de gerar video e publicar.

Fluxo macro:

1. Buscar tendencias.
2. Analisar e interpretar relevancia.
3. Criar ideias de conteudo.
4. Gerar roteiro.
5. Esperar aprovacao humana.
6. Gerar video em ferramenta de IA.
7. Opcionalmente agendar/publicar via ferramenta de social media.

## Fluxo para o Dr. Guilherme

1. `trend_hunter.py` coleta noticias e tendencias sobre obesidade, emagrecimento, GLP-1, Mounjaro, Ozempic, dieta, metabolismo e saude metabolica.
2. O sistema transforma as melhores tendencias em ideias de Reels.
3. Cada ideia vira um roteiro curto com:
   - tema;
   - hook;
   - roteiro de 30 segundos;
   - CTA;
   - cuidado medico/compliance.
4. O Dr. Guilherme ou o time aprova, ajusta ou rejeita.
5. Depois da aprovacao, o sistema pode enviar o roteiro para uma ferramenta de criacao de video.
6. Depois de aprovado o video final, o sistema pode enviar para agendamento/publicacao.

## Integracoes cogitadas

### HeyGen

Possivel uso para geracao de videos com avatar ou apresentador por IA.

Observacoes:

- Existe indicacao de conta Business+ para o perfil do Dr. Guilherme.
- A ferramenta aparenta ter API.
- Antes de integrar, confirmar:
  - acesso real da conta;
  - disponibilidade da API no plano atual;
  - modelo de custo por credito/minuto;
  - limites de uso;
  - formato de entrada aceito pela API;
  - formato de saida do video.

Credenciais nunca devem ser salvas em arquivos do projeto. Usar variaveis de ambiente, por exemplo:

```bash
export HEYGEN_API_KEY="..."
```

### Grok

Possivel uso para geracao ou apoio criativo, caso o fluxo dependa de criacao dentro do Grok.

Ponto de atencao:

- Se nao houver API adequada, pode ser necessario manter essa etapa manual ou trocar por uma API com melhor automacao.

### SocialPilot

Possivel uso para agendamento e publicacao automatica.

Antes de integrar, confirmar:

- disponibilidade de API no plano;
- redes sociais conectadas;
- permissao para postar Reels/Shorts/TikTok;
- se a API aceita upload direto de video;
- se permite fluxo de rascunho/aprovacao;
- custo e limites.

## Modelo de estados

Cada pauta/video deve passar por estados claros:

- `trend_detected`: tendencia coletada.
- `idea_generated`: ideia de Reel criada.
- `script_generated`: roteiro criado.
- `needs_review`: aguardando aprovacao humana.
- `approved`: aprovado para gerar video.
- `rejected`: rejeitado.
- `video_requested`: pedido enviado para ferramenta de video.
- `video_ready`: video gerado.
- `video_approved`: video final aprovado.
- `scheduled`: agendado.
- `published`: publicado.

## Regra principal

Nenhuma etapa que gaste creditos, gere video final ou publique conteudo deve acontecer sem aprovacao explicita.

## Compliance medico

- Nao prescrever medicamentos.
- Nao citar doses.
- Nao prometer resultado.
- Nao fazer sensacionalismo medico.
- Nao usar IA como fonte medica final.
- Validar informacao medica antes de gravar/publicar.
- Reforcar que medicacao exige indicacao, acompanhamento e avaliacao individual.

## Proximas entregas sugeridas

### 1. Gerador de ideias

Criar:

```text
trend_hunter/ideas_generator.py
```

Funcao:

- ler o CSV mais recente em `trend_hunter/output`;
- selecionar as melhores tendencias;
- gerar `ideias_reels_AAAA-MM-DD.md`;
- incluir tema, hook, roteiro, CTA e cuidado medico.

### 2. Camada de aprovacao

Criar um arquivo de trabalho, inicialmente em Markdown ou JSON, para marcar cada ideia como:

- aprovada;
- rejeitada;
- precisa de ajuste.

### 3. Integracao HeyGen

Criar modulo separado:

```text
integrations/heygen_client.py
```

Somente depois de confirmar API key, endpoints e custos.

### 4. Integracao SocialPilot

Criar modulo separado:

```text
integrations/socialpilot_client.py
```

Somente depois de confirmar permissao de API para upload/agendamento de videos.
