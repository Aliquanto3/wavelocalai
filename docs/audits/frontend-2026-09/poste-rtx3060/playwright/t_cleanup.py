import sys; sys.path.insert(0, sys.argv[1]); SH = sys.argv[1] + "/shots"
from common import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1400, "height": 1000})
    page.goto(f"{BASE}/RAG_Knowledge"); settle(page)
    print("before:", page.get_by_text("chunks indexés").inner_text())
    page.get_by_role("button", name="Gérer les Documents").click(); page.wait_for_timeout(1500)
    page.get_by_role("dialog").get_by_role("button", name="Tout supprimer").click(); settle(page); page.wait_for_timeout(1500)
    print("after:", page.get_by_text("chunks indexés").inner_text(), "| empty-state:", page.get_by_text("Votre base de connaissances est vide").count())
    report(page, "RAG reset")
    page.goto(f"{BASE}/Socle_Hardware"); settle(page)
    page.get_by_role("button", name="Rafraîchir").click(); settle(page)
    report(page, "Hardware refresh")
