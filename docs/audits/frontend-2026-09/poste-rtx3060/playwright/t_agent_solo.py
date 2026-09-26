import sys; sys.path.insert(0, sys.argv[1]); SH = sys.argv[1] + "/shots"
from common import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1400, "height": 1100})
    page.goto(f"{BASE}/Agent_Lab"); settle(page)
    print("model:", select_option(page, 0, "Qwen 3.5 4B")); settle(page)
    page.get_by_placeholder("Votre instruction...").fill("Combien font 1234 multiplié par 5678 ? Utilise la calculatrice.")
    page.keyboard.press("Enter"); d = settle(page, 400)
    msgs = page.locator('[data-testid="stChatMessage"]')
    print(f"solo: {msgs.count()} msgs in {d:.0f}s")
    if msgs.count(): print("  last:", msgs.last.inner_text()[:900].replace("\n"," | "))
    report(page, "Agent solo calc"); page.screenshot(path=f"{SH}/agent_solo_calc.png", full_page=True)
    # quick action
    page.get_by_role("button", name="Reset Chat").click(); settle(page)
    btn = page.get_by_role("button", name="Lancer l'audit")
    if btn.count():
        btn.click(); d = settle(page, 400)
        msgs = page.locator('[data-testid="stChatMessage"]')
        print(f"audit: {msgs.count()} msgs in {d:.0f}s")
        if msgs.count(): print("  last:", msgs.last.inner_text()[:900].replace("\n"," | "))
        report(page, "Agent solo audit"); page.screenshot(path=f"{SH}/agent_solo_audit.png", full_page=True)
    else:
        print("no audit button after reset")
