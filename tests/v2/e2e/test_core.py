"""Modules core/ du front (story 1.9) dans un vrai navigateur : formats fr-FR, client SSE unique,
store et appels à l'API. Les flux de run sont simulés par interception (trames exactes) pour
éprouver l'aiguillage, le dédoublonnage et la reprise ; un run scripté du vrai serveur boucle la
chaîne."""

from __future__ import annotations

import json

import pytest

from .test_shell import wait_ready

NBSP = "\N{NO-BREAK SPACE}"
NNBSP = "\N{NARROW NO-BREAK SPACE}"


@pytest.fixture
def core(page, server):
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    return page


@pytest.fixture
def core_lenient(page_tolerating_failed_requests, server):
    """Comme `core`, pour un test dont une requête échoue exprès (404 : le navigateur le dit)."""
    page_tolerating_failed_requests.goto(f"{server.base_url}/")
    wait_ready(page_tolerating_failed_requests)
    return page_tolerating_failed_requests


def envelope(seq: int, run_id: str, kind: str, data: dict | None = None) -> str:
    body = {"seq": seq, "run_id": run_id, "type": kind, "ts": "2026-10-18T10:00:00Z"}
    return f"id: {seq}\ndata: {json.dumps({**body, 'data': data or {}})}\n\n"


def sse_response(route, body: str, status: int = 200) -> None:
    route.fulfill(status=status, body=body, headers={"Content-Type": "text/event-stream"})


# --- core/format.js ---------------------------------------------------------------------------

FORMAT = """async (calls) => {
    const format = await import('/static/core/format.js');
    return calls.map(([name, ...args]) => format[name](...args));
}"""


def formatted(page, *calls):
    return page.evaluate(FORMAT, [list(call) for call in calls])


def test_co2_picks_mg_g_or_kg_and_never_shows_a_zero_for_an_unknown(core):
    assert formatted(
        core,
        ("formatCo2", 1.8),
        ("formatCo2", 0),
        ("formatCo2", 12.34),
        ("formatCo2", 999.6),
        ("formatCo2", 1500),
        ("formatCo2", 12345),
        ("formatCo2", 1_500_000),
        ("formatCo2", None),
        ("formatCo2", None, {"unit": "g"}),
    ) == [
        f"1,8{NBSP}mg",
        f"0{NBSP}mg",  # une mesure à zéro est une mesure
        f"12,3{NBSP}mg",
        f"1{NBSP}g",  # jamais « 1 000 mg »
        f"1,5{NBSP}g",
        f"12,3{NBSP}g",
        f"1,5{NBSP}kg",
        "inconnu",
        "inconnu",
    ]


def test_a_comparison_of_co2_values_uses_a_single_unit(core):
    result = core.evaluate(
        """async () => {
            const { co2Group } = await import('/static/core/format.js');
            const group = co2Group([1500, 1.8, 0.9, null]);
            return [group.unit, group.format(1500), group.format(1.8), group.format(null)];
        }"""
    )
    assert result == ["g", f"1,5{NBSP}g", f"0,0018{NBSP}g", "inconnu"]


def test_numbers_use_the_french_locale_with_three_significant_digits(core):
    assert formatted(
        core,
        ("formatNumber", 0.66),
        ("formatNumber", 13.84),
        ("formatNumber", 1234),
        ("formatNumber", None),
        ("formatInteger", 1234567),
        ("formatGb", 13.84),
        ("formatGb", None),
        ("formatRate", 38.2),
        ("formatPercent", 12.4),
        ("formatPercent", 0),
        ("formatPercent", None),
    ) == [
        "0,66",
        "13,8",
        f"1{NNBSP}230",
        "inconnu",
        f"1{NNBSP}234{NNBSP}567",
        f"13,8{NBSP}Go",
        "inconnu",
        f"38,2{NBSP}tokens/s",
        f"12{NBSP}%",
        f"0{NBSP}%",  # un 0 mesuré reste un 0 ; seul un inconnu devient « inconnu »
        "inconnu",
    ]


def test_durations_dates_and_scores(core):
    assert formatted(
        core,
        ("formatDuration", 0.66),
        ("formatDuration", 5.84),
        ("formatDuration", 59.97),
        ("formatDuration", 72),
        ("formatDuration", 60),
        ("formatDuration", 3900),
        ("formatDuration", None),
        ("formatDate", "2026-10-18T10:00:00Z"),
        ("formatDate", "pas une date"),
        ("formatScore", 72.46),
        ("formatScore", 0),
        ("formatScore", None),
    ) == [
        f"0,66{NBSP}s",
        f"5,84{NBSP}s",
        f"1{NBSP}min",
        f"1{NBSP}min 12{NBSP}s",
        f"1{NBSP}min",
        f"1{NBSP}h 05{NBSP}min",
        "inconnu",
        "18 oct. 2026",
        "inconnu",
        "72,5/100",
        "0/100",
        "non évalué",  # jamais 0/100 pour un score absent
    ]


# --- core/sse.js ------------------------------------------------------------------------------


def test_the_parser_rebuilds_frames_split_anywhere_in_the_stream(core):
    frames = core.evaluate(
        """async () => {
            const { SseParser } = await import('/static/core/sse.js');
            const parser = new SseParser();
            const out = [];
            const chunks = ['id: 1\\r\\nda', 'ta: {"a":1}\\r', '\\n\\r\\n', ': ping\\n\\n',
                'data: x\\ndata: y\\n\\n', 'event: ignoré\\ndata: z\\n\\n', 'data: pas fini'];
            for (const chunk of chunks) out.push(...parser.feed(chunk));
            return out;
        }"""
    )
    assert frames == [
        {"id": "1", "data": '{"a":1}'},
        {"id": None, "data": "x\ny"},
        {"id": None, "data": "z"},  # le champ \event:\ n'aiguille rien
    ]


RUN_STREAM = """async (runId) => {
    const sse = await import('/static/core/sse.js');
    const { store } = await import('/static/core/store.js');
    const seen = [];
    const statuses = [];
    const record = (data, envelope) => seen.push(envelope.type + ':' + envelope.seq);
    await new Promise((resolve) => {
        sse.connectRun(
            runId,
            { run_started: record, token: record, metrics: record, run_ended: record },
            ({ status }) => {
                statuses.push(status);
                if (status === 'closed' || status === 'failed') resolve();
            },
        );
    });
    return { seen, statuses, runs: store.get().runs };
}"""


def test_a_run_stream_routes_by_type_drops_seen_seq_and_closes_at_run_ended(core):
    requests: list[str] = []
    body = "".join(
        [
            envelope(1, "r1", "run_started"),
            envelope(2, "r1", "token", {"lane": "a", "text": "Bon"}),
            envelope(2, "r1", "token", {"lane": "a", "text": "Bon"}),  # doublon
            envelope(1, "r1", "run_started"),  # ancien seq rejoué
            envelope(3, "r1", "type_inconnu", {"x": 1}),  # ignoré, sans erreur
            envelope(4, "r1", "run_ended", {"status": "done"}),
            envelope(5, "r1", "token", {"lane": "a", "text": "après la fin"}),
        ]
    )

    def handle(route, request):
        requests.append(request.url)
        sse_response(route, body)

    core.route("**/api/runs/r1/events**", handle)
    result = core.evaluate(RUN_STREAM, "r1")
    assert result["seen"] == ["run_started:1", "token:2", "run_ended:4"]
    assert result["statuses"] == ["open", "closed"]
    assert result["runs"] == {}  # le run terminé n'est plus suivi
    assert len(requests) == 1  # fermé à \run_ended\ : pas de reconnexion


def test_a_dropped_run_stream_resumes_after_the_last_seq(core):
    urls: list[str] = []

    def handle(route, request):
        urls.append(request.url.split("127.0.0.1:")[1].split("/", 1)[1])
        if len(urls) == 1:  # coupé après deux événements, sans \run_ended\
            sse_response(route, envelope(1, "r2", "run_started") + envelope(2, "r2", "token"))
        else:
            sse_response(
                route,
                envelope(2, "r2", "token")  # rejoué par prudence : écarté
                + envelope(3, "r2", "token")
                + envelope(4, "r2", "run_ended", {"status": "done"}),
            )

    core.route("**/api/runs/r2/events**", handle)
    result = core.evaluate(RUN_STREAM, "r2")
    assert urls == ["api/runs/r2/events", "api/runs/r2/events?after=2"]
    assert result["seen"] == ["run_started:1", "token:2", "token:3", "run_ended:4"]
    assert result["statuses"] == ["open", "retrying", "open", "closed"]


def test_a_204_closes_the_run_stream_and_an_unknown_run_gives_up(core_lenient):
    core_lenient.route(
        "**/api/runs/fini/events**", lambda route, request: route.fulfill(status=204)
    )
    assert core_lenient.evaluate(RUN_STREAM, "fini")["statuses"] == ["closed"]
    # Run inconnu du vrai serveur : 404, inutile de réessayer.
    assert core_lenient.evaluate(RUN_STREAM, "inconnu")["statuses"] == ["failed"]


def test_an_inherited_property_is_an_unknown_type(core):
    core.route(
        "**/api/runs/r3/events**",
        lambda route, request: sse_response(
            route,
            envelope(1, "r3", "inherited")
            + envelope(2, "r3", "constructor")
            + envelope(3, "r3", "run_ended", {"status": "done"}),
        ),
    )
    result = core.evaluate(
        """async () => {
            const { connectRun } = await import('/static/core/sse.js');
            const calls = [];
            const handlers = Object.create({ inherited: () => calls.push('inherited') });
            handlers.run_ended = () => calls.push('run_ended');
            await new Promise((resolve) => connectRun('r3', handlers, ({ status }) => {
                if (status === 'closed' || status === 'failed') resolve();
            }));
            return calls;
        }"""
    )
    assert result == ["run_ended"]


def test_a_silent_stream_counts_as_a_failure(core_lenient):
    # Le serveur accepte la requête et se tait : sans chien de garde, la page attendrait sans fin.
    core_lenient.route("**/api/silence", lambda route, request: None)
    statuses = core_lenient.evaluate(
        """async () => {
            const { connectStream } = await import('/static/core/sse.js');
            const statuses = [];
            await new Promise((resolve) => connectStream({
                url: '/api/silence', idleMs: 300, maxAttempts: 2, backoffMs: [50],
                onStatus: ({ status }) => {
                    statuses.push(status);
                    if (status === 'failed') resolve();
                },
            }));
            return statuses;
        }"""
    )
    assert statuses == ["retrying", "failed"]


def test_a_scripted_run_of_the_real_server_streams_to_run_ended(core, server):
    started = core.request.post(
        f"{server.base_url}/api/test/runs",
        data={"script": [{"text": "Bon"}, {"text": "jour"}], "model": "fake:1b"},
    ).json()
    result = core.evaluate(RUN_STREAM, started["run_id"])
    assert result["statuses"][-1] == "closed"
    kinds = [item.split(":")[0] for item in result["seen"]]
    assert kinds[0] == "run_started" and kinds[-1] == "run_ended" and "token" in kinds
    seqs = [int(item.split(":")[1]) for item in result["seen"]]
    assert seqs == sorted(set(seqs))  # croissants, sans doublon


def test_the_system_stream_state_has_the_documented_shape(core):
    state = core.evaluate(
        """async () => {
            const { connectSystem } = await import('/static/core/sse.js');
            return await new Promise((resolve) => {
                const stream = connectSystem({ system_state: (data) => { stream.close(); resolve(data); } });
            });
        }"""
    )
    assert {"ollama", "cpu_percent", "memory", "models_loaded", "runs_active"} <= set(state)
    assert state["ollama"]["up"] is False  # Ollama arrêté (port fermé)


# --- core/store.js et core/api.js -------------------------------------------------------------


def test_the_store_notifies_only_selected_changes_and_cloud_defaults_to_off(core):
    result = core.evaluate(
        """async () => {
            const { createStore, store } = await import('/static/core/store.js');
            const local = createStore({ a: 1, b: 1 });
            const seen = [];
            local.select((s) => s.a, (a) => seen.push(a));
            local.set({ b: 2 });
            local.set({ a: 2 });
            local.set((s) => ({ a: s.a }));
            return { seen, cloud: store.get().allowCloud };
        }"""
    )
    assert result == {"seen": [1, 2], "cloud": False}


def test_an_api_error_keeps_the_envelope_of_the_server(core_lenient):
    error = core_lenient.evaluate(
        """async () => {
            const { request, ApiError } = await import('/static/core/api.js');
            try {
                await request('/api/test/runs', { method: 'POST', body: { model: 'inconnu:1b' } });
            } catch (error) {
                return { api: error instanceof ApiError, status: error.status, envelope: error.envelope };
            }
        }"""
    )
    assert error["api"] and error["status"] == 404
    assert set(error["envelope"]) == {"code", "message", "action", "detail"}
    assert error["envelope"]["code"] == "not_found"
