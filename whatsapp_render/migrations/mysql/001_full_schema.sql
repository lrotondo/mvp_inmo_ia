-- Esquema completo whatsapp_render para MySQL 8+ (utf8mb4)
-- Equivalente a app/models.py. Postgres: ver migrations/embedded_signup.sql (legacy).

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS tenants (
    id INT NOT NULL AUTO_INCREMENT,
    phone_number_id VARCHAR(64) NOT NULL,
    access_token TEXT NOT NULL,
    name VARCHAR(255) NULL,
    system_prompt TEXT NULL,
    catalog_csv_path VARCHAR(512) NULL,
    catalog_rent_csv_path VARCHAR(512) NULL,
    waba_id VARCHAR(64) NULL,
    business_portfolio_id VARCHAR(64) NULL,
    onboarding_status VARCHAR(32) NOT NULL DEFAULT 'manual',
    onboarding_error TEXT NULL,
    connected_at DATETIME(6) NULL,
    token_expires_at DATETIME(6) NULL,
    platform_tenant_id INT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tenants_phone_number_id (phone_number_id),
    KEY ix_tenants_phone_number_id (phone_number_id),
    KEY ix_tenants_waba_id (waba_id),
    KEY ix_tenants_platform_tenant_id (platform_tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS onboarding_sessions (
    id INT NOT NULL AUTO_INCREMENT,
    invite_token VARCHAR(64) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    waba_id VARCHAR(64) NULL,
    phone_number_id VARCHAR(64) NULL,
    business_portfolio_id VARCHAR(64) NULL,
    tenant_id INT NULL,
    platform_tenant_id INT NULL,
    error_message TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_onboarding_sessions_invite_token (invite_token),
    KEY ix_onboarding_sessions_waba_id (waba_id),
    KEY ix_onboarding_sessions_phone_number_id (phone_number_id),
    KEY ix_onboarding_sessions_platform_tenant_id (platform_tenant_id),
    CONSTRAINT fk_onboarding_sessions_tenant FOREIGN KEY (tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INT NOT NULL AUTO_INCREMENT,
    phone_number_id VARCHAR(64) NOT NULL,
    wa_id VARCHAR(32) NOT NULL,
    flow_path VARCHAR(32) NOT NULL DEFAULT 'nuevo',
    bot_paused TINYINT(1) NOT NULL DEFAULT 0,
    capture_data TEXT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_chat_session (phone_number_id, wa_id),
    KEY ix_chat_sessions_phone_number_id (phone_number_id),
    KEY ix_chat_sessions_wa_id (wa_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_messages (
    id INT NOT NULL AUTO_INCREMENT,
    phone_number_id VARCHAR(64) NOT NULL,
    wa_id VARCHAR(32) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY ix_chat_messages_phone_number_id (phone_number_id),
    KEY ix_chat_messages_wa_id (wa_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_leads (
    id INT NOT NULL AUTO_INCREMENT,
    phone_number_id VARCHAR(64) NOT NULL,
    wa_id VARCHAR(32) NOT NULL,
    contact_name VARCHAR(255) NULL,
    property_ref VARCHAR(512) NULL,
    lead_type VARCHAR(32) NOT NULL DEFAULT 'venta',
    capture_summary TEXT NULL,
    interest_summary TEXT NOT NULL,
    conversation_summary TEXT NOT NULL,
    conversation_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY ix_client_leads_phone_number_id (phone_number_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS client_waitlist (
    id INT NOT NULL AUTO_INCREMENT,
    phone_number_id VARCHAR(64) NOT NULL,
    wa_id VARCHAR(32) NOT NULL,
    contact_name VARCHAR(255) NULL,
    seek_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    requirements_json TEXT NOT NULL,
    requirements_summary TEXT NOT NULL,
    conversation_summary TEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_client_waitlist_active (phone_number_id, wa_id, seek_type, status),
    KEY ix_client_waitlist_phone_number_id (phone_number_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
