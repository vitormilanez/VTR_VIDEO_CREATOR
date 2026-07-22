# Projeto AI VIDEO CREATOR - Dr. Guilherme

## Objetivo

Criar um sistema de apoio para producao de videos curtos com IA sobre obesidade, emagrecimento, GLP-1, Mounjaro, Ozempic, dieta, metabolismo e saude metabolica.

O projeto nao substitui avaliacao medica. Ele serve para detectar tendencias, organizar ideias e acelerar o processo editorial antes da validacao final do Dr. Guilherme.

## Primeiro modulo: Trend Hunter

Arquivo principal:

```text
trend_hunter/trend_hunter.py
```

O script:

- busca tendencias por dia, semana, quinzena e mes;
- usa Google News RSS gratis;
- opcionalmente usa SerpAPI para Google Trends se houver `SERPAPI_KEY`;
- ranqueia temas por relevancia;
- gera CSV e JSON;
- inclui periodo, fonte, trend, score, termos encontrados, angulo de conteudo, cuidado medico/compliance e link da fonte.

## Como rodar

```bash
cd "CAMINHO/DA/PASTA/AI VIDEO CREATOR/trend_hunter"
python3 -m venv ../.venv
../.venv/bin/python -m pip install -r requirements.txt
../.venv/bin/python trend_hunter.py
```

## Resultados esperados

Os arquivos serao criados em:

```text
trend_hunter/output/trends_AAAA-MM-DD.csv
trend_hunter/output/trends_AAAA-MM-DD.json
```

## Fluxo editorial

1. Rodar o Trend Hunter.
2. Abrir o CSV/JSON em `trend_hunter/output`.
3. Escolher tendencias com bom score.
4. Transformar em ideias de Reels.
5. Criar hook, conflito, explicacao simples, virada e CTA.
6. Validar a parte medica com Dr. Guilherme antes de publicar.

## Estrutura sugerida para Reels

### Hook

Uma frase curta que captura atencao sem prometer resultado.

Exemplos:

- "O problema nao e so falta de forca de vontade."
- "Por que tanta gente volta a engordar depois de emagrecer?"
- "O que a noticia sobre GLP-1 realmente significa?"

### Conflito

Apontar a duvida, mito ou tensao que a audiencia ja sente.

### Explicacao simples

Traduzir o mecanismo medico em linguagem acessivel.

### Virada

Mostrar uma mudanca de perspectiva: do julgamento para compreensao, do atalho para acompanhamento, da promessa para tratamento individualizado.

### CTA

Convidar para salvar, compartilhar, comentar uma duvida ou procurar avaliacao individual, sem induzir automedicacao.

## Cuidados de compliance medico

- Nao prescrever medicamentos.
- Nao citar doses.
- Nao prometer resultado.
- Nao fazer sensacionalismo medico.
- Nao usar IA como fonte medica final.
- Validar informacao medica antes de gravar/publicar.
- Evitar frases que transformem medicamento em solucao estetica rapida.
- Reforcar que obesidade e uma condicao multifatorial e que tratamento precisa de avaliacao individual.

## Proximos modulos possiveis

- Gerador de ideias de Reels a partir do CSV.
- Gerador de roteiro com hook, conflito, explicacao, virada e CTA.
- Painel web simples para selecionar tendencias e aprovar pautas.
- Biblioteca de angulos por tema: GLP-1, comportamento alimentar, metabolismo, exercicio, sono, compulsoes e efeito sanfona.
- Checklist automatico de compliance antes da publicacao.
