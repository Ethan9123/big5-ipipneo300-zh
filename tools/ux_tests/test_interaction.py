import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18811

def wait_port(port, timeout=15):
    import socket, time as _t
    end = _t.time() + timeout
    while _t.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close(); return
        except OSError:
            _t.sleep(0.2)
    raise SystemExit("test server did not start on port %d" % port)
import sys, subprocess, time, json, os, tempfile, random
from playwright.sync_api import sync_playwright
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "csp_test_server.py"), str(PORT), SRC],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
wait_port(PORT)
BASE = "http://127.0.0.1:%d/" % PORT
KEY = "ipipneo300_zh_v1"
res = []
def check(n, c, d=""): res.append((n, bool(c), d))
def seed(pg, n, done=False, sex="F", age=27, page=0, seedv=1):
    rnd = random.Random(seedv); a = [0] * 301
    for i in range(1, n + 1): a[i] = rnd.randint(1, 5)
    pg.goto(BASE, wait_until="networkidle")
    pg.evaluate("o => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('%s', JSON.stringify(o)); }" % KEY,
                {"v": 1, "answers": a, "sex": sex, "age": age, "page": page, "mode": "plain", "done": done, "savedAt": 1})
    pg.goto("about:blank"); pg.goto(BASE, wait_until="networkidle"); pg.wait_for_timeout(600)
ans = lambda pg, q: pg.evaluate("q => { const b = document.querySelector('.qrow[data-qid=\"' + q + '\"] .opt[aria-checked=\"true\"]'); return b ? +b.dataset.v : 0 }", q)
errors = []
try:
  with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    # ---------------- desktop ----------------
    ctx = b.new_context(viewport={"width": 1280, "height": 860}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.goto(BASE, wait_until="networkidle"); pg.evaluate("localStorage.clear()"); pg.goto(BASE, wait_until="networkidle")
    check("boot: no booting class, start enabled with label",
          pg.evaluate("!document.documentElement.classList.contains('booting') && !document.getElementById('startBtn').disabled && /开始/.test(document.getElementById('startBtn').textContent)"))
    check("intro: answering-only controls hidden", pg.evaluate("['#pcount','#hintToggle','#enToggle','.bar'].every(s => document.querySelector(s).classList.contains('hide'))"))
    pg.click("#startBtn")
    check("start error: sex marked invalid", pg.evaluate("document.getElementById('sex').getAttribute('aria-invalid') === 'true' && !document.getElementById('startError').classList.contains('hide')"))
    pg.select_option("#sex", "F")
    check("start error: invalid cleared on input", pg.evaluate("!document.getElementById('sex').hasAttribute('aria-invalid')"))
    pg.fill("#age", "27"); pg.click("#startBtn"); pg.wait_for_selector("#test:not(.hide)"); pg.wait_for_timeout(500)
    check("test: one tab stop per question", pg.evaluate("document.querySelectorAll('#qlist .opt[tabindex=\"0\"]').length") == 15)
    check("test: options are radios with visible-text names", pg.evaluate("[...document.querySelectorAll('#qlist .opt')].every(o => o.getAttribute('role') === 'radio' && !o.hasAttribute('aria-label'))"))
    check("test: rows are radiogroups labelled by number + text", pg.evaluate("document.querySelector('.qrow').getAttribute('role') === 'radiogroup' && document.querySelector('.qrow').getAttribute('aria-labelledby').startsWith('qnum-')"))
    check("title shows page", "第 1 / 20 页" in pg.title(), pg.title())
    # arrows move focus but do not answer
    pg.focus('.qrow[data-qid="1"] .opt[tabindex="0"]'); pg.keyboard.press("ArrowRight"); pg.keyboard.press("ArrowRight")
    check("arrows move focus within a question", pg.evaluate("document.activeElement.dataset.v") == "3")
    check("arrows do not answer", ans(pg, 1) == 0)
    pg.keyboard.press("Space"); pg.wait_for_timeout(200)
    check("space answers the focused option", ans(pg, 1) == 3)
    # key auto-repeat ignored
    pg.evaluate("document.body.focus()")
    pg.evaluate("() => { const ev = new KeyboardEvent('keydown', {key:'2', code:'Digit2', repeat:true, bubbles:true}); dispatchEvent(ev); }")
    check("held key (repeat) ignored", ans(pg, 2) == 0)
    # hint toggle keeps the middle question in place
    pg.evaluate("document.querySelector('.qrow[data-qid=\"8\"]').scrollIntoView({block:'center'})"); pg.wait_for_timeout(200)
    before = pg.evaluate("document.querySelector('.qrow[data-qid=\"8\"]').getBoundingClientRect().top")
    pg.click("#hintToggle"); pg.wait_for_timeout(200)
    after = pg.evaluate("document.querySelector('.qrow[data-qid=\"8\"]').getBoundingClientRect().top")
    check("hints toggle keeps row in place", abs(after - before) < 4, (before, after))
    pg.click("#hintToggle")
    pg.click("#enToggle"); check("EN toggle exposes pressed state", pg.get_attribute("#enToggle", "aria-pressed") == "true"); pg.click("#enToggle")
    # finish page 1 -> auto advance -> undo offer
    for q in range(2, 16): pg.click('.qrow[data-qid="%d"] .opt[data-v="2"]' % q)
    pg.wait_for_timeout(1000)
    check("auto page turn offers undo", pg.evaluate("!document.getElementById('pageUndo').classList.contains('hide')") and "第 2 页" in pg.inner_text("#pageTitle"))
    # ghost tap: a real click right after the page turn is dropped; keyboard is not
    pg.click("#pageUndoBtn"); pg.wait_for_timeout(300)
    check("undo -> back on page 1, last question focused", "第 1 页" in pg.inner_text("#pageTitle") and pg.evaluate("document.activeElement.closest('.qrow')?.dataset.qid") == "15")
    pg.click("#nextBtn"); pg.click('.qrow[data-qid="16"] .opt[data-v="4"]')
    check("ghost tap within 450ms dropped", ans(pg, 16) == 0)
    pg.wait_for_timeout(500); pg.click('.qrow[data-qid="16"] .opt[data-v="4"]')
    check("normal tap after 450ms works", ans(pg, 16) == 4)
    # history: test -> back -> intro -> forward -> test
    pg.go_back(); pg.wait_for_timeout(400)
    check("back from test goes to intro (stays on site)", pg.evaluate("document.body.dataset.view") == "intro" and pg.url.startswith(BASE), pg.url)
    check("intro shows resume card after back", pg.evaluate("!document.getElementById('resumeCard').classList.contains('hide')"))
    pg.go_forward(); pg.wait_for_timeout(400)
    check("forward returns to test", pg.evaluate("document.body.dataset.view") == "test")
    # copy link fallbacks
    pg.evaluate("navigator.clipboard.writeText = () => Promise.reject(new Error('x')); document.execCommand = () => false;")
    pg.click("#linkBtn"); pg.wait_for_timeout(300)
    check("copy fails -> link shown for manual copy", pg.evaluate("(document.querySelector('.manual-copy input')||{}).value || ''").startswith(BASE))
    check("copy failure message is not 'address bar'", "地址栏" not in pg.inner_text("#copied"), pg.inner_text("#copied"))
    ctx.close()

    # ---------------- result / print / tooltip / import ----------------
    ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, color_scheme="dark"); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    seed(pg, 300, done=True, seedv=5)
    check("restored result at boot: title not focused (no focus ring on first paint)", pg.evaluate("document.activeElement.id") != "resultTitle")
    check("result document title", "测评结果" in pg.title(), pg.title())
    bg = pg.evaluate("getComputedStyle(document.getElementById('cardBtn')).backgroundColor")
    check("dark primary button fill is the darker accent", bg == "rgb(31, 111, 209)", bg)
    pg.dispatch_event(".fbar", "pointermove", {"pointerType": "touch", "clientX": 100, "clientY": 100})
    check("touch pointermove does not open tooltip", pg.evaluate("getComputedStyle(document.getElementById('tip')).opacity") == "0")
    check("phone hides the second print button", pg.evaluate("getComputedStyle(document.getElementById('printBtn2')).display") == "none")
    hs = pg.evaluate("[...document.querySelectorAll('.result-actions .iconbtn')].map(b => Math.round(b.getBoundingClientRect().height))")
    check("phone secondary buttons >= 44px", min(hs) >= 44, hs)
    pg.emulate_media(media="print")
    pr = pg.evaluate("(() => { const i = document.querySelector('#domain-O .track i'), cs = getComputedStyle(i); return [cs.backgroundColor, cs.printColorAdjust || cs.webkitPrintColorAdjust, getComputedStyle(document.body).color]; })()")
    check("print: light tokens + exact bar colour", pr[0] == "rgb(42, 120, 214)" and pr[1] == "exact" and pr[2] in ("rgb(11, 11, 11)",), pr)
    pg.emulate_media(media="screen")
    # import an exported result file (300 answers, text mode)
    rnd = random.Random(9); exported = {"instrument": "IPIP-NEO-300", "lang": "zh-CN", "sex": "M", "age": 40,
        "mode": "standard (标准模式)", "domains": {}, "answers": [rnd.randint(1, 5) for _ in range(300)]}
    fp = os.path.join(tempfile.gettempdir(), "b3_export.json"); json.dump(exported, open(fp, "w", encoding="utf-8"))
    pg.click("#restartBtn"); pg.wait_for_timeout(300)
    pg.on("dialog", lambda d: d.accept())
    pg.set_input_files("#importFile", fp); pg.wait_for_timeout(800)
    st = pg.evaluate("(() => { const s = JSON.parse(localStorage.getItem('%s')); return [document.body.dataset.view, s.sex, s.age, s.mode, s.done]; })()" % KEY)
    check("exported result JSON imports as a finished result", st == ["result", "M", 40, "plain", True], st)
    ctx.close()
    b.close()
finally:
    srv.terminate()
for n, ok, d in res: print(("PASS " if ok else "FAIL ") + n + ("" if ok else "   " + json.dumps(d, ensure_ascii=False)[:300]))
print("%d/%d passed; errors: %s" % (sum(r[1] for r in res), len(res), errors[:5]))
