import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18821

def wait_port(port, timeout=15):
    import socket, time as _t
    end = _t.time() + timeout
    while _t.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close(); return
        except OSError:
            _t.sleep(0.2)
    raise SystemExit("test server did not start on port %d" % port)
import sys, subprocess, time, json, os, random
from urllib.parse import quote
from playwright.sync_api import sync_playwright
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "csp_test_server.py"), str(PORT), SRC],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
wait_port(PORT)
BASE = "http://127.0.0.1:%d/" % PORT
KEY = "ipipneo300_zh_v1"
A36 = "0123456789abcdefghijklmnopqrstuvwxyz"
R = ("1M031H19Dpvpadvdzavwtebwvwe8vwdz8tdhhtypvsbaqzn8dvpgbsvvyd7ppzadphhdpwyptqdwz"
     "gyaz87phwqxzzsaqpr7ta8tabpbzfdvdb7yavhb8wbhg7qbdbw7pbahvbnqdwet7wqvbeqyga7dxstpwxq")
def dec(r):
    a = [0] * 301
    for k, ch in enumerate(r[9:]): v = A36.index(ch); a[2*k+1] = v // 6; a[2*k+2] = v % 6
    return a
res = []; errors = []
def check(n, c, d=""): res.append((n, bool(c), d))
def seed(pg, a, sex="M", age=31, done=True, page=19):
    pg.goto(BASE, wait_until="networkidle")
    pg.evaluate("o => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('%s', JSON.stringify(o)); }" % KEY,
                {"v": 1, "answers": a, "sex": sex, "age": age, "page": page, "mode": "plain", "done": done, "savedAt": 1})
    pg.goto("about:blank"); pg.goto(BASE, wait_until="networkidle"); pg.wait_for_timeout(500)
def newpg(ctx):
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.on("dialog", lambda d: d.accept())
    return pg
try:
  with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    phone = dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    ctx = b.new_context(**phone); pg = newpg(ctx)
    # real protocol: no reliability flag; profile renders even though its JSON block comes after the main script
    seed(pg, dec(R))
    check("real protocol: no reliability flag", "个人信度" not in pg.inner_text("#result"))
    check("profile renders from the deferred JSON block", pg.evaluate("!!document.querySelector('#profile .pf h3')"))
    check("care note shown for N94 / 抑郁 94", pg.evaluate("!!document.querySelector('.care-note')"))
    check("adult: no under-18 note", pg.evaluate("document.getElementById('ageNote').classList.contains('hide')"))
    check("restored result: no floating toast", pg.evaluate("document.getElementById('restoreToast').classList.contains('hide')"))
    check("restored result: save note says it's the last result", "上次的结果" in pg.inner_text("#resultSaveNote"))
    # unit checks inside the page
    u = pg.evaluate("""() => [level(69.6), level(69.4), level(30.4), level(30.6), tendencyTag(DATA.domains[0], 69.6).split(' ')[0],
        careNote({pct:90, facets:[{pct:1},{pct:1},{pct:60},{pct:1},{pct:1},{pct:60}]}) === null,
        careNote({pct:84.4, facets:[{pct:1},{pct:1},{pct:95},{pct:1},{pct:1},{pct:95}]}) === null,
        careNote({pct:86, facets:[{pct:1},{pct:1},{pct:85.2},{pct:1},{pct:1},{pct:10}]}) !== null]""")
    check("bands follow the displayed integer (69.6 -> 高, 30.4 -> 低)", u[:4] == ["高", "中等", "低", "中等"] and u[4] == "高", u)
    check("care note: N high alone -> none; N3/N6 high alone -> none; both -> shown", u[5] and u[6] and u[7], u)
    # chip -> facet row gets focus
    pg.click(".hero-chip"); pg.wait_for_timeout(700)
    check("chip moves focus to the facet row", pg.evaluate("document.activeElement.classList.contains('fbar')"))
    check("facet glosses limited to the chip set", pg.evaluate("document.querySelectorAll('.fgloss').length <= document.querySelectorAll('.hero-chip').length"),
          pg.evaluate("[document.querySelectorAll('.fgloss').length, document.querySelectorAll('.hero-chip').length]"))
    # share card: Esc returns focus to the button; back button closes the sheet instead of leaving the result
    pg.click("#cardBtn"); pg.wait_for_selector("#cardSheet:not(.hide)"); pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    check("card sheet: Esc returns focus to the card button", pg.evaluate("document.activeElement.id") == "cardBtn")
    pg.click("#cardBtn"); pg.wait_for_selector("#cardSheet:not(.hide)"); pg.go_back(); pg.wait_for_timeout(400)
    check("card sheet: back closes it and stays on the result", pg.evaluate("document.getElementById('cardSheet').classList.contains('hide') && document.body.dataset.view === 'result'"))
    check("phone: second print button hidden", pg.evaluate("getComputedStyle(document.getElementById('printBtn2')).display") == "none")
    ctx.close()

    # random responder -> flagged, panel open
    ctx = b.new_context(**phone); pg = newpg(ctx)
    rnd = random.Random(3); ra = [0] + [rnd.randint(1, 5) for _ in range(300)]
    seed(pg, ra, sex="F", age=16)
    txt = pg.inner_text("#validity")
    check("random responder: reliability flag shown and panel open", "个人信度" in txt and pg.evaluate("document.querySelector('#validity details').open"), txt[:120])
    check("age 16: under-18 norm note shown", pg.evaluate("!document.getElementById('ageNote').classList.contains('hide')"))
    ctx.close()

    # answering page: restore notice in place, page jump, out-of-order answering, trait dots, legend
    ctx = b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True); pg = newpg(ctx)
    pg.goto(BASE, wait_until="networkidle"); pg.evaluate("localStorage.clear()"); pg.goto(BASE, wait_until="networkidle")
    check("phone intro keeps the trait dots", pg.evaluate("getComputedStyle(document.querySelector('.trait-dots')).display") != "none")
    a = [0] * 301
    for i in range(1, 21): a[i] = 1 + i % 5
    seed(pg, a, sex="F", age=25, done=False, page=1)
    check("restored test: notice next to the current question, no floating toast",
          "已自动恢复" in (pg.inner_text("#pageFeedback") + pg.evaluate("(document.querySelector('.resume-note') || {}).textContent || ''")) and pg.evaluate("document.getElementById('restoreToast').classList.contains('hide')"))
    check("legend shows the short phone labels", pg.evaluate("getComputedStyle(document.querySelector('.lg-short')).display") != "none")
    pg.focus("#pageJump"); pg.keyboard.press("ArrowDown"); pg.wait_for_timeout(200)
    t1 = pg.inner_text("#pageTitle")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
    t2 = pg.inner_text("#pageTitle")
    check("page jump: arrow alone does not turn the page; Enter does", "第 2 页" in t1 and "第 3 页" in t2, (t1, t2))
    pg.wait_for_timeout(500)
    pg.evaluate("document.querySelector('.qrow[data-qid=\"39\"]').scrollIntoView({block:'center'})"); pg.wait_for_timeout(200)
    y0 = pg.evaluate("scrollY")
    pg.tap('.qrow[data-qid="39"] .opt[data-v="2"]'); pg.wait_for_timeout(500)
    check("out-of-order answer: current moves forward, no jump back up",
          pg.evaluate("document.querySelector('.qrow.cur').dataset.qid") == "40" and pg.evaluate("scrollY") >= y0 - 2,
          (pg.evaluate("document.querySelector('.qrow.cur').dataset.qid"), y0, pg.evaluate("scrollY")))
    ctx.close()

    # 320px: no option overflows
    ctx = b.new_context(viewport={"width": 320, "height": 640}, is_mobile=True, has_touch=True); pg = newpg(ctx)
    seed(pg, a, sex="F", age=25, done=False, page=1)
    over = pg.evaluate("[...document.querySelectorAll('.opt')].filter(o => o.scrollWidth > o.clientWidth + 0.5).length")
    check("320px: no option label overflows", over == 0, over)
    ctx.close()

    # tablet touch: print button visible
    ctx = b.new_context(viewport={"width": 1024, "height": 768}, has_touch=True); pg = newpg(ctx)
    seed(pg, dec(R))
    check("tablet touch: hero print button visible", pg.evaluate("getComputedStyle(document.getElementById('printBtn2')).display") != "none")
    # forced colors: selected option and bars distinguishable
    pg.emulate_media(forced_colors="active")
    fc = pg.evaluate("""(() => { const t = getComputedStyle(document.querySelector('#domain-O .track')).backgroundColor,
        i = getComputedStyle(document.querySelector('#domain-O .track i')).backgroundColor; return [t, i]; })()""")
    check("forced colors: bar differs from its track", fc[0] != fc[1], fc)
    pg.emulate_media(forced_colors="none")
    # pasting a different link into the open tab reloads and classifies it (here: someone else's -> view only)
    other = "1F028P19D" + "".join(A36[random.Random(4).randint(1, 5) * 6 + random.Random(5).randint(1, 5)] for _ in range(150))
    pg.evaluate("h => { location.hash = 'p=' + h; }", other); pg.wait_for_timeout(1500)
    check("pasted foreign link in an open tab -> reload into view-only",
          pg.evaluate("!document.getElementById('viewBanner').classList.contains('hide')"))
    check("own saved result untouched by the pasted link", pg.evaluate("JSON.parse(localStorage.getItem('%s')).sex" % KEY) == "M")
    ctx.close()

    # %-encoded fragment behaves like a normal link
    ctx = b.new_context(**phone); pg = newpg(ctx)
    pg.goto("about:blank"); pg.goto(BASE + "#p%3D" + R, wait_until="networkidle"); pg.wait_for_timeout(500)
    check("%-encoded #p%3D link opens like #p= (view-only)", pg.evaluate("!document.getElementById('viewBanner').classList.contains('hide')"))
    ctx.close()
    b.close()
finally:
    srv.terminate()
for n, ok, d in res: print(("PASS " if ok else "FAIL ") + n + ("" if ok else "   " + json.dumps(d, ensure_ascii=False)[:300]))
print("%d/%d passed; errors: %s" % (sum(r[1] for r in res), len(res), errors[:5]))
