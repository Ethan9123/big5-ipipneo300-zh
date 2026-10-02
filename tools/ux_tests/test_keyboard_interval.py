import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18851

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
RESULT = ("1M031H19Dpvpadvdzavwtebwvwe8vwdz8tdhhtypvsbaqzn8dvpgbsvvyd7ppzadphhdpwyptqdwz"
          "gyaz87phwqxzzsaqpr7ta8tabpbzfdvdb7yavhb8wbhg7qbdbw7pbahvbnqdwet7wqvbeqyga7dxstpwxq")
PARTIAL = "1M031H00P" + RESULT[9] + "0" * 149     # page 1, only Q1,Q2 answered

def seed(pg, base, r, done):
    pg.goto(base, wait_until="networkidle")
    pg.evaluate("""([r, done]) => { localStorage.clear(); sessionStorage.clear();
        const A = '0123456789abcdefghijklmnopqrstuvwxyz', a = new Array(301).fill(0);
        for (let k = 0; k < 150; k++){ const v = A.indexOf(r[9 + k]); a[2*k+1] = Math.floor(v/6); a[2*k+2] = v % 6; }
        localStorage.setItem('ipipneo300_zh_v1', JSON.stringify({v:1, answers:a, sex:r[1], age:+r.slice(2,5),
          page:+r.slice(6,8), mode:'plain', done, savedAt:Date.now()})); }""", [r, done])
    pg.goto("about:blank"); pg.goto(base, wait_until="networkidle")
res = {}
def ans(page, q):
    return page.evaluate("q => { const r=document.querySelector('.qrow[data-qid=\"'+q+'\"]'); const b=r&&r.querySelector('.opt[aria-checked=\"true\"]'); return b?+b.dataset.v:0 }", q)
cur = lambda page: page.evaluate("(document.querySelector('.qrow.cur')||{dataset:{}}).dataset.qid")
foc = lambda page: page.evaluate("(()=>{const r=document.activeElement&&document.activeElement.closest('.qrow');return r?r.dataset.qid:null})()")
try:
  with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    # ---------- desktop keyboard ----------
    ctx = b.new_context(viewport={"width":1280,"height":860})
    pg = ctx.new_page(); errs=[]
    pg.on("console", lambda m: m.type=="error" and errs.append(m.text))
    seed(pg, base, PARTIAL, False)
    pg.wait_for_selector("#test:not(.hide)")
    res["start_cur"] = cur(pg); res["q1"] = ans(pg,1); res["q2"] = ans(pg,2)
    # A: mouse-click Q5 option1, then Tab to Q5 option2 (keyboard focus), press 4 -> Q5 should become 4
    pg.click('.qrow[data-qid="5"] .opt[data-v="1"]')
    res["A_after_click_cur"] = cur(pg)
    pg.keyboard.press("ArrowRight")   # roving tabindex: arrows move within the question
    res["A_focus_row"] = foc(pg)
    pg.keyboard.press("4")
    res["A_q5"] = ans(pg,5); res["A_q3"] = ans(pg,3); res["A_focus_after"] = foc(pg)
    # B: mouse-click Q6 option1 (mouse focus, not focus-visible), press 5 -> current row (Q3) gets 5
    pg.click('.qrow[data-qid="6"] .opt[data-v="1"]')
    pg.keyboard.press("5")
    res["B_q6"] = ans(pg,6); res["B_q3"] = ans(pg,3); res["B_q7"] = ans(pg,7); res["B_cur"] = cur(pg)
    # C: keyboard-focus inside current row, press 3 -> answered, focus follows to next current row
    c = cur(pg)
    pg.focus('.qrow[data-qid="%s"] .opt[data-v="1"]' % c)
    pg.keyboard.press("3")
    res["C_row"] = c; res["C_ans"] = ans(pg,int(c)); res["C_cur_after"] = cur(pg); res["C_focus_after"] = foc(pg)
    res["desktop_errors"] = errs
    ctx.close()
    # ---------- phone toast ----------
    ctx = b.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    seed(pg, base, RESULT, True)
    pg.wait_for_selector("#result:not(.hide)")
    box = pg.evaluate("(()=>{const t=document.getElementById('restoreToast');const r=t.getBoundingClientRect();return {hidden:t.classList.contains('hide'),top:Math.round(r.top),bottom:Math.round(r.bottom)}})()")
    res["toast_phone"] = box
    import tempfile; pg.screenshot(path=os.path.join(tempfile.gettempdir(), "ux_p0_toast_phone.png"))   # never write into the repo
    pg.wait_for_timeout(600)
    pg.mouse.wheel(0, 400); pg.wait_for_timeout(400)
    pg.evaluate("window.scrollBy(0, 400)"); pg.wait_for_timeout(300)
    res["toast_after_scroll_hidden"] = pg.evaluate("document.getElementById('restoreToast').classList.contains('hide')")
    # table + aria
    pg.click("#tableToggle")
    res["table_head"] = pg.evaluate("[...document.querySelectorAll('#tableView th')].map(t=>t.textContent)")
    res["table_row1"] = pg.evaluate("[...document.querySelectorAll('#tableView tbody tr')][0].innerText")
    res["table_overflow"] = pg.evaluate("(()=>{const t=document.getElementById('tableView');return [t.scrollWidth,t.clientWidth, document.documentElement.scrollWidth]})()")
    res["track_aria"] = pg.evaluate("[...document.querySelectorAll('.track[aria-label]')].map(t=>t.getAttribute('aria-label'))")
    res["ftrack_aria_sample"] = pg.evaluate("[...document.querySelectorAll('.ftrack[aria-label]')].slice(0,3).map(t=>t.getAttribute('aria-label'))")
    res["evidence"] = pg.evaluate("[...document.querySelectorAll('.domain-evidence')].map(e=>e.textContent.slice(0,60))")
    ctx.close(); b.close()
finally:
    srv.terminate()

_exp = {"A_q5": 4, "A_q3": 0, "A_focus_after": "5", "B_q6": 1, "B_q3": 0, "B_q7": 5, "C_ans": 3,
        "C_focus_after": str(int(res["C_row"]) + 1), "toast_after_scroll_hidden": True}
_ok = 0
for k, v in _exp.items():
    good = res.get(k) == v; _ok += good
    print(("PASS " if good else "FAIL ") + k + ("" if good else "   got %r want %r" % (res.get(k), v)))
good = res["toast_phone"]["hidden"] and not res["desktop_errors"]; _ok += good
print(("PASS " if good else "FAIL ") + "restored result shows no floating toast over the buttons; no page errors")
good = "95% 区间" in res["table_head"] and all("95% 估计区间" in a for a in res["track_aria"]); _ok += good
print(("PASS " if good else "FAIL ") + "interval column in the table and in every track's accessible name")
print("%d/%d passed" % (_ok, len(_exp) + 2))
