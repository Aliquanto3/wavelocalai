import sys; sys.path.insert(0, sys.argv[1]); SH = sys.argv[1] + "/shots"
from common import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1400, "height": 1100})
    page.goto(f"{BASE}/RAG_Knowledge"); settle(page)
    print("sidebar:", page.locator('[data-testid="stSidebar"]').inner_text()[:300].replace("\n"," | "))
    tabs = page.get_by_role("tab"); print("tabs:", [tabs.nth(i).inner_text() for i in range(tabs.count())])
    panel = page.locator('[role="tabpanel"]:visible').first
    print("model:", select_option(page, 0, "Gemma 3 1B", scope=panel)); settle(page)
    page.get_by_placeholder("Posez une question à vos documents...").fill("Quel est le budget du projet Hirondelle et qui en est la cheffe de projet ?")
    page.keyboard.press("Enter"); d = settle(page, 300)
    msgs = page.locator('[data-testid="stChatMessage"]')
    print(f"rag chat: {msgs.count()} msgs in {d:.0f}s")
    if msgs.count(): print("  last:", msgs.last.inner_text()[:700].replace("\n"," | "))
    report(page, "RAG chat"); page.screenshot(path=f"{SH}/rag_chat.png", full_page=True)
    tabs.nth(1).click(); page.wait_for_timeout(1500)
    report(page, "RAG eval"); page.screenshot(path=f"{SH}/rag_eval.png", full_page=True)
    print("  eval panel:", page.locator('[role="tabpanel"]:visible').first.inner_text()[:700].replace("\n"," | "))
