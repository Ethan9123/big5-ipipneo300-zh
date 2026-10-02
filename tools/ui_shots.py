# -*- coding: utf-8 -*-
"""Screenshot harness for UI/UX review. Drives the system Chrome via Playwright.

  python tools/ui_shots.py [outdir] [--dir dist] [--port 8811]

Serves the build with the real _headers (CSP included) and captures the screens a user
actually lives in -- intro, answering, the result page in sections -- at phone and desktop
widths, light and dark. Also dumps console errors and CSP violations, since a screenshot
can look fine while the page is quietly broken.
"""
import json
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = args[0] if args else os.path.join(ROOT, "tools", "out", "shots")
SRC = sys.argv[sys.argv.index("--dir") + 1] if "--dir" in sys.argv else "dist"
PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8811
os.makedirs(OUT, exist_ok=True)

# a real completed protocol (M, 31) -- exercises the border warning and extreme tails
RESULT = ("1M031H19Dpvpadvdzavwtebwvwe8vwdz8tdhhtypvsbaqzn8dvpgbsvvyd7ppzadphhdpwyptqdwz"
          "gyaz87phwqxzzsaqpr7ta8tabpbzfdvdb7yavhb8wbhg7qbdbw7pbahvbnqdwet7wqvbeqyga7dxstpwxq")
VIEWPORTS = {"phone": {"width": 390, "height": 844}, "desktop": {"width": 1280, "height": 860}}

srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "csp_test_server.py"),
                        str(PORT), SRC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
base = "http://127.0.0.1:%d/" % PORT
report = {"src": SRC, "shots": [], "console": [], "csp": []}

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for scheme in ("light", "dark"):
            for vp_name, vp in VIEWPORTS.items():
                def fresh_page():
                    c = browser.new_context(viewport=vp, color_scheme=scheme,
                                            device_scale_factor=2 if vp_name == "phone" else 1,
                                            is_mobile=(vp_name == "phone"), has_touch=(vp_name == "phone"))
                    pg = c.new_page()
                    pg.on("console", lambda m, t=f"{scheme}/{vp_name}": m.type in ("error", "warning")
                          and report["console"].append({"where": t, "type": m.type, "text": m.text[:300]}))
                    pg.add_init_script("""document.addEventListener('securitypolicyviolation',
                        e => console.error('CSP ' + e.effectiveDirective + ' ' + e.blockedURI));""")
                    return c, pg
                ctx, page = fresh_page()

                def shot(name, full=False):
                    f = os.path.join(OUT, f"{scheme}-{vp_name}-{name}.png")
                    page.screenshot(path=f, full_page=full)
                    report["shots"].append(os.path.relpath(f, ROOT))

                # 1 intro
                page.goto(base, wait_until="networkidle")
                page.evaluate("localStorage.clear(); sessionStorage.clear()")
                page.goto(base, wait_until="networkidle")
                shot("01-intro")
                shot("01-intro-full", full=True)

                # 2 answering: start, answer 7 on page 1 so 'current' row and answered rows show
                page.select_option("#sex", "F")
                page.fill("#age", "28")
                page.click("#startBtn")
                page.wait_for_selector("#qlist .qrow")
                page.wait_for_timeout(500)   # taps within 450 ms of a page turn are ignored as ghost taps
                shot("02-test-start")
                rows = page.query_selector_all("#qlist .qrow")
                for i, r in enumerate(rows[:7]):
                    r.query_selector_all(".opt")[(i * 2) % 5].click()
                page.wait_for_timeout(400)
                shot("03-test-midpage")

                # 3 result: seed the protocol as this browser's own saved result. Opening the
                # bare #p= link would (correctly) show someone-else's-link view mode instead.
                # A hash-only change does not re-run boot(), so go via about:blank. Seed from a
                # fresh context: leaving the answering page saves its own state on pagehide.
                ctx.close()
                ctx, page = fresh_page()
                page.goto(base, wait_until="networkidle")
                page.evaluate("""r => { localStorage.clear(); sessionStorage.clear();
                    const A = '0123456789abcdefghijklmnopqrstuvwxyz', a = new Array(301).fill(0);
                    for (let k = 0; k < 150; k++){ const v = A.indexOf(r[9 + k]); a[2*k+1] = Math.floor(v/6); a[2*k+2] = v % 6; }
                    localStorage.setItem('ipipneo300_zh_v1', JSON.stringify({v:1, answers:a, sex:r[1], age:+r.slice(2,5),
                      page:19, mode:r[5] === 'H' ? 'hints' : 'plain', done:true, savedAt:Date.now()})); }""", RESULT)
                page.goto("about:blank")
                page.goto(base, wait_until="networkidle")
                page.wait_for_selector("#result:not(.hide)")
                page.wait_for_timeout(700)
                shot("04-result-top")
                for sel, nm in (("#domains", "05-domains"), ("#profile", "06-profile"),
                                ("#facets", "07-facets")):
                    el = page.query_selector(sel)
                    if el:
                        el.scroll_into_view_if_needed()
                        page.evaluate("window.scrollBy(0,-70)")
                        page.wait_for_timeout(250)
                        shot(nm)
                shot("08-result-full", full=True)
                ctx.close()
        browser.close()
finally:
    srv.terminate()

json.dump(report, open(os.path.join(OUT, "report.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("shots: %d   console errors/warnings: %d" % (len(report["shots"]), len(report["console"])))
for c in report["console"][:10]:
    print("  [%s] %s %s" % (c["where"], c["type"], c["text"][:160]))
print("out:", os.path.relpath(OUT, ROOT))
