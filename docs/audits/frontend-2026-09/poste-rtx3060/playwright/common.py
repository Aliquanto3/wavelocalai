import time
BASE = "http://localhost:8501"

def running(page):
    return page.locator('[data-testid="stStatusWidgetRunningIcon"], [data-testid="stStatusWidget"] :text("Running")').count() > 0

def settle(page, timeout=300):
    page.wait_for_selector('[data-testid="stApp"]', timeout=90000)
    page.wait_for_timeout(1200)
    t0 = time.time()
    while running(page) and time.time() - t0 < timeout:
        page.wait_for_timeout(500)
    page.wait_for_timeout(800)
    return time.time() - t0

def report(page, label):
    out = []
    for sel, tag in [('[data-testid="stException"]', "EXC"), ('[data-testid="stAlertContentError"]', "ERR"), ('[data-testid="stAlertContentWarning"]', "WARN")]:
        loc = page.locator(sel)
        for i in range(loc.count()):
            out.append(f"  {tag}: " + loc.nth(i).inner_text()[:900].replace("\n", " | "))
    print(f"--- {label}: {'OK' if not out else ''}")
    for o in out: print(o)

def select_option(page, box_index, contains, scope=None):
    root = scope or page
    root.locator('[data-testid="stSelectbox"]').nth(box_index).click()
    page.wait_for_timeout(400)
    page.keyboard.type(contains); page.wait_for_timeout(500)
    opts = page.locator('[role="option"]')
    names = [opts.nth(i).inner_text() for i in range(opts.count())]
    for i, n in enumerate(names):
        if contains.lower() in n.lower():
            opts.nth(i).click(); page.wait_for_timeout(800); return n
    page.keyboard.press("Escape")
    raise RuntimeError(f"option '{contains}' not in {names}")

def list_options(page, box_index):
    page.locator('[data-testid="stSelectbox"]').nth(box_index).click()
    page.wait_for_timeout(400)
    opts = page.locator('[role="option"]')
    names = [opts.nth(i).inner_text() for i in range(opts.count())]
    page.keyboard.press("Escape")
    return names
