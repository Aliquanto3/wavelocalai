"""Coquille de la maquette : menus de la barre haute au clavier (ouverture, Échap, retour du
focus), menu replié sous 1 024 px, interrupteur cloud non mémorisé, thème sans rechargement, page
ouverte en file:// qui explique quoi faire, simulateur fidèle au format SSE de la spine."""

from __future__ import annotations

import pytest
from conftest import ROOT, assert_no_axe_violations, open_route, wait_for

DISCLOSURES = [
    ("ollama-button", "ollama-panel"),
    ("cloud-help-button", "cloud-help"),
    ("co2-button", "co2-panel"),
    ("display-button", "display-panel"),
]


@pytest.mark.parametrize(("button", "panel"), DISCLOSURES, ids=[b for b, _ in DISCLOSURES])
def test_topbar_panels_open_and_close_with_escape(page, base_url, button, panel):
    open_route(page, base_url, "/")
    page.locator(f"#{button}").focus()
    page.keyboard.press("Enter")
    page.locator(f"#{panel}").wait_for(state="visible")
    assert page.locator(f"#{button}").get_attribute("aria-expanded") == "true"
    assert_no_axe_violations(page, f"panneau {panel} ouvert")
    page.keyboard.press("Escape")
    page.locator(f"#{panel}").wait_for(state="hidden")
    assert page.evaluate("() => document.activeElement.id") == button


def test_module_menu_collapses_under_1024_px(page, base_url):
    page.set_viewport_size({"width": 768, "height": 900})
    open_route(page, base_url, "/")
    toggle = page.locator("#nav-toggle")
    assert toggle.is_visible()
    assert page.locator("#module-list").is_hidden()
    toggle.focus()
    page.keyboard.press("Enter")
    page.locator("#module-list").wait_for(state="visible")
    page.keyboard.press("Tab")
    page.keyboard.press("Escape")
    page.locator("#module-list").wait_for(state="hidden")
    assert page.evaluate("() => document.activeElement.id") == "nav-toggle"


def test_six_modules_and_route_change_moves_focus_to_h1(page, base_url):
    open_route(page, base_url, "/")
    labels = page.locator("#module-list a").all_inner_texts()
    assert labels == ["Accueil", "Arène", "Documents", "Agents", "Sobriété", "Modèles"]
    page.locator("#module-list a", has_text="Sobriété").click()
    wait_for(page, "() => window.__maquette.current().slug === 'sobriete'")
    assert page.evaluate("() => document.activeElement.tagName") == "H1"
    assert page.locator("#module-list a[aria-current='page']").inner_text() == "Sobriété"


def test_unknown_route_returns_home(page, base_url):
    open_route(page, base_url, "/nulle-part")
    assert page.evaluate("() => window.__maquette.current().slug") == "accueil"


def test_cloud_switch_survives_navigation_not_reload(page, base_url):
    open_route(page, base_url, "/")
    page.locator("#cloud-switch").check()
    page.evaluate("() => window.__maquette.navigate('/arene/chat')")
    assert page.locator("#cloud-switch").is_checked()
    assert page.evaluate(
        "() => Object.values(localStorage).every((v) => !String(v).includes('cloud'))"
    )
    page.reload()
    wait_for(page, "() => window.__maquette && window.__maquette.ready === true")
    assert not page.locator("#cloud-switch").is_checked()


def test_theme_applies_without_reload(page, base_url):
    open_route(page, base_url, "/")
    page.locator("#display-button").click()
    page.get_by_label("Sombre").check()
    assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
    page.get_by_label("Système").check()
    assert page.evaluate("() => localStorage.getItem('wl.theme')") == "system"


def test_file_protocol_explains_what_to_do(browser):
    page = browser.new_page()
    page.goto((ROOT / "index.html").as_uri())
    assert "ouvrir.cmd" in page.locator("main").inner_text()
    page.close()


SSE_CHECK = """async () => {
  const { sim } = await import('./js/sim/sim.js');
  const seen = [];
  const run = sim.play('chat-libre-reponse', { '*': (data, envelope) => seen.push(envelope) }, {
    kind: 'test', speed: 200,
    vars: { tag: 'qwen3.5:2b', temperature: 0.7, loading: true, load_s: 3.2, thought: 'Réflexion.',
            answer: 'Une réponse courte.', partial: '', tps: 41,
            metrics: { lane: 'qwen3.5:2b', tps: 41, co2: { mg: 1.8, method: 'codecarbon', estimated: false,
                       range_mg: null, allocation: 'direct', reason: null } } },
  });
  await run.done;
  return seen;
}"""


def test_simulator_emits_spine_envelopes(page, base_url):
    open_route(page, base_url, "/")
    events = page.evaluate(SSE_CHECK)
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "run_started" and events[-1]["type"] == "run_ended"
    assert sum(event["type"] == "run_ended" for event in events) == 1
    for event in events:
        assert set(event) == {"seq", "run_id", "type", "ts", "data"}
        assert event["ts"].endswith("Z")
        if event["type"] in {"token", "metrics"}:
            assert event["data"]["lane"] == "qwen3.5:2b"
    channels = {event["data"]["channel"] for event in events if event["type"] == "token"}
    assert channels == {"thought", "answer"}


def test_simulator_resumes_after_seq_without_duplicates(page, base_url):
    open_route(page, base_url, "/")
    seqs = page.evaluate(
        """async () => {
          const { sim } = await import('./js/sim/sim.js');
          const seen = [];
          const vars = { tag: 'm', temperature: 0, loading: false, load_s: null, thought: '',
                         answer: 'x'.repeat(400), partial: '', tps: 40, metrics: { lane: 'm' } };
          const run = sim.play('chat-libre-reponse', null, { kind: 'reprise', speed: 20, vars });
          let first = run.attach({ '*': (d, e) => seen.push(e.seq) });
          await new Promise((r) => setTimeout(r, 120));
          first.close();
          const after = seen.at(-1) ?? 0;
          await new Promise((r) => setTimeout(r, 120));
          run.attach({ '*': (d, e) => seen.push(e.seq) }, { after });
          await run.done;
          return seen;
        }"""
    )
    assert seqs == list(range(1, len(seqs) + 1)), seqs
