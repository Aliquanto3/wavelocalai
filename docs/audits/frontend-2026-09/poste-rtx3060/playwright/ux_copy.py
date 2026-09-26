import sys; sys.path.insert(0, sys.argv[1])
from common import settle
from playwright.sync_api import sync_playwright
JS = r"""() => {
 const vis = e => e.offsetParent !== null;
 const btn = [...document.querySelectorAll('button')].filter(vis).map(b => (b.getAttribute('aria-label')||'') + ' | ' + b.innerText.trim().replace(/\n/g,' ')).filter(t => t.trim() !== '|');
 const tabs = [...document.querySelectorAll('[role=tab]')].map(t => t.innerText.trim());
 const nav = [...document.querySelectorAll('[data-testid="stSidebarNav"] a')].map(a => a.innerText.trim());
 const side = (document.querySelector('[data-testid="stSidebarUserContent"]')||{innerText:''}).innerText.replace(/\n+/g,' / ').slice(0,300);
 return {title: document.title, nav, tabs, btn, side};
}"""
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1440, "height": 900})
    for path in ["", "Socle_Hardware", "Inference_Arena", "RAG_Knowledge", "Agent_Lab"]:
        page.goto(f"http://localhost:8501/{path}"); settle(page)
        r = page.evaluate(JS)
        print(f"=== /{path}  <title>{r['title']}</title>")
        if not path: print("nav:", r["nav"])
        print("tabs:", r["tabs"]); print("sidebar:", r["side"])
        for b in r["btn"]: print("  btn:", b[:90])
