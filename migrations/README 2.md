# Migrations PostgreSQL

As migrations usam `DATABASE_URL` e o driver psycopg 3.

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic downgrade -1
```

O metadata fica em `api/database/models/`. Alterações de schema devem gerar
uma nova revision; migrations já aplicadas nunca devem importar ou chamar
`Base.metadata.create_all()`.

Crie uma revisão candidata com:

```bash
.venv/bin/alembic revision --autogenerate -m "descricao da alteracao"
```

Revise o arquivo gerado antes de aplicá-lo, especialmente constraints
declaradas com `use_alter=True`, policies RLS e operações destrutivas. O teste
de fundação aplica a cadeia completa em um cluster PostgreSQL temporário,
compara o banco ao metadata e executa o downgrade:

```bash
.venv/bin/python -m pytest -q tests/test_database_foundation.py
```

Em produção, a role usada pelo FastAPI não deve ser dona das tabelas nem ter
`BYPASSRLS`. Cada transação de negócio deve passar por
`Database.tenant_transaction()` para configurar `app.user_id` e
`app.organization_id` localmente à transação.
