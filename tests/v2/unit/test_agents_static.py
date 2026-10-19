"""Écran Agent seul et trace d'étapes (story 6.4) : règles de structure, de textes et d'AD-20, sans
navigateur. Les parcours (étapes, validation, reprise, axe) vivent dans
`tests/v2/e2e/test_agents_solo.py`."""

from __future__ import annotations

import re

from .static_files import STATIC, catalog, read, registry_text, text_file_names

SCRIPTS = [
    "screens/agents-solo.js",
    "screens/agents-approval.js",
    "screens/agents-tools.js",
    "components/wl-step-trace.js",
    "core/api/agents.js",
]
CATALOG = catalog()


def linked_stylesheets_of(html: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="/static/([\w/.-]+)">', html)


def test_the_agent_screen_is_registered_available_with_its_loader_and_the_crew_stays_planned():
    text = registry_text()
    assert re.search(
        r'id: "agents-solo",\s*path: "/agents/seul",\s*status: "available",\s*'
        r'load: \(\) => import\("\.\./\.\./screens/agents-solo\.js"\)',
        text,
    )
    assert re.search(r'id: "agents-crew",\s*path: "/agents/equipe",[^}]*status: "planned"', text)
    assert (STATIC / "screens/agents-solo.js").is_file()


def test_the_screen_texts_are_in_their_own_file_and_every_agents_key_is_used_and_exists():
    assert "agents" in text_file_names() and (STATIC / "i18n/fr/agents.json").is_file()
    code = "\n".join(read(name) for name in SCRIPTS)
    used = set(re.findall(r"""["']agents\.([\w.]+)["']""", code))
    # Les textes d'accueil se nomment par `agents.welcome.${name}_…` : on les ajoute à la main.
    used |= {f"welcome.{n}_{k}" for n in ("audit", "data") for k in ("title", "button", "prompt")}
    used |= {"welcome.sobriety_title", "welcome.sobriety_text"}

    def flat(value, prefix=""):
        if isinstance(value, dict):
            return {k for name, v in value.items() for k in flat(v, f"{prefix}{name}.")}
        return {prefix.rstrip(".")}

    assert used == flat(CATALOG["agents"])


def test_the_step_trace_and_status_texts_exist_and_are_all_used():
    trace = read("components/wl-step-trace.js")
    wanted = set(re.findall(r"""["']components\.step_trace\.(\w+)["']""", trace))
    wanted |= {f"state_{state}" for state in ("running", "approval")}  # `state_${current}`
    assert wanted == set(CATALOG["components"]["step_trace"])
    status = CATALOG["components"]["run_status"]
    assert {"thinking", "tool", "approval"} <= set(status)
    assert "{tool}" in status["tool"]
    assert "steps" in CATALOG["components"]["thread"]


def test_the_trace_is_exported_styled_and_linked_before_the_screens():
    assert 'WlStepTrace } from "./wl-step-trace.js"' in read("components/index.js")
    links = linked_stylesheets_of(read("index.html"))
    assert "css/components/step-trace.css" in links
    assert links.index("css/components/step-trace.css") < links.index("screens.css")
    assert links.index("agents.css") > links.index("screens.css")


def test_the_new_scripts_never_write_html_and_stay_under_the_size_limit():
    for name in SCRIPTS:
        code = read(name)
        assert "innerHTML" not in code and "insertAdjacentHTML" not in code, name
        assert len(code.splitlines()) <= 600, name
    for name in ("components/wl-chat-thread.js", "components/wl-run-status.js"):
        assert len(read(name).splitlines()) <= 600, name


def test_the_screen_reads_its_footer_from_the_server_and_computes_no_metric():
    """AD-20 : CO2, étapes et durée du pied viennent de `totals` ; l'écran n'additionne rien."""
    screen = read("screens/agents-solo.js")
    assert "summarize(" in screen and ".totals" in screen
    code = "\n".join(read(name) for name in SCRIPTS)
    assert not re.search(
        r"\.reduce\(|Math\.(round|floor|ceil)\(.*duration|duration_s\s*[-+*/]", code
    )


def test_the_reduced_footer_has_no_rate_tokens_or_load_and_the_download_is_a_server_route():
    thread = read("components/wl-chat-thread.js")
    reduced = thread[thread.index("#reducedFoot() {") : thread.index("dispose() {")]
    for forbidden in ("rate", "tokens", "components.thread.load", "first_token"):
        assert forbidden not in reduced, forbidden
    screen = read("screens/agents-solo.js")
    assert "conversationExportUrl" in screen
    assert not re.search(r"createObjectURL|new Blob|href = [\"'`]blob", screen)


def test_the_unavailable_switch_state_exists_and_blocks_the_toggle():
    tools = read("screens/agents-tools.js")
    assert 'role", "switch"' in tools and 'setAttribute("aria-disabled", "true")' in tools
    assert "preventDefault" in tools and "disabled = true" not in tools  # focalisable
    assert 'input[aria-disabled="true"]' in read("css/components/switch.css")


def test_the_approval_flow_answers_only_through_the_route_and_never_decides_alone():
    approval = read("screens/agents-approval.js")
    assert approval.count("api.answerApproval(") == 1
    assert '"approved"' in approval and "expired" in approval
    # « Annuler » refuse ; fermer par le serveur ou l'écran masqué ne répond jamais.
    assert 'confirmed ? "approved" : "rejected"' in approval
    assert "request.resolved || request.suspended" in approval


def test_the_status_keeps_escape_for_an_open_modal_dialog():
    assert 'document.querySelector("dialog[open]")' in read("components/wl-run-status.js")
