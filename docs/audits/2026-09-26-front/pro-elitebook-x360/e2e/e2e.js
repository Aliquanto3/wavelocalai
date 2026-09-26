// Parcours fonctionnel de l'app Streamlit, en mode local strict (aucun appel cloud).
// Prérequis : app lancée sur http://localhost:8501, Ollama démarré, modèles ci-dessous installés.
//
//   npm install            (PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 : on utilise le Chrome installé)
//   node e2e.js [--skip-arena] [--with-upload] [--only=1-socle,8-agent-solo]
//
// Chaque étape vérifie le comportement attendu. Au 2026-09-26, les étapes 1, 7 et 8 échouent
// à cause des défauts F-01, F-03 et F-04 du rapport ; elles doivent passer une fois corrigés.
//
// --with-upload est opt-in : une fois F-03 corrigé, l'étape indexera vraiment sample_doc.md
// dans la collection Chroma locale.

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const h = require('./helpers');

const URL = process.env.APP_URL || 'http://localhost:8501/';
const MODEL_CHAT = process.env.MODEL_CHAT || 'Gemma 3 1B';
const MODEL_SMALL = process.env.MODEL_SMALL || 'Granite 4.0 350M';
const MODEL_AGENT = process.env.MODEL_AGENT || 'Qwen 3.5 0.8B';
const REPO = path.resolve(__dirname, '../../../../..');
const OUT = path.join(__dirname, 'out');

const args = process.argv.slice(2);
const only = (args.find(a => a.startsWith('--only=')) || '').slice(7).split(',').filter(Boolean);
const flat = s => (s || '').replace(/\s+/g, ' ').trim();
const main = page => page.locator('[data-testid="stMainBlockContainer"]');
const sidebar = page => page.locator('[data-testid="stSidebar"]');
const results = [];

class Expectation extends Error {}
const expect = (cond, msg) => { if (!cond) throw new Expectation(msg); };

async function step(page, name, fn, { ignore } = {}) {
  if (only.length && !only.includes(name)) return;
  const t0 = Date.now();
  const r = { name };
  try {
    r.note = (await fn()) || '';
    const errs = (await h.errors(page)).filter(e => !(ignore && ignore.test(e)));
    r.ok = errs.length === 0;
    if (errs.length) r.note += ` | erreurs UI : ${errs.join(' | ')}`;
  } catch (e) {
    r.ok = false;
    r.note = (e instanceof Expectation ? 'ATTENDU NON RESPECTÉ : ' : 'EXCEPTION : ') + e.message.split('\n')[0];
  }
  r.s = ((Date.now() - t0) / 1000).toFixed(1);
  results.push(r);
  console.log(`${r.ok ? 'OK' : 'KO'}  ${name} (${r.s} s) ${r.note}`);
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
}

function lastCsvEmissionKg(file) {
  const lines = fs.readFileSync(file, 'utf8').trim().split(/\r?\n/);
  const head = lines[0].split(',');
  const row = lines.at(-1).split(',');
  return { kg: parseFloat(row[head.indexOf('emissions')]), project: row[head.indexOf('project_name')] };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  // Fenêtre haute : le contenu défile dans un conteneur interne, fullPage ne le capture pas.
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 2400 } })).newPage();
  await page.goto(URL); await h.idle(page);

  await step(page, '0-accueil-local', async () => {
    await page.getByText('Autoriser les API Cloud').click(); await h.idle(page);
    const privacy = flat(await page.locator('[data-testid="stMetric"]').nth(3).innerText());
    expect(/100% Local/.test(privacy), `indicateur de confidentialité = "${privacy}"`);
    return privacy;
  });

  await step(page, '1-socle', async () => {
    await h.nav(page, 'Socle Hardware');
    await page.getByRole('button', { name: /Arrêter & Sauvegarder/ }).click(); await h.idle(page);
    const shown = flat(await main(page).getByText(/kgCO₂/).first().innerText());
    const uiKg = parseFloat(shown.replace(',', '.'));
    await page.getByRole('button', { name: /Reprendre le tracking/ }).click(); await h.idle(page);
    // Le suivi de session écrit dans data/logs/emissions.csv (voir F-02 pour le fichier lu par le graphique).
    const csv = lastCsvEmissionKg(path.join(REPO, 'data/logs/emissions.csv'));
    const note = `UI "${shown}" / CSV ${csv.kg} kg (${csv.project})`;
    expect(Math.abs(uiKg - csv.kg) <= Math.max(1e-6, csv.kg * 0.05), `F-01 : ${note}`);
    return note;
  });

  await step(page, '2-chat', async () => {
    await h.nav(page, 'Inference Arena');
    await h.choose(page, main(page).locator('[data-testid="stSelectbox"]').first(), MODEL_CHAT);
    await page.getByPlaceholder('Votre message...').fill('Donne en une phrase la capitale de la France.');
    await page.keyboard.press('Enter'); await h.idle(page);
    const msgs = await main(page).locator('[data-testid="stChatMessage"]').allInnerTexts();
    expect(msgs.length >= 2 && /Paris/i.test(msgs.at(-1)), `réponse : "${flat(msgs.at(-1))}"`);
    return flat(msgs.at(-1)).slice(0, 160);
  });

  await step(page, '3-lab', async () => {
    await page.getByRole('tab', { name: /Labo de Tests/ }).click(); await h.idle(page);
    const panel = page.locator('[role="tabpanel"]:visible');
    await h.choose(page, panel.locator('[data-testid="stSelectbox"]').first(), MODEL_CHAT);
    await page.getByRole('button', { name: /Lancer le Test/ }).click(); await h.idle(page);
    const m = (await panel.locator('[data-testid="stMetric"]').allInnerTexts()).map(flat);
    expect(m.length === 4, `${m.length} métriques affichées`);
    return m.join(' / ');
  });

  if (!args.includes('--skip-arena')) {
    await step(page, '4-arena', async () => {
      await page.getByRole('tab', { name: /Arena/ }).click(); await h.idle(page);
      const panel = page.locator('[role="tabpanel"]:visible');
      const ms = panel.locator('[data-testid="stMultiSelect"]').first();
      const clear = ms.locator('[aria-label="Clear all"], [title="Clear all"]');
      if (await clear.count()) { await clear.first().click(); await h.idle(page); }
      for (const m of [MODEL_SMALL, MODEL_CHAT]) {
        await ms.click(); await page.keyboard.type(m);
        await page.locator('[role="option"]', { hasText: m }).first().click(); await h.idle(page);
      }
      await page.keyboard.press('Escape');
      await panel.getByText('Options du Juge').click(); await h.idle(page);
      await h.choose(page, panel.locator('[data-testid="stSelectbox"]').first(), MODEL_CHAT);
      await page.getByRole('button', { name: /FIGHT/ }).click(); await h.idle(page);
      const verdict = await panel.getByText('Le Verdict').count();
      const chart = await panel.locator('[data-testid="stPlotlyChart"]').count();
      const m = (await panel.locator('[data-testid="stMetric"]').allInnerTexts()).map(flat);
      expect(verdict === 1 && chart === 1, `verdict=${verdict} graphique=${chart}`);
      return m.join(' / ');
    });
  }

  await step(page, '5-gestion-modeles', async () => {
    await page.getByRole('tab', { name: /Gestion Modèles/ }).click(); await h.idle(page);
    const df = await page.locator('[role="tabpanel"]:visible [data-testid="stDataFrame"]').count();
    await page.getByRole('button', { name: /Ajouter un Modèle/i }).click(); await h.idle(page);
    const dialog = await page.locator('[role="dialog"]').count();
    await page.keyboard.press('Escape'); await h.idle(page);
    expect(df === 1 && dialog === 1, `tableau=${df} fenêtre=${dialog}`);
    return 'tableau et fenêtre d\'installation OK';
  });

  await step(page, '6-rag-chat', async () => {
    await h.nav(page, 'RAG Knowledge');
    const chunks = flat(await sidebar(page).getByText(/chunks indexés/).innerText());
    await h.choose(page, main(page).locator('[data-testid="stSelectbox"]').first(), MODEL_CHAT);
    await page.getByPlaceholder('Posez une question à vos documents...').fill('De quoi parlent ces documents ? Réponds en deux phrases.');
    await page.keyboard.press('Enter'); await h.idle(page);
    await page.waitForTimeout(1500);
    const sources = flat(await main(page).getByText(/Sources utilisées/).first().innerText().catch(() => ''));
    expect(sources, 'aucune source affichée');
    return `${chunks} ; ${sources}`;
  });

  if (args.includes('--with-upload')) {
    await step(page, '7-rag-upload', async () => {
      const before = parseInt((await sidebar(page).getByText(/chunks indexés/).innerText()).match(/\d+/)[0], 10);
      await page.getByRole('button', { name: /Gérer les Documents/ }).first().click(); await h.idle(page);
      await page.locator('[role="dialog"] input[type="file"]').setInputFiles(path.join(__dirname, 'sample_doc.md')); await h.idle(page);
      await page.getByRole('button', { name: /Indexer maintenant/ }).click(); await h.idle(page);
      await page.keyboard.press('Escape'); await h.idle(page);
      const after = parseInt((await sidebar(page).getByText(/chunks indexés/).innerText()).match(/\d+/)[0], 10);
      expect(after > before, `F-03 : ${before} chunks avant, ${after} après l'indexation annoncée réussie`);
      return `${before} -> ${after} chunks`;
    });
  }

  await step(page, '8-agent-solo', async () => {
    await h.nav(page, 'Agent Lab');
    await h.choose(page, main(page).locator('[data-testid="stSelectbox"]').first(), MODEL_AGENT);
    await page.getByPlaceholder('Votre instruction...').fill("Quelle heure est-il ? Utilise l'outil Time.");
    await page.keyboard.press('Enter'); await h.idle(page);
    // Garde-fou de l'app (st.warning) : il refuse de lancer l'agent si la RAM libre ne suffit pas.
    const ramGuard = flat(await main(page).getByText(/RAM Insuffisante/).first().innerText().catch(() => ''));
    expect(!ramGuard, `non testable ici, garde-fou RAM : "${ramGuard}" (libérer de la RAM ou choisir un MODEL_AGENT plus petit)`);
    const answered = /Terminé/.test(await main(page).innerText());
    // N'importe quel rerun doit conserver la conversation : ici, aller-retour sur le choix d'architecture.
    await sidebar(page).getByText('Crew (Multi-Agent)').click(); await h.idle(page);
    await sidebar(page).getByText('Solo (LangGraph)').click(); await h.idle(page);
    const msgs = (await main(page).locator('[data-testid="stChatMessage"]').allInnerTexts()).map(flat);
    const kept = msgs.some(m => /\d{1,2}:\d{2}/.test(m) && !/Résultat de l'outil/.test(m));
    expect(answered && kept, `F-04 : réponse affichée=${answered}, conservée après rerun=${kept} ; messages : ${msgs.map(m => `«${m.slice(0, 80)}»`).join(' ')}`);
    return `${msgs.length} messages conservés`;
  });

  await step(page, '9-crew-rendu', async () => {
    await sidebar(page).getByText('Crew (Multi-Agent)').click(); await h.idle(page);
    const gv = await main(page).locator('[data-testid="stGraphVizChart"]').count();
    const btn = (await main(page).getByRole('button', { name: /Lancer|Risqué/ }).allInnerTexts()).map(flat);
    expect(gv === 1, 'schéma d\'équipe absent');
    // L'avertissement RAM est un st.error légitime quand la machine manque de mémoire : il est rapporté, pas compté.
    const ram = flat(await main(page).getByText(/requiert ~.* de RAM/).first().innerText().catch(() => ''));
    return `schéma OK ; bouton "${btn.join(' | ')}"${ram ? ` ; ${ram}` : ''}`;
  }, { ignore: /requiert ~.* de RAM/ });

  console.log('\n===== RÉSUMÉ =====');
  for (const r of results) console.log(`${r.ok ? 'OK' : 'KO'}  ${r.name} (${r.s} s)`);
  await browser.close();
  process.exit(results.every(r => r.ok) ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
