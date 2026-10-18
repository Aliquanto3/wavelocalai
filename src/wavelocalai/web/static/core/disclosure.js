// Panneau déroulant d'un bouton de la barre haute (menu Affichage, Ollama, CO2, aide du cloud) :
// ouvert par le bouton, fermé par Échap (le focus revient au bouton), par un clic ailleurs et
// quand le focus quitte la zone. Un panneau ouvert referme les autres.

const openers = new Set();

// `scope` : l'élément qui contient le bouton et le panneau (`.tool`).
export function bindDisclosure({ button, panel, scope, onToggle = () => {} }) {
  const setOpen = (open) => {
    if (open) {
      for (const close of openers) if (close !== setClosed) close();
    }
    panel.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    onToggle(open);
  };
  const setClosed = () => {
    if (!panel.hidden) setOpen(false);
  };
  openers.add(setClosed);
  setOpen(false);

  button.addEventListener("click", () => setOpen(panel.hidden));
  document.addEventListener("pointerdown", (event) => {
    if (!panel.hidden && !scope.contains(event.target)) setOpen(false);
  });
  scope.addEventListener("focusout", (event) => {
    if (!panel.hidden && event.relatedTarget && !scope.contains(event.relatedTarget)) {
      setOpen(false);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      event.preventDefault(); // Échap a fermé le panneau : il n'arrête pas un run suivi
      setOpen(false);
      button.focus();
    }
  });
  return { open: () => setOpen(true), close: setClosed };
}
