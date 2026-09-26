import sys; sys.path.insert(0, sys.argv[1]); SH = sys.argv[1] + "/shots"
from common import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1400, "height": 1000})
    page.goto(f"{BASE}/RAG_Knowledge"); settle(page)
    print("sidebar before:", page.locator('[data-testid="stSidebar"]').inner_text()[:400].replace("\n"," | "))
    page.get_by_role("button", name="Commencer l'ingestion").click(); page.wait_for_timeout(1500)
    dlg = page.get_by_role("dialog")
    dlg.locator('input[type="file"]').set_input_files(sys.argv[1] + "/doc_test_rag.txt"); page.wait_for_timeout(2000)
    print("dialog:", dlg.inner_text()[:400].replace("\n"," | "))
    dlg.get_by_role("button", name="Indexer maintenant").click()
    page.wait_for_timeout(1200); page.screenshot(path=f"{SH}/rag_upload_success.png")
    settle(page); page.wait_for_timeout(2000)
    report(page, "RAG after upload")
    print("sidebar after:", page.locator('[data-testid="stSidebar"]').inner_text()[:400].replace("\n"," | "))
    print("main has empty-state:", page.get_by_text("Votre base de connaissances est vide").count())
    page.screenshot(path=f"{SH}/rag_after_upload.png", full_page=True)
