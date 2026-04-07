BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'auth_provider') THEN
        CREATE TYPE auth_provider AS ENUM ('LOCAL', 'GOOGLE', 'MICROSOFT');
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('SUPER_ADMIN', 'ADMIN', 'USER');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(320) NOT NULL UNIQUE,
    mobile VARCHAR(32),
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),
    provider auth_provider NOT NULL DEFAULT 'LOCAL',
    provider_id VARCHAR(255),
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    role user_role NOT NULL DEFAULT 'USER',
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_provider_id_required_for_sso
        CHECK (
            (provider = 'LOCAL' AND provider_id IS NULL)
            OR
            (provider IN ('GOOGLE', 'MICROSOFT') AND provider_id IS NOT NULL)
        ),
    CONSTRAINT users_password_required_for_local
        CHECK (
            (provider = 'LOCAL' AND password_hash IS NOT NULL)
            OR
            (provider IN ('GOOGLE', 'MICROSOFT'))
        )
);

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
);

ALTER TABLE users
ADD COLUMN IF NOT EXISTS permissions JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE quotes
ADD COLUMN IF NOT EXISTS created_by UUID;

ALTER TABLE quotes
ADD COLUMN IF NOT EXISTS one_time_total NUMERIC(12, 2) NOT NULL DEFAULT 0;

ALTER TABLE quotes
ADD COLUMN IF NOT EXISTS monthly_total NUMERIC(12, 2) NOT NULL DEFAULT 0;

ALTER TABLE quotes
ADD COLUMN IF NOT EXISTS projected_12_month_cost NUMERIC(12, 2) NOT NULL DEFAULT 0;

ALTER TABLE quotes
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS otps (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS refresh_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users (tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_provider_provider_id ON users (provider, provider_id);
CREATE INDEX IF NOT EXISTS idx_otps_user_id ON otps (user_id);
CREATE INDEX IF NOT EXISTS idx_otps_expires_at ON otps (expires_at);
CREATE INDEX IF NOT EXISTS idx_refresh_sessions_user_id ON refresh_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_sessions_expires_at ON refresh_sessions (expires_at);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE SEQUENCE IF NOT EXISTS quote_public_id_seq START WITH 1 INCREMENT BY 1;
CREATE SEQUENCE IF NOT EXISTS order_public_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE IF NOT EXISTS quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    public_id VARCHAR(32) NOT NULL UNIQUE DEFAULT ('QID' || lpad(nextval('quote_public_id_seq')::text, 4, '0')),
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    one_time_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    monthly_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    projected_12_month_cost NUMERIC(12, 2) NOT NULL DEFAULT 0,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT quotes_status_check CHECK (status IN ('DRAFT', 'SENT', 'ACCEPTED', 'EXPIRED', 'CONVERTED'))
);

CREATE TABLE IF NOT EXISTS quote_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quote_id UUID NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    line_type VARCHAR(16) NOT NULL,
    name VARCHAR(255) NOT NULL,
    sku VARCHAR(128),
    vendor VARCHAR(128),
    qty INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(12, 2) NOT NULL,
    billing VARCHAR(16) NOT NULL,
    interval VARCHAR(16),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    parent_line_id UUID REFERENCES quote_lines(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT quote_lines_type_check CHECK (line_type IN ('DEVICE', 'SERVICE')),
    CONSTRAINT quote_lines_billing_check CHECK (billing IN ('ONE_TIME', 'RECURRING')),
    CONSTRAINT quote_lines_interval_check CHECK (interval IS NULL OR interval IN ('MONTH', 'YEAR'))
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    public_id VARCHAR(32) NOT NULL UNIQUE DEFAULT ('OID' || lpad(nextval('order_public_id_seq')::text, 4, '0')),
    status VARCHAR(32) NOT NULL DEFAULT 'SUBMITTED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT orders_status_check CHECK (status IN ('SUBMITTED', 'PROCESSING', 'VENDOR_ORDERED', 'SHIPPED', 'DELIVERED', 'ACTIVE'))
);

CREATE TABLE IF NOT EXISTS order_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    line_type VARCHAR(16) NOT NULL,
    name VARCHAR(255) NOT NULL,
    sku VARCHAR(128),
    vendor VARCHAR(128),
    qty INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(12, 2) NOT NULL,
    billing VARCHAR(16) NOT NULL,
    interval VARCHAR(16),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    parent_line_id UUID REFERENCES order_lines(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT order_lines_type_check CHECK (line_type IN ('DEVICE', 'SERVICE')),
    CONSTRAINT order_lines_billing_check CHECK (billing IN ('ONE_TIME', 'RECURRING')),
    CONSTRAINT order_lines_interval_check CHECK (interval IS NULL OR interval IN ('MONTH', 'YEAR'))
);

CREATE TABLE IF NOT EXISTS contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    term_months INTEGER NOT NULL DEFAULT 12,
    sla_tier VARCHAR(64) NOT NULL DEFAULT 'STANDARD',
    entitlements JSONB NOT NULL DEFAULT '{}'::jsonb,
    start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    end_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT contracts_status_check CHECK (status IN ('ACTIVE', 'PAUSED', 'CANCELLED', 'EXPIRED'))
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    order_line_id UUID REFERENCES order_lines(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    sku VARCHAR(128),
    vendor VARCHAR(128),
    qty INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    interval VARCHAR(16) NOT NULL DEFAULT 'MONTH',
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    end_date DATE,
    next_billing_date DATE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT subscriptions_interval_check CHECK (interval IN ('MONTH', 'YEAR')),
    CONSTRAINT subscriptions_status_check CHECK (status IN ('ACTIVE', 'PAUSED', 'CANCELLED'))
);

CREATE TABLE IF NOT EXISTS workflow_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    order_id UUID NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
    template_key VARCHAR(64) NOT NULL DEFAULT 'order_fulfillment',
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    current_stage VARCHAR(64) NOT NULL DEFAULT 'ordered',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workflow_instances_status_check CHECK (status IN ('ACTIVE', 'COMPLETED', 'FAILED'))
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_instance_id UUID NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    stage_key VARCHAR(64) NOT NULL,
    display_name VARCHAR(64) NOT NULL,
    sequence INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    retries INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT workflow_steps_status_check CHECK (status IN ('PENDING', 'IN_PROGRESS', 'DONE', 'FAILED'))
);

CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    contract_id UUID REFERENCES contracts(id) ON DELETE SET NULL,
    order_line_id UUID REFERENCES order_lines(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    sku VARCHAR(128),
    vendor VARCHAR(128),
    asset_type VARCHAR(64) NOT NULL DEFAULT 'device',
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    location VARCHAR(255),
    serial_number VARCHAR(128),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT assets_status_check CHECK (status IN ('PROVISIONING', 'ACTIVE', 'RETIRED'))
);

CREATE TABLE IF NOT EXISTS invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
    billing_month DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    status VARCHAR(16) NOT NULL DEFAULT 'DUE',
    due_date DATE NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT invoices_status_check CHECK (status IN ('DUE', 'PAID', 'VOID')),
    CONSTRAINT uq_invoices_subscription_billing_month UNIQUE (subscription_id, billing_month)
);

CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    invoice_id UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    status VARCHAR(32) NOT NULL DEFAULT 'SUCCEEDED',
    method VARCHAR(32) NOT NULL DEFAULT 'MANUAL',
    external_reference VARCHAR(255),
    paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT payments_status_check CHECK (status IN ('SUCCEEDED', 'FAILED')),
    CONSTRAINT payments_method_check CHECK (method IN ('MANUAL', 'CARD', 'BANK_TRANSFER'))
);

CREATE INDEX IF NOT EXISTS idx_quotes_tenant_created_at ON quotes (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_quote_lines_quote_id ON quote_lines (quote_id);
CREATE INDEX IF NOT EXISTS idx_orders_tenant_created_at ON orders (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_lines_order_id ON order_lines (order_id);
CREATE INDEX IF NOT EXISTS idx_contracts_tenant_created_at ON contracts (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant_status ON subscriptions (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_workflow_instances_order_id ON workflow_instances (order_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow_instance_id ON workflow_steps (workflow_instance_id);
CREATE INDEX IF NOT EXISTS idx_assets_tenant_created_at ON assets (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_tenant_billing_month ON invoices (tenant_id, billing_month DESC);
CREATE INDEX IF NOT EXISTS idx_payments_invoice_id ON payments (invoice_id);

COMMIT;
