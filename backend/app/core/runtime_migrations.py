from sqlalchemy import text
from app.core.database import engine
from app.core.tenancy import CELLHUB_MASTER_TENANT_ID, CELLHUB_MASTER_TENANT_NAME


def apply_runtime_migrations() -> None:
    with engine.begin() as conn:
        # RBAC permissions column for existing databases.
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB NOT NULL DEFAULT '[]'::jsonb"))

        # Company-first signup (PLAN.md §1): membership status + billing-owner flag
        # on users, and the canonical email-domain key on tenants.
        conn.execute(text(
            "DO $$ BEGIN CREATE TYPE user_status AS ENUM ('ACTIVE','PENDING'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$;"
        ))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS status user_status NOT NULL DEFAULT 'ACTIVE'"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_billing_owner BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email_domain VARCHAR(255)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_email_domain ON tenants (email_domain)"))

        # Tenant onboarding state.
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS tenant_onboarding (
                    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                    organization_name VARCHAR(255),
                    admin_name VARCHAR(255),
                    admin_email VARCHAR(320),
                    admin_phone VARCHAR(64),
                    credit_validation_status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
                    tax_validation_status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
                    duns_number VARCHAR(64),
                    tax_id VARCHAR(64),
                    company_setup_completed BOOLEAN NOT NULL DEFAULT FALSE,
                    payment_method_setup BOOLEAN NOT NULL DEFAULT FALSE,
                    payment_validation_status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
                    payment_method_type VARCHAR(32),
                    payment_method_last4 VARCHAR(8),
                    onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )

        # Backward compatibility for earlier table versions created without server defaults.
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS organization_name VARCHAR(255)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS admin_name VARCHAR(255)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS admin_email VARCHAR(320)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS admin_phone VARCHAR(64)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS credit_validation_status VARCHAR(16)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS tax_validation_status VARCHAR(16)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS duns_number VARCHAR(64)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS tax_id VARCHAR(64)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS company_setup_completed BOOLEAN"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS payment_method_setup BOOLEAN"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS payment_validation_status VARCHAR(16)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS payment_method_type VARCHAR(32)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS payment_method_last4 VARCHAR(8)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS operations_address JSONB"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS billing_address JSONB"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS billing_same_as_operations BOOLEAN"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS metadata JSONB"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))

        conn.execute(text("UPDATE tenant_onboarding SET credit_validation_status = 'PENDING' WHERE credit_validation_status IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET tax_validation_status = 'PENDING' WHERE tax_validation_status IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET company_setup_completed = FALSE WHERE company_setup_completed IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET payment_method_setup = FALSE WHERE payment_method_setup IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET payment_validation_status = 'PENDING' WHERE payment_validation_status IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET onboarding_completed = FALSE WHERE onboarding_completed IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET operations_address = '{}'::jsonb WHERE operations_address IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET billing_address = '{}'::jsonb WHERE billing_address IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET billing_same_as_operations = TRUE WHERE billing_same_as_operations IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET metadata = '{}'::jsonb WHERE metadata IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET created_at = NOW() WHERE created_at IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET updated_at = NOW() WHERE updated_at IS NULL"))

        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN credit_validation_status SET DEFAULT 'PENDING'"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN tax_validation_status SET DEFAULT 'PENDING'"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN company_setup_completed SET DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN payment_method_setup SET DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN payment_validation_status SET DEFAULT 'PENDING'"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN onboarding_completed SET DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN operations_address SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN billing_address SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN billing_same_as_operations SET DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN metadata SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN created_at SET DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN updated_at SET DEFAULT NOW()"))

        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN credit_validation_status SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN tax_validation_status SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN company_setup_completed SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN payment_method_setup SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN payment_validation_status SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN onboarding_completed SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN operations_address SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN billing_address SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN billing_same_as_operations SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN metadata SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN created_at SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN updated_at SET NOT NULL"))

        conn.execute(
            text(
                """
                INSERT INTO tenant_onboarding (
                    tenant_id,
                    organization_name,
                    credit_validation_status,
                    tax_validation_status,
                    company_setup_completed,
                    payment_method_setup,
                    payment_validation_status,
                    onboarding_completed,
                    metadata,
                    created_at,
                    updated_at
                )
                SELECT
                    id,
                    name,
                    'PENDING',
                    'PENDING',
                    FALSE,
                    FALSE,
                    'PENDING',
                    FALSE,
                    '{}'::jsonb,
                    NOW(),
                    NOW()
                FROM tenants
                ON CONFLICT (tenant_id) DO NOTHING
                """
            )
        )

        # Tenant-level order notification recipients for fulfillment handoff.
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS tenant_order_notification_settings (
                    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                    recipient_emails JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ADD COLUMN IF NOT EXISTS tenant_id UUID"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ADD COLUMN IF NOT EXISTS recipient_emails JSONB"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ADD COLUMN IF NOT EXISTS updated_by UUID"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
        conn.execute(text("UPDATE tenant_order_notification_settings SET recipient_emails = '[]'::jsonb WHERE recipient_emails IS NULL"))
        conn.execute(text("UPDATE tenant_order_notification_settings SET created_at = NOW() WHERE created_at IS NULL"))
        conn.execute(text("UPDATE tenant_order_notification_settings SET updated_at = NOW() WHERE updated_at IS NULL"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ALTER COLUMN recipient_emails SET DEFAULT '[]'::jsonb"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ALTER COLUMN created_at SET DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ALTER COLUMN updated_at SET DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ALTER COLUMN recipient_emails SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ALTER COLUMN created_at SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_order_notification_settings ALTER COLUMN updated_at SET NOT NULL"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'tenant_order_notification_settings_tenant_id_fkey'
                    ) THEN
                        ALTER TABLE tenant_order_notification_settings
                        ADD CONSTRAINT tenant_order_notification_settings_tenant_id_fkey
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'tenant_order_notification_settings_updated_by_fkey'
                    ) THEN
                        ALTER TABLE tenant_order_notification_settings
                        ADD CONSTRAINT tenant_order_notification_settings_updated_by_fkey
                        FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL;
                    END IF;
                END
                $$;
                """
            )
        )

        # Quote schema compatibility: support older installs that still use v1 column names.
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS created_by UUID"))
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS one_time_total NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS monthly_total NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS projected_12_month_cost NUMERIC(12, 2) NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'status'
                          AND udt_name = 'quote_status'
                    ) THEN
                        EXECUTE 'ALTER TABLE quotes ALTER COLUMN status TYPE VARCHAR(32) USING status::text';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'status'
                    ) THEN
                        EXECUTE 'UPDATE quotes SET status = ''DRAFT'' WHERE status = ''QUOTE''';
                        EXECUTE 'UPDATE quotes SET status = ''SENT'' WHERE status = ''SUBMITTED''';
                        EXECUTE 'UPDATE quotes SET status = ''CONVERTED'' WHERE status IN (''FULFILLMENT'', ''DELIVERED'')';
                        EXECUTE 'ALTER TABLE quotes ALTER COLUMN status SET DEFAULT ''DRAFT''';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'user_id'
                    ) THEN
                        EXECUTE 'UPDATE quotes SET created_by = user_id WHERE created_by IS NULL';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'one_time_subtotal'
                    ) THEN
                        EXECUTE 'UPDATE quotes SET one_time_total = one_time_subtotal';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'monthly_subtotal'
                    ) THEN
                        EXECUTE 'UPDATE quotes SET monthly_total = monthly_subtotal';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'estimated_12_month_total'
                    ) THEN
                        EXECUTE 'UPDATE quotes SET projected_12_month_cost = estimated_12_month_total';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'created_at'
                    ) THEN
                        EXECUTE 'UPDATE quotes SET updated_at = COALESCE(updated_at, created_at)';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'quote_number'
                    ) THEN
                        EXECUTE 'ALTER TABLE quotes ALTER COLUMN quote_number SET DEFAULT (''Q-'' || upper(substr(replace(gen_random_uuid()::text, ''-'', ''''), 1, 8)))';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'user_id'
                    ) THEN
                        EXECUTE 'ALTER TABLE quotes ALTER COLUMN user_id DROP NOT NULL';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'one_time_subtotal'
                    ) THEN
                        EXECUTE 'ALTER TABLE quotes ALTER COLUMN one_time_subtotal SET DEFAULT 0';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'monthly_subtotal'
                    ) THEN
                        EXECUTE 'ALTER TABLE quotes ALTER COLUMN monthly_subtotal SET DEFAULT 0';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'estimated_12_month_total'
                    ) THEN
                        EXECUTE 'ALTER TABLE quotes ALTER COLUMN estimated_12_month_total SET DEFAULT 0';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'quotes'
                          AND column_name = 'snapshot'
                    ) THEN
                        EXECUTE 'ALTER TABLE quotes ALTER COLUMN snapshot SET DEFAULT ''{}''::jsonb';
                    END IF;
                END
                $$;
                """
            )
        )

        # Lightweight lead capture + persisted network design history for demo workflow.
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS design_leads (
                    id UUID PRIMARY KEY,
                    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
                    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    full_name VARCHAR(255) NOT NULL,
                    email VARCHAR(320) NOT NULL,
                    company_name VARCHAR(255) NOT NULL,
                    phone VARCHAR(64),
                    notes TEXT,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS tenant_id UUID"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS user_id UUID"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS email VARCHAR(320)"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS company_name VARCHAR(255)"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS phone VARCHAR(64)"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS notes TEXT"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS metadata JSONB"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE design_leads ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
        conn.execute(text("UPDATE design_leads SET metadata = '{}'::jsonb WHERE metadata IS NULL"))
        conn.execute(text("UPDATE design_leads SET created_at = NOW() WHERE created_at IS NULL"))
        conn.execute(text("UPDATE design_leads SET updated_at = NOW() WHERE updated_at IS NULL"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'design_leads_tenant_id_fkey'
                    ) THEN
                        ALTER TABLE design_leads
                        ADD CONSTRAINT design_leads_tenant_id_fkey
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE SET NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'design_leads_user_id_fkey'
                    ) THEN
                        ALTER TABLE design_leads
                        ADD CONSTRAINT design_leads_user_id_fkey
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
                    END IF;
                END
                $$;
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS network_designs (
                    id UUID PRIMARY KEY,
                    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
                    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                    lead_id UUID REFERENCES design_leads(id) ON DELETE SET NULL,
                    design_name VARCHAR(255),
                    status VARCHAR(32) NOT NULL DEFAULT 'draft',
                    calculator_input JSONB NOT NULL DEFAULT '{}'::jsonb,
                    calculator_result JSONB NOT NULL DEFAULT '{}'::jsonb,
                    bom JSONB NOT NULL DEFAULT '{}'::jsonb,
                    topology JSONB NOT NULL DEFAULT '{}'::jsonb,
                    drawio_xml TEXT,
                    assumptions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    estimate_capex NUMERIC(12, 2),
                    ap_count INTEGER NOT NULL DEFAULT 0,
                    switch_count INTEGER NOT NULL DEFAULT 0,
                    session_key VARCHAR(128),
                    submitted_at TIMESTAMPTZ,
                    status_updated_at TIMESTAMPTZ,
                    status_history JSONB NOT NULL DEFAULT '[]'::jsonb,
                    milestones JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updates JSONB NOT NULL DEFAULT '[]'::jsonb,
                    install_assistance JSONB NOT NULL DEFAULT '{}'::jsonb,
                    decomposition JSONB NOT NULL DEFAULT '{}'::jsonb,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS tenant_id UUID"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS created_by UUID"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS lead_id UUID"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS design_name VARCHAR(255)"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS status VARCHAR(32)"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS calculator_input JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS calculator_result JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS bom JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS topology JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS drawio_xml TEXT"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS assumptions JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS estimate_capex NUMERIC(12, 2)"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS ap_count INTEGER"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS switch_count INTEGER"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS session_key VARCHAR(128)"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS status_history JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS milestones JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS updates JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS install_assistance JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS decomposition JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS metadata JSONB"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
        conn.execute(text("UPDATE network_designs SET status = 'proposal_ready' WHERE status = 'quote_ready'"))
        conn.execute(text("UPDATE network_designs SET status = 'completed' WHERE status = 'fulfilled'"))
        conn.execute(text("UPDATE network_designs SET status = 'draft' WHERE status IS NULL"))
        conn.execute(text("UPDATE network_designs SET calculator_input = '{}'::jsonb WHERE calculator_input IS NULL"))
        conn.execute(text("UPDATE network_designs SET calculator_result = '{}'::jsonb WHERE calculator_result IS NULL"))
        conn.execute(text("UPDATE network_designs SET bom = '{}'::jsonb WHERE bom IS NULL"))
        conn.execute(text("UPDATE network_designs SET topology = '{}'::jsonb WHERE topology IS NULL"))
        conn.execute(text("UPDATE network_designs SET assumptions = '[]'::jsonb WHERE assumptions IS NULL"))
        conn.execute(text("UPDATE network_designs SET ap_count = 0 WHERE ap_count IS NULL"))
        conn.execute(text("UPDATE network_designs SET switch_count = 0 WHERE switch_count IS NULL"))
        conn.execute(text("UPDATE network_designs SET status_updated_at = COALESCE(status_updated_at, submitted_at, updated_at, created_at, NOW())"))
        conn.execute(text("UPDATE network_designs SET status_history = '[]'::jsonb WHERE status_history IS NULL"))
        conn.execute(text("UPDATE network_designs SET milestones = '{}'::jsonb WHERE milestones IS NULL"))
        conn.execute(text("UPDATE network_designs SET updates = '[]'::jsonb WHERE updates IS NULL"))
        conn.execute(text("UPDATE network_designs SET install_assistance = '{}'::jsonb WHERE install_assistance IS NULL"))
        conn.execute(text("UPDATE network_designs SET decomposition = '{}'::jsonb WHERE decomposition IS NULL"))
        conn.execute(text("UPDATE network_designs SET metadata = '{}'::jsonb WHERE metadata IS NULL"))
        conn.execute(text("UPDATE network_designs SET created_at = NOW() WHERE created_at IS NULL"))
        conn.execute(text("UPDATE network_designs SET updated_at = NOW() WHERE updated_at IS NULL"))

        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN status SET DEFAULT 'draft'"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN calculator_input SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN calculator_result SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN bom SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN topology SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN assumptions SET DEFAULT '[]'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN ap_count SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN switch_count SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN status_history SET DEFAULT '[]'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN milestones SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN updates SET DEFAULT '[]'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN install_assistance SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN decomposition SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN metadata SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN created_at SET DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN updated_at SET DEFAULT NOW()"))

        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN status SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN calculator_input SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN calculator_result SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN bom SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN topology SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN assumptions SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN ap_count SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN switch_count SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN status_history SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN milestones SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN updates SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN install_assistance SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN decomposition SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN metadata SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN created_at SET NOT NULL"))
        conn.execute(text("ALTER TABLE network_designs ALTER COLUMN updated_at SET NOT NULL"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'network_designs_tenant_id_fkey'
                    ) THEN
                        ALTER TABLE network_designs
                        ADD CONSTRAINT network_designs_tenant_id_fkey
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE SET NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'network_designs_created_by_fkey'
                    ) THEN
                        ALTER TABLE network_designs
                        ADD CONSTRAINT network_designs_created_by_fkey
                        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'network_designs_lead_id_fkey'
                    ) THEN
                        ALTER TABLE network_designs
                        ADD CONSTRAINT network_designs_lead_id_fkey
                        FOREIGN KEY (lead_id) REFERENCES design_leads(id) ON DELETE SET NULL;
                    END IF;
                END
                $$;
                """
            )
        )

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_design_leads_tenant_email ON design_leads (tenant_id, email)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_network_designs_tenant_status ON network_designs (tenant_id, status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_network_designs_created_by ON network_designs (created_by)"))

        # Catalog vendor fields.
        conn.execute(text("ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS vendor VARCHAR(128)"))
        conn.execute(text("ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS vendor_sku VARCHAR(255)"))
        conn.execute(text("UPDATE catalog_items SET vendor = COALESCE(vendor, 'CDW') WHERE vendor IS NULL"))
        conn.execute(text("UPDATE catalog_items SET vendor_sku = COALESCE(vendor_sku, sku) WHERE vendor_sku IS NULL"))

        # Quote line pricing snapshots.
        conn.execute(text("ALTER TABLE quote_lines ADD COLUMN IF NOT EXISTS catalog_item_id UUID"))
        conn.execute(text("ALTER TABLE quote_lines ADD COLUMN IF NOT EXISTS list_price_snapshot NUMERIC(12, 2)"))
        conn.execute(text("UPDATE quote_lines SET list_price_snapshot = unit_price WHERE list_price_snapshot IS NULL"))
        conn.execute(text("ALTER TABLE quote_lines ALTER COLUMN list_price_snapshot SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE quote_lines ALTER COLUMN list_price_snapshot SET NOT NULL"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'quote_lines_catalog_item_id_fkey'
                    ) THEN
                        ALTER TABLE quote_lines
                        ADD CONSTRAINT quote_lines_catalog_item_id_fkey
                        FOREIGN KEY (catalog_item_id) REFERENCES catalog_items(id) ON DELETE SET NULL;
                    END IF;
                END
                $$;
                """
            )
        )

        # Order schema extension for quote linkage + fulfillment dates + expanded statuses.
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS quote_id UUID"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS estimated_delivery_date DATE"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS confirmed_delivery_date DATE"))

        # Human-readable sequential IDs for quotes/orders (keep UUIDs as internal PKs).
        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS quote_public_id_seq START WITH 1 INCREMENT BY 1"))
        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS order_public_id_seq START WITH 1 INCREMENT BY 1"))
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS public_id VARCHAR(32)"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS public_id VARCHAR(32)"))
        conn.execute(
            text(
                """
                UPDATE quotes
                SET public_id = 'QID' || lpad(nextval('quote_public_id_seq')::text, 4, '0')
                WHERE public_id IS NULL OR btrim(public_id) = ''
                """
            )
        )
        conn.execute(text("UPDATE quotes SET public_id = regexp_replace(public_id, '^QID\\s+', 'QID') WHERE public_id ~ '^QID\\s+'"))
        conn.execute(
            text(
                """
                UPDATE orders
                SET public_id = 'OID' || lpad(nextval('order_public_id_seq')::text, 4, '0')
                WHERE public_id IS NULL OR btrim(public_id) = ''
                """
            )
        )
        conn.execute(text("UPDATE orders SET public_id = regexp_replace(public_id, '^OID\\s+', 'OID') WHERE public_id ~ '^OID\\s+'"))
        conn.execute(
            text(
                """
                DO $$
                DECLARE max_quote_num BIGINT;
                BEGIN
                    SELECT COALESCE(MAX(NULLIF(regexp_replace(public_id, '[^0-9]', '', 'g'), '')::BIGINT), 0)
                    INTO max_quote_num
                    FROM quotes;
                    IF max_quote_num > 0 THEN
                        PERFORM setval('quote_public_id_seq', max_quote_num, true);
                    ELSE
                        PERFORM setval('quote_public_id_seq', 1, false);
                    END IF;
                END
                $$;
                """
            )
        )
        conn.execute(
            text(
                """
                DO $$
                DECLARE max_order_num BIGINT;
                BEGIN
                    SELECT COALESCE(MAX(NULLIF(regexp_replace(public_id, '[^0-9]', '', 'g'), '')::BIGINT), 0)
                    INTO max_order_num
                    FROM orders;
                    IF max_order_num > 0 THEN
                        PERFORM setval('order_public_id_seq', max_order_num, true);
                    ELSE
                        PERFORM setval('order_public_id_seq', 1, false);
                    END IF;
                END
                $$;
                """
            )
        )
        conn.execute(
            text(
                "ALTER TABLE quotes ALTER COLUMN public_id SET DEFAULT ('QID' || lpad(nextval('quote_public_id_seq')::text, 4, '0'))"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE orders ALTER COLUMN public_id SET DEFAULT ('OID' || lpad(nextval('order_public_id_seq')::text, 4, '0'))"
            )
        )
        conn.execute(text("ALTER TABLE quotes ALTER COLUMN public_id SET NOT NULL"))
        conn.execute(text("ALTER TABLE orders ALTER COLUMN public_id SET NOT NULL"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_quotes_public_id ON quotes (public_id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_public_id ON orders (public_id)"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'orders_quote_id_fkey'
                    ) THEN
                        ALTER TABLE orders
                        ADD CONSTRAINT orders_quote_id_fkey
                        FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE SET NULL;
                    END IF;
                END
                $$;
                """
            )
        )

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'orders_status_check'
                    ) THEN
                        ALTER TABLE orders DROP CONSTRAINT orders_status_check;
                    END IF;
                    ALTER TABLE orders
                    ADD CONSTRAINT orders_status_check
                    CHECK (status IN ('SUBMITTED', 'PROCESSING', 'VENDOR_ORDERED', 'SHIPPED', 'DELIVERED', 'ACTIVE'));
                EXCEPTION WHEN duplicate_object THEN
                    NULL;
                END
                $$;
                """
            )
        )

        # Order line pricing snapshots.
        conn.execute(text("ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS catalog_item_id UUID"))
        conn.execute(text("ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS list_price_snapshot NUMERIC(12, 2)"))
        conn.execute(text("UPDATE order_lines SET list_price_snapshot = unit_price WHERE list_price_snapshot IS NULL"))
        conn.execute(text("ALTER TABLE order_lines ALTER COLUMN list_price_snapshot SET DEFAULT 0"))
        conn.execute(text("ALTER TABLE order_lines ALTER COLUMN list_price_snapshot SET NOT NULL"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'order_lines_catalog_item_id_fkey'
                    ) THEN
                        ALTER TABLE order_lines
                        ADD CONSTRAINT order_lines_catalog_item_id_fkey
                        FOREIGN KEY (catalog_item_id) REFERENCES catalog_items(id) ON DELETE SET NULL;
                    END IF;
                END
                $$;
                """
            )
        )

        # Pricing tables (tenant-scoped list + default customer + per-deal discounts).
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS customer_pricing (
                    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                    default_discount_pct NUMERIC(6, 4) NOT NULL DEFAULT 0.30,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS list_prices (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    catalog_item_id UUID NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
                    vendor VARCHAR(128) NOT NULL DEFAULT 'CDW',
                    list_price NUMERIC(12, 2) NOT NULL,
                    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_list_prices_tenant_item_vendor UNIQUE (tenant_id, catalog_item_id, vendor)
                )
                """
            )
        )
        # Ensure existing databases created before this migration have the correct default on id.
        conn.execute(text("ALTER TABLE list_prices ALTER COLUMN id SET DEFAULT gen_random_uuid()"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS deal_pricing (
                    quote_id UUID PRIMARY KEY REFERENCES quotes(id) ON DELETE CASCADE,
                    incremental_discount_pct NUMERIC(6, 4) NOT NULL DEFAULT 0.0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO customer_pricing (tenant_id, default_discount_pct)
                SELECT t.id, 0.30
                FROM tenants t
                ON CONFLICT (tenant_id) DO NOTHING
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO list_prices (tenant_id, catalog_item_id, vendor, list_price, currency)
                SELECT t.id, c.id, COALESCE(c.vendor, 'CDW'), c.price, c.currency
                FROM tenants t
                CROSS JOIN catalog_items c
                GROUP BY t.id, c.id, c.vendor, c.price, c.currency
                ON CONFLICT (tenant_id, catalog_item_id, vendor) DO NOTHING
                """
            )
        )

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_list_prices_tenant_item ON list_prices (tenant_id, catalog_item_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_pricing_quote_id ON deal_pricing (quote_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_quote_id ON orders (quote_id)"))

        conn.execute(text("UPDATE quotes SET created_by = (SELECT id FROM users ORDER BY created_at ASC LIMIT 1) WHERE created_by IS NULL"))
        conn.execute(text("ALTER TABLE quotes ALTER COLUMN created_by SET NOT NULL"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'quotes_created_by_fkey'
                    ) THEN
                        ALTER TABLE quotes
                        ADD CONSTRAINT quotes_created_by_fkey
                        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE;
                    END IF;
                END
                $$;
                """
            )
        )

        # --- Multi-tenant type support (CELLHUB / VENDOR / COMPANY) ---
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tenant_type') THEN
                        CREATE TYPE tenant_type AS ENUM ('CELLHUB', 'VENDOR', 'COMPANY');
                    END IF;
                END
                $$;
                """
            )
        )
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS tenant_type VARCHAR(32) NOT NULL DEFAULT 'CELLHUB'"))
        conn.execute(text("UPDATE tenants SET tenant_type = 'CELLHUB' WHERE tenant_type IS NULL"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_type_enum') THEN
                        CREATE TYPE user_type_enum AS ENUM ('CELLHUB', 'VENDOR', 'COMPANY');
                    END IF;
                END
                $$;
                """
            )
        )
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS user_type VARCHAR(32) NOT NULL DEFAULT 'CELLHUB'"))
        conn.execute(text("UPDATE users SET user_type = 'CELLHUB' WHERE user_type IS NULL"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS vendors (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
                    company_name VARCHAR(255) NOT NULL,
                    address_street VARCHAR(500) NOT NULL DEFAULT '',
                    address_city VARCHAR(255) NOT NULL DEFAULT '',
                    address_state VARCHAR(100) NOT NULL DEFAULT '',
                    address_zip VARCHAR(20) NOT NULL DEFAULT '',
                    company_website VARCHAR(500) NOT NULL DEFAULT '',
                    company_email VARCHAR(320) NOT NULL DEFAULT '',
                    federal_tax_id VARCHAR(64) NOT NULL DEFAULT '',
                    bbb_good_standing BOOLEAN NOT NULL DEFAULT FALSE,
                    sos_good_standing BOOLEAN NOT NULL DEFAULT FALSE,
                    corporate_liable_sales BOOLEAN NOT NULL DEFAULT FALSE,
                    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
                    company_name VARCHAR(255) NOT NULL,
                    industry VARCHAR(255),
                    billing_email VARCHAR(320),
                    subscription_tier VARCHAR(32) NOT NULL DEFAULT 'free',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )

        # ── Managed-service per-SKU pricing column on catalog_items ──
        conn.execute(text(
            "ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS managed_service_price NUMERIC(12, 2)"
        ))

        # Seed default managed-service prices by device category
        conn.execute(text("""
            UPDATE catalog_items SET managed_service_price = 10.00
            WHERE managed_service_price IS NULL AND type = 'DEVICE'
              AND attributes->>'category' IN ('router','wifi_ap','switch','firewall','cellular_gateway')
        """))
        conn.execute(text("""
            UPDATE catalog_items SET managed_service_price = 5.00
            WHERE managed_service_price IS NULL AND type = 'DEVICE'
              AND attributes->>'category' IN ('security_appliance','camera','sensor')
        """))
        conn.execute(text("""
            UPDATE catalog_items SET managed_service_price = 2.00
            WHERE managed_service_price IS NULL AND type = 'DEVICE'
              AND attributes->>'category' = 'laptop'
        """))
        conn.execute(text("""
            UPDATE catalog_items SET managed_service_price = 0.25
            WHERE managed_service_price IS NULL AND type = 'DEVICE'
              AND attributes->>'category' = 'phone'
        """))
        conn.execute(text("""
            UPDATE catalog_items SET managed_service_price = 1.50
            WHERE managed_service_price IS NULL AND type = 'DEVICE'
              AND attributes->>'category' = 'tablet'
        """))
        conn.execute(text("""
            UPDATE catalog_items SET managed_service_price = 1.00
            WHERE managed_service_price IS NULL AND type = 'DEVICE'
              AND attributes->>'category' = 'hotspot'
        """))

        # ── Managed-services selection on network_designs ──
        conn.execute(text(
            "ALTER TABLE network_designs ADD COLUMN IF NOT EXISTS managed_services JSONB NOT NULL DEFAULT '{}'::jsonb"
        ))
        conn.execute(text(
            "UPDATE network_designs SET managed_services = '{}'::jsonb WHERE managed_services IS NULL"
        ))

        # ── OTP attempt counter (brute-force protection) ──
        # New column; existing active OTPs are seeded with the default quota so
        # ongoing verification flows don't break mid-migration.
        conn.execute(text(
            "ALTER TABLE otps ADD COLUMN IF NOT EXISTS attempts_remaining INTEGER NOT NULL DEFAULT 5"
        ))
        conn.execute(text("UPDATE otps SET attempts_remaining = 5 WHERE attempts_remaining IS NULL"))

        # ── OTP issuance timestamp (per-email request throttle) ──
        # Existing rows get NOW() so they fall outside future throttle windows
        # immediately rather than being treated as a fresh burst.
        conn.execute(text(
            "ALTER TABLE otps ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ))
        conn.execute(text("UPDATE otps SET created_at = NOW() WHERE created_at IS NULL"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_otps_user_created_at ON otps (user_id, created_at)"
        ))

        # ── Stripe integration columns ──
        conn.execute(text(
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(64)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_stripe_customer_id "
            "ON tenants (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL"
        ))

        conn.execute(text(
            "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(64)"
        ))
        conn.execute(text(
            "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS stripe_price_id VARCHAR(64)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_subscriptions_stripe_subscription_id "
            "ON subscriptions (stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL"
        ))
        # Tenant-level Stripe checkout subscriptions have no order/contract.
        conn.execute(text(
            "ALTER TABLE subscriptions ALTER COLUMN contract_id DROP NOT NULL"
        ))

        conn.execute(text(
            "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS stripe_invoice_id VARCHAR(64)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_invoices_stripe_invoice_id "
            "ON invoices (stripe_invoice_id) WHERE stripe_invoice_id IS NOT NULL"
        ))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stripe_events (
                id           VARCHAR(64) PRIMARY KEY,
                type         VARCHAR(128) NOT NULL,
                received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                payload      JSONB NOT NULL
            )
        """))

        # ── Component pricing engine (Secure Office, Phase 1) ──
        # New tables are also declared as ORM models (app/models/product.py,
        # financing.py) so the service layer can query them; we create them here
        # too because apply_runtime_migrations() runs BEFORE create_all() and the
        # FK ALTERs below reference products/product_components. This mirrors the
        # existing customer_pricing/list_prices convention (ORM + raw create).
        # Enum columns are VARCHAR + CHECK (native_enum=False parity).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS products (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                vendor          VARCHAR(128) NOT NULL,
                technology      VARCHAR(128) NOT NULL,
                sku             VARCHAR(128) NOT NULL UNIQUE,
                vendor_sku      VARCHAR(128),
                name            VARCHAR(255) NOT NULL,
                description     VARCHAR(1024),
                default_financial_model VARCHAR(8) NOT NULL DEFAULT 'BOTH'
                    CHECK (default_financial_model IN ('CAPEX','OPEX','BOTH')),
                margin_pct      NUMERIC(6,4),
                leasing_pct     NUMERIC(6,4),
                is_active       BOOLEAN NOT NULL DEFAULT TRUE,
                attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_products_vendor_tech ON products (vendor, technology)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS product_components (
                id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                product_id         UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                component_type     VARCHAR(32) NOT NULL,
                financial_model    VARCHAR(8) NOT NULL DEFAULT 'BOTH'
                    CHECK (financial_model IN ('CAPEX','OPEX','BOTH')),
                label              VARCHAR(255) NOT NULL,
                vendor_component_sku VARCHAR(128),
                vendor_cost        NUMERIC(12,4) NOT NULL,
                msrp               NUMERIC(12,2),
                uom                VARCHAR(16) NOT NULL DEFAULT 'PER_DEVICE',
                billing            VARCHAR(16) NOT NULL DEFAULT 'ONE_TIME',
                interval           VARCHAR(16),
                margin_pct         NUMERIC(6,4),
                leasing_pct        NUMERIC(6,4),
                default_qty        INTEGER NOT NULL DEFAULT 1,
                is_required        BOOLEAN NOT NULL DEFAULT TRUE,
                catalog_item_id    UUID REFERENCES catalog_items(id) ON DELETE SET NULL,
                is_active          BOOLEAN NOT NULL DEFAULT TRUE,
                attributes         JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT pc_billing_check CHECK (billing IN ('ONE_TIME','RECURRING')),
                CONSTRAINT pc_interval_check CHECK (interval IS NULL OR interval IN ('MONTH','YEAR')),
                CONSTRAINT uq_pc_product_type_sku UNIQUE (product_id, component_type, vendor_component_sku)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_components_product ON product_components (product_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_components_type ON product_components (component_type)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bundles (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku          VARCHAR(128) NOT NULL UNIQUE,
                name         VARCHAR(255) NOT NULL,
                vendor       VARCHAR(128),
                technology   VARCHAR(128),
                description  VARCHAR(1024),
                is_active    BOOLEAN NOT NULL DEFAULT TRUE,
                attributes   JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bundle_items (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                bundle_id    UUID NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
                product_id   UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                default_qty  INTEGER NOT NULL DEFAULT 1,
                is_optional  BOOLEAN NOT NULL DEFAULT FALSE,
                is_removable BOOLEAN NOT NULL DEFAULT TRUE,
                sort_order   INTEGER NOT NULL DEFAULT 0,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_bundle_items_bundle_product UNIQUE (bundle_id, product_id)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bundle_items_bundle ON bundle_items (bundle_id)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS financing_terms (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name            VARCHAR(128) NOT NULL,
                term_months     INTEGER NOT NULL DEFAULT 36,
                annual_rate_pct NUMERIC(6,4) NOT NULL DEFAULT 0.0500,
                subscription_interval VARCHAR(16) NOT NULL DEFAULT 'MONTH',
                is_default      BOOLEAN NOT NULL DEFAULT FALSE,
                is_active       BOOLEAN NOT NULL DEFAULT TRUE,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customer_price_overrides (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                product_id    UUID REFERENCES products(id) ON DELETE CASCADE,
                component_id  UUID REFERENCES product_components(id) ON DELETE CASCADE,
                override_margin_pct NUMERIC(6,4),
                override_unit_price NUMERIC(12,2),
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT cpo_target_check CHECK (product_id IS NOT NULL OR component_id IS NOT NULL)
            )
        """))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_cpo_tenant_component ON customer_price_overrides (tenant_id, component_id) WHERE component_id IS NOT NULL"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_cpo_tenant_product ON customer_price_overrides (tenant_id, product_id) WHERE product_id IS NOT NULL"))

        # §4.5 customer_pricing: cost-plus-margin model alongside legacy discount.
        conn.execute(text("ALTER TABLE customer_pricing ADD COLUMN IF NOT EXISTS default_margin_pct NUMERIC(6,4) NOT NULL DEFAULT 0.2000"))
        conn.execute(text("ALTER TABLE customer_pricing ADD COLUMN IF NOT EXISTS credit_status VARCHAR(16) NOT NULL DEFAULT 'PENDING'"))
        conn.execute(text("ALTER TABLE customer_pricing ADD COLUMN IF NOT EXISTS credit_limit NUMERIC(12,2)"))
        conn.execute(text("ALTER TABLE customer_pricing ADD COLUMN IF NOT EXISTS opex_eligible BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE customer_pricing ADD COLUMN IF NOT EXISTS credit_checked_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE customer_pricing ADD COLUMN IF NOT EXISTS credit_bureau_ref VARCHAR(128)"))

        # §4.7 tenant_onboarding: business-credit inputs (consumed by future credit layer).
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS legal_company_name VARCHAR(255)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS ein VARCHAR(32)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS business_registration_no VARCHAR(64)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS business_credit_bureau VARCHAR(64)"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS business_credit_score INTEGER"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS credit_check_result JSONB NOT NULL DEFAULT '{}'::jsonb"))

        # §4.8 quotes header: financial model.
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS financial_model VARCHAR(8) NOT NULL DEFAULT 'CAPEX'"))
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS subscription_interval VARCHAR(16)"))

        # §4.8 quote_lines / order_lines: component-pricing snapshots (mirror each other).
        for _ln_table in ('quote_lines', 'order_lines'):
            conn.execute(text(f"ALTER TABLE {_ln_table} ADD COLUMN IF NOT EXISTS component_type VARCHAR(32)"))
            conn.execute(text(f"ALTER TABLE {_ln_table} ADD COLUMN IF NOT EXISTS financial_model VARCHAR(8)"))
            conn.execute(text(f"ALTER TABLE {_ln_table} ADD COLUMN IF NOT EXISTS product_id UUID REFERENCES products(id) ON DELETE SET NULL"))
            conn.execute(text(f"ALTER TABLE {_ln_table} ADD COLUMN IF NOT EXISTS component_id UUID REFERENCES product_components(id) ON DELETE SET NULL"))
            conn.execute(text(f"ALTER TABLE {_ln_table} ADD COLUMN IF NOT EXISTS cost_snapshot NUMERIC(12,4) NOT NULL DEFAULT 0"))
            conn.execute(text(f"ALTER TABLE {_ln_table} ADD COLUMN IF NOT EXISTS margin_pct_snapshot NUMERIC(6,4) NOT NULL DEFAULT 0"))
            conn.execute(text(f"ALTER TABLE {_ln_table} ADD COLUMN IF NOT EXISTS leasing_pct_snapshot NUMERIC(6,4)"))
            conn.execute(text(f"ALTER TABLE {_ln_table} ADD COLUMN IF NOT EXISTS term_months INTEGER"))

        # §4.8 orders header parity.
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS financial_model VARCHAR(8) NOT NULL DEFAULT 'CAPEX'"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS subscription_interval VARCHAR(16)"))

        # --- Multi-tenant Phase 0: canonical CellHub master tenant ---
        # Stable, well-known row that per-tenant config is backfilled and cloned
        # from in later phases. Idempotent: only inserted if its fixed id is
        # absent, so re-runs and existing data are left untouched.
        conn.execute(
            text(
                """
                INSERT INTO tenants (id, name, tenant_type)
                SELECT :tid, :tname, 'CELLHUB'
                WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE id = :tid)
                """
            ),
            {"tid": CELLHUB_MASTER_TENANT_ID, "tname": CELLHUB_MASTER_TENANT_NAME},
        )

        # --- Multi-tenant Phase 1: financing_terms become per-tenant ---
        # Shared-catalog decision: financing is the ONLY global config table that
        # goes per-tenant; products/catalog/bundles stay global. Existing global
        # rows are backfilled to the master tenant (runs after the seed above so
        # the master row is guaranteed to exist).
        conn.execute(text(
            "ALTER TABLE financing_terms ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE"
        ))
        conn.execute(
            text("UPDATE financing_terms SET tenant_id = :master WHERE tenant_id IS NULL"),
            {"master": CELLHUB_MASTER_TENANT_ID},
        )
        # Defensive: collapse duplicate (tenant_id, name) rows before the unique
        # index. Pre-per-tenant data could have several same-named global rows that
        # all backfilled onto the master tenant. Keep the earliest of each. Safe —
        # financing_terms is looked up by value, not referenced by any FK.
        conn.execute(text(
            """
            DELETE FROM financing_terms ft
            WHERE ft.id NOT IN (
                SELECT DISTINCT ON (tenant_id, name) id FROM financing_terms
                ORDER BY tenant_id, name, created_at
            )
            """
        ))
        # Defensive: a partial-unique default index aborts the whole migration txn
        # if dirty data already has >1 default per tenant. Keep the earliest.
        conn.execute(text(
            """
            UPDATE financing_terms SET is_default = FALSE
            WHERE is_default = TRUE AND id NOT IN (
                SELECT DISTINCT ON (tenant_id) id FROM financing_terms
                WHERE is_default = TRUE ORDER BY tenant_id, created_at
            )
            """
        ))
        conn.execute(text("ALTER TABLE financing_terms ALTER COLUMN tenant_id SET NOT NULL"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_financing_tenant_name ON financing_terms (tenant_id, name)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_financing_tenant_default ON financing_terms (tenant_id) WHERE is_default"
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_financing_tenant ON financing_terms (tenant_id)"))

        # --- Multi-tenant Phase 3: tenant_settings (JSONB soft toggles) ---
        # Typed tables hold money/pricing/financing (Phases 0–1); soft toggles —
        # design-ops prefs, managed-service category availability, feature flags —
        # live here as JSONB. One row per tenant (backfilled below; new tenants get
        # one via TenantProvisioningService).
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS tenant_settings (
              tenant_id      UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
              design_ops     JSONB NOT NULL DEFAULT '{}'::jsonb,
              admin_services JSONB NOT NULL DEFAULT '{}'::jsonb,
              feature_flags  JSONB NOT NULL DEFAULT '{}'::jsonb,
              updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO tenant_settings (tenant_id)
            SELECT id FROM tenants
            WHERE NOT EXISTS (SELECT 1 FROM tenant_settings ts WHERE ts.tenant_id = tenants.id)
            """
        ))

        _apply_rls_policies(conn)


def _apply_rls_policies(conn) -> None:
    """Multi-tenant Phase 4 — Row-Level Security (behind the ENABLE_RLS flag).

    Idempotent and *bidirectional*: when ``ENABLE_RLS`` is on, every tenant-scoped
    table gets RLS enabled+forced with a ``tenant_isolation`` policy; when off, the
    same tables are reverted (policy dropped, RLS disabled) so the flag is a true
    kill switch and a stuck-on state self-heals on the next boot.

    The policy allows all rows when ``app.current_tenant_id`` is unset (migrations,
    seeds, cron, unauthenticated paths) and otherwise restricts to the active
    tenant. ``FORCE`` makes it apply to the table owner too — but a SUPERUSER DB
    role still bypasses RLS, so the app must connect as a non-superuser owner.
    """
    from app.core.config import get_settings

    enable = get_settings().enable_rls

    # Every table that carries a tenant_id. Shared catalog tables (products,
    # product_components, bundles, bundle_items, catalog_items) are intentionally
    # global and excluded. Names are a fixed allowlist (safe to interpolate).
    rls_tables = (
        'users', 'quotes', 'orders', 'contracts', 'subscriptions', 'invoices',
        'payments', 'assets', 'network_designs', 'carts', 'customer_pricing',
        'customer_price_overrides', 'list_prices', 'tenant_order_notification_settings',
        'tenant_onboarding', 'financing_terms', 'tenant_settings',
    )

    # NULLIF(..., '') because a custom GUC, once set then reset at transaction end,
    # reverts to an EMPTY STRING (not NULL) on a pooled connection — so both NULL
    # and '' must mean "no tenant context → allow all" (system/seed/unauth paths).
    policy = (
        "NULLIF(current_setting('app.current_tenant_id', true), '') IS NULL "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    )

    for table in rls_tables:
        has_tenant_col = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t AND column_name = 'tenant_id'
                """
            ),
            {'t': table},
        ).first()
        if not has_tenant_col:
            continue

        # Always drop first so re-runs (and policy-text changes) are clean.
        conn.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON {table}'))
        if enable:
            conn.execute(text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY'))
            conn.execute(text(
                f'CREATE POLICY tenant_isolation ON {table} '
                f'USING ({policy}) WITH CHECK ({policy})'
            ))
        else:
            conn.execute(text(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY'))
            conn.execute(text(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY'))
