-- Migración Embedded Signup (ejecutar en Postgres existente)

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS waba_id VARCHAR(64);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS business_portfolio_id VARCHAR(64);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS onboarding_status VARCHAR(32) NOT NULL DEFAULT 'manual';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS onboarding_error TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_tenants_waba_id ON tenants (waba_id);

UPDATE tenants SET onboarding_status = 'manual' WHERE onboarding_status IS NULL;

CREATE TABLE IF NOT EXISTS onboarding_sessions (
    id SERIAL PRIMARY KEY,
    invite_token VARCHAR(64) UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    waba_id VARCHAR(64),
    phone_number_id VARCHAR(64),
    business_portfolio_id VARCHAR(64),
    tenant_id INTEGER REFERENCES tenants(id),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_onboarding_sessions_waba_id ON onboarding_sessions (waba_id);
CREATE INDEX IF NOT EXISTS ix_onboarding_sessions_phone_number_id ON onboarding_sessions (phone_number_id);
