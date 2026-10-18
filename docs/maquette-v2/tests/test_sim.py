"""Simulateur de runs (js/sim/sim.js) : fin de run pendant une coupure, pause de décision, script
construit à l'exécution, contrôle préalable d'un téléchargement sous garde-fou mémoire."""

from __future__ import annotations

from conftest import open_route

SIM = "./js/sim/sim.js"
SYSTEME = "./js/sim/systeme.js"
STORE = "./js/core/store.js"


def test_run_that_ends_during_a_cut_is_delivered_on_reconnect(page, base_url):
    open_route(page, base_url, "/")
    result = page.evaluate(
        """async ([simPath, sysPath, storePath]) => {
            const { sim } = await import(simPath);
            const { loseConnection, restoreConnection } = await import(sysPath);
            const { store } = await import(storePath);
            const types = [];
            loseConnection();
            while (store.get().connection.status !== "lost") await new Promise((resolve) => setTimeout(resolve, 10));
            const run = sim.play({ kind: "test-coupure", events: [
              { wait: 0, type: "run_started", data: {} },
              { wait: 10, type: "token", data: { lane: 0, text: "a", channel: "answer" } },
              { wait: 10, type: "run_ended", data: { status: "ok", error: null } },
            ] }, { "*": (data, env) => types.push(env.type) }, { speed: 1 });
            const status = await run.done;
            const beforeRestore = types.length;
            restoreConnection();
            await new Promise((resolve) => setTimeout(resolve, 50));
            return { status, beforeRestore, types };
        }""",
        [SIM, SYSTEME, STORE],
    )
    assert result["status"] == "ok"
    assert result["beforeRestore"] == 0
    assert result["types"] == ["run_started", "token", "run_ended"]


def test_pause_waits_for_a_decision_then_resumes(page, base_url):
    open_route(page, base_url, "/")
    result = page.evaluate(
        """async (simPath) => {
            const { sim } = await import(simPath);
            const types = [];
            const run = sim.play({ kind: "test-pause", events: [
              { wait: 0, type: "run_started", data: {} },
              { wait: 5, type: "approval_required", data: {} },
              { pause: true },
              { wait: 5, type: "run_ended", data: { status: "ok", error: null } },
            ] }, { "*": (data, env) => types.push(env.type) }, { speed: 1 });
            await new Promise((resolve) => setTimeout(resolve, 120));
            const paused = run.paused && !run.ended;
            run.resume(sim.prepare([{ wait: 5, type: "approval_resolved", data: { decision: "{{d}}" } }], { d: "approved" }));
            const status = await run.done;
            return { paused, status, types, decision: run.log[2].data.decision };
        }""",
        SIM,
    )
    assert result["paused"] is True
    assert result["status"] == "ok"
    assert result["types"] == ["run_started", "approval_required", "approval_resolved", "run_ended"]
    assert result["decision"] == "approved"


def test_precheck_does_not_oppose_ram_guard_to_a_pull(page, base_url):
    open_route(page, base_url, "/")
    codes = page.evaluate(
        """async ([simPath, storePath]) => {
            const { sim } = await import(simPath);
            const { setMaquette } = await import(storePath);
            setMaquette({ ramGuard: true });
            const pull = sim.precheck({ kind: "pull" });
            const chat = sim.precheck({ kind: "chat" });
            setMaquette({ ramGuard: false });
            return { pull: pull?.code ?? null, chat: chat?.code ?? null };
        }""",
        [SIM, STORE],
    )
    assert codes == {"pull": None, "chat": "ram_guard"}
