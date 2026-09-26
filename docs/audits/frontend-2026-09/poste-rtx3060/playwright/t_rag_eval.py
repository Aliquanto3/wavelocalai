import sys; sys.path.insert(0, sys.argv[1]); SH = sys.argv[1] + "/shots"
from common import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1400, "height": 1100})
    page.goto(f"{BASE}/RAG_Knowledge"); settle(page)
    page.get_by_role("tab").nth(1).click(); page.wait_for_timeout(1500)
    panel = page.locator('[role="tabpanel"]:visible').first
    ms = panel.locator('[data-testid="stMultiSelect"]').first
    ms.locator("input").click()
    for _ in range(4): page.keyboard.press("Backspace"); page.wait_for_timeout(300)
    ms.locator("input").fill("Gemma 3 1B"); page.wait_for_timeout(600)
    page.locator('[role="option"]', has_text="Gemma 3 1B").first.click(); page.wait_for_timeout(800)
    page.keyboard.press("Escape"); settle(page)
    print("candidates:", panel.locator('[data-testid="stMultiSelect"]').first.inner_text().replace("\n"," | "))
    print("judge:", select_option(page, 0, "Llama 3.2 3B", scope=panel)); settle(page)
    panel.locator("textarea").first.fill("Quel est le budget du projet Hirondelle ?")
    page.get_by_role("button", name="Lancer le Benchmark").click()
    d = settle(page, 500); print(f"eval done in {d:.0f}s")
    report(page, "RAG eval run"); page.screenshot(path=f"{SH}/rag_eval_run.png", full_page=True)
    print("  eval tail:", page.locator('[role="tabpanel"]:visible').first.inner_text()[-1200:].replace("\n"," | "))
