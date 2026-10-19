// Menu « Exporter » (UX-DR21, D-3, AD-20) : un bouton par format en large ; sous 768 px, un seul
// bouton « Exporter » qui ouvre la liste des formats. Utilitaire partagé : le Chat l'utilise pour
// JSON et Markdown, l'Arène (story 3.6) le reprendra pour CSV et Markdown.
//
//   const menu = exportMenu({ items: [{ label, onClick }, …], label? });
//   host.append(menu.root);  menu.setDisabled(bool);  menu.setHidden(bool);
//
// `onClick` suit la route d'export du serveur (un lien `Content-Disposition: attachment`, jamais
// de `blob:`) : le composant ne fabrique aucun fichier. La bascule large / étroit est faite en CSS
// (`.wl-export-wide`, `.wl-export-narrow`, css/components/export-menu.css) : les deux jeux de
// boutons existent, un seul est affiché.
//
// Clavier (patron du bouton à menu) : sur « Exporter », Entrée, Espace ou Flèche bas ouvrent la
// liste sur son premier format ; Flèche haut / bas, Début et Fin la parcourent en boucle ; Entrée
// ou Espace choisit ; Échap ferme et rend le focus à « Exporter » ; un clic ailleurs, ou le focus
// qui sort de la liste, la ferme. Sans Shadow DOM.

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";

let counter = 0;

// `items` : [{label, onClick}] ; `label` : nom du groupe et du bouton replié (« Exporter »).
export function exportMenu({ items, label = t("components.export_menu.label"), className = "" }) {
  const id = `wl-export-${++counter}`;
  const root = element("div", `wl-export ${className}`.trim());
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", label);

  const wide = element("div", "wl-export-wide");
  const buttons = items.map((item) => {
    const button = element("button", "btn", item.label);
    button.type = "button";
    button.addEventListener("click", () => item.onClick());
    wide.append(button);
    return button;
  });

  const narrow = element("div", "wl-export-narrow");
  const toggle = element("button", "btn");
  toggle.type = "button";
  toggle.setAttribute("aria-haspopup", "menu");
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", id);
  toggle.append(element("span", "", label), icon("expand-more"));
  const list = element("ul", "wl-export-list");
  list.id = id;
  list.setAttribute("role", "menu");
  list.setAttribute("aria-label", label);
  list.hidden = true;
  const choices = items.map((item) => {
    const choice = element("button", "btn wl-export-choice", item.label);
    choice.type = "button";
    choice.tabIndex = -1;
    choice.setAttribute("role", "menuitem");
    choice.addEventListener("click", () => {
      setOpen(false);
      toggle.focus();
      item.onClick();
    });
    const entry = element("li");
    entry.setAttribute("role", "none");
    entry.append(choice);
    list.append(entry);
    return choice;
  });
  narrow.append(toggle, list);
  root.append(wide, narrow);

  const outside = (event) => {
    if (!root.contains(event.target)) setOpen(false);
  };
  function setOpen(open) {
    list.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) document.addEventListener("pointerdown", outside);
    else document.removeEventListener("pointerdown", outside);
  }
  function openAndFocus(index = 0) {
    setOpen(true);
    choices[index]?.focus();
  }
  function move(step) {
    const at = choices.indexOf(document.activeElement);
    const next = at === -1 ? 0 : (at + step + choices.length) % choices.length;
    choices[next].focus();
  }

  toggle.addEventListener("click", () => {
    if (list.hidden) openAndFocus();
    else setOpen(false);
  });
  toggle.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openAndFocus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openAndFocus(choices.length - 1);
    }
  });
  list.addEventListener("keydown", (event) => {
    const moves = { ArrowDown: () => move(1), ArrowUp: () => move(-1) };
    if (event.key === "Home") choices[0].focus();
    else if (event.key === "End") choices[choices.length - 1].focus();
    else if (moves[event.key]) moves[event.key]();
    else return;
    event.preventDefault();
  });
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !list.hidden) {
      event.preventDefault();
      event.stopPropagation(); // Échap ferme le menu avant d'arrêter une réponse (wl-run-status)
      setOpen(false);
      toggle.focus();
    }
  });
  root.addEventListener("focusout", (event) => {
    if (event.relatedTarget && !root.contains(event.relatedTarget)) setOpen(false);
  });

  return {
    root,
    buttons,
    toggle,
    setDisabled(disabled) {
      for (const button of [...buttons, ...choices, toggle]) button.disabled = disabled;
      if (disabled) setOpen(false);
    },
    setHidden(hidden) {
      root.hidden = hidden;
      if (hidden) setOpen(false);
    },
    open: () => openAndFocus(),
    close: () => setOpen(false),
  };
}
