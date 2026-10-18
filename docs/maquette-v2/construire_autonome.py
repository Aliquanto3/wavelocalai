"""Construit `maquette-autonome.html`, la maquette en un seul fichier ouvrable au double-clic (file://).

Usage : python construire_autonome.py [--verifier]
Bibliothèque standard seulement. Les sources modulaires restent la référence : relancer ce script
après toute modification de la maquette (le test `test_autonome.py` échoue sinon).

Technique (en file://, Chromium refuse les modules ES et `fetch` sur des fichiers voisins) :
- chaque module de `js/` est embarqué en URL `data:` dans une carte d'import (`importmap`)
  statique ; ses spécificateurs relatifs, y compris le préfixe des `import()` à gabarit du
  routeur, deviennent des noms nus `@wl/js/...`. Une seule URL par module : le chargeur du
  navigateur gère les cycles d'import comme avec les fichiers ;
- `import.meta.url` devient l'adresse fictive `wl:/js/...` : les `new URL("../../donnees/", …)`
  des modules restent valides, et un `fetch` intercepté sert les JSON (`donnees/`, `i18n/`)
  embarqués ; les feuilles d'écran (`css/screens/`) passent par des URL `blob:` ;
- feuilles communes, polices (URL `data:`), favicon et sprite d'icônes sont insérés dans la page.
"""

from __future__ import annotations

import argparse
import base64
import json
import posixpath
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SORTIE = ROOT / "maquette-autonome.html"
MIME = {".woff2": "font/woff2", ".svg": "image/svg+xml", ".png": "image/png"}

# Spécificateur relatif d'un import statique, d'un `export … from` ou d'un `import()` littéral.
SPEC_STATIQUE = re.compile(r"""(\bfrom\s*|\bimport\s*\(?\s*)(["'])(\.{1,2}/[^"'\s]+\.js)\2""")
# `import(`../screens/${screen}.js`)` : seul le préfixe littéral est résolu.
SPEC_GABARIT = re.compile(r"(\bimport\s*\(\s*`)(\.{1,2}/[^`$]*)")
URL_CSS = re.compile(r"""url\(\s*(["']?)(?!data:|#)([^"')]+)\1\s*\)""")


def lire(path: Path) -> str:
    """Texte UTF-8 aux fins de ligne LF : le résultat ne dépend pas de `core.autocrlf`."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def data_uri(path: Path) -> str:
    mime = MIME[path.suffix]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def remplacer(texte: str, ancien: str, nouveau: str, ou: str) -> str:
    if ancien not in texte:
        raise SystemExit(f"Motif attendu absent de {ou} : {ancien!r} (mettre à jour construire_autonome.py)")
    return texte.replace(ancien, nouveau)


def css_autonome(path: Path) -> str:
    """Feuille dont les `url()` relatives (polices, images) deviennent des URL `data:`."""
    base = path.parent

    def inline(match: re.Match) -> str:
        return f'url("{data_uri((base / match.group(2)).resolve())}")'

    return URL_CSS.sub(inline, lire(path))


def module_autonome(path: Path) -> str:
    nom = rel(path)
    dossier = posixpath.dirname(nom)
    texte = lire(path)

    def nu(spec: str) -> str:
        cible = posixpath.normpath(posixpath.join(dossier, spec))
        if spec.endswith("/"):
            cible += "/"
        return f"@wl/{cible}"

    texte = SPEC_STATIQUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{nu(m.group(3))}{m.group(2)}", texte)
    texte = SPEC_GABARIT.sub(lambda m: f"{m.group(1)}{nu(m.group(2))}", texte)
    if nom == "js/core/dom.js":
        # Le sprite est inséré dans la page : références `#i-<nom>` sans fichier.
        texte = remplacer(texte, 'new URL("../../icons.svg", import.meta.url).pathname', '""', nom)
    texte = texte.replace("import.meta.url", json.dumps(f"wl:/{nom}"))
    if re.search(r"""(from|import)\s*\(?\s*["'`]\.{1,2}/""", texte):
        raise SystemExit(f"Spécificateur relatif non réécrit dans {nom}")
    return texte


def json_script(identifiant: str, valeur: object) -> str:
    texte = json.dumps(valeur, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    texte = texte.replace("</", "<\\/")  # `\/` est un échappement JSON valide
    return f'<script type="application/json" id="{identifiant}">{texte}</script>'


AMORCE = """<script>
  // Page autonome : sert les fichiers embarqués aux modules (fetch, feuilles d'écran).
  (function () {
    window.__wlAutonome = true;
    var fichiers = JSON.parse(document.getElementById("wl-fichiers").textContent);
    var PREFIXE = "wl:/";
    function chemin(adresse) {
      return adresse.indexOf(PREFIXE) === 0 ? adresse.slice(PREFIXE.length).split(/[?#]/)[0] : null;
    }
    var fetchNatif = window.fetch.bind(window);
    window.fetch = function (entree, options) {
      var adresse = typeof entree === "string" ? entree : entree instanceof URL ? entree.href : entree.url;
      var nom = chemin(adresse);
      if (nom === null) return fetchNatif(entree, options);
      if (!Object.prototype.hasOwnProperty.call(fichiers, nom)) {
        return Promise.resolve(new Response("", { status: 404, statusText: "Not Found" }));
      }
      return Promise.resolve(new Response(fichiers[nom], { status: 200, headers: { "Content-Type": "application/json; charset=utf-8" } }));
    };
    var blobs = {};
    var href = Object.getOwnPropertyDescriptor(HTMLLinkElement.prototype, "href");
    Object.defineProperty(HTMLLinkElement.prototype, "href", {
      configurable: true,
      enumerable: href.enumerable,
      get: href.get,
      set: function (valeur) {
        var nom = chemin(String(valeur));
        if (nom !== null && Object.prototype.hasOwnProperty.call(fichiers, nom)) {
          blobs[nom] = blobs[nom] || URL.createObjectURL(new Blob([fichiers[nom]], { type: "text/css" }));
          valeur = blobs[nom];
        }
        href.set.call(this, valeur);
      },
    });
  })();
</script>"""


def construire() -> str:
    page = lire(ROOT / "index.html")

    # Feuilles communes insérées dans la page, dans l'ordre d'index.html.
    def feuille(match: re.Match) -> str:
        nom = match.group(1)
        return f'<style data-source="{nom}">\n{css_autonome(ROOT / nom)}</style>'

    page, nombre = re.subn(r'<link rel="stylesheet" href="([^"]+)">', feuille, page)
    if nombre == 0:
        raise SystemExit("Aucune feuille de style trouvée dans index.html")

    favicon = data_uri(ROOT / "favicon.svg")
    page = remplacer(page, 'href="favicon.svg"', f'href="{favicon}"', "index.html")
    page = remplacer(page, 'src="favicon.svg"', f'src="{favicon}"', "index.html")
    page = remplacer(page, 'href="icons.svg#', 'href="#', "index.html")

    # Fichiers servis par le fetch intercepté : JSON de données et de textes, feuilles d'écran.
    fichiers: dict[str, str] = {}
    for dossier, motif in (("donnees", "*.json"), ("i18n", "*.json")):
        for path in sorted((ROOT / dossier).rglob(motif)):
            fichiers[rel(path)] = lire(path)
    for path in sorted((ROOT / "css" / "screens").glob("*.css")):
        fichiers[rel(path)] = css_autonome(path)

    modules = {}
    for path in sorted((ROOT / "js").rglob("*.js")):
        source = module_autonome(path).encode("utf-8")
        modules[f"@wl/{rel(path)}"] = "data:text/javascript;charset=utf-8;base64," + base64.b64encode(source).decode("ascii")
    carte = json.dumps({"imports": modules}, sort_keys=True, separators=(",", ":"))

    tete = "\n".join(
        [
            "<!-- Fichier généré par construire_autonome.py : ne pas modifier à la main. -->",
            json_script("wl-fichiers", fichiers),
            AMORCE,
        ]
    )
    page = remplacer(page, '<meta charset="utf-8">', f'<meta charset="utf-8">\n{tete}', "index.html")
    page = remplacer(
        page,
        '<script type="module" src="js/main.js"></script>',
        f'<script type="importmap">{carte}</script>\n  <script type="module">import "@wl/js/main.js";</script>',
        "index.html",
    )

    sprite = lire(ROOT / "icons.svg").strip()
    sprite = remplacer(
        sprite,
        '<svg xmlns="http://www.w3.org/2000/svg">',
        '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" width="0" height="0" style="position:absolute;overflow:hidden">',
        "icons.svg",
    )
    page = remplacer(page, "<body>\n", f"<body>\n{sprite}\n", "index.html")
    return page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verifier", action="store_true", help="échoue si le fichier n'est pas à jour")
    args = parser.parse_args()
    page = construire()
    if args.verifier:
        actuel = lire(SORTIE) if SORTIE.exists() else ""
        if actuel != page:
            print(f"{SORTIE.name} n'est pas à jour : relancez python construire_autonome.py")
            return 1
        print(f"{SORTIE.name} est à jour.")
        return 0
    SORTIE.write_bytes(page.encode("utf-8"))
    print(f"{SORTIE.name} écrit ({len(page.encode('utf-8')) / 1024:.0f} Kio).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
