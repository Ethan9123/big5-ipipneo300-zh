import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18861

def wait_port(port, timeout=15):
    import socket, time as _t
    end = _t.time() + timeout
    while _t.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close(); return
        except OSError:
            _t.sleep(0.2)
    raise SystemExit("test server did not start on port %d" % port)
import sys, subprocess, time, json, os
from playwright.sync_api import sync_playwright
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "csp_test_server.py"), str(PORT), SRC],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
wait_port(PORT)
base = "http://127.0.0.1:%d/" % PORT
EMPTY = "1M031H00P" + "6" + "0" * 149   # only Q1 answered

def seed(pg, base, r, done):
    pg.goto(base, wait_until="networkidle")
    pg.evaluate("""([r, done]) => { localStorage.clear(); sessionStorage.clear();
        const A = '0123456789abcdefghijklmnopqrstuvwxyz', a = new Array(301).fill(0);
        for (let k = 0; k < 150; k++){ const v = A.indexOf(r[9 + k]); a[2*k+1] = Math.floor(v/6); a[2*k+2] = v % 6; }
        localStorage.setItem('ipipneo300_zh_v1', JSON.stringify({v:1, answers:a, sex:r[1], age:+r.slice(2,5),
          page:+r.slice(6,8), mode:'plain', done, savedAt:Date.now()})); }""", [r, done])
    pg.goto("about:blank"); pg.goto(base, wait_until="networkidle")
r = {}
try:
  with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width":1280,"height":860}); errs = []
    pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    pg.on("pageerror", lambda e: errs.append(str(e)))
    seed(pg, base, EMPTY, False)
    pg.wait_for_selector("#test:not(.hide)")
    r["title0"] = pg.inner_text("#pageTitle")
    # answer all 15 on page 1 with keyboard only, then wait for auto-advance
    for i in range(14): pg.keyboard.press(str(1 + i % 5))
    pg.wait_for_timeout(1200)
    r["title_after_auto"] = pg.inner_text("#pageTitle")
    r["focus_after_auto"] = pg.evaluate("document.activeElement.id || document.activeElement.tagName")
    pg.keyboard.press("2")
    r["p2_q16"] = pg.evaluate("(()=>{const b=document.querySelector('.qrow[data-qid=\"16\"] .opt[aria-checked=\"true\"]');return b?+b.dataset.v:0})()")
    # prev button by mouse -> focus goes to title, no visible ring
    pg.click("#prevBtn")
    r["title_after_prev"] = pg.inner_text("#pageTitle")
    r["focus_after_prev"] = pg.evaluate("document.activeElement.id")
    r["prev_focus_visible"] = pg.evaluate("document.activeElement.matches(':focus-visible')")
    # page jump select keeps focus
    pg.focus("#pageJump"); pg.select_option("#pageJump", "3")
    r["focus_after_jump"] = pg.evaluate("document.activeElement.id")
    r["title_after_jump"] = pg.inner_text("#pageTitle")
    r["landmarks"] = pg.evaluate("[...document.querySelectorAll('header.topbar, main#main')].map(e=>e.tagName)")
    r["lang_en"] = pg.evaluate("document.querySelectorAll('.qen[lang=en]').length")
    r["errors"] = errs
    b.close()
finally:
    srv.terminate()

_checks = [("auto page turn moves focus to the page title", r["focus_after_auto"] == "pageTitle"),
           ("digit keys keep answering after the page turn", r["p2_q16"] == 2),
           ("mouse 'previous page' does not show a focus ring", not r["prev_focus_visible"]),
           ("page-jump select keeps focus", r["focus_after_jump"] == "pageJump"),
           ("banner + main landmarks", r["landmarks"] == ["HEADER", "MAIN"]),
           ("English item text marked lang=en", r["lang_en"] == 15),
           ("no page errors", not r["errors"])]
for n, g in _checks: print(("PASS " if g else "FAIL ") + n)
print("%d/%d passed" % (sum(g for _, g in _checks), len(_checks)))
