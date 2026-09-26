import sys, json; sys.path.insert(0, sys.argv[1]); OUT = sys.argv[1] + "/ux"
from common import settle
from playwright.sync_api import sync_playwright
AXE = "https://cdn.jsdelivr.net/npm/axe-core@4.10.2/axe.min.js"
PAGES = [("accueil", ""), ("hardware", "Socle_Hardware"), ("inference", "Inference_Arena"), ("rag", "RAG_Knowledge"), ("agent", "Agent_Lab")]
THEMES = [("light", 8501), ("dark", 8502)]
VIEWS = [("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})]
STATS_JS = r"""
() => {
  const main = document.querySelector('[data-testid="stMain"]') || document.body;
  const txt = main.innerText;
  const emoji = (txt.match(/\p{Extended_Pictographic}/gu) || []).length;
  const fonts = new Set(), btnBg = new Set();
  document.querySelectorAll('h1,h2,h3,p,button,label,span').forEach(e => fonts.add(getComputedStyle(e).fontFamily.split(',')[0]));
  document.querySelectorAll('button').forEach(b => { const c = getComputedStyle(b).backgroundColor; if (c !== 'rgba(0, 0, 0, 0)') btnBg.add(c); });
  const h = [...main.querySelectorAll('h1,h2,h3,h4')].map(e => e.tagName + ':' + e.innerText.trim().slice(0,40));
  return {emoji, words: txt.split(/\s+/).length, fonts: [...fonts], buttonBg: [...btnBg], headings: h,
          hscroll: document.documentElement.scrollWidth > window.innerWidth + 1};
}
"""
res = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for theme, port in THEMES:
        for vname, vp in VIEWS:
            page = b.new_page(viewport=vp)
            for name, path in PAGES:
                key = f"{name}_{theme}_{vname}"
                page.goto(f"http://localhost:{port}/{path}"); settle(page)
                page.screenshot(path=f"{OUT}/{key}.png", full_page=True)
                st = page.evaluate(STATS_JS)
                if vname == "desktop":
                    page.add_script_tag(url=AXE)
                    ax = page.evaluate("async () => (await axe.run(document, {resultTypes:['violations']})).violations.map(v => ({id:v.id, impact:v.impact, n:v.nodes.length, help:v.help, ex:v.nodes.slice(0,3).map(n => (n.any[0]||{}).message || n.target.join(' '))}))")
                    st["axe"] = ax
                res[key] = st
                print(key, "emoji", st["emoji"], "hscroll", st["hscroll"], "axe", [(a["id"], a["n"]) for a in st.get("axe", [])])
            page.close()
    b.close()
json.dump(res, open(f"{OUT}/stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
