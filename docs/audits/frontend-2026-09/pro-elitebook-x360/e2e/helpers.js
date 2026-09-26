// Helpers Playwright pour piloter l'app Streamlit (v1.52).

// Streamlit affiche une icône « Running... » tant que le script de la page tourne.
async function idle(page, timeout = 900000) {
  await page.waitForTimeout(1000);
  await page.waitForFunction(
    () => !document.querySelector('[data-testid="stStatusWidgetRunningIcon"]'),
    null,
    { timeout, polling: 500 },
  );
  await page.waitForTimeout(800);
}

// Exceptions Python et st.error visibles ; les éléments vides sont ignorés.
async function errors(page) {
  return page.$$eval('[data-testid="stException"], [data-testid="stAlertContentError"]', els =>
    els.map(e => e.innerText.replace(/\s+/g, ' ').trim().slice(0, 400)).filter(Boolean));
}

// La navigation par la barre latérale garde la session (st.session_state) ; page.goto en ouvre une nouvelle.
// On attend l'URL de la page, puis la fin du script et des éléments périmés de la page précédente :
// les pages lourdes (Agent Lab) mettent plus d'une seconde à démarrer.
async function nav(page, name) {
  const slug = name.replace(/ /g, '_');
  await page.locator('[data-testid="stSidebarNav"] a', { hasText: name }).first().click();
  await page.waitForURL(u => u.pathname.endsWith('/' + slug));
  await idle(page);
  await page.waitForFunction(() => !document.querySelector('[data-stale="true"]'), null, { timeout: 120000 });
  await idle(page);
}

// Les listes d'options sont virtualisées : on tape pour filtrer, puis on clique la correspondance.
async function choose(page, selectbox, text) {
  await selectbox.click();
  await page.keyboard.type(text);
  await page.locator('[role="option"]', { hasText: text }).first().click();
  await idle(page);
}

module.exports = { idle, errors, nav, choose };
