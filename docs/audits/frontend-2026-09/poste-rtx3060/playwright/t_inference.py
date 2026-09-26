import sys, time; sys.path.insert(0, sys.argv[1]); SH = sys.argv[1] + "/shots"
from common import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1400, "height": 1100})
    errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"{BASE}/Inference_Arena"); settle(page)
    tabs = page.get_by_role("tab")
    print("tabs:", [tabs.nth(i).inner_text() for i in range(tabs.count())])

    if 'chat' in sys.argv:  # le chat a été validé au premier passage ; ajouter 'chat' pour le rejouer
        # 1. Chat libre
        print("chat model:", select_option(page, 0, "Gemma 3 1B")); settle(page)
        page.get_by_placeholder("Votre message...").fill("Quelle est la capitale de la France ? Réponds en une phrase.")
        page.keyboard.press("Enter")
        d = settle(page, 240)
        msgs = page.locator('[data-testid="stChatMessage"]')
        print(f"chat: {msgs.count()} messages after {d:.0f}s")
        if msgs.count(): print("  last:", msgs.last.inner_text()[:400].replace("\n", " | "))
        report(page, "Chat"); page.screenshot(path=f"{SH}/inf_chat.png", full_page=True)

    # 2. Labo de tests
    tabs.nth(1).click(); page.wait_for_timeout(1000)
    panel = page.locator('[role="tabpanel"]:visible').first
    print("lab model:", select_option(page, 0, "Gemma 3 1B", scope=panel)); settle(page)
    page.get_by_role("button", name="Lancer le Test").click()
    d = settle(page, 240); print(f"lab done in {d:.0f}s")
    report(page, "Lab"); page.screenshot(path=f"{SH}/inf_lab.png", full_page=True)
    print("  lab panel:", page.locator('[role="tabpanel"]:visible').first.inner_text()[-700:].replace("\n", " | "))

    # 3. Arena
    tabs.nth(2).click(); page.wait_for_timeout(1000)
    panel = page.locator('[role="tabpanel"]:visible').first
    ms = panel.locator('[data-testid="stMultiSelect"]')
    # clear defaults
    clear = ms.locator('[aria-label*="Clear all"], [title*="Clear all"], svg[role="button"]')
    for _ in range(5):
        chips = ms.locator('[data-baseweb="tag"] [role="presentation"], [data-baseweb="tag"] span[role="button"]')
        if chips.count() == 0: break
        chips.first.click(); page.wait_for_timeout(700)
    for name in ["Gemma 3 1B", "Qwen 3.5 0.8B"]:
        ms.locator("input").click(); ms.locator("input").fill(name.split()[0] + " " + name.split()[1]); page.wait_for_timeout(500)
        opts = page.locator('[role="option"]'); names = [opts.nth(i).inner_text() for i in range(opts.count())]
        hit = [i for i, n in enumerate(names) if name.lower() in n.lower()]
        print(f"  arena search {name}: {names[:6]}")
        if hit: opts.nth(hit[0]).click(); page.wait_for_timeout(800)
        page.keyboard.press("Escape")
    settle(page)
    print("  arena selected:", [t.inner_text() for t in ms.locator('[data-baseweb="tag"]').all()])
    page.get_by_role("button", name="FIGHT").click()
    d = settle(page, 400); print(f"arena done in {d:.0f}s")
    report(page, "Arena"); page.screenshot(path=f"{SH}/inf_arena.png", full_page=True)
    print("  arena panel tail:", page.locator('[role="tabpanel"]:visible').first.inner_text()[-900:].replace("\n", " | "))

    # 4. Gestion modèles (lecture seule)
    tabs.nth(3).click(); page.wait_for_timeout(1500)
    report(page, "Manager"); page.screenshot(path=f"{SH}/inf_manager.png", full_page=True)
    print("  manager head:", page.locator('[role="tabpanel"]:visible').first.inner_text()[:600].replace("\n", " | "))
    print("PAGE ERRORS:", errs)
