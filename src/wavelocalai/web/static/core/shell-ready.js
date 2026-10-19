// Repère `shell-ready` (AD-15) : `main.js` le pose une fois la coquille et l'écran courant rendus.
// Un écran monté pendant `router.start()` attend ce repère avant tout appel à `/api/`, pour que la
// coquille s'affiche sans attendre le serveur.
//
//   await shellReady();

export function shellReady() {
  return new Promise((resolve) => {
    const check = () =>
      performance.getEntriesByName("shell-ready").length > 0 ? resolve() : requestAnimationFrame(check);
    check();
  });
}
