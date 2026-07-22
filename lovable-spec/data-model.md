# Modelo de Dados Sugerido

Use Supabase/Postgres. Os nomes abaixo sao sugestao para uma primeira versao.

## `trends`

```sql
create table trends (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  trend_date date,
  theme text not null,
  subtheme text,
  source text,
  reference_url text,
  trend_signal text,
  audience_pain text,
  viral_potential integer default 1 check (viral_potential between 1 and 10),
  priority text not null default 'Media',
  status text not null default 'Pendente',
  notes text
);
```

## `ideas`

```sql
create table ideas (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  trend_id uuid references trends(id) on delete set null,
  theme text not null,
  hook text not null,
  angle text,
  content_type text not null default 'Reel',
  audience_pain text,
  cta text,
  priority text not null default 'Media',
  status text not null default 'Ideia gerada',
  origin_url text,
  notes text
);
```

## `scripts`

```sql
create table scripts (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  idea_id uuid references ideas(id) on delete set null,
  category text not null default 'Educativo',
  theme text not null,
  title text not null,
  hook text,
  conflict text,
  simple_explanation text,
  turn text,
  cta text,
  medical_care text,
  risk text not null default 'Medio',
  suggested_format text not null default 'Avatar medico falando',
  status text not null default 'Aguardando validacao medica',
  approver text,
  approved_at timestamptz,
  asset_url text,
  script_text text
);
```

## `video_jobs`

```sql
create table video_jobs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  script_id uuid references scripts(id) on delete set null,
  provider text not null default 'heygen',
  provider_video_id text,
  title text,
  avatar_id text,
  voice_id text,
  status text not null default 'waiting',
  duration_seconds numeric,
  video_url text,
  captioned_video_url text,
  subtitle_url text,
  thumbnail_url text,
  video_page_url text,
  failure_code text,
  failure_message text
);
```

## `calendar_posts`

```sql
create table calendar_posts (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  script_id uuid references scripts(id) on delete set null,
  video_job_id uuid references video_jobs(id) on delete set null,
  publish_date date,
  channel text not null default 'Instagram',
  theme text,
  format text not null default 'Reel',
  title_or_hook text,
  owner text,
  asset_ready boolean not null default false,
  status text not null default 'Pendente',
  post_url text,
  notes text
);
```

## `performance_metrics`

```sql
create table performance_metrics (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  calendar_post_id uuid references calendar_posts(id) on delete set null,
  metric_date date,
  channel text not null default 'Instagram',
  theme text,
  views integer not null default 0,
  retention_percent numeric not null default 0,
  comments integer not null default 0,
  saves integer not null default 0,
  shares integer not null default 0,
  new_followers integer not null default 0,
  clicks integer not null default 0,
  leads integer not null default 0,
  score_note text,
  learning text,
  post_url text
);
```

## `app_settings`

```sql
create table app_settings (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);
```

## Indices uteis

```sql
create index trends_status_idx on trends(status);
create index trends_priority_idx on trends(priority);
create index ideas_status_idx on ideas(status);
create index scripts_status_idx on scripts(status);
create index video_jobs_status_idx on video_jobs(status);
create index calendar_posts_publish_date_idx on calendar_posts(publish_date);
create index performance_metrics_theme_idx on performance_metrics(theme);
```
