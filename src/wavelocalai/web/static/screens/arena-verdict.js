// Verdict local/cloud de l'Arène (story 3.5, AD-5, AD-10, AD-20).
//
//   const verdict = verdictView(uid, nameOf);   // `nameOf(tag)` : le nom lisible d'un modèle
//   verdict.el  verdict.load(runId)  verdict.reset()
//
// Le serveur calcule le verdict à la fin de la comparaison et le rend dans l'instantané du run
// (`GET /api/runs/{id}`, champ `verdict`) : cette vue le lit à `run_ended` et à la réouverture (le
// rejeu finit aussi par `run_ended`), et n'en calcule rien. Elle choisit la phrase selon `leader`,
// met en forme montants, points et CO2, et affiche la date de la table de prix avec le coût. Sans
// verdict (pas de modèle cloud noté, run arrêté), la section ne paraît pas. Un coût inconnu dit la
// raison du serveur, jamais 0 ni « — ».

import { api } from "../core/api.js";
import { element } from "../core/dom.js";
import { co2Group, formatDate, formatInteger, formatMoney, formatNumber, formatScore } from "../core/format.js";
import { t } from "../core/i18n.js";

function co2Text(co2, group) {
  if (co2 === null || co2 === undefined) return t("arena.results.not_measured");
  if (typeof co2.mg !== "number") return t("components.thread.co2_unmeasurable");
  const value = group.format(co2.mg);
  return co2.estimated ? t("components.thread.co2_estimated", { value }) : value;
}

function scoreLine(verdict, name) {
  const { local, cloud } = verdict;
  const vars = {
    local: name(local.model),
    cloud: name(cloud.model),
    localScore: formatScore(local.score),
    cloudScore: formatScore(cloud.score),
    gap: t(verdict.score_gap === 1 ? "arena.verdict.points_one" : "arena.verdict.points_many", {
      count: formatNumber(verdict.score_gap),
    }),
  };
  return t(`arena.verdict.score_${verdict.leader}`, vars);
}

function priceNote(table) {
  const lines = [];
  if (table.retrieved_at) {
    lines.push(t("arena.verdict.price_date", { date: formatDate(table.retrieved_at) }));
    if (table.source) lines.push(t("arena.verdict.price_source", { source: table.source }));
  } else {
    lines.push(t("arena.verdict.price_no_date"));
  }
  return lines;
}

function costCell(verdict, name) {
  const { local, cloud, price_table: table } = verdict;
  const known = typeof cloud.cost.amount === "number";
  const cell = element("dd");
  cell.append(
    t("arena.verdict.cost_text", {
      local: formatMoney(local.cost.amount, local.cost.currency),
      cloud: known ? formatMoney(cloud.cost.amount, cloud.cost.currency) : t("arena.verdict.cost_unknown"),
      name: name(cloud.model),
    }),
  );
  if (!known) cell.append(" ", cloud.cost.reason ?? "");
  const note = element("p", "help arena-verdict-note");
  note.append(...priceNote(table).flatMap((line, index) => (index ? [element("br"), line] : [line])));
  cell.append(note);
  return cell;
}

export function verdictView(uid, nameOf) {
  const el = element("section", "arena-results-block arena-verdict");
  el.hidden = true;
  const title = element("h2", "arena-results-title", t("arena.verdict.title"));
  title.id = `${uid}-verdict-title`;
  el.setAttribute("aria-labelledby", title.id);
  const help = element("p", "help", t("arena.verdict.help"));
  const body = element("div", "arena-verdict-body");
  el.append(title, help, body);

  let ticket = 0; // une lecture tardive d'une comparaison précédente n'écrase pas la courante

  function render(verdict) {
    const name = (tag) => nameOf(tag) ?? tag;
    const group = co2Group([verdict.local.co2?.mg, verdict.cloud.co2?.mg].filter((mg) => typeof mg === "number"));
    const locals = verdict.data_on_device.count;
    const data = verdict.data_on_device.judge_off_device
      ? t("arena.verdict.data_judge_cloud")
      : t(locals === 1 ? "arena.verdict.data_one" : "arena.verdict.data_many", { count: formatInteger(locals) });
    const list = element("dl", "arena-verdict-list");
    const row = (label, value) => {
      const item = element("div", "arena-verdict-row");
      item.append(element("dt", "", label), value instanceof Node ? value : element("dd", "", value));
      list.append(item);
    };
    row(t("arena.verdict.score"), scoreLine(verdict, name));
    row(t("arena.verdict.cost", { requests: formatInteger(verdict.requests) }), costCell(verdict, name));
    row(
      t("arena.verdict.co2"),
      t("arena.verdict.co2_text", {
        local: co2Text(verdict.local.co2, group),
        cloud: co2Text(verdict.cloud.co2, group),
        name: name(verdict.cloud.model),
      }),
    );
    row(t("arena.verdict.data"), data);
    body.replaceChildren(list);
    help.hidden = false;
    el.hidden = false;
  }

  function reset() {
    ticket += 1;
    el.hidden = true;
    body.replaceChildren();
  }

  return {
    el,
    reset,
    // Lit l'instantané du run terminé ; sans `verdict`, la section reste cachée.
    async load(runId) {
      const mine = ++ticket;
      let snapshot;
      try {
        snapshot = await api.run(runId);
      } catch {
        if (mine !== ticket) return;
        body.replaceChildren(element("p", "help arena-verdict-unavailable", t("arena.verdict.unavailable")));
        help.hidden = true;
        el.hidden = false;
        return;
      }
      if (mine !== ticket) return;
      if (snapshot?.verdict) render(snapshot.verdict);
      else reset();
    },
  };
}
