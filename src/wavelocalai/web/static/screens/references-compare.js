// « Comparer ces modèles » (story 5.8, D-19) : ouvre l'Arène (`#/arene/comparer`) avec, dans son
// sélecteur de modèles, ceux du groupe que le serveur a dits installés sur ce poste (`compare.tags`).
// L'écran de l'Arène ne change pas : son sélecteur reçoit le choix de l'extérieur, comme le fait
// `arena-actions.js` pour « Relancer », puis l'Arène recalcule la raison du bouton Lancer.
//
// Le routeur monte l'Arène à la demande, puis l'affiche (`hidden` retiré) : on attend ce moment, jamais
// plus de `WAIT_MS`, pour ne pas poser le choix sur un sélecteur que le routeur est en train de
// remplacer.

const WAIT_MS = 8000;
const ARENA = 'section[data-screen="arena-compare"]';

function apply(picker, tags) {
  picker.values = tags;
  picker.dispatchEvent(new CustomEvent("wl-model-change", { bubbles: true, detail: { values: picker.values } }));
}

export function openArenaWith(tags) {
  const started = performance.now();
  const tick = () => {
    const host = document.querySelector(ARENA);
    const picker = host && !host.hidden ? host.querySelector('wl-model-picker[purpose="arena"]') : null;
    if (picker) apply(picker, tags);
    else if (performance.now() - started < WAIT_MS) requestAnimationFrame(tick);
  };
  location.hash = "#/arene/comparer";
  requestAnimationFrame(tick);
}
