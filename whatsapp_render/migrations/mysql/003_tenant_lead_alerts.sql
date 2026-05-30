-- Alertas de interés por tenant (email + WhatsApp)

ALTER TABLE tenants
    ADD COLUMN lead_alert_email VARCHAR(255) NULL,
    ADD COLUMN lead_alert_whatsapp_to VARCHAR(32) NULL,
    ADD COLUMN lead_notify_email_enabled TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN lead_notify_whatsapp_enabled TINYINT(1) NOT NULL DEFAULT 1;
