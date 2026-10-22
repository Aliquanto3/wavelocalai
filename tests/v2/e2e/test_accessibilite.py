"""Accessibilité de tous les écrans (story 8.2 ; NFR8, UX-DR19, UX-DR25, AD-20).

Les routes viennent du registre réel (`static/core/routes/*.js`, par `core/registry.js`), jamais d'une
liste écrite ici : un écran livré est vérifié sans toucher ce fichier. Chaque écran est joué dans six
réglages d'affichage (clair, sombre, « Système » avec un système clair puis sombre, projection en
clair puis en sombre), avec ses panneaux, listes et dialogues ouverts quand il en a. axe-core est
lancé tel quel : aucune règle désactivée, aucune exclusion.

Le serveur est celui des autres E2E (Ollama arrêté). La liste des modèles est simulée par le test
(`page.route`, comme `test_picker.py`) pour que les sélecteurs, les formulaires et la fiche d'un modèle
soient dans leur état rempli.

Le reflux (320 px CSS, zoom à 200 %, texte à 200 %) est vérifié sans défilement horizontal de la
page : un tableau large défile dans son conteneur, jamais dans la page.
"""

from __future__ import annotations

import json
import re

import pytest
from axe_playwright_python.sync_playwright import Axe

from .test_arena import JUDGE_DEFAULT
from .test_arena import MODELS as ARENA_MODELS
from .test_arena import wait_banner
from .test_arena_reopen import post_run
from .test_arena_results import mixed_lanes, wait_names
from .test_chat import DONE as CHAT_DONE
from .test_chat import MODEL as CHAT_MODEL
from .test_chat import (
    ask,
    forget_conversations,
)
from .test_chat import scripted as chat_scripted
from .test_picker import LOCAL, model
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

# Réglage d'affichage -> (choix de thème, thème du système d'exploitation, projection).
MODES = {
    "clair": ("light", "light", False),
    "sombre": ("dark", "light", False),
    "systeme-clair": ("system", "light", False),
    "systeme-sombre": ("system", "dark", False),
    "projection-clair": ("light", "light", True),
    "projection-sombre": ("dark", "light", True),
}
# Le jeu de jetons que chaque réglage doit appliquer (« Système » choisit d'après le système).
APPLIED = {
    "clair": "light",
    "sombre": "dark",
    "systeme-clair": "light",
    "systeme-sombre": "dark",
    "projection-clair": "light",
    "projection-sombre": "dark",
}

# Largeurs en pixels CSS : 320 (UX-DR19), 640 (zoom à 200 % d'une fenêtre de 1 280), et un texte à
# 200 % sur la fenêtre de 1 440 (RGAA 10.4).
REFLOW = {
    "320 px": (320, 640, None),
    "zoom 200 %": (640, 480, None),
    "texte 200 %": (1440, 900, "200%"),
}

EXPECTED_SCENES = {
    "au repos",
    "liste des modèles ouverte",
    "fiche du modèle ouverte",
    "panneaux dépliés",
    "dialogue de confirmation",
    "dialogue avec le détail à valider",
    "chat : réflexion et aide ouvertes",
    "comparaison rouverte, dialogue d'effacement",
    "modèles : fiche d'un modèle",
    "modèles : dialogue de suppression",
    "sobriété, détails dépliés",
}
# Revue 8.2 : ce que chaque écran doit ouvrir, route par route (l'union sur toutes les routes laissait
# passer en silence un écran qui perd sa liste ou son dialogue). Un écran ajouté au registre sans
# ligne ici est vérifié au repos ; une ligne sans écran fait échouer le test.
PICKER = {"liste des modèles ouverte", "fiche du modèle ouverte"}
DIALOGS = {"dialogue de confirmation", "dialogue avec le détail à valider"}
EXPECTED_BY_ROUTE = {
    "/": set(),
    "/arene/chat": PICKER | {"panneaux dépliés"},
    "/arene/comparer": PICKER,
    "/arene/banc": PICKER,
    "/arene/references": set(),
    "/documents": set(),
    "/documents/base": DIALOGS,
    "/documents/evaluation": PICKER,
    "/agents/seul": PICKER | DIALOGS,
    "/agents/equipe": PICKER | DIALOGS | {"panneaux dépliés"},
    "/sobriete": {"panneaux dépliés"},
    "/modeles": DIALOGS,
}
PANELS = ["ollama-button", "cloud-help-button", "co2-button", "display-button"]

CONFIRM_DIALOG = """(long) => {
    const dialog = [...document.querySelectorAll('.screen:not([hidden]) wl-confirm-dialog')]
        .find((node) => node.offsetParent);
    if (!dialog) return false;
    dialog.ask({
        title: 'Envoyer cet email ?',
        consequence: "Le message part vers l'adresse indiquée, sans retour possible.",
        confirmLabel: 'Envoyer',
        details: long
            ? [
                { label: 'Destinataire', value: 'equipe@exemple.fr' },
                { label: 'Objet', value: 'Compte rendu de la mission' },
                { label: 'Message', value: 'Bonjour,\\n'.repeat(30), long: true },
            ]
            : [],
    });
    return true;
}"""


def install_models(page) -> None:
    """La liste des modèles et leurs défauts, simulées : le modèle `fake:1b` du chat, les cinq de
    l'Arène, six modèles locaux de formes variées (`test_picker.LOCAL`) et, cloud autorisé, deux
    modèles cloud. Un modèle cloud ne vient qu'avec `allow_cloud=true`, comme le serveur."""
    listed = [CHAT_MODEL, *ARENA_MODELS, *LOCAL]
    cloud = [
        model(
            "anthropic:claude-haiku-5-5", "claude-haiku-5-5", provider="anthropic", origin="cloud"
        ),
        model("openai:gpt-4o-mini", "gpt-4o-mini", provider="openai", origin="cloud"),
    ]

    def on_models(route):
        models = listed + (cloud if "allow_cloud=true" in route.request.url else [])
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"models": models, "ollama_up": True, "refreshed_at": "2026-10-18T10:00:00Z"}
            ),
        )

    def on_defaults(route):
        purpose = re.search(r"purpose=(\w+)", route.request.url).group(1)
        tags = {"arena": ["fake:a", "fake:b"], "judge": [JUDGE_DEFAULT]}.get(purpose, ["fake:1b"])
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "purpose": purpose,
                    "tags": tags,
                    "reason": "Le défaut de ce poste.",
                    "source": "rule",
                }
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def registry_routes(page) -> list[str]:
    """Chemins de tous les écrans `available` du registre, dans l'ordre de la navigation."""
    return page.evaluate(
        """async () => (await import('/static/core/registry.js')).SCREENS
            .filter((screen) => screen.status === 'available').map((screen) => screen.path)"""
    )


def apply_mode(page, mode: str) -> None:
    choice, system, projection = MODES[mode]
    page.emulate_media(color_scheme=system)
    page.evaluate(
        """async ([choice, projection]) => {
            const theme = await import('/static/core/theme.js');
            theme.setTheme(choice);
            theme.setProjection(projection);
        }""",
        [choice, projection],
    )
    assert page.get_attribute("html", "data-theme") == APPLIED[mode], mode
    assert page.get_attribute("html", "data-projection") == str(projection).lower()


def go(page, path: str) -> None:
    page.evaluate("(path) => { location.hash = '#' + path; }", path)
    wait_for(
        page,
        """() => {
            const screen = document.querySelector('.screen:not([hidden])');
            return screen && screen.dataset.screen && screen.querySelector('h1');
        }""",
    )
    page.wait_for_timeout(300)  # les lectures de l'écran, simulées ou refusées, sont revenues


def screen(page):
    return page.locator(".screen:not([hidden])")


def open_disclosures(page) -> int:
    """Déplie chaque bouton `aria-expanded="false"` de l'écran (accordéons, volets, aides)."""
    opened = 0
    for _ in range(4):  # un volet ouvert peut en révéler d'autres
        buttons = screen(page).locator(
            '[aria-expanded="false"]:not([role="combobox"]):not([disabled]):visible'
        )
        count = buttons.count()
        if count == 0:
            break
        for index in range(count):
            button = buttons.nth(index)
            if button.is_visible() and button.get_attribute("aria-expanded") == "false":
                button.click()
                opened += 1
    return opened


def open_picker(page) -> bool:
    combo = screen(page).locator('wl-model-picker [role="combobox"]:visible').first
    if combo.count() == 0:
        return False
    combo.click()
    screen(page).locator('wl-model-picker [role="listbox"]:visible').first.wait_for()
    return True


def open_dialog(page, long: bool = False) -> bool:
    if not page.evaluate(CONFIRM_DIALOG, long):
        return False
    screen(page).locator("dialog[open]").wait_for()
    return True


def close_dialog(page) -> None:
    page.keyboard.press("Escape")
    page.locator("dialog[open]").wait_for(state="hidden")


def open_card(page) -> bool:
    button = screen(page).locator("button.models-card-open:visible").first
    if button.count() == 0:
        return False
    button.click()
    page.locator("aside.models-card-drawer").wait_for()
    page.wait_for_timeout(400)
    return True


def close_card(page) -> None:
    page.locator("aside.models-card-drawer .models-card-close").click()
    page.locator("aside.models-card-drawer").wait_for(state="detached")


def scenes(page):
    """Les états à vérifier de l'écran courant : chaque nom rendu est un état atteint, que
    l'appelant contrôle avant de reprendre le générateur. Le générateur remet l'écran à son état
    de départ entre deux scènes ; les panneaux dépliés et les dialogues viennent en dernier."""
    yield "au repos"
    if open_picker(page):
        yield "liste des modèles ouverte"
        page.keyboard.press("Escape")
    if open_card(page):
        yield "fiche du modèle ouverte"
        close_card(page)
    if open_disclosures(page):
        yield "panneaux dépliés"
    if open_dialog(page):
        yield "dialogue de confirmation"
        close_dialog(page)
    if open_dialog(page, long=True):
        yield "dialogue avec le détail à valider"
        close_dialog(page)


def route_scenes(page, path: str, missing: list[str]):
    """`scenes` de l'écran `path` ; chaque état attendu pour cet écran et non atteint est ajouté à
    `missing`."""
    reached = set()
    for scene in scenes(page):
        reached.add(scene)
        yield scene
    expected = {"au repos"} | EXPECTED_BY_ROUTE.get(path, set())
    if expected - reached:
        missing.append(f"{path} : {sorted(expected - reached)}")


def assert_expectations_match_the_registry(routes: list[str]) -> None:
    stale = set(EXPECTED_BY_ROUTE) - set(routes)
    assert not stale, f"états attendus pour des écrans absents du registre : {sorted(stale)}"


# axe rend aussi des résultats « incomplets » : pour `color-contrast`, des textes dont il ne calcule
# pas le fond (texte d'un SVG, texte d'un seul caractère, fond recouvert par une liste ou un dialogue
# ouvert, coin arrondi). Revue 8.2 : le test calcule lui-même leur contraste, d'après la couleur du
# texte (`fill` dans un SVG) et le fond peint sous lui (formes du SVG placées dessous, sur le premier
# fond opaque des ancêtres) ; un fond non calculable (image, dégradé, couleur inconnue) échoue.
AXE_OPTIONS = {"resultTypes": ["violations", "incomplete"]}

OWN_CONTRAST = r"""(targets) => {
    const parse = (value) => {
        let m = value.match(/^rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)$/);
        if (m) return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]];
        m = value.match(/^color\(srgb ([\d.e-]+) ([\d.e-]+) ([\d.e-]+)(?: \/ ([\d.]+))?\)$/);
        if (m) return [m[1] * 255, m[2] * 255, m[3] * 255, m[4] === undefined ? 1 : +m[4]];
        return null;
    };
    const over = (top, under) => top.slice(0, 3).map((c, i) => c * top[3] + under[i] * (1 - top[3]));
    const lum = (rgb) => {
        const [r, g, b] = rgb.map((c) => {
            c /= 255;
            return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const htmlBackground = (node) => {
        const layers = [];
        for (let up = node; up; up = up.parentElement) {
            const style = getComputedStyle(up);
            if (style.backgroundImage !== 'none') return null;
            const color = parse(style.backgroundColor);
            if (color === null) return null;
            if (color[3] > 0) layers.push(color);
            if (color[3] >= 1) break;
        }
        return layers.reduceRight((under, top) => over(top, under), [255, 255, 255]);
    };
    const svgBackground = (el) => {
        const svg = el.closest('svg');
        const box = el.getBoundingClientRect();
        const [x, y] = [box.left + box.width / 2, box.top + box.height / 2];
        let base = htmlBackground(svg);
        if (base === null) return null;
        for (const shape of svg.querySelectorAll('rect, circle, ellipse, polygon, path')) {
            if (!(shape.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
            if (shape.closest('marker, defs')) continue;
            const r = shape.getBoundingClientRect();
            if (x < r.left || x > r.right || y < r.top || y > r.bottom) continue;
            const style = getComputedStyle(shape);
            if (style.fill === 'none') continue;
            const fill = parse(style.fill);
            if (fill === null) return null;
            fill[3] *= parseFloat(style.fillOpacity) * parseFloat(style.opacity);
            base = over(fill, base);
        }
        return base;
    };
    return targets.map((target) => {
        const el = document.querySelector(target);
        if (!el) return { target, problem: 'introuvable' };
        // Sans texte propre (axe signale parfois `:root` pendant l'ouverture d'un panneau) : rien à lire.
        const own = [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
        if (!own) return null;
        const style = getComputedStyle(el);
        const inSvg = el instanceof SVGElement;
        const fg = parse(inSvg ? style.fill : style.color);
        const bg = inSvg ? svgBackground(el) : htmlBackground(el);
        if (fg === null || bg === null) {
            return { target, problem: `non calculable (${inSvg ? style.fill : style.color})` };
        }
        const shown = over(fg, bg);
        const [light, dark] = [lum(shown), lum(bg)].sort((p, q) => q - p);
        const ratio = (light + 0.05) / (dark + 0.05);
        const scale = inSvg ? el.closest('svg').getScreenCTM()?.a ?? 1 : 1;
        const size = parseFloat(style.fontSize) * scale;
        const large = size >= 24 || (size >= 18.66 && parseInt(style.fontWeight, 10) >= 700);
        const need = large ? 3 : 4.5;
        return ratio + 0.005 >= need ? null : { target, problem: `${ratio.toFixed(2)}:1 < ${need}:1` };
    }).filter(Boolean);
}"""


def axe_problems(page, where: str) -> list[str]:
    """Violations axe, et contrastes qu'axe laisse « incomplets » et qui ne tiennent pas une fois
    calculés par `OWN_CONTRAST`."""
    results = Axe().run(page, options=AXE_OPTIONS)
    problems = []
    if results.violations_count:
        problems.append(f"{where} :\n{results.generate_report()}")
    targets = []
    for rule in results.response["incomplete"]:
        if rule["id"] != "color-contrast":
            continue
        for node in rule["nodes"]:
            if len(node["target"]) != 1:  # dans un shadow DOM : aucun ici, le dire s'il en vient
                problems.append(f"{where} : contraste non vérifié dans {node['target']}")
            else:
                targets.append(node["target"][0])
    unresolved = page.evaluate(OWN_CONTRAST, targets) if targets else []
    if unresolved:
        problems.append(f"{where} : contraste calculé insuffisant {unresolved}")
    return problems


def prepare_rich(page, server) -> str:
    """Une comparaison de l'Arène terminée (quatre colonnes : notées, en délai, sans réponse) et un
    échange de chat fini, que les écrans rouvrent ; rend l'identifiant de la comparaison."""
    run_id = post_run(page, server, mixed_lanes())
    chat_scripted(
        page,
        server,
        [
            {
                "text": "Réponse **en gras** avec `code` et un [lien](https://example.org).\n\n- a\n- b"
            },
            {"text": "Réflexion", "channel": "thought"},
            {"done": CHAT_DONE},
        ],
    )
    forget_conversations(server.base_url)  # l'écran rouvre la dernière conversation (story 2.6)
    go(page, "/arene/chat")
    ask(page, "Une question pour la recette")
    page.locator(".wl-msg-foot").filter(has_text="Durée totale").wait_for()
    return run_id


def rich_scenes(page, run_id: str):
    """Les états remplis : un échange de chat fini (réflexion dépliée, aide d'une mesure ouverte) et
    la comparaison rouverte (classement, matrice, tableau, actions, dialogue d'effacement)."""
    go(page, "/arene/chat")
    page.locator(".wl-msg-foot").filter(has_text="Durée totale").wait_for()
    yield "chat : échange fini"
    page.locator("details.wl-thought summary").click()
    page.locator(".wl-msg-foot wl-metric", has_text="Débit").get_by_role("button").click()
    yield "chat : réflexion et aide ouvertes"

    go(page, f"/arene/comparer/{run_id}")
    wait_banner(page, "Comparaison terminée")
    wait_for(page, "() => !document.querySelector('.arena-run-actions button')?.disabled")
    wait_names(page)
    yield "comparaison rouverte"
    page.get_by_role("group", name="Actions sur cette comparaison").get_by_role(
        "button", name="Effacer la comparaison"
    ).click()
    page.get_by_role("dialog").wait_for()
    yield "comparaison rouverte, dialogue d'effacement"
    close_dialog(page)
    if open_disclosures(page):
        yield "comparaison rouverte, panneaux dépliés"

    go(page, "/modeles")
    screen(page).locator("wl-data-table tbody a").first.click()
    page.wait_for_timeout(800)  # la fiche (`#/modeles/<tag>`) lit le catalogue
    yield "modèles : fiche d'un modèle"
    go(page, "/modeles")
    screen(page).get_by_role("button", name="Supprimer").first.click()
    page.get_by_role("dialog").wait_for()
    yield "modèles : dialogue de suppression"
    close_dialog(page)

    go(page, "/sobriete")
    page.wait_for_timeout(500)
    yield "sobriété avec l'historique de ces réponses"
    open_disclosures(page)
    yield "sobriété, détails dépliés"


def open_topbar_panels(page):
    """Chaque panneau de la barre haute, ouvert un par un (un panneau ouvert referme les autres)."""
    for button_id in PANELS:
        button = page.locator(f"#{button_id}")
        button.click()
        page.locator(f"#{button.get_attribute('aria-controls')}").wait_for(state="visible")
        yield button_id
        button.click()


@pytest.fixture
def app(page_tolerating_failed_requests, server):
    """L'application ouverte à l'Accueil, avec une liste de modèles simulée."""
    page = page_tolerating_failed_requests
    install_models(page)
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    return page


# --- axe-core : toutes les routes, tous les réglages d'affichage -------------------------------


def test_every_screen_of_the_registry_is_available(app):
    statuses = app.evaluate(
        "async () => (await import('/static/core/registry.js')).SCREENS.map((s) => s.status)"
    )
    assert statuses and set(statuses) == {"available"}, statuses
    assert len(registry_routes(app)) == len(statuses)


@pytest.mark.parametrize("mode", list(MODES))
def test_axe_finds_no_violation_on_any_route_in_any_display_mode(app, server, mode):
    run_id = prepare_rich(app, server)
    apply_mode(app, mode)
    failures, missing = [], []
    seen = set()
    routes = registry_routes(app)
    assert_expectations_match_the_registry(routes)
    for path in routes:
        go(app, path)
        for scene in route_scenes(app, path, missing):
            seen.add(scene)
            failures += axe_problems(app, f"{path} · {scene}")
    for scene in rich_scenes(app, run_id):
        seen.add(scene)
        failures += axe_problems(app, scene)
    assert not failures, f"{mode} :\n" + "\n".join(failures)
    # Les états qui font la valeur du test ont bien été atteints, écran par écran.
    assert not missing, f"{mode} : états non atteints :\n" + "\n".join(missing)
    assert seen >= EXPECTED_SCENES, EXPECTED_SCENES - seen


def test_own_contrast_reads_the_shape_under_a_svg_text_and_the_html_background(app):
    """L'oracle des contrastes « incomplets » d'axe (`OWN_CONTRAST`) : valeurs attendues écrites à la
    main (WCAG : #767676 sur blanc = 4,54:1, #aaa sur blanc = 2,32:1, #777 sur #888 = 1,26:1)."""
    app.evaluate(
        """() => {
            const box = document.createElement('div');
            box.id = 'probe';
            box.style.background = '#ffffff';  // CSSOM : la politique de contenu refuse `style=""`
            box.innerHTML = `<p id="ok">Lisible</p><p id="weak">Pâle</p>
                <svg width="200" height="40" viewBox="0 0 200 40">
                  <rect x="0" y="0" width="200" height="40" fill="#888888"></rect>
                  <text id="svg-weak" x="10" y="25" fill="#777777" font-size="16">Sur la forme</text>
                </svg>
                <svg width="200" height="40" viewBox="0 0 200 40">
                  <text id="svg-ok" x="10" y="25" fill="#000000" font-size="16">Sur le fond</text>
                </svg>`;
            document.body.prepend(box);
            box.querySelector('#ok').style.color = '#767676';
            box.querySelector('#weak').style.color = '#aaaaaa';
        }"""
    )
    found = app.evaluate(OWN_CONTRAST, ["#ok", "#weak", "#svg-weak", "#svg-ok"])
    assert [item["target"] for item in found] == ["#weak", "#svg-weak"], found
    assert found[0]["problem"].startswith("2.32:1")
    assert found[1]["problem"].startswith("1.26:1")


@pytest.mark.parametrize("mode", list(MODES))
def test_axe_finds_no_violation_on_the_topbar_panels_in_any_display_mode(app, mode):
    apply_mode(app, mode)
    failures = []
    for path in registry_routes(app):
        go(app, path)
        for button_id in open_topbar_panels(app):
            failures += axe_problems(app, f"{path} · {button_id}")
    assert not failures, f"{mode} :\n" + "\n".join(failures)


# --- Reflux : 320 px CSS, zoom à 200 %, texte à 200 % ------------------------------------------


def overflow(page) -> dict:
    return page.evaluate(
        """() => {
            const root = document.documentElement;
            const wide = [...document.querySelectorAll('body *')].filter((node) => {
                const box = node.getBoundingClientRect();
                if (box.width === 0 || box.right <= root.clientWidth + 1) return false;
                if (getComputedStyle(node).visibility === 'hidden') return false;
                // Un tableau large défile dans son conteneur : un ancêtre qui défile le contient. Un
                // ancêtre qui masque son trop-plein (`hidden`, `clip`) coupe le contenu : signalé
                // (revue 8.2), comme une racine qui masque le défilement de la page.
                for (let up = node.parentElement; up && up !== document.body; up = up.parentElement) {
                    const x = getComputedStyle(up).overflowX;
                    if (/(auto|scroll)/.test(x)) return false;
                    if (/(hidden|clip)/.test(x)) return true;
                }
                return true;
            }).slice(0, 5).map((node) => node.localName + '.' + node.className);
            const masked = [root, document.body]
                .filter((node) => /(hidden|clip)/.test(getComputedStyle(node).overflowX))
                .map((node) => node.localName + ' masque le défilement');
            return { page: root.scrollWidth - root.clientWidth, wide: [...masked, ...wide] };
        }"""
    )


@pytest.mark.parametrize("reflow", list(REFLOW))
@pytest.mark.parametrize("mode", ["clair", "projection-sombre"])
def test_no_horizontal_scroll_on_any_route(app, server, mode, reflow):
    run_id = prepare_rich(app, server)
    width, height, text = REFLOW[reflow]
    app.set_viewport_size({"width": width, "height": height})
    apply_mode(app, mode)
    if text:
        app.evaluate("(size) => { document.documentElement.style.fontSize = size; }", text)
    failures, missing = [], []
    for path in registry_routes(app):
        go(app, path)
        for scene in route_scenes(app, path, missing):
            measured = overflow(app)
            if measured["page"] > 0 or measured["wide"]:
                failures.append(f"{path} · {scene} : {measured}")
        for button_id in open_topbar_panels(app):
            measured = overflow(app)
            if measured["page"] > 0 or measured["wide"]:
                failures.append(f"{path} · panneau {button_id} : {measured}")
    for scene in rich_scenes(app, run_id):
        measured = overflow(app)
        if measured["page"] > 0 or measured["wide"]:
            failures.append(f"{scene} : {measured}")
    assert not failures, f"{mode}, {reflow} :\n" + "\n".join(failures)
    assert not missing, f"{mode}, {reflow} : états non atteints :\n" + "\n".join(missing)


@pytest.mark.parametrize("reflow", ["320 px", "zoom 200 %"])
def test_axe_finds_no_violation_on_any_route_when_reflowed(app, server, reflow):
    run_id = prepare_rich(app, server)
    width, height, _ = REFLOW[reflow]
    app.set_viewport_size({"width": width, "height": height})
    failures, missing = [], []
    for path in registry_routes(app):
        go(app, path)
        for scene in route_scenes(app, path, missing):
            failures += axe_problems(app, f"{path} · {scene}")
    for scene in rich_scenes(app, run_id):
        failures += axe_problems(app, scene)
    assert not failures, f"{reflow} :\n" + "\n".join(failures)
    assert not missing, f"{reflow} : états non atteints :\n" + "\n".join(missing)


# --- Lisibilité en projection (UX-DR2) ---------------------------------------------------------

PROJECTION_RATIO = 9 / 7  # rampe typographique du mode projection (`base.css`)

SMALLEST_TEXT = """() => {
    // Taille rendue du plus petit texte visible de l'écran : le texte d'un SVG compte pour sa taille
    // à l'écran (échelle de la `viewBox` comprise), jamais pour la valeur écrite en CSS.
    const walker = document.createTreeWalker(
        document.querySelector('.screen:not([hidden])'), NodeFilter.SHOW_TEXT);
    let smallest = [Infinity, ''];
    while (walker.nextNode()) {
        const text = walker.currentNode.textContent.trim();
        const el = walker.currentNode.parentElement;
        if (!text || el.closest('.sr-only')) continue;
        const svg = el.closest('svg');
        if (!svg && !el.offsetParent) continue;
        const scale = svg ? svg.getScreenCTM()?.a ?? 1 : 1;
        const size = parseFloat(getComputedStyle(el).fontSize) * scale;
        if (size < smallest[0]) smallest = [size, `${el.localName}.${el.getAttribute('class')} « ${text.slice(0, 20)} »`];
    }
    return smallest;
}"""


def test_projection_scales_the_smallest_text_of_every_route_by_the_ramp(app, server):
    """Aucun texte ne reste à sa taille normale en projection (un SVG à largeur en pixels, une taille
    écrite en `px`) : le plus petit texte de chaque écran grandit du rapport 9/7 de la rampe."""
    run_id = prepare_rich(app, server)
    routes = [*registry_routes(app), f"/arene/comparer/{run_id}"]
    smallest = {}
    for mode in ("clair", "projection-clair"):
        apply_mode(app, mode)
        for path in routes:
            go(app, path)
            if path.startswith("/arene/comparer/"):
                wait_banner(app, "Comparaison terminée")
            smallest[mode, path] = app.evaluate(SMALLEST_TEXT)
    # Revue 8.2 : un écran dont aucun texte n'est mesuré (taille infinie) ne passe pas sans mesure.
    unmeasured = [key for key, value in smallest.items() if value[0] == float("inf")]
    assert not unmeasured, f"aucun texte mesuré : {unmeasured}"
    too_small = [
        f"{path} : {smallest['clair', path]} -> {smallest['projection-clair', path]}"
        for path in routes
        if smallest["projection-clair", path][0]
        < smallest["clair", path][0] * PROJECTION_RATIO * 0.97
    ]
    assert not too_small, "texte qui ne grandit pas en projection :\n" + "\n".join(too_small)
    sizes = {key: value[0] for key, value in smallest.items() if key[0] == "projection-clair"}
    assert all(size >= 15 for size in sizes.values()), sizes


# --- Focus au premier chargement (B16, RGAA 12.7) ----------------------------------------------


def shift_tab_to_skip_link(page, limit: int = 60) -> int:
    """Remonte par Maj+Tab jusqu'au lien d'évitement ; rend le nombre d'appuis (échec au-delà)."""
    for presses in range(1, limit + 1):
        page.keyboard.press("Shift+Tab")
        if page.evaluate("document.activeElement.id") == "skip-link":
            return presses
    raise AssertionError(f"lien d'évitement non atteint en {limit} Maj+Tab")


def test_first_load_moves_the_focus_to_the_h1_and_keeps_the_skip_link_reachable(
    page_tolerating_failed_requests, server
):
    """Décision B16 (revue 8.2) : le critère de la story 1.8 (« à chaque route, le focus va sur le
    `h1` ») vaut aussi au premier chargement, lien profond compris. Le lien d'évitement reste le
    premier élément focalisable du document (RGAA 12.7) : Maj+Tab depuis le `h1` le rejoint, et il
    mène toujours à `main` sans changer la route."""
    page = page_tolerating_failed_requests
    install_models(page)
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.activeElement.localName === 'h1'")
    assert page.evaluate("document.activeElement.closest('.screen').dataset.screen")
    assert page.title().startswith("Chat libre")
    first_focusable = page.evaluate(
        """() => [...document.querySelectorAll('a[href], button, input, select, textarea, [tabindex]')]
            .find((node) => node.tabIndex >= 0 && !node.disabled).id"""
    )
    assert first_focusable == "skip-link"
    shift_tab_to_skip_link(page)
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"
    assert page.evaluate("location.hash") == "#/arene/chat"
    assert_no_axe_violations(page, "premier chargement, focus sur le contenu")


def test_a_route_change_moves_the_focus_to_the_h1_of_the_screen(app):
    app.locator('#module-list a[data-module="sobriety"]').click()
    wait_for(app, "() => document.activeElement.localName === 'h1'")
    assert app.evaluate("document.activeElement.textContent") == app.evaluate(
        "document.querySelector('.screen:not([hidden]) h1').textContent"
    )


# --- Critères RGAA vérifiables par le navigateur (grille : docs/accessibilite/grille-rgaa-v2.md) ---


def test_every_screen_has_one_h1_a_distinct_title_and_the_french_language(app):
    """RGAA 8.3, 8.5, 8.6, 9.1 : langue de la page, un titre de page par écran, un seul `h1`."""
    assert app.get_attribute("html", "lang") == "fr"
    titles = []
    for path in registry_routes(app):
        go(app, path)
        assert screen(app).locator("h1").count() == 1, path
        titles.append(app.title())
    assert all(title.endswith(" · WaveLocalAI") or title == "WaveLocalAI" for title in titles)
    assert len(set(titles)) == len(titles), titles


def test_no_positive_tabindex_and_no_new_window_without_a_warning(app, server):
    """RGAA 12.8 (ordre de tabulation : aucun `tabindex` positif) et 13.2 (un lien qui ouvre une
    nouvelle fenêtre le dit : ici, tous les liens d'une réponse Markdown)."""
    run_id = prepare_rich(app, server)
    for path in [*registry_routes(app), f"/arene/comparer/{run_id}"]:
        go(app, path)
        positive = app.evaluate(
            "[...document.querySelectorAll('[tabindex]')].filter((n) => n.tabIndex > 0).length"
        )
        assert positive == 0, path
    go(app, "/arene/chat")
    links = app.locator('a[target="_blank"]')
    assert links.count() >= 1  # le lien de la réponse écrite par `prepare_rich`
    for index in range(links.count()):
        assert links.nth(index).get_attribute("title") == "S'ouvre dans une nouvelle fenêtre"
        assert links.nth(index).get_attribute("rel") == "noopener noreferrer"


def test_keyboard_reaches_every_stop_with_a_visible_focus_and_never_gets_trapped(app, server):
    """RGAA 10.7 (focus visible), 12.9 (aucun piège au clavier), 7.3 : en tabulant dans chaque écran,
    chaque arrêt porte un indicateur de focus (contour ou ombre) et le parcours avance."""
    run_id = prepare_rich(app, server)
    problems = []
    for path in [*registry_routes(app), f"/arene/comparer/{run_id}"]:
        go(app, path)
        app.evaluate("document.activeElement.blur()")
        seen = []
        for _ in range(40):
            app.keyboard.press("Tab")
            stop = app.evaluate(
                """() => {
                    const el = document.activeElement;
                    const style = getComputedStyle(el);
                    const outlined = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0;
                    const shadowed = style.boxShadow !== 'none';
                    return {
                        id: el.localName + '.' + el.className + '#' + el.id + ':' + (el.textContent || '').trim().slice(0, 20),
                        visible: outlined || shadowed,
                        body: el === document.body,
                    };
                }"""
            )
            if stop["body"]:
                break  # le parcours a fait le tour de la page
            seen.append(stop["id"])
            if not stop["visible"]:
                problems.append(f"{path} : pas d'indicateur de focus sur {stop['id']}")
        if len(set(seen)) < 3:
            problems.append(f"{path} : le parcours au clavier tourne en rond : {seen[:8]}")
    assert not problems, "\n".join(problems)


SPACING = """() => {
    // Propriétés d'espacement du texte (WCAG 1.4.12, RGAA 10.12), posées par une feuille construite :
    // la politique de contenu refuse les `<style>` en ligne, pas cette interface.
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(`* {
        line-height: 1.5 !important;
        letter-spacing: 0.12em !important;
        word-spacing: 0.16em !important;
    } p { margin-bottom: 2em !important; }`);
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
}"""

CLIPPED = """() => {
    // Un texte coupé : un élément dont le contenu dépasse la boîte alors qu'elle masque son trop-plein.
    return [...document.querySelectorAll('.screen:not([hidden]) *, header *')].filter((node) => {
        const style = getComputedStyle(node);
        if (!node.offsetParent || !node.textContent.trim()) return false;
        if (!/(hidden|clip)/.test(style.overflowY + style.overflowX)) return false;
        if (node.closest('.sr-only') || node.classList.contains('sr-only')) return false;
        return node.scrollHeight > node.clientHeight + 2 || node.scrollWidth > node.clientWidth + 2;
    }).slice(0, 5).map((node) => node.localName + '.' + node.className);
}"""


@pytest.mark.parametrize("width", [1440, 320])
def test_text_spacing_overrides_clip_no_text_and_cause_no_horizontal_scroll(app, server, width):
    run_id = prepare_rich(app, server)
    app.set_viewport_size({"width": width, "height": 900})
    app.evaluate(SPACING)
    assert app.evaluate("getComputedStyle(document.body).letterSpacing") != "normal"  # appliquée
    failures = []
    for path in [*registry_routes(app), f"/arene/comparer/{run_id}"]:
        go(app, path)
        clipped = app.evaluate(CLIPPED)
        measured = overflow(app)
        if clipped or measured["page"] > 0 or measured["wide"]:
            failures.append(f"{path} : texte coupé {clipped}, défilement {measured}")
    assert not failures, "\n".join(failures)


def _luminance(color: str) -> float:
    red, green, blue = (int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def linear(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def contrast(first: str, second: str) -> float:
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("theme", ["clair", "sombre"])
def test_interface_component_tokens_keep_three_to_one_on_both_surfaces(app, theme):
    """RGAA 3.3 (WCAG 1.4.11) : la bordure des champs et des boutons, le contour de focus et le
    liseré des interrupteurs (jetons `gray-graphic`, `ink-secondary`, `primary`) tiennent 3:1 sur les
    deux fonds. Les points `chart-*` des graphiques portent en plus un contour d'encre."""
    apply_mode(app, theme)
    tokens = app.evaluate(
        """() => {
            const style = getComputedStyle(document.documentElement);
            const read = (name) => style.getPropertyValue(`--color-${name}`).trim();
            return Object.fromEntries(['gray-graphic', 'ink-secondary', 'primary', 'surface',
                'surface-alt'].map((name) => [name, read(name)]));
        }"""
    )
    for name in ("gray-graphic", "ink-secondary", "primary"):
        for surface in ("surface", "surface-alt"):
            ratio = contrast(tokens[name], tokens[surface])
            assert ratio >= 3, f"{theme} : {name} sur {surface} = {ratio:.2f}:1"


# Couleur et fond effectivement rendus d'une icône de module : le navigateur résout `color-mix`, un
# canevas 1x1 ramène chaque couleur calculée (rgb() ou color(srgb ...)) à un hex sRGB.
RENDERED_MODULE_ICONS = """() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    const hex = (css) => {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = '#000';
        context.fillStyle = css;
        context.fillRect(0, 0, 1, 1);
        const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data;
        if (a !== 255) return null;  // fond transparent : la pastille n'est pas rendue
        return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('').toUpperCase();
    };
    const out = {};
    for (const mod of ['arena', 'bench', 'docs', 'models']) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', `icon icon-mod ${mod}`);
        document.body.append(svg);
        const style = getComputedStyle(svg);
        out[mod] = [hex(style.color), hex(style.backgroundColor)];
        svg.remove();
    }
    return out;
}"""


@pytest.mark.parametrize("theme", ["clair", "sombre"])
def test_module_icons_keep_three_to_one_on_their_rendered_pastille(app, theme):
    """Icône de module sur sa pastille (story 9.7, `.icon-mod`, base.css) : au moins 3:1, mesuré sur
    la couleur et le fond rendus par le navigateur (table de `docs/maquette-v2-mise-en-page/DECISIONS.md`
    §2)."""
    apply_mode(app, theme)
    rendered = app.evaluate(RENDERED_MODULE_ICONS)
    for mod, (color, pastille) in rendered.items():
        assert color and pastille, f"{theme} : .icon-mod.{mod} sans couleur ou sans pastille rendue"
        assert color != pastille, f"{theme} : .icon-mod.{mod} sans pastille distincte"
        ratio = contrast(color, pastille)
        assert ratio >= 3, f"{theme} : icône {mod} ({color} sur {pastille}) = {ratio:.2f}:1"
