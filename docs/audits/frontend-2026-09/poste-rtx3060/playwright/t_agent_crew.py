import sys; sys.path.insert(0, sys.argv[1]); SH = sys.argv[1] + "/shots"
from common import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1400, "height": 1200})
    page.goto(f"{BASE}/Agent_Lab"); settle(page)
    page.get_by_text("Crew (Multi-Agent)").click(); settle(page)
    report(page, "Crew initial"); page.screenshot(path=f"{SH}/crew_initial.png", full_page=True)
    # open collapsed expanders in main area
    exps = page.locator('[data-testid="stMain"] [data-testid="stExpander"] summary')
    for i in range(exps.count()):
        exps.nth(i).click(); page.wait_for_timeout(500)
    boxes = page.locator('[data-testid="stSelectbox"]')
    idx = [i for i in range(boxes.count()) if "Modèle IA" in boxes.nth(i).inner_text()]
    print("selectboxes:", [boxes.nth(i).inner_text()[:40].replace("\n"," ") for i in range(boxes.count())])
    if idx:
        print("agent model:", select_option(page, idx[0], "Qwen 3.5 4B")); settle(page)
    page.get_by_role("button", name="Lancer").click()
    d = settle(page, 900); print(f"crew done in {d:.0f}s")
    report(page, "Crew run"); page.screenshot(path=f"{SH}/crew_run.png", full_page=True)
    print("tail:", page.locator('[data-testid="stMain"]').inner_text()[-1500:].replace("\n"," | "))
