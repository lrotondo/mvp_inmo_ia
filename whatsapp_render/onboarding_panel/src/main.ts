import {
  fetchConfig,
  fetchPendingSession,
  fetchSessionByWaba,
  postComplete,
  postSessionEvent,
  patchTenant,
  type EmbeddedAssets,
  type CompleteResult,
  type OnboardingConfig,
} from "./api";

declare global {
  interface Window {
    fbAsyncInit?: () => void;
    FB?: {
      init: (opts: Record<string, unknown>) => void;
      login: (
        cb: (response: { authResponse?: { code?: string }; status?: string }) => void,
        opts: Record<string, unknown>,
      ) => void;
    };
  }
}

let embeddedAssets: EmbeddedAssets | null = null;
let lastComplete: CompleteResult | null = null;
let platformTenantId: number | null = null;
let appConfig: OnboardingConfig | null = null;

const configStatus = document.getElementById("config-status")!;
const btnConnect = document.getElementById("btn-connect") as HTMLButtonElement;
const connectHint = document.getElementById("connect-hint")!;
const stepCatalog = document.getElementById("step-catalog")!;
const stepDone = document.getElementById("step-done")!;
const stepError = document.getElementById("step-error")!;
const doneSummary = document.getElementById("done-summary")!;
const errorMessage = document.getElementById("error-message")!;
const btnSaveCatalog = document.getElementById("btn-save-catalog") as HTMLButtonElement;
const catalogStatus = document.getElementById("catalog-status")!;

function parsePlatformTenantId(): number | null {
  const raw = new URLSearchParams(window.location.search).get("platform_tenant_id");
  if (!raw) return null;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function isValidWabaId(wabaId: string | undefined): boolean {
  const w = (wabaId || "").trim();
  if (!w) return false;
  if (appConfig?.app_id && w === appConfig.app_id) return false;
  return true;
}

function showError(msg: string) {
  stepError.classList.remove("hidden");
  errorMessage.textContent = msg;
}

function hideError() {
  stepError.classList.add("hidden");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollPendingSession(
  attempts = 4,
  delayMs = 500,
): Promise<{ wabaId: string; phoneId: string; businessPortfolioId?: string } | null> {
  for (let i = 0; i < attempts; i += 1) {
    const sess = await fetchPendingSession(platformTenantId, {
      wabaId: isValidWabaId(embeddedAssets?.waba_id)
        ? embeddedAssets!.waba_id
        : undefined,
      phoneNumberId: embeddedAssets?.phone_number_id,
    }).catch(() => null);
    if (sess?.waba_id && isValidWabaId(sess.waba_id)) {
      return {
        wabaId: sess.waba_id,
        phoneId: (sess.phone_number_id || "").trim(),
        businessPortfolioId: sess.business_portfolio_id || undefined,
      };
    }
    if (i < attempts - 1) {
      await sleep(delayMs);
    }
  }
  return null;
}

async function resolveAssetsForComplete(): Promise<{
  wabaId: string;
  phoneId: string;
  businessPortfolioId?: string;
} | null> {
  let wabaId = isValidWabaId(embeddedAssets?.waba_id)
    ? (embeddedAssets!.waba_id as string).trim()
    : "";
  let phoneId = (embeddedAssets?.phone_number_id || "").trim();
  let businessPortfolioId = embeddedAssets?.business_portfolio_id;

  if (!phoneId && wabaId) {
    const sess = await fetchSessionByWaba(wabaId).catch(() => null);
    phoneId = sess?.phone_number_id?.trim() || phoneId;
    businessPortfolioId = businessPortfolioId || sess?.business_portfolio_id || undefined;
  }

  if (!wabaId || !phoneId) {
    const pending = await pollPendingSession();
    if (pending) {
      wabaId = pending.wabaId;
      phoneId = pending.phoneId || phoneId;
      businessPortfolioId = pending.businessPortfolioId || businessPortfolioId;
    }
  }

  if (!wabaId || !isValidWabaId(wabaId)) {
    return null;
  }
  return { wabaId, phoneId, businessPortfolioId };
}

window.addEventListener("message", (event) => {
  if (!event.origin.endsWith("facebook.com")) return;
  try {
    const data = JSON.parse(event.data as string);
    if (data.type === "WA_EMBEDDED_SIGNUP" && data.data) {
      const d = data.data;
      const rawWaba = String(d.waba_id || "").trim();
      embeddedAssets = {
        waba_id: isValidWabaId(rawWaba) ? rawWaba : undefined,
        phone_number_id: d.phone_number_id
          ? String(d.phone_number_id)
          : undefined,
        business_portfolio_id: d.business_id
          ? String(d.business_id)
          : undefined,
        event: data.event ? String(data.event) : undefined,
      };
      if (embeddedAssets.waba_id || embeddedAssets.phone_number_id || platformTenantId != null) {
        postSessionEvent(embeddedAssets, platformTenantId).catch((err) =>
          console.warn("session-event:", err),
        );
        connectHint.textContent = embeddedAssets.waba_id
          ? "Cuenta detectada. Completá el popup si aún está abierto…"
          : "Cuenta detectada (sin teléfono en el popup). Completá el popup…";
      }
    }
  } catch {
    /* ignore non-JSON */
  }
});

async function initFacebookSdk(appId: string, graphVersion: string): Promise<void> {
  return new Promise((resolve) => {
    window.fbAsyncInit = () => {
      window.FB?.init({
        appId,
        autoLogAppEvents: true,
        xfbml: true,
        version: graphVersion,
      });
      resolve();
    };
    if (window.FB) {
      window.fbAsyncInit();
    }
  });
}

function launchWhatsAppSignup(configId: string) {
  if (!window.FB) {
    showError("SDK de Facebook no cargó. Recargá la página.");
    return;
  }
  hideError();
  embeddedAssets = null;
  connectHint.textContent = "Abrí el popup de Meta y seguí los pasos…";

  window.FB.login(
    (response) => {
      void (async () => {
        if (!response.authResponse?.code) {
          showError("No se recibió código de autorización. Intentá de nuevo.");
          return;
        }
        connectHint.textContent = "Finalizando conexión con el servidor…";
        const resolved = await resolveAssetsForComplete();
        try {
          const name = (document.getElementById("tenant-name") as HTMLInputElement).value.trim();
          const payload: Parameters<typeof postComplete>[0] = {
            code: response.authResponse.code,
            name: name || undefined,
            platform_tenant_id: platformTenantId ?? undefined,
            business_portfolio_id: resolved?.businessPortfolioId,
            event: embeddedAssets?.event,
          };
          if (resolved) {
            payload.waba_id = resolved.wabaId;
            if (resolved.phoneId) {
              payload.phone_number_id = resolved.phoneId;
            }
          }
          lastComplete = await postComplete(payload);
          stepCatalog.classList.remove("hidden");
          connectHint.textContent = "Conexión exitosa.";
          doneSummary.textContent = `Tenant #${lastComplete.tenant_id} — teléfono ${
            lastComplete.display_phone || lastComplete.phone_number_id
          }`;
        } catch (err) {
          if (!resolved) {
            showError(
              "No encontramos la cuenta WhatsApp pendiente. Esperá unos segundos y volvé a conectar, " +
                "o abrí el panel con ?platform_tenant_id= en la URL.",
            );
          } else {
            showError(err instanceof Error ? err.message : String(err));
          }
        }
      })();
    },
    {
      config_id: configId,
      response_type: "code",
      override_default_response_type: true,
      extras: { setup: {} },
    },
  );
}

btnConnect.addEventListener("click", () => {
  const configId = btnConnect.dataset.configId;
  if (configId) launchWhatsAppSignup(configId);
});

btnSaveCatalog.addEventListener("click", async () => {
  if (!lastComplete) return;
  const sale = (document.getElementById("catalog-sale") as HTMLInputElement).value.trim();
  const rent = (document.getElementById("catalog-rent") as HTMLInputElement).value.trim();
  const name = (document.getElementById("tenant-name") as HTMLInputElement).value.trim();
  catalogStatus.textContent = "Guardando…";
  try {
    await patchTenant(lastComplete.tenant_id, {
      catalog_csv_path: sale || undefined,
      catalog_rent_csv_path: rent || undefined,
      name: name || undefined,
    });
    catalogStatus.textContent = "Catálogo guardado.";
    stepDone.classList.remove("hidden");
  } catch (err) {
    catalogStatus.textContent = "";
    showError(err instanceof Error ? err.message : String(err));
  }
});

(async () => {
  platformTenantId = parsePlatformTenantId();
  try {
    const cfg = await fetchConfig();
    appConfig = cfg;
    if (!cfg.configured) {
      configStatus.textContent =
        "Backend sin META_APP_ID / META_EMBEDDED_SIGNUP_CONFIG_ID. Configurá Render primero.";
      return;
    }
    const platformHint =
      platformTenantId != null ? ` — inmobiliaria #${platformTenantId}` : "";
    configStatus.textContent = `App ${cfg.app_id} — Graph ${cfg.graph_version}${platformHint}`;
    await initFacebookSdk(cfg.app_id, cfg.graph_version);
    btnConnect.disabled = false;
    btnConnect.dataset.configId = cfg.config_id;
    connectHint.textContent =
      "Necesitás permisos de administrador en el Business Manager de la inmobiliaria.";
  } catch (err) {
    configStatus.textContent = "No se pudo cargar la configuración del API.";
    showError(err instanceof Error ? err.message : String(err));
  }
})();
