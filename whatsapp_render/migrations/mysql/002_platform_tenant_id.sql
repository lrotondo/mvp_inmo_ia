-- Vincular inmobiliaria Espacios360 (ID externo) con onboarding y tenants WhatsApp

ALTER TABLE tenants
    ADD COLUMN platform_tenant_id INT NULL,
    ADD KEY ix_tenants_platform_tenant_id (platform_tenant_id);

ALTER TABLE onboarding_sessions
    ADD COLUMN platform_tenant_id INT NULL,
    ADD KEY ix_onboarding_sessions_platform_tenant_id (platform_tenant_id);
