// Page d'essai du sélecteur de modèle et de l'état de run (story 1.10) : servie par les tests E2E
// seulement (`/__fixtures__/`). Elle charge les vrais modules de `/static/`, comme la coquille :
// textes d'abord, composants ensuite. Les réponses de `/api/models*` sont simulées par le test.

import { applyTexts, loadTexts } from "/static/core/i18n.js";
import { setTheme } from "/static/core/theme.js";

await loadTexts();
applyTexts();
const theme = new URLSearchParams(location.search).get("theme");
if (theme) setTheme(theme);
await import("/static/components/index.js");

window.changes = [];
for (const id of ["single", "multi"]) {
  document.getElementById(id).addEventListener("wl-model-change", (event) => {
    window.changes.push({ id, values: event.detail.values });
  });
}
window.ended = [];
document.getElementById("status").addEventListener("wl-run-ended", (event) => {
  window.ended.push(event.detail.status);
});
document.body.dataset.ready = "true";
