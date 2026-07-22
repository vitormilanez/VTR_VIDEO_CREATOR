# Lovable Spec - AI Video Creator

Esta pasta prepara o projeto para ser reconstruido no Lovable como um app web.

Use estes arquivos como briefing:

- `lovable-prompt.md`: prompt principal para colar no Lovable.
- `screens-and-flows.md`: telas, navegacao e fluxos esperados.
- `data-model.md`: modelo de dados sugerido para Supabase/Postgres.
- `api-and-integrations.md`: como adaptar Google Sheets, HeyGen, Instagram e busca de tendencias.
- `compliance-rules.md`: regras de seguranca editorial e medica.

## Objetivo da migracao

Transformar o projeto atual, que roda como scripts Python e dashboard local, em um web app operacional para gerenciar:

1. tendencias;
2. ideias;
3. roteiros;
4. validacao medica;
5. producao de videos;
6. calendario;
7. performance.

O Lovable deve tratar o codigo Python atual como referencia de produto e regras de negocio, nao como codigo que precisa rodar diretamente no navegador.

## Decisao recomendada

Criar um app novo no Lovable com:

- React/Vite ou stack padrao do Lovable;
- Supabase como banco e autenticacao;
- Edge Functions ou backend seguro para chamadas externas;
- chaves de API sempre em variaveis de ambiente do servidor;
- nenhuma chamada HeyGen/Meta feita direto pelo frontend.

## Referencias do projeto atual

- Fluxo geral: `../README.md`
- Dashboard local: `../dashboard/app.py`
- Tendencias: `../trend_hunter/trend_hunter.py`
- Ideias: `../generate_ideas_from_radar.py`
- Roteiros: `../generate_scripts_from_ideas.py`
- Sheets: `../docs/google-sheets-clients.md`
- HeyGen: `../integrations/heygen_client.py`
