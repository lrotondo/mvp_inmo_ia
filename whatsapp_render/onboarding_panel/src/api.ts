const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);
const API_SECRET = import.meta.env.VITE_ONBOARDING_API_SECRET || "";

function authHeaders(): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (API_SECRET) {
    h.Authorization = `Bearer ${API_SECRET}`;
  }
  return h;
}

export type OnboardingConfig = {
  app_id: string;
  config_id: string;
  graph_version: string;
  configured: boolean;
};

export async function fetchConfig(): Promise<OnboardingConfig> {
  const res = await fetch(`${API_BASE}/api/onboarding/config`);
  if (!res.ok) throw new Error(`Config: ${res.status}`);
  return res.json();
}

export type EmbeddedAssets = {
  waba_id: string;
  phone_number_id: string;
  business_portfolio_id?: string;
  event?: string;
};

export async function postSessionEvent(assets: EmbeddedAssets): Promise<void> {
  const res = await fetch(`${API_BASE}/api/onboarding/session-event`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(assets),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `session-event: ${res.status}`);
  }
}

export type CompletePayload = EmbeddedAssets & {
  code: string;
  name?: string;
  catalog_csv_path?: string;
  catalog_rent_csv_path?: string;
};

export type CompleteResult = {
  ok: boolean;
  tenant_id: number;
  phone_number_id: string;
  waba_id: string;
  display_phone?: string;
  onboarding_status: string;
};

export async function postComplete(body: CompletePayload): Promise<CompleteResult> {
  const res = await fetch(`${API_BASE}/api/onboarding/complete`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = (data as { detail?: string }).detail || res.statusText;
    throw new Error(detail);
  }
  return res.json();
}

export async function patchTenant(
  tenantId: number,
  body: Record<string, string | undefined>,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/onboarding/tenants/${tenantId}`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail || `PATCH: ${res.status}`);
  }
}
