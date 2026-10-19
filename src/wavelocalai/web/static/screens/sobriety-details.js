// Sobriété, les deux panneaux repliés (story 5.1) : « Carte d'identité technique » et « Comment ces
// chiffres sont calculés ». Rien n'est lu avant l'ouverture d'un panneau, puis une lecture à chaque
// ouverture (jamais en boucle), toujours après le repère `shell-ready` (AD-15).
//
// - Identité : `GET /api/system/identity` (fiche machine et version d'Ollama de l'état en cache de
//   la sonde) ; la version de WaveLocalAI vient de `/api/health`, déjà dans le store.
// - Méthode : CodeCarbon pour le local, ecologits pour le cloud (« estimé »), règle D3 du débit, ce
//   qui rend une réponse non mesurable, puis l'équivalence parlante en voiture (D-38) lue sur
//   `GET /api/carbon/method` : distance, facteur, source et date viennent du serveur, jamais d'une
//   constante du front. Panneau ouvert, chaque nouvelle somme de session la relit. L'équivalence
//   n'apparaît nulle part ailleurs.
// - Une réponse tardive d'un panneau refermé ou d'un écran démonté ne touche à rien.

import { api } from "../core/api.js";
import { element } from "../core/dom.js";
import {
  formatCo2,
  formatDate,
  formatDistance,
  formatGb,
  formatInteger,
  formatNumber,
} from "../core/format.js";
import { t } from "../core/i18n.js";
import { shellReady } from "../core/shell-ready.js";
import { store } from "../core/store.js";

export const METHOD_ID = "sob-method";

function row(list, label, value) {
  list.append(element("dt", "", label), element("dd", "", value));
}

// La fiche en liste de définitions ; chaque champ que le serveur n'a pas pu lire se dit « indisponible ».
function renderIdentity(list, identity, state) {
  const unavailable = t("sobriety.identity.unavailable");
  const accelerator = identity.accelerator ?? {};
  const cores =
    identity.cpu_cores_physical != null && identity.cpu_cores_logical != null
      ? ` (${t("sobriety.identity.cores", {
          physical: formatInteger(identity.cpu_cores_physical),
          logical: formatInteger(identity.cpu_cores_logical),
        })})`
      : "";
  const gpu = accelerator.name
    ? accelerator.memory_total_gb != null
      ? t("sobriety.identity.accelerator_value", {
          name: accelerator.name,
          memory: formatGb(accelerator.memory_total_gb),
        })
      : accelerator.name
    : t("sobriety.identity.accelerator_none");
  const ollama = identity.ollama_version ?? state.ollama.version;
  list.replaceChildren();
  row(list, t("sobriety.identity.cpu"), identity.cpu ? `${identity.cpu}${cores}` : unavailable);
  row(
    list,
    t("sobriety.identity.memory"),
    identity.ram_gb != null
      ? t("sobriety.identity.memory_value", { total: formatGb(identity.ram_gb) })
      : unavailable,
  );
  row(list, t("sobriety.identity.accelerator"), gpu);
  row(list, t("sobriety.identity.os"), identity.os || unavailable);
  row(list, t("sobriety.identity.ollama"), ollama || t("sobriety.identity.ollama_unknown"));
  row(list, t("sobriety.identity.app"), state.version ?? unavailable);
}

// La phrase d'équivalence ; sans réglage serveur (`equivalence` nul), aucune phrase.
function equivalenceText(equivalence) {
  const vars = {
    factor: formatNumber(equivalence.g_per_km),
    source: equivalence.source,
    date: formatDate(equivalence.retrieved_at),
  };
  if (equivalence.distance_m == null) return t("sobriety.method.equivalence_none", vars);
  return t("sobriety.method.equivalence", {
    ...vars,
    value: formatCo2(equivalence.total_mg),
    distance: formatDistance(equivalence.distance_m),
  });
}

export function buildDetails() {
  const identity = element("details", "sob-details");
  identity.dataset.panel = "identity";
  identity.append(element("summary", "", t("sobriety.identity.title")));
  const identityStatus = element("p", "help");
  const identityList = element("dl", "sob-dl");
  identity.append(identityStatus, identityList);

  const method = element("details", "sob-details");
  method.id = METHOD_ID;
  method.dataset.panel = "method";
  const methodSummary = element("summary", "", t("sobriety.method.title"));
  method.append(methodSummary);
  const methodList = element("ul", "sob-method-list");
  for (const key of ["local", "cloud", "throughput", "unmeasurable", "no_threshold"]) {
    methodList.append(element("li", "", t(`sobriety.method.${key}`)));
  }
  const equivalence = element("li", "sob-equivalence");
  equivalence.hidden = true;
  methodList.append(equivalence);
  method.append(methodList);

  let alive = true;
  let identityRead = 0;
  let methodRead = 0;

  async function readIdentity() {
    const mine = ++identityRead;
    identityStatus.textContent = t("sobriety.identity.loading");
    await shellReady();
    try {
      const fiche = await api.systemIdentity();
      if (!alive || mine !== identityRead || !identity.open) return;
      identityStatus.textContent = "";
      renderIdentity(identityList, fiche, store.get());
    } catch {
      if (!alive || mine !== identityRead) return;
      identityStatus.textContent = t("sobriety.identity.failed");
    }
  }

  async function readMethod() {
    const mine = ++methodRead;
    await shellReady();
    try {
      const { equivalence: data } = await api.carbonMethod();
      if (!alive || mine !== methodRead || !method.open) return;
      equivalence.hidden = !data;
      if (data) equivalence.textContent = equivalenceText(data);
    } catch {
      if (!alive || mine !== methodRead) return;
      equivalence.hidden = false;
      equivalence.textContent = t("sobriety.method.equivalence_failed");
    }
  }

  identity.addEventListener("toggle", () => {
    if (identity.open) readIdentity();
  });
  method.addEventListener("toggle", () => {
    if (method.open) readMethod();
  });

  return {
    identity,
    method,
    // « non mesurables » : déplie le panneau de méthode et y amène le focus.
    openMethod() {
      method.open = true;
      methodSummary.focus();
      method.scrollIntoView?.({ block: "nearest" });
    },
    // Panneau de méthode ouvert : la somme de la session a changé, l'équivalence est relue.
    carbonChanged(hidden) {
      if (method.open && !hidden) readMethod();
    },
    // L'écran redevient visible : les panneaux ouverts sont relus.
    shown() {
      if (method.open) readMethod();
      if (identity.open) readIdentity();
    },
    dispose() {
      alive = false;
    },
  };
}
