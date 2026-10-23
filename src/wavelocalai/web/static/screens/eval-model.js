// Données d'une évaluation (story 7.3, AD-20) : ce que les événements du flux et l'instantané du run
// ont publié, rangé pour l'écran. Aucun DOM ici, et aucune note n'est calculée : le serveur donne
// chaque note (`eval_metric`) et chaque moyenne (`aggregate`, `summary`) ; ce module les range et
// dit seulement dans quel état se trouve chaque étape (à partir des statuts de lane).
//
//   const model = createModel();
//   model.apply(type, data)            un événement du flux (`run_started`, `eval_questions`, `judge`,
//                                      `lane_status`, `sources`, `eval_answer`, `metrics`, `eval_metric`,
//                                      `run_ended`)
//   model.applySnapshot(snapshot)      l'instantané `GET /api/runs/{id}` : notes, résumé, `partial`,
//                                      `missing` ; il règle ce que le flux a dit en cours de route
//   model.steps()  model.cell(lane, metric)  model.detail(lane, metric)  model.measures(lane)
//
// Un inconnu n'est jamais un 0 : une note absente est « en cours », ou « non évalué » avec sa raison.

export const METRICS = ["faithfulness", "relevance", "context_precision"];
export const STOPPED_REASON = "évaluation arrêtée";
const PAST_ANSWER = new Set(["judging", "done", "failed", "timeout"]);
const NO_ANSWER = new Set(["failed", "timeout"]);

const key = (...parts) => parts.join("|");

// « non évalué : juge indisponible » -> « juge indisponible » (le préfixe est dit par l'écran).
export function bareReason(reason) {
  const text = String(reason ?? "")
    .replace(/^\s*non évalué\s*:\s*/i, "")
    .trim();
  return text;
}

export function createModel() {
  let s = fresh();

  function fresh() {
    return {
      lanes: [],
      laneStatus: new Map(), // tag -> { status, error }
      questions: [],
      sources: new Map(), // question_index -> [source]
      answers: new Map(), // lane|qi -> { text, error }
      notes: new Map(), // lane|qi|metric -> note
      aggregates: new Map(), // lane|metric -> aggregate (le dernier publié)
      measures: new Map(), // lane -> mesures cumulées du serveur (`lane_measures`, `measures`)
      judge: null,
      started: false,
      ended: null, // ok | cancelled | error | interrupted
      partial: false,
      missing: new Map(), // lane|qi|metric -> raison
    };
  }

  const handlers = {
    run_started: (data) => {
      s.started = true;
      if (Array.isArray(data?.models) && s.lanes.length === 0) {
        s.lanes = [...data.models];
        for (const tag of s.lanes) if (!s.laneStatus.has(tag)) s.laneStatus.set(tag, { status: "waiting", error: null });
      }
    },
    eval_questions: (data) => {
      s.questions = Array.isArray(data?.questions) ? [...data.questions] : [];
    },
    judge: (data) => {
      s.judge = data ?? null;
    },
    lane_status: (data) => {
      if (!data?.lane) return;
      if (!s.lanes.includes(data.lane)) s.lanes.push(data.lane);
      s.laneStatus.set(data.lane, { status: data.status, error: data.error ?? null });
    },
    sources: (data) => {
      s.sources.set(Number(data?.question_index ?? 0), Array.isArray(data?.sources) ? data.sources : []);
    },
    eval_answer: (data) => {
      s.answers.set(key(data?.lane, data?.question_index ?? 0), { text: data?.text ?? null, error: data?.error ?? null });
    },
    metrics: (data) => {
      if (data?.lane && data.lane_measures) s.measures.set(data.lane, data.lane_measures);
    },
    eval_metric: (data) => {
      if (!data?.lane || !METRICS.includes(data.metric)) return;
      const qi = data.question_index ?? 0;
      s.notes.set(key(data.lane, qi, data.metric), {
        score: typeof data.score === "number" ? data.score : null,
        reason: data.reason ?? null,
        verdicts: data.verdicts ?? null,
        questions: data.questions ?? null,
        useful: data.useful ?? null,
      });
      if (data.aggregate) s.aggregates.set(key(data.lane, data.metric), data.aggregate);
      if (!s.lanes.includes(data.lane)) s.lanes.push(data.lane);
    },
    run_ended: (data) => {
      s.ended = ["ok", "cancelled", "error"].includes(data?.status) ? data.status : "interrupted";
    },
  };

  const count = () => Math.max(s.questions.length, 1);
  const retrievalDone = () => s.questions.length > 0 && s.sources.size >= s.questions.length;

  return {
    reset() {
      s = fresh();
    },
    apply(type, data) {
      handlers[type]?.(data);
    },
    // L'instantané règle le flux : les notes (même forme que `eval_metric`), les moyennes finales,
    // `partial` et les notes non produites. Une note déjà reçue du flux n'est pas remplacée.
    applySnapshot(snapshot) {
      if (!snapshot || snapshot.kind !== "eval") return;
      const config = snapshot.config ?? {};
      if (!s.questions.length && Array.isArray(config.questions)) s.questions = [...config.questions];
      for (const tag of config.models ?? []) {
        if (!s.lanes.includes(tag)) s.lanes.push(tag);
      }
      for (const row of snapshot.evaluations ?? []) {
        const id = key(row.lane, row.question_index ?? 0, row.metric);
        if (s.notes.has(id)) continue;
        s.notes.set(id, {
          score: typeof row.score === "number" ? row.score : null,
          reason: row.reason ?? null,
          verdicts: row.verdicts ?? null,
          questions: row.questions ?? null,
          useful: row.useful ?? null,
        });
      }
      for (const [lane, byMetric] of Object.entries(snapshot.summary ?? {})) {
        for (const [metric, aggregate] of Object.entries(byMetric ?? {})) s.aggregates.set(key(lane, metric), aggregate);
      }
      for (const [lane, totals] of Object.entries(snapshot.measures ?? {})) {
        if (totals) s.measures.set(lane, totals);
      }
      s.partial = snapshot.partial === true;
      for (const row of snapshot.missing ?? []) {
        s.missing.set(key(row.lane, row.question_index ?? 0, row.metric), bareReason(row.reason) || STOPPED_REASON);
      }
      s.judge ??= snapshot.judge ?? null;
    },
    get state() {
      return s;
    },
    get questionCount() {
      return count();
    },
    get isSet() {
      return s.questions.length > 1;
    },
    get lanes() {
      return s.lanes;
    },
    get partial() {
      return s.partial || ["cancelled", "interrupted", "error"].includes(s.ended);
    },
    get ended() {
      return s.ended;
    },

    // --- Étapes ------------------------------------------------------------------------------
    // Chaque état : pending, current, done, failed, stopped (arrêtée en cours), not_started.
    steps() {
      const lanes = s.lanes.map((tag) => {
        const entry = s.laneStatus.get(tag) ?? { status: "waiting", error: null };
        return { tag, status: entry.status, error: entry.error };
      });
      const total = s.lanes.length * count() * METRICS.length;
      const done = s.notes.size;
      const settled = (reached) => (s.ended === "error" ? "failed" : reached ? "stopped" : "not_started");

      let retrieval;
      if (retrievalDone()) retrieval = "done";
      else if (s.ended) retrieval = s.ended === "error" ? "failed" : "stopped";
      else retrieval = s.started ? "current" : "pending";

      const answered = lanes.length > 0 && lanes.every((lane) => PAST_ANSWER.has(lane.status));
      const started = lanes.some((lane) => lane.status !== "waiting");
      let answers;
      if (answered) answers = lanes.every((lane) => NO_ANSWER.has(lane.status)) ? "failed" : "done";
      else if (s.ended) answers = settled(started);
      else answers = retrievalDone() ? "current" : "pending";

      let scoring;
      if (total > 0 && done >= total) scoring = "done";
      else if (s.ended === "ok") scoring = "done";
      else if (s.ended) scoring = settled(done > 0);
      else scoring = done > 0 || lanes.some((lane) => lane.status === "judging") ? "current" : "pending";

      return { retrieval, answers, scoring, lanes, scoringDone: done, scoringTotal: total };
    },

    // --- Cellules du tableau -----------------------------------------------------------------
    // { kind: "score", aggregate } | { kind: "unevaluated", reason } | { kind: "progress" }
    cell(lane, metric) {
      const aggregate = s.aggregates.get(key(lane, metric)) ?? null;
      if (aggregate && typeof aggregate.score === "number") return { kind: "score", aggregate };
      if (aggregate && !(aggregate.pending > 0 && !s.ended)) return { kind: "unevaluated", reason: this.firstReason(lane, metric), aggregate };
      if (aggregate) return { kind: "progress", aggregate };
      if (s.ended) {
        const missing = [...s.missing.entries()].find(([id]) => id.startsWith(key(lane, "")) && id.endsWith(`|${metric}`));
        return { kind: "unevaluated", reason: missing?.[1] ?? STOPPED_REASON, aggregate: null };
      }
      return { kind: "progress", aggregate: null };
    },
    // La raison du premier « non évalué » de la métrique (sans préfixe), ou celle d'un arrêt.
    firstReason(lane, metric) {
      for (let qi = 0; qi < count(); qi += 1) {
        const note = s.notes.get(key(lane, qi, metric));
        if (note && note.score === null) return bareReason(note.reason) || null;
      }
      return null;
    },

    // --- Détail d'une note -------------------------------------------------------------------
    detail(lane, metric) {
      const entries = [];
      for (let qi = 0; qi < count(); qi += 1) {
        const note = s.notes.get(key(lane, qi, metric)) ?? null;
        const missing = s.missing.get(key(lane, qi, metric)) ?? null;
        entries.push({
          index: qi,
          question: s.questions[qi] ?? "",
          note,
          missing: note ? null : (missing ?? (s.ended ? STOPPED_REASON : null)),
          sources: s.sources.get(qi) ?? [],
          answer: s.answers.get(key(lane, qi)) ?? null,
        });
      }
      return { entries, aggregate: s.aggregates.get(key(lane, metric)) ?? null };
    },

    // --- Mesures du serveur ------------------------------------------------------------------
    // Débit moyen et CO2 total d'un modèle, tels que le serveur les publie (AD-20 : aucun calcul
    // ici) ; `rateOf` / `co2Of` : « n sur m » quand des réponses n'ont pas de mesure.
    measures(lane) {
      const m = s.measures.get(lane) ?? null;
      const co2 = m?.co2 ?? null;
      const total = m?.total ?? count();
      return {
        rate: typeof m?.tps === "number" ? m.tps : null,
        co2mg: typeof co2?.mg === "number" ? co2.mg : null,
        co2estimated: co2?.estimated === true,
        co2unmeasurable: co2?.unmeasurable === true,
        rateOf: m && typeof m.tps === "number" && m.tps_measured < total ? { n: m.tps_measured, total } : null,
        co2Of: co2 && typeof co2.mg === "number" && co2.measured < total ? { n: co2.measured, total } : null,
      };
    },
  };
}
