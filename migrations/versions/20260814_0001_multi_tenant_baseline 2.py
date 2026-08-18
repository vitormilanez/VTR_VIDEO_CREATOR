"""multi tenant baseline

Revision ID: 20260814_0001
Revises:
Create Date: 2026-08-14 10:59:55.146323
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '20260814_0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_TABLES = (
    'ai_response_cache',
    'ai_usage',
    'asset_variants',
    'audit_events',
    'avatar_identities',
    'avatar_looks',
    'avatar_set_looks',
    'avatar_sets',
    'calendar_posts',
    'ideas',
    'job_events',
    'jobs',
    'legacy_id_map',
    'legacy_import_runs',
    'media_assets',
    'organization_memberships',
    'organization_settings',
    'performance_metrics',
    'production_profiles',
    'provider_capabilities',
    'provider_connections',
    'scene_plans',
    'script_editor_states',
    'script_reviews',
    'script_versions',
    'scripts',
    'social_accounts',
    'story_critiques',
    'story_projects',
    'story_shot_generations',
    'story_shots',
    'story_versions',
    'trends',
    'video_slide_renders',
    'visual_packs',
    'visual_plans',
    'voices',
)

ADMIN_WRITE_TABLES = {
    'legacy_id_map',
    'legacy_import_runs',
    'organization_settings',
    'provider_capabilities',
    'provider_connections',
}

SPECIAL_POLICY_TABLES = {'audit_events', 'organization_memberships'}


def _create_rls_helpers() -> None:
    op.execute(
        sa.text(
            """
            CREATE SCHEMA IF NOT EXISTS app;

            CREATE OR REPLACE FUNCTION app.current_user_id()
            RETURNS uuid
            LANGUAGE plpgsql
            STABLE
            AS $$
            DECLARE
                raw_value text;
            BEGIN
                raw_value := NULLIF(current_setting('app.user_id', true), '');
                IF raw_value IS NOT NULL THEN
                    RETURN raw_value::uuid;
                END IF;

                raw_value := NULLIF(current_setting('request.jwt.claim.sub', true), '');
                IF raw_value IS NOT NULL THEN
                    RETURN raw_value::uuid;
                END IF;

                raw_value := NULLIF(current_setting('request.jwt.claims', true), '');
                IF raw_value IS NOT NULL THEN
                    RETURN NULLIF(raw_value::jsonb ->> 'sub', '')::uuid;
                END IF;

                RETURN NULL;
            EXCEPTION
                WHEN invalid_text_representation THEN
                    RETURN NULL;
            END;
            $$;

            CREATE OR REPLACE FUNCTION app.organization_scope_allows(target_organization_id uuid)
            RETURNS boolean
            LANGUAGE sql
            STABLE
            AS $$
                SELECT COALESCE(
                    NULLIF(current_setting('app.organization_id', true), '')::uuid
                        = target_organization_id,
                    true
                );
            $$;

            CREATE OR REPLACE FUNCTION app.is_organization_member(
                target_organization_id uuid,
                allowed_roles text[] DEFAULT NULL
            )
            RETURNS boolean
            LANGUAGE sql
            STABLE
            SECURITY DEFINER
            SET search_path = public, pg_temp
            AS $$
                SELECT EXISTS (
                    SELECT 1
                    FROM public.organization_memberships membership
                    WHERE membership.organization_id = target_organization_id
                      AND membership.user_id = app.current_user_id()
                      AND membership.status = 'active'
                      AND (allowed_roles IS NULL OR membership.role = ANY(allowed_roles))
                );
            $$;

            CREATE OR REPLACE FUNCTION app.shares_organization_with(target_user_id uuid)
            RETURNS boolean
            LANGUAGE sql
            STABLE
            SECURITY DEFINER
            SET search_path = public, pg_temp
            AS $$
                SELECT target_user_id = app.current_user_id()
                    OR EXISTS (
                        SELECT 1
                        FROM public.organization_memberships mine
                        JOIN public.organization_memberships theirs
                          ON theirs.organization_id = mine.organization_id
                        WHERE mine.user_id = app.current_user_id()
                          AND mine.status = 'active'
                          AND theirs.user_id = target_user_id
                          AND theirs.status = 'active'
                    );
            $$;
            """
        )
    )


def _create_rls_policies() -> None:
    op.execute('ALTER TABLE organizations ENABLE ROW LEVEL SECURITY')
    op.execute(
        "CREATE POLICY organizations_tenant_select ON organizations FOR SELECT "
        "USING (app.organization_scope_allows(id) AND app.is_organization_member(id))"
    )
    op.execute(
        "CREATE POLICY organizations_tenant_update ON organizations FOR UPDATE "
        "USING (app.organization_scope_allows(id) AND "
        "app.is_organization_member(id, ARRAY['owner', 'admin'])) "
        "WITH CHECK (app.organization_scope_allows(id) AND "
        "app.is_organization_member(id, ARRAY['owner', 'admin']))"
    )

    op.execute('ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY')
    op.execute(
        "CREATE POLICY user_profiles_member_select ON user_profiles FOR SELECT "
        "USING (app.shares_organization_with(id))"
    )
    op.execute(
        "CREATE POLICY user_profiles_self_insert ON user_profiles FOR INSERT "
        "WITH CHECK (id = app.current_user_id())"
    )
    op.execute(
        "CREATE POLICY user_profiles_self_update ON user_profiles FOR UPDATE "
        "USING (id = app.current_user_id()) WITH CHECK (id = app.current_user_id())"
    )

    for table_name in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')

    op.execute(
        "CREATE POLICY organization_memberships_tenant_select ON organization_memberships "
        "FOR SELECT USING (app.organization_scope_allows(organization_id) AND "
        "app.is_organization_member(organization_id))"
    )
    for operation in ('INSERT', 'UPDATE', 'DELETE'):
        policy_name = f'organization_memberships_tenant_{operation.lower()}'
        predicate = (
            "app.organization_scope_allows(organization_id) AND "
            "app.is_organization_member(organization_id, ARRAY['owner', 'admin'])"
        )
        if operation == 'INSERT':
            op.execute(
                f"CREATE POLICY {policy_name} ON organization_memberships FOR INSERT "
                f"WITH CHECK ({predicate})"
            )
        elif operation == 'UPDATE':
            op.execute(
                f"CREATE POLICY {policy_name} ON organization_memberships FOR UPDATE "
                f"USING ({predicate}) WITH CHECK ({predicate})"
            )
        else:
            op.execute(
                f"CREATE POLICY {policy_name} ON organization_memberships FOR DELETE "
                f"USING ({predicate})"
            )

    op.execute(
        "CREATE POLICY audit_events_tenant_select ON audit_events FOR SELECT "
        "USING (app.organization_scope_allows(organization_id) AND "
        "app.is_organization_member(organization_id))"
    )
    op.execute(
        "CREATE POLICY audit_events_tenant_insert ON audit_events FOR INSERT "
        "WITH CHECK (app.organization_scope_allows(organization_id) AND "
        "app.is_organization_member(organization_id))"
    )

    for table_name in TENANT_TABLES:
        if table_name in SPECIAL_POLICY_TABLES:
            continue
        write_roles = (
            "ARRAY['owner', 'admin']"
            if table_name in ADMIN_WRITE_TABLES
            else "ARRAY['owner', 'admin', 'editor', 'reviewer']"
            if table_name == 'script_reviews'
            else "ARRAY['owner', 'admin', 'editor']"
        )
        read_predicate = (
            "app.organization_scope_allows(organization_id) AND "
            "app.is_organization_member(organization_id)"
        )
        write_predicate = (
            "app.organization_scope_allows(organization_id) AND "
            f"app.is_organization_member(organization_id, {write_roles})"
        )
        op.execute(
            f'CREATE POLICY "{table_name}_tenant_select" ON "{table_name}" '
            f'FOR SELECT USING ({read_predicate})'
        )
        op.execute(
            f'CREATE POLICY "{table_name}_tenant_insert" ON "{table_name}" '
            f'FOR INSERT WITH CHECK ({write_predicate})'
        )
        op.execute(
            f'CREATE POLICY "{table_name}_tenant_update" ON "{table_name}" '
            f'FOR UPDATE USING ({write_predicate}) WITH CHECK ({write_predicate})'
        )
        op.execute(
            f'CREATE POLICY "{table_name}_tenant_delete" ON "{table_name}" '
            f'FOR DELETE USING ({write_predicate})'
        )


def _drop_rls_helpers() -> None:
    # As policies dependem das funções. CASCADE remove somente essas policies e
    # os helpers pertencentes ao schema criado por esta migration.
    op.execute('DROP SCHEMA IF EXISTS app CASCADE')


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('organizations',
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('timezone', sa.String(length=80), server_default=sa.text("'America/Sao_Paulo'"), nullable=False),
    sa.Column('locale', sa.String(length=20), server_default=sa.text("'pt-BR'"), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('active', 'suspended', 'archived')", name=op.f('ck_organizations_organization_status')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organizations')),
    sa.UniqueConstraint('slug', name=op.f('uq_organizations_slug'))
    )
    op.create_table('user_profiles',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=True),
    sa.Column('avatar_url', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_profiles')),
    sa.UniqueConstraint('email', name=op.f('uq_user_profiles_email'))
    )
    op.create_table('ai_response_cache',
    sa.Column('cache_key', sa.String(length=180), nullable=False),
    sa.Column('operation', sa.String(length=120), nullable=False),
    sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_ai_response_cache_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_response_cache')),
    sa.UniqueConstraint('organization_id', 'cache_key', name='uq_ai_response_cache_org_cache_key'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_ai_response_cache_org_id_id')
    )
    op.create_index('ix_ai_response_cache_expires', 'ai_response_cache', ['expires_at'], unique=False)
    op.create_index('ix_ai_response_cache_org_operation', 'ai_response_cache', ['organization_id', 'operation'], unique=False)
    op.create_table('audit_events',
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.String(length=120), nullable=False),
    sa.Column('entity_type', sa.String(length=80), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['user_profiles.id'], name=op.f('fk_audit_events_actor_user_id_user_profiles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_audit_events_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_audit_events_organization_id_id')
    )
    op.create_index('ix_audit_events_org_created', 'audit_events', ['organization_id', 'created_at'], unique=False)
    op.create_index('ix_audit_events_org_entity', 'audit_events', ['organization_id', 'entity_type', 'entity_id'], unique=False)
    op.create_table('avatar_identities',
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('provider', sa.String(length=40), server_default=sa.text("'heygen'"), nullable=False),
    sa.Column('provider_group_id', sa.String(length=240), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'processing', 'ready', 'error', 'archived')", name=op.f('ck_avatar_identities_avatar_identity_status')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_avatar_identities_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_avatar_identities')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_avatar_identities_org_id_id'),
    sa.UniqueConstraint('organization_id', 'provider', 'provider_group_id', name='uq_avatar_identities_provider_group')
    )
    op.create_index('ix_avatar_identities_org_status', 'avatar_identities', ['organization_id', 'status'], unique=False)
    op.create_table('legacy_import_runs',
    sa.Column('source', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'running'"), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status IN ('running', 'succeeded', 'failed', 'rolled_back')", name=op.f('ck_legacy_import_runs_legacy_import_run_status')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_legacy_import_runs_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_legacy_import_runs')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_legacy_import_runs_org_id_id')
    )
    op.create_index('ix_legacy_import_runs_org_started', 'legacy_import_runs', ['organization_id', 'started_at'], unique=False)
    op.create_table('media_assets',
    sa.Column('kind', sa.String(length=80), nullable=False),
    sa.Column('storage_bucket', sa.String(length=120), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('original_filename', sa.Text(), nullable=True),
    sa.Column('mime_type', sa.String(length=160), nullable=True),
    sa.Column('byte_size', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'uploading', 'ready', 'error', 'archived')", name=op.f('ck_media_assets_media_asset_status')),
    sa.CheckConstraint('byte_size >= 0', name=op.f('ck_media_assets_media_asset_byte_size')),
    sa.ForeignKeyConstraint(['created_by'], ['user_profiles.id'], name=op.f('fk_media_assets_created_by_user_profiles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_media_assets_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media_assets')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_media_assets_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'storage_bucket', 'storage_key', name='uq_media_assets_storage_key')
    )
    op.create_index('ix_media_assets_org_kind_created', 'media_assets', ['organization_id', 'kind', 'created_at'], unique=False)
    op.create_index('ix_media_assets_org_sha256', 'media_assets', ['organization_id', 'sha256'], unique=False)
    op.create_table('organization_memberships',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=20), server_default=sa.text("'viewer'"), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
    sa.Column('invited_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('owner', 'admin', 'editor', 'reviewer', 'viewer')", name=op.f('ck_organization_memberships_membership_role')),
    sa.CheckConstraint("status IN ('active', 'invited', 'suspended')", name=op.f('ck_organization_memberships_membership_status')),
    sa.ForeignKeyConstraint(['invited_by'], ['user_profiles.id'], name=op.f('fk_organization_memberships_invited_by_user_profiles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_organization_memberships_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user_profiles.id'], name=op.f('fk_organization_memberships_user_id_user_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organization_memberships')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_memberships_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'user_id', name='uq_memberships_organization_user')
    )
    op.create_index('ix_memberships_user_status', 'organization_memberships', ['user_id', 'status'], unique=False)
    op.create_table('organization_settings',
    sa.Column('key', sa.String(length=120), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('schema_version', sa.String(length=40), server_default=sa.text("'1'"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_organization_settings_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organization_settings')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_org_settings_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'key', name='uq_org_settings_organization_key')
    )
    op.create_table('provider_capabilities',
    sa.Column('provider', sa.String(length=80), nullable=False),
    sa.Column('cli_version', sa.String(length=80), server_default=sa.text("''"), nullable=False),
    sa.Column('capabilities_version', sa.String(length=80), nullable=False),
    sa.Column('capabilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_provider_capabilities_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_provider_capabilities')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_provider_capabilities_org_id_id'),
    sa.UniqueConstraint('organization_id', 'provider', name='uq_provider_capabilities_org_provider')
    )
    op.create_table('provider_connections',
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('external_account_id', sa.String(length=240), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
    sa.Column('secret_ref', sa.Text(), nullable=True),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'active', 'error', 'revoked')", name=op.f('ck_provider_connections_provider_connection_status')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_provider_connections_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_provider_connections')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_provider_connections_org_id_id'),
    sa.UniqueConstraint('organization_id', 'provider', 'external_account_id', name='uq_provider_connections_external_account')
    )
    op.create_index('uq_provider_connections_default', 'provider_connections', ['organization_id', 'provider'], unique=True, postgresql_where=sa.text('external_account_id IS NULL'))
    op.create_table('trends',
    sa.Column('legacy_id', sa.String(length=120), nullable=True),
    sa.Column('trend_date', sa.Date(), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('subtheme', sa.String(length=500), nullable=True),
    sa.Column('source', sa.String(length=240), nullable=True),
    sa.Column('reference_url', sa.Text(), nullable=True),
    sa.Column('trend_signal', sa.Text(), nullable=True),
    sa.Column('audience_pain', sa.Text(), nullable=True),
    sa.Column('viral_potential', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('priority', sa.String(length=20), server_default=sa.text("'medium'"), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'new'"), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("priority IN ('high', 'medium', 'low')", name=op.f('ck_trends_trend_priority')),
    sa.CheckConstraint("status IN ('new', 'analyzing', 'discarded')", name=op.f('ck_trends_trend_status')),
    sa.CheckConstraint('viral_potential BETWEEN 0 AND 10', name=op.f('ck_trends_trend_viral_potential')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_trends_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_trends')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_trends_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'legacy_id', name='uq_trends_organization_legacy')
    )
    op.create_index('ix_trends_org_priority', 'trends', ['organization_id', 'priority'], unique=False)
    op.create_index('ix_trends_org_status_created', 'trends', ['organization_id', 'status', 'created_at'], unique=False)
    op.create_table('voices',
    sa.Column('provider', sa.String(length=40), server_default=sa.text("'heygen'"), nullable=False),
    sa.Column('provider_voice_id', sa.String(length=240), nullable=False),
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('language', sa.String(length=40), nullable=True),
    sa.Column('gender', sa.String(length=40), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('active', 'processing', 'error', 'archived')", name=op.f('ck_voices_voice_status')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_voices_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_voices')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_voices_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'provider', 'provider_voice_id', name='uq_voices_provider_voice')
    )
    op.create_index('ix_voices_org_status', 'voices', ['organization_id', 'status'], unique=False)
    op.create_table('asset_variants',
    sa.Column('media_asset_id', sa.Uuid(), nullable=False),
    sa.Column('variant', sa.String(length=80), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('mime_type', sa.String(length=160), nullable=True),
    sa.Column('byte_size', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('byte_size >= 0', name=op.f('ck_asset_variants_asset_variant_byte_size')),
    sa.ForeignKeyConstraint(['organization_id', 'media_asset_id'], ['media_assets.organization_id', 'media_assets.id'], name='fk_asset_variants_org_asset', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_asset_variants_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_asset_variants')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_asset_variants_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'media_asset_id', 'variant', name='uq_asset_variants_asset_variant')
    )
    op.create_table('avatar_looks',
    sa.Column('avatar_identity_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=40), server_default=sa.text("'heygen'"), nullable=False),
    sa.Column('provider_avatar_id', sa.String(length=240), nullable=False),
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('role_hint', sa.String(length=80), nullable=True),
    sa.Column('preview_asset_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'ready'"), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'processing', 'ready', 'error', 'archived')", name=op.f('ck_avatar_looks_avatar_look_status')),
    sa.ForeignKeyConstraint(['organization_id', 'avatar_identity_id'], ['avatar_identities.organization_id', 'avatar_identities.id'], name='fk_avatar_looks_org_identity', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'preview_asset_id'], ['media_assets.organization_id', 'media_assets.id'], name='fk_avatar_looks_org_preview_asset', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_avatar_looks_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_avatar_looks')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_avatar_looks_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'provider', 'provider_avatar_id', name='uq_avatar_looks_provider_avatar')
    )
    op.create_index('ix_avatar_looks_org_identity', 'avatar_looks', ['organization_id', 'avatar_identity_id'], unique=False)
    op.create_table('ideas',
    sa.Column('legacy_id', sa.String(length=120), nullable=True),
    sa.Column('trend_id', sa.Uuid(), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('family', sa.String(length=40), server_default=sa.text("'educational'"), nullable=False),
    sa.Column('hook', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('angle', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('content_type', sa.String(length=80), nullable=True),
    sa.Column('audience_pain', sa.Text(), nullable=True),
    sa.Column('cta', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('origin_url', sa.Text(), nullable=True),
    sa.Column('compliance_notes', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('priority', sa.String(length=20), server_default=sa.text("'medium'"), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'new'"), nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("priority IN ('high', 'medium', 'low')", name=op.f('ck_ideas_idea_priority')),
    sa.CheckConstraint("status IN ('new', 'analyzing', 'approved', 'discarded')", name=op.f('ck_ideas_idea_status')),
    sa.ForeignKeyConstraint(['organization_id', 'trend_id'], ['trends.organization_id', 'trends.id'], name='fk_ideas_org_trend', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_ideas_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ideas')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_ideas_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'legacy_id', name='uq_ideas_organization_legacy')
    )
    op.create_index('ix_ideas_org_status_created', 'ideas', ['organization_id', 'status', 'created_at'], unique=False)
    op.create_index('ix_ideas_org_trend', 'ideas', ['organization_id', 'trend_id'], unique=False)
    op.create_table('legacy_id_map',
    sa.Column('import_run_id', sa.Uuid(), nullable=False),
    sa.Column('source_system', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=80), nullable=False),
    sa.Column('source_key', sa.Text(), nullable=False),
    sa.Column('target_table', sa.String(length=80), nullable=False),
    sa.Column('target_id', sa.Uuid(), nullable=False),
    sa.Column('fingerprint', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'import_run_id'], ['legacy_import_runs.organization_id', 'legacy_import_runs.id'], name='fk_legacy_id_map_org_run', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_legacy_id_map_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_legacy_id_map')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_legacy_id_map_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'source_system', 'entity_type', 'source_key', name='uq_legacy_id_map_source_key')
    )
    op.create_index('ix_legacy_id_map_org_target', 'legacy_id_map', ['organization_id', 'target_table', 'target_id'], unique=False)
    op.create_table('social_accounts',
    sa.Column('provider_connection_id', sa.Uuid(), nullable=True),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('external_account_id', sa.String(length=240), nullable=False),
    sa.Column('username', sa.String(length=240), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('active', 'error', 'revoked', 'archived')", name=op.f('ck_social_accounts_social_account_status')),
    sa.ForeignKeyConstraint(['organization_id', 'provider_connection_id'], ['provider_connections.organization_id', 'provider_connections.id'], name='fk_social_accounts_org_connection', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_social_accounts_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_social_accounts')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_social_accounts_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'provider', 'external_account_id', name='uq_social_accounts_external')
    )
    op.create_table('avatar_sets',
    sa.Column('name', sa.String(length=240), nullable=False),
    sa.Column('voice_id', sa.Uuid(), nullable=True),
    sa.Column('primary_look_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('active', 'archived')", name=op.f('ck_avatar_sets_avatar_set_status')),
    sa.ForeignKeyConstraint(['organization_id', 'primary_look_id'], ['avatar_looks.organization_id', 'avatar_looks.id'], name='fk_avatar_sets_org_primary_look', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'voice_id'], ['voices.organization_id', 'voices.id'], name='fk_avatar_sets_org_voice', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_avatar_sets_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_avatar_sets')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_avatar_sets_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'name', name='uq_avatar_sets_organization_name')
    )
    op.create_table('scripts',
    sa.Column('legacy_id', sa.String(length=120), nullable=True),
    sa.Column('idea_id', sa.Uuid(), nullable=True),
    sa.Column('category', sa.String(length=80), server_default=sa.text("'educational'"), nullable=False),
    sa.Column('theme', sa.String(length=500), server_default=sa.text("''"), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('hook', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('conflict', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('simple_explanation', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('turn', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('cta', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('medical_care', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('risk', sa.String(length=20), server_default=sa.text("'medium'"), nullable=False),
    sa.Column('suggested_format', sa.String(length=120), server_default=sa.text("'Reels'"), nullable=False),
    sa.Column('status', sa.String(length=40), server_default=sa.text("'awaiting_validation'"), nullable=False),
    sa.Column('approver_name', sa.String(length=240), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_asset_url', sa.Text(), nullable=True),
    sa.Column('editorial_tone', sa.String(length=40), nullable=True),
    sa.Column('spoken_text', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('outro_text', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('generation_provider', sa.String(length=80), nullable=True),
    sa.Column('generation_flow_version', sa.String(length=100), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("risk IN ('low', 'medium', 'high')", name=op.f('ck_scripts_script_risk')),
    sa.CheckConstraint("status IN ('awaiting_validation', 'in_review', 'clinically_approved', 'rejected')", name=op.f('ck_scripts_script_status')),
    sa.ForeignKeyConstraint(['organization_id', 'idea_id'], ['ideas.organization_id', 'ideas.id'], name='fk_scripts_org_idea', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_scripts_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scripts')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_scripts_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'legacy_id', name='uq_scripts_organization_legacy')
    )
    op.create_index('ix_scripts_org_idea', 'scripts', ['organization_id', 'idea_id'], unique=False)
    op.create_index('ix_scripts_org_status_created', 'scripts', ['organization_id', 'status', 'created_at'], unique=False)
    op.create_table('avatar_set_looks',
    sa.Column('avatar_set_id', sa.Uuid(), nullable=False),
    sa.Column('avatar_look_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=80), nullable=False),
    sa.Column('label', sa.String(length=160), nullable=True),
    sa.Column('position', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('position >= 0', name=op.f('ck_avatar_set_looks_avatar_set_look_position')),
    sa.ForeignKeyConstraint(['organization_id', 'avatar_look_id'], ['avatar_looks.organization_id', 'avatar_looks.id'], name='fk_avatar_set_looks_org_look', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'avatar_set_id'], ['avatar_sets.organization_id', 'avatar_sets.id'], name='fk_avatar_set_looks_org_set', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_avatar_set_looks_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_avatar_set_looks')),
    sa.UniqueConstraint('organization_id', 'avatar_set_id', 'avatar_look_id', name='uq_avatar_set_looks_pair'),
    sa.UniqueConstraint('organization_id', 'avatar_set_id', 'role', name='uq_avatar_set_looks_role'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_avatar_set_looks_org_id_id')
    )
    op.create_index('ix_avatar_set_looks_org_set', 'avatar_set_looks', ['organization_id', 'avatar_set_id', 'position'], unique=False)
    op.create_table('production_profiles',
    sa.Column('script_id', sa.Uuid(), nullable=False),
    sa.Column('avatar_set_id', sa.Uuid(), nullable=True),
    sa.Column('avatar_look_id', sa.Uuid(), nullable=True),
    sa.Column('voice_id', sa.Uuid(), nullable=True),
    sa.Column('speech_mode', sa.String(length=40), server_default=sa.text("'natural'"), nullable=False),
    sa.Column('generation_mode', sa.String(length=40), server_default=sa.text("'avatar'"), nullable=False),
    sa.Column('avatar_mode', sa.String(length=20), server_default=sa.text("'single'"), nullable=False),
    sa.Column('position_count', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('music_asset_id', sa.Uuid(), nullable=True),
    sa.Column('music_volume', sa.Float(), server_default=sa.text('0.12'), nullable=False),
    sa.Column('cinematic_prompt', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('voice_mood', sa.String(length=80), server_default=sa.text("'confident'"), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('music_volume >= 0 AND music_volume <= 1', name=op.f('ck_production_profiles_production_profile_music_volume')),
    sa.CheckConstraint('position_count > 0', name=op.f('ck_production_profiles_production_profile_position_count')),
    sa.ForeignKeyConstraint(['organization_id', 'avatar_look_id'], ['avatar_looks.organization_id', 'avatar_looks.id'], name='fk_production_profiles_org_avatar_look', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'avatar_set_id'], ['avatar_sets.organization_id', 'avatar_sets.id'], name='fk_production_profiles_org_avatar_set', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'music_asset_id'], ['media_assets.organization_id', 'media_assets.id'], name='fk_production_profiles_org_music', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_production_profiles_org_script', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'voice_id'], ['voices.organization_id', 'voices.id'], name='fk_production_profiles_org_voice', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_production_profiles_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_production_profiles')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_production_profiles_org_id_id'),
    sa.UniqueConstraint('organization_id', 'script_id', name='uq_production_profiles_script')
    )
    op.create_table('scene_plans',
    sa.Column('script_id', sa.Uuid(), nullable=False),
    sa.Column('script_version_id', sa.Uuid(), nullable=True),
    sa.Column('plan', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('contract_version', sa.String(length=80), server_default=sa.text("'1'"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_scene_plans_org_script', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'script_version_id'], ['script_versions.organization_id', 'script_versions.id'], name='fk_scene_plans_org_script_version', ondelete='RESTRICT', use_alter=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_scene_plans_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scene_plans')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_scene_plans_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'script_id', name='uq_scene_plans_script')
    )
    op.create_table('script_editor_states',
    sa.Column('script_id', sa.Uuid(), nullable=False),
    sa.Column('duration_seconds', sa.Integer(), server_default=sa.text('45'), nullable=False),
    sa.Column('human_review_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('title_choice', sa.String(length=40), server_default=sa.text("'current'"), nullable=False),
    sa.Column('suggested_title', sa.Text(), nullable=True),
    sa.Column('schema_valid', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('technical_error', sa.Text(), nullable=True),
    sa.Column('previous_script', sa.Text(), nullable=True),
    sa.Column('last_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('script_revision', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('final_speech_hash', sa.String(length=128), nullable=True),
    sa.Column('approved_script_revision', sa.Integer(), nullable=True),
    sa.Column('approved_final_speech_hash', sa.String(length=128), nullable=True),
    sa.Column('approval_history', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('contract_version', sa.String(length=80), server_default=sa.text("''"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('duration_seconds > 0', name=op.f('ck_script_editor_states_script_editor_duration')),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_script_editor_states_org_script', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_script_editor_states_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_script_editor_states')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_script_editor_states_org_id_id'),
    sa.UniqueConstraint('organization_id', 'script_id', name='uq_script_editor_states_script')
    )
    op.create_table('script_versions',
    sa.Column('script_id', sa.Uuid(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('final_speech', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('final_speech_hash', sa.String(length=128), nullable=True),
    sa.Column('contract_version', sa.String(length=80), server_default=sa.text("'1'"), nullable=False),
    sa.Column('generation_provider', sa.String(length=80), nullable=True),
    sa.Column('generation_flow_version', sa.String(length=100), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('revision > 0', name=op.f('ck_script_versions_script_version_positive_revision')),
    sa.ForeignKeyConstraint(['created_by'], ['user_profiles.id'], name=op.f('fk_script_versions_created_by_user_profiles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_script_versions_org_script', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_script_versions_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_script_versions')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_script_versions_org_id_id'),
    sa.UniqueConstraint('organization_id', 'script_id', 'revision', name='uq_script_versions_revision')
    )
    op.create_index('ix_script_versions_org_script', 'script_versions', ['organization_id', 'script_id', 'revision'], unique=False)
    op.create_table('story_projects',
    sa.Column('script_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('active_story_version_id', sa.Uuid(), nullable=True),
    sa.Column('production_tier', sa.String(length=40), nullable=False),
    sa.Column('story_brief', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('budget', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'active_story_version_id'], ['story_versions.organization_id', 'story_versions.id'], name='fk_story_projects_org_active_version', ondelete='RESTRICT', use_alter=True),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_story_projects_org_script', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_story_projects_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_story_projects')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_story_projects_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'script_id', name='uq_story_projects_script')
    )
    op.create_index('ix_story_projects_org_status', 'story_projects', ['organization_id', 'status'], unique=False)
    op.create_table('video_slide_renders',
    sa.Column('script_id', sa.Uuid(), nullable=False),
    sa.Column('render', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('output_asset_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'output_asset_id'], ['media_assets.organization_id', 'media_assets.id'], name='fk_video_slide_renders_org_output_asset', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_video_slide_renders_org_script', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_video_slide_renders_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_video_slide_renders')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_video_slide_renders_org_id_id'),
    sa.UniqueConstraint('organization_id', 'script_id', name='uq_video_slide_renders_script')
    )
    op.create_table('visual_packs',
    sa.Column('script_id', sa.Uuid(), nullable=False),
    sa.Column('pack', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('source_avatar_look_id', sa.Uuid(), nullable=True),
    sa.Column('contract_version', sa.String(length=80), server_default=sa.text("'1'"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_visual_packs_org_script', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'source_avatar_look_id'], ['avatar_looks.organization_id', 'avatar_looks.id'], name='fk_visual_packs_org_avatar_look', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_visual_packs_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_visual_packs')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_visual_packs_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'script_id', name='uq_visual_packs_script')
    )
    op.create_table('visual_plans',
    sa.Column('script_id', sa.Uuid(), nullable=False),
    sa.Column('plan', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('contract_version', sa.String(length=80), server_default=sa.text("'1'"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_visual_plans_org_script', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_visual_plans_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_visual_plans')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_visual_plans_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'script_id', name='uq_visual_plans_script')
    )
    op.create_table('jobs',
    sa.Column('legacy_id', sa.String(length=120), nullable=True),
    sa.Column('kind', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=60), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('script_id', sa.Uuid(), nullable=True),
    sa.Column('script_version_id', sa.Uuid(), nullable=True),
    sa.Column('provider_connection_id', sa.Uuid(), nullable=True),
    sa.Column('provider', sa.String(length=80), nullable=True),
    sa.Column('external_job_id', sa.String(length=240), nullable=True),
    sa.Column('remote_session_id', sa.String(length=240), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('claimed_by', sa.String(length=160), nullable=True),
    sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('available_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('attempt_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('max_attempts', sa.Integer(), server_default=sa.text('3'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('attempt_count >= 0', name=op.f('ck_jobs_job_attempt_count')),
    sa.CheckConstraint('max_attempts > 0', name=op.f('ck_jobs_job_max_attempts')),
    sa.ForeignKeyConstraint(['organization_id', 'provider_connection_id'], ['provider_connections.organization_id', 'provider_connections.id'], name='fk_jobs_org_provider_connection', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_jobs_org_script', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'script_version_id'], ['script_versions.organization_id', 'script_versions.id'], name='fk_jobs_org_script_version', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_jobs_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_jobs_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'kind', 'idempotency_key', name='uq_jobs_org_kind_idempotency')
    )
    op.create_index('ix_jobs_org_kind_created', 'jobs', ['organization_id', 'kind', 'created_at'], unique=False)
    op.create_index('ix_jobs_org_script', 'jobs', ['organization_id', 'script_id', 'created_at'], unique=False)
    op.create_index('ix_jobs_org_status_available', 'jobs', ['organization_id', 'status', 'available_at'], unique=False)
    op.create_index('uq_jobs_org_remote_session', 'jobs', ['organization_id', 'remote_session_id'], unique=True, postgresql_where=sa.text('remote_session_id IS NOT NULL'))
    op.create_table('script_reviews',
    sa.Column('script_version_id', sa.Uuid(), nullable=False),
    sa.Column('reviewer_user_id', sa.Uuid(), nullable=True),
    sa.Column('review_type', sa.String(length=40), server_default=sa.text("'medical'"), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status IN ('open', 'approved', 'reopened', 'rejected')", name=op.f('ck_script_reviews_script_review_status')),
    sa.ForeignKeyConstraint(['organization_id', 'script_version_id'], ['script_versions.organization_id', 'script_versions.id'], name='fk_script_reviews_org_version', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_script_reviews_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewer_user_id'], ['user_profiles.id'], name=op.f('fk_script_reviews_reviewer_user_id_user_profiles'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_script_reviews')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_script_reviews_org_id_id')
    )
    op.create_index('ix_script_reviews_org_version', 'script_reviews', ['organization_id', 'script_version_id'], unique=False)
    op.create_table('story_versions',
    sa.Column('story_project_id', sa.Uuid(), nullable=False),
    sa.Column('story_revision', sa.Integer(), nullable=False),
    sa.Column('script_revision', sa.Integer(), nullable=False),
    sa.Column('final_speech_hash', sa.String(length=128), nullable=False),
    sa.Column('script_contract_version', sa.String(length=80), nullable=False),
    sa.Column('story_contract_version', sa.String(length=80), nullable=False),
    sa.Column('provider_capabilities_version', sa.String(length=80), nullable=False),
    sa.Column('story_bible', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('character_bible', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('visual_bible', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('shot_plan', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('story_hash', sa.String(length=128), nullable=False),
    sa.Column('request_fingerprint', sa.String(length=128), nullable=False),
    sa.Column('prompt_version', sa.String(length=80), nullable=False),
    sa.Column('model', sa.String(length=160), nullable=False),
    sa.Column('active_critique_id', sa.Uuid(), nullable=True),
    sa.Column('story_bible_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('budget_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('budget_approval', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('story_revision > 0', name=op.f('ck_story_versions_story_version_positive_revision')),
    sa.ForeignKeyConstraint(['organization_id', 'active_critique_id'], ['story_critiques.organization_id', 'story_critiques.id'], name='fk_story_versions_org_active_critique', ondelete='RESTRICT', use_alter=True),
    sa.ForeignKeyConstraint(['organization_id', 'story_project_id'], ['story_projects.organization_id', 'story_projects.id'], name='fk_story_versions_org_project', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_story_versions_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_story_versions')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_story_versions_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'request_fingerprint', name='uq_story_versions_request_fingerprint'),
    sa.UniqueConstraint('organization_id', 'story_project_id', 'story_revision', name='uq_story_versions_revision')
    )
    op.create_index('ix_story_versions_org_project', 'story_versions', ['organization_id', 'story_project_id'], unique=False)
    op.create_table('ai_usage',
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('job_id', sa.Uuid(), nullable=True),
    sa.Column('operation', sa.String(length=120), nullable=False),
    sa.Column('model', sa.String(length=160), nullable=False),
    sa.Column('input_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('output_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('cache_read_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('cache_write_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('estimated_cost_usd', sa.Numeric(precision=14, scale=8), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('estimated_cost_usd >= 0', name=op.f('ck_ai_usage_ai_usage_nonnegative_cost')),
    sa.CheckConstraint('input_tokens >= 0 AND output_tokens >= 0 AND cache_read_tokens >= 0 AND cache_write_tokens >= 0', name=op.f('ck_ai_usage_ai_usage_nonnegative_tokens')),
    sa.ForeignKeyConstraint(['actor_user_id'], ['user_profiles.id'], name=op.f('fk_ai_usage_actor_user_id_user_profiles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id', 'job_id'], ['jobs.organization_id', 'jobs.id'], name='fk_ai_usage_org_job', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_ai_usage_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_usage')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_ai_usage_organization_id_id')
    )
    op.create_index('ix_ai_usage_org_created', 'ai_usage', ['organization_id', 'created_at'], unique=False)
    op.create_index('ix_ai_usage_org_operation', 'ai_usage', ['organization_id', 'operation', 'created_at'], unique=False)
    op.create_table('calendar_posts',
    sa.Column('legacy_id', sa.String(length=120), nullable=True),
    sa.Column('script_id', sa.Uuid(), nullable=True),
    sa.Column('job_id', sa.Uuid(), nullable=True),
    sa.Column('social_account_id', sa.Uuid(), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('theme', sa.String(length=500), nullable=True),
    sa.Column('content_format', sa.String(length=80), nullable=True),
    sa.Column('responsible', sa.String(length=240), nullable=True),
    sa.Column('channel', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('post_url', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'scheduled', 'published', 'failed', 'cancelled')", name=op.f('ck_calendar_posts_calendar_post_status')),
    sa.ForeignKeyConstraint(['organization_id', 'job_id'], ['jobs.organization_id', 'jobs.id'], name='fk_calendar_posts_org_job', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'script_id'], ['scripts.organization_id', 'scripts.id'], name='fk_calendar_posts_org_script', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'social_account_id'], ['social_accounts.organization_id', 'social_accounts.id'], name='fk_calendar_posts_org_social_account', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_calendar_posts_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calendar_posts')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_calendar_posts_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'legacy_id', name='uq_calendar_posts_org_legacy')
    )
    op.create_index('ix_calendar_posts_org_scheduled', 'calendar_posts', ['organization_id', 'scheduled_at'], unique=False)
    op.create_index('ix_calendar_posts_org_status', 'calendar_posts', ['organization_id', 'status', 'scheduled_at'], unique=False)
    op.create_table('job_events',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('event_type', sa.String(length=80), nullable=False),
    sa.Column('previous_status', sa.String(length=60), nullable=True),
    sa.Column('next_status', sa.String(length=60), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'job_id'], ['jobs.organization_id', 'jobs.id'], name='fk_job_events_org_job', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_job_events_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job_events')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_job_events_organization_id_id')
    )
    op.create_index('ix_job_events_org_job_created', 'job_events', ['organization_id', 'job_id', 'created_at'], unique=False)
    op.create_table('story_critiques',
    sa.Column('story_version_id', sa.Uuid(), nullable=False),
    sa.Column('critique_revision', sa.Integer(), nullable=False),
    sa.Column('critique', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('budget', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('critique_hash', sa.String(length=128), nullable=False),
    sa.Column('request_fingerprint', sa.String(length=128), nullable=False),
    sa.Column('contract_version', sa.String(length=80), nullable=False),
    sa.Column('prompt_version', sa.String(length=80), nullable=False),
    sa.Column('model', sa.String(length=160), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'story_version_id'], ['story_versions.organization_id', 'story_versions.id'], name='fk_story_critiques_org_version', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_story_critiques_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_story_critiques')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_story_critiques_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'request_fingerprint', name='uq_story_critiques_request_fingerprint'),
    sa.UniqueConstraint('organization_id', 'story_version_id', 'critique_revision', name='uq_story_critiques_revision')
    )
    op.create_table('story_shots',
    sa.Column('story_version_id', sa.Uuid(), nullable=False),
    sa.Column('shot_key', sa.String(length=120), nullable=False),
    sa.Column('shot_order', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('prompt', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('prompt_hash', sa.String(length=128), nullable=False),
    sa.Column('continuity_hash', sa.String(length=128), nullable=False),
    sa.Column('controls', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('shot_revision', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('remote_job_id', sa.String(length=240), nullable=True),
    sa.Column('asset_id', sa.Uuid(), nullable=True),
    sa.Column('regeneration_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('quality_status', sa.String(length=40), nullable=True),
    sa.Column('current_generation_id', sa.Uuid(), nullable=True),
    sa.Column('thumbnail_asset_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('shot_order >= 0', name=op.f('ck_story_shots_story_shot_order')),
    sa.ForeignKeyConstraint(['organization_id', 'asset_id'], ['media_assets.organization_id', 'media_assets.id'], name='fk_story_shots_org_asset', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'current_generation_id'], ['story_shot_generations.organization_id', 'story_shot_generations.id'], name='fk_story_shots_org_current_generation', ondelete='RESTRICT', use_alter=True),
    sa.ForeignKeyConstraint(['organization_id', 'story_version_id'], ['story_versions.organization_id', 'story_versions.id'], name='fk_story_shots_org_version', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'thumbnail_asset_id'], ['media_assets.organization_id', 'media_assets.id'], name='fk_story_shots_org_thumbnail', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_story_shots_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_story_shots')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_story_shots_organization_id_id'),
    sa.UniqueConstraint('organization_id', 'story_version_id', 'shot_key', name='uq_story_shots_version_key')
    )
    op.create_index('ix_story_shots_org_version_order', 'story_shots', ['organization_id', 'story_version_id', 'shot_order'], unique=False)
    op.create_table('performance_metrics',
    sa.Column('calendar_post_id', sa.Uuid(), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('views', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('likes', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('retention_percent', sa.Numeric(precision=7, scale=3), server_default=sa.text('0'), nullable=False),
    sa.Column('comments', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('shares', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('saves', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('new_followers', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('clicks', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('leads', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('score_note', sa.Text(), nullable=True),
    sa.Column('learning', sa.Text(), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('views >= 0 AND likes >= 0 AND comments >= 0 AND shares >= 0 AND saves >= 0 AND new_followers >= 0 AND clicks >= 0 AND leads >= 0', name=op.f('ck_performance_metrics_performance_metrics_nonnegative')),
    sa.ForeignKeyConstraint(['organization_id', 'calendar_post_id'], ['calendar_posts.organization_id', 'calendar_posts.id'], name='fk_performance_metrics_org_post', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_performance_metrics_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_performance_metrics')),
    sa.UniqueConstraint('organization_id', 'calendar_post_id', 'observed_at', name='uq_performance_metrics_observation'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_performance_metrics_org_id_id')
    )
    op.create_index('ix_performance_metrics_org_observed', 'performance_metrics', ['organization_id', 'observed_at'], unique=False)
    op.create_index('ix_performance_metrics_org_post', 'performance_metrics', ['organization_id', 'calendar_post_id'], unique=False)
    op.create_table('story_shot_generations',
    sa.Column('story_shot_id', sa.Uuid(), nullable=False),
    sa.Column('story_version_id', sa.Uuid(), nullable=False),
    sa.Column('shot_revision', sa.Integer(), nullable=False),
    sa.Column('strategy', sa.String(length=80), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('spoken_text', sa.Text(), nullable=False),
    sa.Column('avatar_look_id', sa.Uuid(), nullable=True),
    sa.Column('duration_seconds', sa.Numeric(precision=10, scale=3), nullable=False),
    sa.Column('continuity', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('idempotency_key', sa.String(length=180), nullable=False),
    sa.Column('provider_job_id', sa.String(length=240), nullable=True),
    sa.Column('provider_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('output_asset_id', sa.Uuid(), nullable=True),
    sa.Column('output_url', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('retry_safe', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('estimated_cost_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('duration_seconds >= 0', name=op.f('ck_story_shot_generations_story_shot_generation_duration')),
    sa.ForeignKeyConstraint(['organization_id', 'avatar_look_id'], ['avatar_looks.organization_id', 'avatar_looks.id'], name='fk_story_shot_generations_org_avatar_look', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'output_asset_id'], ['media_assets.organization_id', 'media_assets.id'], name='fk_story_shot_generations_org_output_asset', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id', 'story_shot_id'], ['story_shots.organization_id', 'story_shots.id'], name='fk_story_shot_generations_org_shot', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'story_version_id'], ['story_versions.organization_id', 'story_versions.id'], name='fk_story_shot_generations_org_version', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_story_shot_generations_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_story_shot_generations')),
    sa.UniqueConstraint('organization_id', 'id', name='uq_story_shot_generations_org_id_id'),
    sa.UniqueConstraint('organization_id', 'idempotency_key', name='uq_story_shot_generations_idempotency')
    )
    op.create_index('ix_story_shot_generations_org_shot', 'story_shot_generations', ['organization_id', 'story_shot_id'], unique=False)
    op.create_foreign_key(
        'fk_scene_plans_org_script_version',
        'scene_plans',
        'script_versions',
        ['organization_id', 'script_version_id'],
        ['organization_id', 'id'],
        ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_story_projects_org_active_version',
        'story_projects',
        'story_versions',
        ['organization_id', 'active_story_version_id'],
        ['organization_id', 'id'],
        ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_story_shots_org_current_generation',
        'story_shots',
        'story_shot_generations',
        ['organization_id', 'current_generation_id'],
        ['organization_id', 'id'],
        ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_story_versions_org_active_critique',
        'story_versions',
        'story_critiques',
        ['organization_id', 'active_critique_id'],
        ['organization_id', 'id'],
        ondelete='RESTRICT',
    )
    _create_rls_helpers()
    _create_rls_policies()
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        'fk_story_versions_org_active_critique', 'story_versions', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_story_shots_org_current_generation', 'story_shots', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_story_projects_org_active_version', 'story_projects', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_scene_plans_org_script_version', 'scene_plans', type_='foreignkey'
    )
    _drop_rls_helpers()
    op.drop_index('ix_story_shot_generations_org_shot', table_name='story_shot_generations')
    op.drop_table('story_shot_generations')
    op.drop_index('ix_performance_metrics_org_post', table_name='performance_metrics')
    op.drop_index('ix_performance_metrics_org_observed', table_name='performance_metrics')
    op.drop_table('performance_metrics')
    op.drop_index('ix_story_shots_org_version_order', table_name='story_shots')
    op.drop_table('story_shots')
    op.drop_table('story_critiques')
    op.drop_index('ix_job_events_org_job_created', table_name='job_events')
    op.drop_table('job_events')
    op.drop_index('ix_calendar_posts_org_status', table_name='calendar_posts')
    op.drop_index('ix_calendar_posts_org_scheduled', table_name='calendar_posts')
    op.drop_table('calendar_posts')
    op.drop_index('ix_ai_usage_org_operation', table_name='ai_usage')
    op.drop_index('ix_ai_usage_org_created', table_name='ai_usage')
    op.drop_table('ai_usage')
    op.drop_index('ix_story_versions_org_project', table_name='story_versions')
    op.drop_table('story_versions')
    op.drop_index('ix_script_reviews_org_version', table_name='script_reviews')
    op.drop_table('script_reviews')
    op.drop_index('uq_jobs_org_remote_session', table_name='jobs', postgresql_where=sa.text('remote_session_id IS NOT NULL'))
    op.drop_index('ix_jobs_org_status_available', table_name='jobs')
    op.drop_index('ix_jobs_org_script', table_name='jobs')
    op.drop_index('ix_jobs_org_kind_created', table_name='jobs')
    op.drop_table('jobs')
    op.drop_table('visual_plans')
    op.drop_table('visual_packs')
    op.drop_table('video_slide_renders')
    op.drop_index('ix_story_projects_org_status', table_name='story_projects')
    op.drop_table('story_projects')
    op.drop_index('ix_script_versions_org_script', table_name='script_versions')
    op.drop_table('script_versions')
    op.drop_table('script_editor_states')
    op.drop_table('scene_plans')
    op.drop_table('production_profiles')
    op.drop_index('ix_avatar_set_looks_org_set', table_name='avatar_set_looks')
    op.drop_table('avatar_set_looks')
    op.drop_index('ix_scripts_org_status_created', table_name='scripts')
    op.drop_index('ix_scripts_org_idea', table_name='scripts')
    op.drop_table('scripts')
    op.drop_table('avatar_sets')
    op.drop_table('social_accounts')
    op.drop_index('ix_legacy_id_map_org_target', table_name='legacy_id_map')
    op.drop_table('legacy_id_map')
    op.drop_index('ix_ideas_org_trend', table_name='ideas')
    op.drop_index('ix_ideas_org_status_created', table_name='ideas')
    op.drop_table('ideas')
    op.drop_index('ix_avatar_looks_org_identity', table_name='avatar_looks')
    op.drop_table('avatar_looks')
    op.drop_table('asset_variants')
    op.drop_index('ix_voices_org_status', table_name='voices')
    op.drop_table('voices')
    op.drop_index('ix_trends_org_status_created', table_name='trends')
    op.drop_index('ix_trends_org_priority', table_name='trends')
    op.drop_table('trends')
    op.drop_index('uq_provider_connections_default', table_name='provider_connections', postgresql_where=sa.text('external_account_id IS NULL'))
    op.drop_table('provider_connections')
    op.drop_table('provider_capabilities')
    op.drop_table('organization_settings')
    op.drop_index('ix_memberships_user_status', table_name='organization_memberships')
    op.drop_table('organization_memberships')
    op.drop_index('ix_media_assets_org_sha256', table_name='media_assets')
    op.drop_index('ix_media_assets_org_kind_created', table_name='media_assets')
    op.drop_table('media_assets')
    op.drop_index('ix_legacy_import_runs_org_started', table_name='legacy_import_runs')
    op.drop_table('legacy_import_runs')
    op.drop_index('ix_avatar_identities_org_status', table_name='avatar_identities')
    op.drop_table('avatar_identities')
    op.drop_index('ix_audit_events_org_entity', table_name='audit_events')
    op.drop_index('ix_audit_events_org_created', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index('ix_ai_response_cache_org_operation', table_name='ai_response_cache')
    op.drop_index('ix_ai_response_cache_expires', table_name='ai_response_cache')
    op.drop_table('ai_response_cache')
    op.drop_table('user_profiles')
    op.drop_table('organizations')
    # ### end Alembic commands ###
