// Exports d'un écran (décision 3) : un bouton par format en large ; sous 768 px, un seul bouton
// « Exporter » qui ouvre la liste des formats (Chat : JSON et Markdown ; Arène : CSV et Markdown).
// La bascule est faite en CSS (`.wl-export-wide`, `.wl-export-narrow`, css/components.css).
// Liste fermée par Échap (focus rendu au bouton), par un clic ailleurs, quand le focus sort, ou
// après un choix.

import { element, icon } from "../core/dom.js";
import { t } from "../core/i18n.js";

let counter = 0;

// `items` : [{label, onClick}] ; `label` : nom du groupe et du bouton replié (« Exporter »).
export function exportMenu({ label = t("export_menu.label"), items, className = "" }) {
  const id = `wl-export-${++counter}`;
  const root = element("div", `wl-export ${className}`.trim());
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", label);

  const wide = element("div", "wl-export-wide");
  const buttons = items.map((item) => {
    const button = element("button", "btn", "");
    button.type = "button";
    button.append(icon("download"), element("span", "", item.label));
    button.addEventListener("click", () => item.onClick());
    wide.append(button);
    return button;
  });

  const narrow = element("div", "wl-export-narrow");
  const toggle = element("button", "btn", "");
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", id);
  toggle.append(icon("download"), element("span", "", label), icon("expand-more"));
  const list = element("ul", "wl-export-list");
  list.id = id;
  list.hidden = true;
  const choices = items.map((item) => {
    const button = element("button", "btn wl-export-choice", item.label);
    button.type = "button";
    button.addEventListener("click", () => {
      setOpen(false);
      toggle.focus();
      item.onClick();
    });
    const li = element("li");
    li.append(button);
    list.append(li);
    return button;
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
  toggle.addEventListener("click", () => {
    setOpen(list.hidden);
    if (!list.hidden) choices[0]?.focus();
  });
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !list.hidden) {
      event.stopPropagation();
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
    setDisabled(disabled) {
      for (const button of [...buttons, ...choices, toggle]) button.disabled = disabled;
      if (disabled) setOpen(false);
    },
    setHidden(hidden) {
      root.hidden = hidden;
      if (hidden) setOpen(false);
    },
    open: () => setOpen(true),
    close: () => setOpen(false),
  };
}
