import sys
from playwright.sync_api import sync_playwright

SHOTS = sys.argv[1]
BASE = "http://localhost:8501"
PAGES = ["", "Socle_Hardware", "Inference_Arena", "RAG_Knowledge", "Agent_Lab"]

def settle(page, timeout=90000):
    page.wait_for_selector('[data-testid="stApp"]', timeout=timeout)
    page.wait_for_timeout(1500)
    # wait while Streamlit is "running"
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] [data-testid=\"stStatusWidgetRunningIcon\"]')", timeout=timeout)
    page.wait_for_timeout(1000)

def report(page, label):
    exc = page.locator('[data-testid="stException"]')
    errs = page.locator('[data-testid="stAlertContentError"]')
    warns = page.locator('[data-testid="stAlertContentWarning"]')
    print(f"--- {label}: exceptions={exc.count()} errors={errs.count()} warnings={warns.count()}")
    for i in range(exc.count()):
        print("  EXC:", exc.nth(i).inner_text()[:800].replace("\n", " | "))
    for i in range(errs.count()):
        print("  ERR:", errs.nth(i).inner_text()[:300].replace("\n", " | "))
    for i in range(warns.count()):
        print("  WARN:", warns.nth(i).inner_text()[:200].replace("\n", " | "))

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1400, "height": 1000})
    console = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    for name in PAGES:
        page.goto(f"{BASE}/{name}")
        settle(page)
        label = name or "Accueil"
        report(page, label)
        page.screenshot(path=f"{SHOTS}/{label}.png", full_page=True)
        tabs = page.locator('[data-baseweb="tab"]')
        n = tabs.count()
        if n:
            print(f"  tabs: {[tabs.nth(i).inner_text() for i in range(n)]}")
        for i in range(1, n):
            tabs.nth(i).click()
            page.wait_for_timeout(1500)
            report(page, f"{label} / tab {i}")
            page.screenshot(path=f"{SHOTS}/{label}_tab{i}.png", full_page=True)
    print("CONSOLE ERRORS:", console[:10])
    b.close()
