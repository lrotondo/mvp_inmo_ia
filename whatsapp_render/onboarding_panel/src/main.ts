import {
  fetchConfig,
  postComplete,
  postSessionEvent,
  patchTenant,
  type EmbeddedAssets,
  type CompleteResult,
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

function showError(msg: string) {
  stepError.classList.remove("hidden");
  errorMessage.textContent = msg;
}

function hideError() {
  stepError.classList.add("hidden");
}

window.addEventListener("message", (event) => {
  if (!event.origin.endsWith("facebook.com")) return;
  try {
    const data = JSON.parse(event.data as string);
    if (data.type === "WA_EMBEDDED_SIGNUP" && data.data) {
      const d = data.data;
      embeddedAssets = {
        waba_id: String(d.waba_id || ""),
        phone_number_id: String(d.phone_number_id || ""),
        business_portfolio_id: d.business_id
          ? String(d.business_id)
          : undefined,
        event: data.event ? String(data.event) : undefined,
      };
      if (embeddedAssets.waba_id && embeddedAssets.phone_number_id) {
        postSessionEvent(embeddedAssets).catch((err) =>
          console.warn("session-event:", err),
        );
        connectHint.textContent = "Cuenta detectada. Completá el popup si aún está abierto…";
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
  connectHint.textContent = "Abrí el popup de Meta y seguí los pasos…";

  window.FB.login(
    async (response) => {
      if (!response.authResponse?.code) {
        showError("No se recibió código de autorización. Intentá de nuevo.");
        return;
      }
      if (!embeddedAssets?.waba_id || !embeddedAssets.phone_number_id) {
        showError(
          "Faltan IDs de WhatsApp (WABA / teléfono). Cerrá el popup y volvé a conectar.",
        );
        return;
      }
      try {
        const name = (document.getElementById("tenant-name") as HTMLInputElement).value.trim();
        lastComplete = await postComplete({
          code: response.authResponse.code,
          ...embeddedAssets,
          name: name || undefined,
        });
        stepCatalog.classList.remove("hidden");
        connectHint.textContent = "Conexión exitosa.";
        doneSummary.textContent = `Tenant #${lastComplete.tenant_id} — teléfono ${
          lastComplete.display_phone || lastComplete.phone_number_id
        }`;
      } catch (err) {
        showError(err instanceof Error ? err.message : String(err));
      }
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
  try {
    const cfg = await fetchConfig();
    if (!cfg.configured) {
      configStatus.textContent =
        "Backend sin META_APP_ID / META_EMBEDDED_SIGNUP_CONFIG_ID. Configurá Render primero.";
      return;
    }
    configStatus.textContent = `App ${cfg.app_id} — Graph ${cfg.graph_version}`;
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
