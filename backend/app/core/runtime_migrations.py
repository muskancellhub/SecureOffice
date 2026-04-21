from sqlalchemy import text
from app.core.database import engine


def apply_runtime_migrations() -> None:
    with engine.begin() as conn:
        # RBAC permissions column for existing databases.
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB NOT NULL DEFAULT '[]'::jsonb"))

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
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS metadata JSONB"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))

        conn.execute(text("UPDATE tenant_onboarding SET credit_validation_status = 'PENDING' WHERE credit_validation_status IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET tax_validation_status = 'PENDING' WHERE tax_validation_status IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET company_setup_completed = FALSE WHERE company_setup_completed IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET payment_method_setup = FALSE WHERE payment_method_setup IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET payment_validation_status = 'PENDING' WHERE payment_validation_status IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET onboarding_completed = FALSE WHERE onboarding_completed IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET metadata = '{}'::jsonb WHERE metadata IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET created_at = NOW() WHERE created_at IS NULL"))
        conn.execute(text("UPDATE tenant_onboarding SET updated_at = NOW() WHERE updated_at IS NULL"))

        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN credit_validation_status SET DEFAULT 'PENDING'"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN tax_validation_status SET DEFAULT 'PENDING'"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN company_setup_completed SET DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN payment_method_setup SET DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN payment_validation_status SET DEFAULT 'PENDING'"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN onboarding_completed SET DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN metadata SET DEFAULT '{}'::jsonb"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN created_at SET DEFAULT NOW()"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN updated_at SET DEFAULT NOW()"))

        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN credit_validation_status SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN tax_validation_status SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN company_setup_completed SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN payment_method_setup SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN payment_validation_status SET NOT NULL"))
        conn.execute(text("ALTER TABLE tenant_onboarding ALTER COLUMN onboarding_completed SET NOT NULL"))
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
