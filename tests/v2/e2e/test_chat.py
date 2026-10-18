"""Écran Chat libre (story 2.2) dans un vrai navigateur, sur le vrai serveur et l'adaptateur `fake`.

Ollama n'est jamais sollicité (le serveur pointe sur un port fermé). La liste des modèles est
simulée par le test (`page.route`) ; les réponses viennent de deux chemins :

- la route de test `POST /api/test/runs` (script de jetons, pauses, mesures), que le test appelle à la
  place de `POST /api/chat/runs` quand il faut une réponse scriptée ;
- la vraie route `POST /api/chat/runs` avec le modèle `fake:1b` (réponse vide), pour le corps des
  commandes (`conversation_id`, `temperature`, `allow_cloud`).

Les arrêts, la reprise `?after=`, le `409 run_busy`, le défilement et axe-core (clair et sombre,
sans exclusion) sont prouvés ici. Aucune requête ne sort de 127.0.0.1 (fixture `context`).
"""

from __future__ import annotations

import contextlib
import json
import re
import time
import urllib.request

import pytest
from axe_playwright_python.sync_playwright import Axe

from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
MODEL = {
    "tag": "fake:1b",
    "name": "Factice 1B",
    "provider": "fake",
    "editor": None,
    "origin": "local",
    "kind": "chat",
    "available": True,
    "digest": "abc",
    "params_total_b": None,
    "params_active_b": None,
    "size_gb": 1.0,
    "quantization": None,
    "context_length": None,
    "needed_gb": 1.5,
    "fits": True,
    "tools_verified": False,
    "reasoning": False,
    "throughput_tps": None,
    "accuracy": None,
    "co2_method": "codecarbon",
    "in_catalog": False,
}
REASON = "Le plus capable qui tient en mémoire sur ce poste."
DONE = {
    "input_tokens": 4,
    "output_tokens": 12,
    "ttft_s": 0.1,
    "load_s": 0.42,
    "eval_s": 0.3,
    "total_s": 1.2,
    "tps": 38.4,
    "tps_source": "ollama_eval",
}
STARTED: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def cancel_leftover_runs():
    """Un seul run de chat à la fois : un test n'en laisse aucun en cours au suivant."""
    yield
    for base_url, run_id in STARTED:
        request = urllib.request.Request(f"{base_url}/api/runs/{run_id}/cancel", method="POST")
        with contextlib.suppress(OSError):  # déjà terminé
            urllib.request.urlopen(request, timeout=5).close()  # noqa: S310
    STARTED.clear()


def install_models(page):
    def on_models(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"models": [MODEL], "ollama_up": True, "refreshed_at": "2026-10-18T10:00:00Z"}
            ),
        )

    def on_defaults(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"purpose": "chat", "tags": ["fake:1b"], "reason": REASON, "source": "rule"}
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def scripted(page, server, script, commands=None, co2=None):
    """Les commandes de chat de la page lancent un run scripté du `fake` (route de test). `co2` fixe
    le champ `co2` de la feuille (AD-10), comme le ferait le compteur CodeCarbon (story 2.3)."""

    def on_chat(route):
        body = json.loads(route.request.post_data)
        if commands is not None:
            commands.append(body)
        response = page.request.post(
            f"{server.base_url}/api/test/runs",
            data={
                "kind": "chat",
                "model": body["model"],
                "message": body["message"],
                "script": script,
                **({} if co2 is None else {"co2": co2}),
            },
        )
        if response.ok:
            STARTED.append((server.base_url, response.json()["run_id"]))
        route.fulfill(status=response.status, content_type="application/json", body=response.text())

    page.route(re.compile(r"/api/chat/runs$"), on_chat)


def start_run(page, server, script, message="Question d'ailleurs"):
    response = page.request.post(
        f"{server.base_url}/api/test/runs",
        data={"kind": "chat", "model": "fake:1b", "message": message, "script": script},
    )
    assert response.ok, response.text()
    run_id = response.json()["run_id"]
    STARTED.append((server.base_url, run_id))
    return run_id


@pytest.fixture
def chat(page, server):
    install_models(page)
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    return page


@pytest.fixture
def chat_lenient(page_tolerating_failed_requests, server):
    """Comme `chat`, pour un test dont la commande échoue exprès (409, 403 : le navigateur le dit)."""
    page = page_tolerating_failed_requests
    install_models(page)
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    return page


def field(page):
    return page.get_by_label("Écrivez votre message")


def ask(page, text):
    field(page).fill(text)
    field(page).press("Enter")


def answer_text(page):
    return page.locator(".wl-msg-assistant .wl-md").inner_text().strip()


def run_status(page, run_id):
    return json.loads(page.request.get(f"{page.url.split('#')[0]}api/runs/{run_id}").text())[
        "status"
    ]


def last_run(server=None):
    return STARTED[-1][1]


# --- Écran : réglages, onglets, aide ---------------------------------------------------------


def test_the_screen_shows_the_picker_the_creativity_slider_the_field_and_its_help(chat):
    assert chat.title() == "Chat libre · WaveLocalAI"
    assert chat.locator("h1").filter(has_text="Chat libre").is_visible()
    # Le sélecteur est sur le défaut `chat`, avec sa raison.
    assert chat.locator("wl-model-picker .wl-picker-help").inner_text().endswith(REASON)
    slider = chat.get_by_label("Créativité")
    assert slider.get_attribute("min") == "0" and slider.get_attribute("max") == "2"
    assert slider.input_value() == "0.2"
    assert chat.locator("output.chat-slider-value").inner_text() == "0,2"
    assert chat.locator(".chat-composer .help").inner_text() == (
        f"Entrée{NBSP}: envoyer · Maj+Entrée{NBSP}: nouvelle ligne · Échap{NBSP}: arrêter"
    )
    assert field(chat).get_attribute("aria-describedby")
    assert chat.get_by_role("button", name="Envoyer").is_enabled()
    assert chat.get_by_role("log").get_attribute("aria-live") == "off"
    assert chat.locator(".chat-empty").is_visible()


def test_the_arena_module_is_available_and_its_other_tabs_are_disabled_with_their_reason(chat):
    link = chat.locator("#module-list a[data-module=arena]")
    assert link.get_attribute("href") == "#/arene/chat"
    assert link.get_attribute("aria-current") == "page"
    tabs = chat.get_by_role("navigation", name="Écrans du module Arène")
    assert tabs.get_by_role("link", name="Chat libre").get_attribute("aria-current") == "page"
    for name in ("Arène", "Banc d'essai"):
        tab = tabs.get_by_role("link", name=name, exact=True)
        assert tab.get_attribute("aria-disabled") == "true"
        assert tab.get_attribute("href") is None
        reason = tab.locator("xpath=following-sibling::span")
        assert reason.is_visible()
        assert reason.inner_text() == "Pas encore disponible dans cette préversion"
        assert tab.get_attribute("aria-describedby") == reason.get_attribute("id")


# --- Flux : premier token, Markdown sûr, raisonnement, pied, annonce -------------------------------


def test_tokens_are_shown_as_safe_markdown_and_the_footer_turns_final(chat, server):
    commands: list[dict] = []
    scripted(
        chat,
        server,
        [
            {"load": "loaded"},
            {"text": "Je réfléchis.", "channel": "thought"},
            {"text": "**Bonjour** le monde. "},
            {"text": '<script>window.__pwned = 1</script><img src=x onerror="window.__pwned = 2">'},
            {"sleep_s": 1.2},
            {"text": " Fin."},
            {"done": DONE},
        ],
        commands,
    )
    ask(chat, "Dis bonjour")
    # L'utilisateur est dans le fil, le champ est vidé, le premier token est affiché.
    assert chat.locator(".wl-msg-user .wl-msg-text").inner_text() == "Dis bonjour"
    assert field(chat).input_value() == ""
    chat.locator(".wl-md strong").filter(has_text="Bonjour").wait_for()
    # Pendant le flux : rien n'est annoncé.
    assert chat.locator("wl-chat-thread [role=status]").inner_text() == ""
    assert chat.get_by_role("log").get_attribute("aria-live") == "off"
    # Le HTML du modèle est du texte : rien ne s'exécute, aucune image n'apparaît.
    assert "<script>window.__pwned = 1</script>" in answer_text(chat)
    assert chat.locator(".wl-md img, .wl-md script").count() == 0
    assert chat.evaluate("window.__pwned") is None
    # Le raisonnement est replié.
    thought = chat.locator("details.wl-thought")
    assert thought.evaluate("node => node.open") is False
    assert "Je réfléchis." in thought.text_content()
    # Fin : pied définitif (débit serveur, chargement et durée totale à part) et annonce.
    chat.locator(".wl-msg-foot").filter(has_text="Durée totale").wait_for()
    foot = re.sub(r"\s+", " ", chat.locator(".wl-msg-foot").inner_text())
    assert chat.locator(".wl-msg-assistant .wl-badge").inner_text() == "Local"
    assert "Débit 38,4 tokens/s" in foot and "(provisoire)" not in foot
    assert "Tokens 12" in foot and "Chargement 0,42 s" in foot and "Durée totale 1,2 s" in foot
    chat.locator(".wl-msg-foot wl-metric", has_text="Débit").get_by_role("button").click()
    rate_help = chat.locator(".wl-msg-foot wl-metric", has_text="Débit").locator(".wl-metric-help")
    assert "chargement du modèle exclu" in rate_help.inner_text()
    wait_for(
        chat,
        "() => document.querySelector('wl-chat-thread [role=status]').textContent"
        " === 'Réponse de Factice 1B terminée, 12 tokens.'",
    )
    assert chat.get_by_role("log").locator(".wl-msg-flag:visible").count() == 0
    assert commands[0]["model"] == "fake:1b" and commands[0]["allow_cloud"] is False


def test_the_footer_is_provisional_and_italic_until_the_metrics_arrive(chat, server):
    scripted(
        chat,
        server,
        [
            {"text": "mot " * 60},
            {"sleep_s": 1.5},
            {"text": "mot " * 60},
            {"sleep_s": 1.5},
            {"done": DONE},
        ],
    )
    ask(chat, "Raconte")
    metric = chat.locator(".wl-msg-foot wl-metric", has_text="Débit")
    wait_for(
        chat,
        "() => /Débit\\s*[\\d,\\s]+tokens\\/s\\s*\\(provisoire\\)/.test("
        "document.querySelector('.wl-msg-foot')?.textContent ?? '')",
    )
    assert (
        metric.locator(".wl-metric-value").evaluate("n => getComputedStyle(n).fontStyle")
        == "italic"
    )
    assert "Durée" in chat.locator(".wl-msg-foot").inner_text()
    chat.locator(".wl-msg-foot").filter(has_text="Durée totale").wait_for()
    assert "(provisoire)" not in chat.locator(".wl-msg-foot").inner_text()


# --- CO2 mesuré dans le pied de réponse (story 2.3) ---------------------------------------------

MEASURED = {"mg": 1.8, "method": "codecarbon", "estimated": False, "allocation": "direct"}
UNMEASURABLE = {
    "mg": None,
    "method": "unmeasurable",
    "reason": "CodeCarbon n'a pas démarré (RuntimeError).",
}


def finished_foot(page):
    page.locator(".wl-msg-foot").filter(has_text="Durée totale").wait_for()
    return page.locator(".wl-msg-foot")


def test_a_measured_local_reply_shows_its_co2_in_the_footer_in_one_unit_and_no_threshold_color(
    chat, server
):
    scripted(chat, server, [{"text": "Bonjour"}, {"done": DONE}], co2=MEASURED)
    ask(chat, "Dis bonjour")
    foot = finished_foot(chat)
    text = re.sub(r"\s+", " ", foot.inner_text())
    assert "CO₂ 1,8 mg" in text  # fr-FR : virgule décimale, espace insécable avant l'unité
    assert text.index("CO₂") < text.index("Débit")  # badge, CO₂, débit, chargement, durée
    co2 = foot.locator("wl-metric", has_text="CO₂")
    assert co2.locator(".wl-metric-unit, .wl-metric-flag").count() == 0
    # Jamais de couleur par seuil : le CO₂ a la couleur des autres chiffres du pied.
    colors = foot.locator(".wl-metric-value").evaluate_all(
        "nodes => nodes.map(n => getComputedStyle(n).color)"
    )
    assert len(set(colors)) == 1, colors


def test_a_large_co2_keeps_a_single_unit(chat, server):
    scripted(chat, server, [{"text": "Long"}, {"done": DONE}], co2={**MEASURED, "mg": 2400.0})
    ask(chat, "Dis bonjour")
    text = re.sub(r"\s+", " ", finished_foot(chat).inner_text())
    assert "CO₂ 2,4 g" in text and " mg" not in text.split("Débit")[0]


def test_an_unmeasurable_reply_says_so_with_its_reason_in_help_and_never_shows_zero(chat, server):
    scripted(chat, server, [{"text": "Bonjour"}, {"done": DONE}], co2=UNMEASURABLE)
    ask(chat, "Dis bonjour")
    foot = finished_foot(chat)
    metric = foot.locator("wl-metric", has_text="CO₂")
    assert re.sub(r"\s+", " ", metric.inner_text()).startswith("CO₂ non mesurable")
    assert not re.search(r"CO₂\s*0", re.sub(r"\s+", " ", foot.inner_text()))
    metric.get_by_role("button").click()
    assert metric.locator(".wl-metric-help").inner_text() == UNMEASURABLE["reason"]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_footer_with_a_measured_and_an_unmeasurable_co2(
    chat, server, theme
):
    chat.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    for co2, label in ((MEASURED, "mesuré"), (UNMEASURABLE, "non mesurable")):
        scripted(chat, server, [{"text": "Bonjour"}, {"done": DONE}], co2=co2)
        ask(chat, f"Question {label}")
        chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
        foot = finished_foot(chat).last
        foot.locator("wl-metric", has_text="CO₂").get_by_role("button").click()
        assert_no_axe_violations(chat, f"pied avec CO₂ {label}, thème {theme}")


# `core/markdown.js` seul, dans une page : titres, listes, code, liens sûrs, jamais du HTML.
MARKDOWN = """async (sources) => {
    const { renderMarkdown } = await import('/static/core/markdown.js');
    return sources.map((source) => {
        const host = document.createElement('div');
        host.append(renderMarkdown(source));
        return host.innerHTML;
    });
}"""


def render(page, *sources):
    return page.evaluate(MARKDOWN, list(sources))


def test_the_markdown_subset(chat):
    (title, html, link, items, fence, plain, quote) = render(
        chat,
        "# Titre\n\nTexte **gras**, *italique* et `code`.",
        "<img src=x onerror=alert(1)> & <b>gras</b>",
        "[ok](https://example.org/a?b=1) [mal](javascript:alert(1)) [rel](/relatif)",
        "- a\n- b\n  - c\n\n1. un\n2. deux",
        "```py\nprint(1)\n<b>x</b>",
        "un_nom_en_snake_case et 2 * 3 * 4",
        "> cité\n> encore\n\n---",
    )
    assert title == (
        '<p class="md-heading md-heading-1"><strong>Titre</strong></p>'
        "<p>Texte <strong>gras</strong>, <em>italique</em> et <code>code</code>.</p>"
    )
    assert html == "<p>&lt;img src=x onerror=alert(1)&gt; &amp; &lt;b&gt;gras&lt;/b&gt;</p>"
    assert link.count("<a ") == 1
    assert 'href="https://example.org/a?b=1" target="_blank" rel="noopener noreferrer"' in link
    assert "[mal](javascript:alert(1))" in link and "[rel](/relatif)" in link
    assert items == (
        "<ul><li>a</li><li>b<ul><li>c</li></ul></li></ul><ol><li>un</li><li>deux</li></ol>"
    )
    assert fence == '<pre class="md-code"><code>print(1)\n&lt;b&gt;x&lt;/b&gt;</code></pre>'
    assert plain == "<p>un_nom_en_snake_case et 2 * 3 * 4</p>"
    assert quote == "<blockquote><p>cité<br>encore</p></blockquote><hr>"


def test_a_pathological_link_pattern_renders_in_linear_time(chat):
    # « [a](b » répété : sans borne sur le libellé et l'adresse, le rendu était quadratique
    # (environ 260 ms pour 50 Ko, à chaque rendu de 150 ms pendant le flux).
    elapsed = chat.evaluate(
        """async () => {
        const { renderMarkdown } = await import('/static/core/markdown.js');
        const source = '[a](b'.repeat(10000);
        const started = performance.now();
        renderMarkdown(source);
        return performance.now() - started;
    }"""
    )
    assert elapsed < 60, elapsed


# --- Arrêt en moins d'une seconde -------------------------------------------------------------


def test_the_stop_button_ends_the_stream_in_under_a_second_and_keeps_the_partial(chat, server):
    scripted(chat, server, [{"text": "Début de réponse"}, {"sleep_s": 30}])
    ask(chat, "Écris longtemps")
    chat.locator(".wl-md").filter(has_text="Début de réponse").wait_for()
    started = time.monotonic()
    chat.get_by_role("button", name="Arrêter").click()
    chat.locator(".wl-msg-flag").filter(has_text="Arrêté").wait_for()
    assert time.monotonic() - started < 1.0
    assert answer_text(chat) == "Début de réponse"
    assert chat.locator(".wl-run-stage").inner_text() == "Arrêté"
    assert run_status(chat, last_run()) == "cancelled"
    assert chat.get_by_role("button", name="Envoyer").is_enabled()  # on peut reposer une question
    wait_for(
        chat,
        "() => document.querySelector('wl-chat-thread [role=status]').textContent"
        " === 'Réponse de Factice 1B arrêtée.'",
    )


def test_the_escape_key_stops_the_generation_in_under_a_second(chat, server):
    scripted(chat, server, [{"text": "Début"}, {"sleep_s": 30}])
    ask(chat, "Écris longtemps")
    chat.locator(".wl-md").filter(has_text="Début").wait_for()
    started = time.monotonic()
    field(chat).press("Escape")
    chat.locator(".wl-msg-flag").filter(has_text="Arrêté").wait_for()
    assert time.monotonic() - started < 1.0
    assert answer_text(chat) == "Début"


# Ce qu'un lecteur d'écran annoncerait : chaque texte écrit dans une région vivante (`aria-live`,
# `role=status|log|alert`) dont la politesse effective, au moment de l'écriture, n'est pas `off`.
RECORD_ANNOUNCEMENTS = """() => {
  window.__said = [];
  const politeness = (node) => {
    for (let n = node; n && n.nodeType === 1; n = n.parentElement) {
      const live = n.getAttribute('aria-live');
      if (live) return live;
      const role = n.getAttribute('role');
      if (role === 'status' || role === 'log') return 'polite';
      if (role === 'alert') return 'assertive';
    }
    return 'off';
  };
  new MutationObserver((records) => {
    for (const record of records) {
      const node = record.target.nodeType === 1 ? record.target : record.target.parentElement;
      if (!node || politeness(node) === 'off') continue;
      const text = node.textContent.trim();
      if (text && window.__said.at(-1) !== text) window.__said.push(text);
    }
  }).observe(document.querySelector('section[data-screen=arena-chat]'),
             { childList: true, characterData: true, subtree: true });
}"""


def test_only_the_stage_change_and_one_end_announcement_are_spoken(chat, server):
    scripted(
        chat,
        server,
        [
            {"load": "loaded"},
            {"text": "Bonjour "},
            {"sleep_s": 0.4},
            {"text": "le monde"},
            {"done": DONE},
        ],
    )
    chat.evaluate(RECORD_ANNOUNCEMENTS)
    ask(chat, "Dis bonjour")
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    wait_for(
        chat,
        "() => document.querySelector('wl-chat-thread [role=status]').textContent !== ''",
    )
    said = chat.evaluate("window.__said")
    # Aucun token annoncé, et la fin une seule fois (pas « Terminé » en plus de la phrase du fil).
    assert not any("Bonjour" in text for text in said), said
    assert "Terminé" not in said, said
    assert said[-1] == "Réponse de Factice 1B terminée, 12 tokens.", said
    assert sum("terminée" in text for text in said) == 1, said


# --- Reprise au retour ------------------------------------------------------------------------

WORDS = ["un ", "deux ", "trois ", "quatre ", "cinq ", "six"]


def test_the_stream_resumes_by_after_without_loss_or_duplicate_after_a_visit_to_home(
    chat, server, traffic
):
    script = []
    for word in WORDS:
        script += [{"text": word}, {"sleep_s": 0.7}]
    scripted(chat, server, script)
    ask(chat, "Compte")
    chat.locator(".wl-md").filter(has_text="un").wait_for()
    run_id = last_run()

    chat.evaluate("location.hash = '#/'")
    chat.locator("section[data-screen=arena-chat]").wait_for(state="hidden")
    time.sleep(1.8)  # la génération continue pendant l'absence
    chat.evaluate("location.hash = '#/arene/chat'")
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()

    assert answer_text(chat) == "un deux trois quatre cinq six"
    assert run_status(chat, run_id) == "ok"  # la génération n'a pas été interrompue
    streams = [url for url in traffic.urls if f"/api/runs/{run_id}/events" in url]
    assert len(streams) == 2 and "?after=" not in streams[0] and "?after=" in streams[1]
    assert chat.locator(".wl-msg-assistant").count() == 1  # une seule réponse, pas de doublon


def test_a_scrolled_up_position_is_kept_after_a_visit_to_home(chat, server):
    lines = [{"text": f"ligne {n}\n\n"} for n in range(60)]
    scripted(chat, server, [*lines, {"sleep_s": 30}])
    ask(chat, "Beaucoup de lignes")
    chat.locator(".wl-md").filter(has_text="ligne 59").wait_for()
    log = chat.get_by_role("log")
    log.evaluate("node => { node.scrollTop = 200; }")  # la personne remonte
    chat.get_by_role("button", name="Aller à la fin").wait_for(state="visible")
    chat.evaluate("location.hash = '#/'")
    chat.locator("section[data-screen=arena-chat]").wait_for(state="hidden")
    chat.evaluate("location.hash = '#/arene/chat'")
    chat.locator("section[data-screen=arena-chat]").wait_for(state="visible")
    # Masqué, `scrollTop` vaut 0 : la position rendue est celle vue avant de partir.
    wait_for(chat, "() => Math.abs(document.querySelector('[role=log]').scrollTop - 200) < 5")
    assert chat.get_by_role("button", name="Aller à la fin").is_visible()


def test_enter_pressed_again_while_the_command_is_pending_sends_nothing_more(chat, server):
    commands: list[dict] = []
    scripted(chat, server, [{"text": "Réponse"}, {"done": DONE}], commands)
    held: list = []  # la commande reste en attente tant que le test ne la relâche pas
    chat.route(re.compile(r"/api/chat/runs$"), lambda route: held.append(route))
    field(chat).fill("Première")
    field(chat).press("Enter")
    wait_for(chat, "() => document.querySelector('.chat-send').disabled")
    field(chat).press("Enter")  # pendant la requête : ignoré
    assert chat.get_by_role("button", name="Effacer la conversation").is_disabled()
    assert len(held) == 1
    held[0].fallback()
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert len(commands) == 1
    assert chat.locator(".wl-msg-user").count() == 1


def test_a_busy_chat_is_joined_instead_of_showing_an_error(chat_lenient, server):
    chat = chat_lenient
    script = [{"text": "Réponse "}, {"sleep_s": 1.0}, {"text": "en cours"}]
    start_run(chat, server, script)
    scripted(chat, server, script)  # la commande de la page se heurte au run actif : 409
    ask(chat, "Ma question")
    chat.locator(".chat-notice").filter(has_text="Une réponse est déjà en cours").wait_for()
    assert chat.locator("wl-error[data-code=run_busy]").count() == 0
    assert chat.locator("wl-error:visible").count() == 0
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert answer_text(chat) == "Réponse en cours"
    assert field(chat).input_value() == "Ma question"  # le message n'est pas parti, il reste


# --- Saisie : clavier, brouillon, commandes -----------------------------------------------------


def test_enter_sends_and_shift_enter_adds_a_line(chat, server):
    commands: list[dict] = []
    scripted(chat, server, [{"text": "ok"}], commands)
    field(chat).fill("a")
    field(chat).press("Shift+Enter")
    field(chat).type("b")
    assert field(chat).input_value() == "a\nb" and commands == []
    field(chat).press("Enter")
    chat.locator(".wl-msg-user").wait_for()
    assert [c["message"] for c in commands] == ["a\nb"]
    assert chat.locator(".wl-msg-user .wl-msg-text").inner_text() == "a\nb"


def test_the_draft_survives_a_reload_and_is_cleared_once_sent(chat, server):
    scripted(chat, server, [{"text": "ok"}])
    field(chat).fill("Brouillon à garder")
    chat.reload()
    wait_ready(chat)
    assert field(chat).input_value() == "Brouillon à garder"
    wait_for(chat, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    field(chat).press("Enter")
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    chat.reload()
    wait_ready(chat)
    assert field(chat).input_value() == ""


def test_the_cloud_switch_is_not_stored_and_the_commands_carry_the_store_value(chat, server):
    commands: list[dict] = []
    scripted(chat, server, [{"text": "ok"}], commands)
    slider = chat.get_by_label("Créativité")
    slider.fill("1.4")
    assert chat.locator("output.chat-slider-value").inner_text() == "1,4"
    ask(chat, "Première")
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    chat.get_by_label("Autoriser le cloud").check()
    ask(chat, "Seconde")
    chat.locator(".wl-msg-user").nth(1).wait_for()
    assert [(c["allow_cloud"], c["temperature"]) for c in commands] == [(False, 1.4), (True, 1.4)]
    assert chat.evaluate("JSON.stringify(Object.entries(localStorage))").find("cloud") == -1


def test_the_real_route_continues_the_same_conversation(chat):
    commands: list[dict] = []
    chat.on(
        "request",
        lambda request: (
            commands.append(json.loads(request.post_data))
            if request.url.endswith("/api/chat/runs")
            else None
        ),
    )
    with chat.expect_response(re.compile(r"/api/chat/runs$")) as first:
        ask(chat, "Bonjour")
    started = first.value.json()
    assert started["run_id"] and started["conversation_id"]
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    ask(chat, "Et ensuite")
    chat.locator(".wl-msg-user").nth(1).wait_for()
    assert commands[0] == {
        "conversation_id": None,
        "model": "fake:1b",
        "message": "Bonjour",
        "temperature": 0.2,
        "allow_cloud": False,
    }
    assert commands[1]["conversation_id"] == started["conversation_id"]
    # Effacer la conversation : sans confirmation, et la suivante en ouvre une autre.
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    chat.get_by_role("button", name="Effacer la conversation").click()
    assert chat.locator(".wl-msg").count() == 0 and chat.locator(".chat-empty").is_visible()
    ask(chat, "Nouveau départ")
    chat.locator(".wl-msg-user").wait_for()
    assert commands[2]["conversation_id"] is None


def test_a_refused_command_shows_the_error_and_keeps_the_message(chat_lenient):
    chat = chat_lenient
    chat.route(
        re.compile(r"/api/chat/runs$"),
        lambda route: route.fulfill(
            status=403,
            content_type="application/json",
            body=json.dumps(
                {
                    "code": "cloud_not_allowed",
                    "message": "Ce modèle est hébergé hors de ce poste.",
                    "action": "Autorisez le mode cloud, ou choisissez un modèle local.",
                    "detail": {"tag": "x"},
                }
            ),
        ),
    )
    ask(chat, "Envoie-moi")
    error = chat.locator("wl-error[data-code=cloud_not_allowed]")
    error.wait_for()
    assert "hébergé hors de ce poste" in error.inner_text()
    assert field(chat).input_value() == "Envoie-moi"
    assert chat.locator(".wl-msg").count() == 0


# --- Défilement ---------------------------------------------------------------------------------


def test_scrolling_follows_only_from_the_bottom_and_offers_to_go_to_the_end(chat, server):
    lines = [{"text": f"ligne {n}\n\n"} for n in range(40)]
    later = []
    for n in range(40, 70):
        later += [{"text": f"ligne {n}\n\n"}, {"sleep_s": 0.08}]
    scripted(chat, server, [*lines, {"sleep_s": 1.5}, *later])
    ask(chat, "Beaucoup de lignes")
    log = chat.get_by_role("log")
    button = chat.get_by_role("button", name="Aller à la fin")
    wait_for(
        chat,
        "() => { const l = document.querySelector('[role=log]'); return l.scrollHeight > l.clientHeight + 200; }",
    )
    at_bottom = "() => { const l = document.querySelector('[role=log]'); return l.scrollHeight - l.scrollTop - l.clientHeight <= 24; }"
    wait_for(chat, at_bottom)  # en bas : le défilement suit
    assert button.is_hidden()
    log.evaluate("node => { node.scrollTop = 0; }")  # la personne remonte
    button.wait_for(state="visible")
    chat.locator(".wl-md").filter(has_text="ligne 69").wait_for()  # la suite arrive
    assert log.evaluate("node => node.scrollTop") < 50  # sans l'entraîner
    assert button.is_visible()
    button.click()
    wait_for(chat, at_bottom)
    assert button.is_hidden()


# --- Accessibilité --------------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_chat_screen(chat, server, theme):
    scripted(
        chat,
        server,
        [
            {
                "text": "Réponse **en cours** avec `code` et un [lien](https://example.org).\n\n- a\n- b"
            },
            {"text": "Réflexion", "channel": "thought"},
            {"sleep_s": 2.5},
            {"done": DONE},
        ],
    )
    chat.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(chat, f"écran vide, thème {theme}")
    ask(chat, "Question")
    chat.locator(".wl-md strong").filter(has_text="en cours").wait_for()
    assert_no_axe_violations(chat, f"réponse en cours, thème {theme}")
    chat.locator(".wl-msg-foot").filter(has_text="Durée totale").wait_for()
    chat.locator("details.wl-thought summary").click()
    chat.locator(".wl-msg-foot wl-metric", has_text="Débit").get_by_role("button").click()
    assert_no_axe_violations(chat, f"réponse terminée, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_a_stopped_answer(chat, server, theme):
    scripted(chat, server, [{"text": "Partiel"}, {"sleep_s": 30}])
    chat.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    ask(chat, "Question")
    chat.locator(".wl-md").filter(has_text="Partiel").wait_for()
    chat.get_by_role("button", name="Arrêter").click()
    chat.locator(".wl-msg-flag").filter(has_text="Arrêté").wait_for()
    assert_no_axe_violations(chat, f"réponse arrêtée, thème {theme}")


def test_every_request_stays_on_127_0_0_1(chat, server, traffic):
    scripted(chat, server, [{"text": "ok"}])
    ask(chat, "Bonjour")
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert traffic.urls and all(url.startswith("http://127.0.0.1") for url in traffic.urls)


# --- A19 : le bouton plein est sur `primary-fill` (décision Q1) ---------------------------------


def contrast_violations(page):
    results = Axe().run(page, options={"runOnly": {"type": "rule", "values": ["color-contrast"]}})
    return results.violations_count, results.generate_report()


@pytest.mark.parametrize(
    ("theme", "fill"), [("light", "rgb(69, 29, 199)"), ("dark", "rgb(106, 77, 230)")]
)
def test_the_first_filled_button_uses_primary_fill_with_white_text_and_passes_color_contrast(
    chat, theme, fill
):
    chat.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    send = chat.get_by_role("button", name="Envoyer")
    style = send.evaluate(
        "n => { const s = getComputedStyle(n); return [s.backgroundColor, s.color]; }"
    )
    assert style == [fill, "rgb(255, 255, 255)"]
    count, report = contrast_violations(chat)  # sans exclusion
    assert count == 0, report


def test_a_disabled_filled_button_is_told_by_colors_not_by_opacity(chat, server):
    scripted(chat, server, [{"text": "x"}, {"sleep_s": 30}])
    chat.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    ask(chat, "Question")
    send = chat.get_by_role("button", name="Envoyer")
    wait_for(chat, "() => document.querySelector('.chat-send').disabled")
    style = send.evaluate(
        "n => { const s = getComputedStyle(n); return [s.backgroundColor, s.color, s.opacity]; }"
    )
    assert style == ["rgb(22, 22, 42)", "rgb(180, 180, 198)", "1"]
    count, report = contrast_violations(chat)
    assert count == 0, report
