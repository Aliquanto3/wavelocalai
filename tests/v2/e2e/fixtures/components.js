// Page d'essai des composants partagés (story 1.9) : servie par les tests E2E seulement
// (`/__fixtures__/`), jamais par le serveur de production. Elle charge les vrais modules de
// `/static/`, comme la coquille : textes d'abord, composants ensuite.

import { applyTexts, loadTexts } from "/static/core/i18n.js";
import { setTheme } from "/static/core/theme.js";

await loadTexts();
applyTexts();
const theme = new URLSearchParams(location.search).get("theme");
if (theme) setTheme(theme);
await import("/static/components/index.js");

document.getElementById("error").error = {
  code: "cloud_unreachable",
  message: "Le fournisseur Anthropic ne répond pas.",
  action: "Vérifiez la connexion, la clé et le quota, ou repassez en Local.",
  detail: { technical: "ConnectTimeout après 30 s", provider: "anthropic" },
};
document.body.dataset.ready = "true";
