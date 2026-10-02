"""Link-ownership scenarios: someone else's #p= link must never overwrite local state;
the user's own links (refresh, bookmark, cross-device) must still restore."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18801

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
from playwright.sync_api import sync_playwright

srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "csp_test_server.py"), str(PORT), SRC],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
wait_port(PORT)
BASE = "http://127.0.0.1:%d/" % PORT
KEY = "ipipneo300_zh_v1"
A36 = "0123456789abcdefghijklmnopqrstuvwxyz"

def answers(n, seed):
    rnd = random.Random(seed)
    a = [0] * 301
    for i in range(1, n + 1): a[i] = rnd.randint(1, 5)
    return a

def enc(a, sex, age, page=0, done=False, mode="P"):
    body = "".join(A36[a[i] * 6 + a[i + 1]] for i in range(1, 301, 2))
    return "1" + sex + str(age).zfill(3) + mode + str(page).zfill(2) + ("D" if done else "-") + body

def local_obj(a, sex, age, done=False, page=0):
    return {"v": 1, "answers": a, "sex": sex, "age": age, "page": page, "mode": "plain", "done": done, "savedAt": 1700000000000}

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

STATE = """(() => { let s = null; try { s = JSON.parse(localStorage.getItem('%s')); } catch(e){}
  return {view: document.body.dataset.view, hash: location.hash.slice(0, 20),
    local: s ? {n: s.answers.slice(1).filter(Boolean).length, sex: s.sex, age: s.age, done: s.done} : null,
    banner: !document.getElementById('viewBanner').classList.contains('hide'),
    bannerMeta: document.getElementById('viewBannerMeta').textContent,
    mineBtn: document.getElementById('viewMineBtn').textContent,
    status: (document.querySelector('.report-status')||{}).textContent,
    card: !document.getElementById('resumeCard').classList.contains('hide'),
    cardTitle: document.getElementById('resumeTitle').textContent,
    cardMeta: document.getElementById('resumeMeta').textContent,
    resumeBtn: document.getElementById('resumeBtn').textContent,
    freshBtn: document.getElementById('freshBtn').textContent,
    toast: document.getElementById('restoreToast').classList.contains('hide') ? '' : document.getElementById('restoreToastTitle').textContent,
    stale: !document.getElementById('staleBanner').classList.contains('hide'),
    feedback: document.getElementById('pageFeedback').textContent + ((document.querySelector('.resume-note') || {}).textContent || ''),
    page: (document.getElementById('pageTitle')||{}).textContent,
    pct: [...document.querySelectorAll('#domains .pct')].map(e => e.textContent).join(',') }; })()""" % KEY

def st(pg):
    pg.wait_for_timeout(250)
    return pg.evaluate(STATE)

def fresh(ctx, local=None):
    pg = ctx.new_page()
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.goto(BASE, wait_until="networkidle")
    pg.evaluate("localStorage.clear(); sessionStorage.clear()")
    if local is not None:
        pg.evaluate("o => localStorage.setItem('%s', JSON.stringify(o))" % KEY, local)
    return pg

def go(pg, hash_=""):
    pg.goto("about:blank")
    pg.goto(BASE + (("#p=" + hash_) if hash_ else ""), wait_until="networkidle")
    pg.wait_for_timeout(300)

dialogs, errors = [], []
FRIEND_DONE = enc(answers(300, 1), "M", 31, page=19, done=True)
FRIEND_60 = enc(answers(60, 2), "F", 28, page=4)
try:
  with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    mk = lambda: b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)

    # A: local 120 (F 24) opens friend's finished result link
    ctx = mk(); pg = fresh(ctx, local_obj(answers(120, 3), "F", 24, page=7))
    go(pg, FRIEND_DONE); s = st(pg)
    check("A view-only result shown", s["view"] == "result" and s["banner"], s)
    check("A local untouched", s["local"] == {"n": 120, "sex": "F", "age": 24, "done": False}, s["local"])
    check("A status says not saved", "未保存" in (s["status"] or ""), s["status"])
    check("A mine button wording", s["mineBtn"] == "回到我自己的作答", s["mineBtn"])
    pg.evaluate("dispatchEvent(new Event('pagehide'))"); pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    s = st(pg); check("A pagehide does not write friend data", s["local"]["n"] == 120 and s["local"]["sex"] == "F", s["local"])
    check("A hash not rewritten", s["hash"].startswith("#p=1M031"), s["hash"])
    go(pg); s = st(pg)
    check("A bare URL -> own progress", s["view"] == "test" and s["local"]["n"] == 120 and s["local"]["sex"] == "F", s)
    ctx.close()

    # E: local finished (F 24) opens friend's finished link, then goes back to own result
    ctx = mk(); mine = answers(300, 4); pg = fresh(ctx, local_obj(mine, "F", 24, done=True, page=19))
    go(pg); own_pct = st(pg)["pct"]
    go(pg, FRIEND_DONE); s = st(pg)
    check("E view-only, local finished untouched", s["banner"] and s["local"]["done"] and s["local"]["sex"] == "F", s)
    check("E friend scores differ from own", s["pct"] != own_pct, (s["pct"], own_pct))
    pg.click("#viewMineBtn"); s = st(pg)
    check("E back to own result", s["view"] == "result" and not s["banner"] and s["pct"] == own_pct and "已完成" in s["status"], s)
    check("E hash now own", s["hash"].startswith("#p=1F024"), s["hash"])
    ctx.close()

    # B: fresh visitor opens friend's in-progress link
    ctx = mk(); pg = fresh(ctx)
    go(pg, FRIEND_60); s = st(pg)
    check("B asks on intro", s["view"] == "intro" and s["card"] and s["cardTitle"] == "这个链接里带着一份作答", s)
    check("B nothing saved yet", s["local"] is None, s["local"])
    check("B buttons", s["resumeBtn"] == "接着答这份" and s["freshBtn"] == "开始我自己的", (s["resumeBtn"], s["freshBtn"]))
    pg.click("#freshBtn"); s = st(pg)
    check("B start own: hash dropped, card hidden, nothing saved", s["hash"] == "" and not s["card"] and s["local"] is None, s)
    ctx.close()

    # B2: same, but it IS mine from another device -> continue
    ctx = mk(); pg = fresh(ctx)
    go(pg, FRIEND_60); pg.click("#resumeBtn"); s = st(pg)
    check("B2 continue link -> test on page 5, saved", s["view"] == "test" and s["local"]["n"] == 60 and "第 5 页" in s["page"], s)
    go(pg, pg.evaluate("location.hash.slice(3)") if False else "")  # bare reload
    s = st(pg); check("B2 bare reload restores adopted progress", s["view"] == "test" and s["local"]["n"] == 60, s)
    ctx.close()

    # C: local 30 (M 40) opens friend's 60 (F 28)
    ctx = mk(); pg = fresh(ctx, local_obj(answers(30, 5), "M", 40, page=2))
    go(pg, FRIEND_60); s = st(pg)
    check("C asks, local untouched", s["card"] and s["local"] == {"n": 30, "sex": "M", "age": 40, "done": False}, s)
    check("C wording mentions replacement", "替换" in s["cardMeta"] and s["freshBtn"] == "继续我自己的作答", (s["cardMeta"], s["freshBtn"]))
    pg.click("#freshBtn"); s = st(pg)
    check("C continue own -> test with own 30", s["view"] == "test" and s["local"]["n"] == 30 and s["local"]["sex"] == "M", s)
    check("C hash rewritten to own", s["hash"].startswith("#p=1M040"), s["hash"])
    ctx.close()

    # C2: choosing the link when local exists asks for confirmation
    ctx = mk(); pg = fresh(ctx, local_obj(answers(30, 5), "M", 40, page=2)); dialogs.clear()
    go(pg, FRIEND_60); pg.click("#resumeBtn"); s = st(pg)
    check("C2 confirm shown before replacing", len(dialogs) == 1 and "替换" in dialogs[0], dialogs)
    check("C2 adopted link", s["local"]["n"] == 60 and s["local"]["sex"] == "F", s["local"])
    ctx.close()

    # D: own link that is a subset of local (stale bookmark) -> merge silently, nothing lost
    ctx = mk(); a100 = answers(100, 6); a60 = a100[:61] + [0] * 240
    pg = fresh(ctx, local_obj(a100, "F", 24, page=6))
    go(pg, enc(a60, "F", 24, page=4)); s = st(pg)
    check("D own subset -> auto restore 100, no ask", s["view"] == "test" and not s["card"] and s["local"]["n"] == 100, s)
    ctx.close()

    # D2: same sex/age but conflicting answers -> other -> ask
    ctx = mk(); pg = fresh(ctx, local_obj(answers(100, 6), "F", 24, page=6))
    go(pg, enc(answers(60, 7), "F", 24, page=4)); s = st(pg)
    check("D2 conflicting same-demographics link -> ask", s["view"] == "intro" and s["card"] and s["local"]["n"] == 100, s)
    ctx.close()

    # O1: refresh in the same tab after answering keeps working (marker)
    ctx = mk(); pg = fresh(ctx)
    pg.goto(BASE, wait_until="networkidle")
    pg.select_option("#sex", "M"); pg.fill("#age", "33"); pg.click("#startBtn")
    pg.wait_for_timeout(500)
    for q in range(1, 6): pg.tap('.qrow[data-qid="%d"] .opt[data-v="%d"]' % (q, 1 + q % 5))
    pg.wait_for_timeout(2300)
    pg.evaluate("dispatchEvent(new Event('pagehide'))")
    h = pg.evaluate("location.hash"); pg.reload(wait_until="networkidle"); s = st(pg)
    check("O1 refresh -> silent restore", s["view"] == "test" and not s["card"] and s["local"]["n"] == 5 and "已自动恢复" in s["feedback"] and not s["toast"], s)
    # O1b: same link pasted into a new tab with only 5 answers (overlap < 8 but identical) -> own
    pg2 = ctx.new_page(); pg2.goto(BASE + h, wait_until="networkidle"); s = st(pg2)
    check("O1b identical link in new tab -> own", s["view"] == "test" and not s["card"], s)
    ctx.close()

    # O3: own finished result link opened in a new tab -> own, no banner
    ctx = mk(); mine = answers(300, 8); pg = fresh(ctx, local_obj(mine, "N", 45, done=True, page=19))
    go(pg, enc(mine, "N", 45, page=19, done=True)); s = st(pg)
    check("O3 own result link -> own result", s["view"] == "result" and not s["banner"] and "已完成" in s["status"], s)
    ctx.close()

    # O5: cross-device own finished link (no local) -> view-only, then save to this device
    ctx = mk(); pg = fresh(ctx); dialogs.clear()
    go(pg, FRIEND_DONE); s = st(pg)
    check("O5 no local -> view-only with adopt offer", s["banner"] and s["mineBtn"] == "我也来测一测" and s["local"] is None, s)
    pg.click("#viewAdoptBtn"); s = st(pg)
    check("O5 adopt -> saved, no confirm needed", s["local"] and s["local"]["done"] and not s["banner"] and not dialogs, (s, dialogs))
    go(pg); s = st(pg)
    check("O5 bare reload -> own result", s["view"] == "result" and not s["banner"], s)
    ctx.close()

    # F: truncated link
    ctx = mk(); pg = fresh(ctx, local_obj(answers(40, 9), "F", 30, page=2))
    go(pg, FRIEND_60[:90]); pg.wait_for_timeout(300); s = st(pg)
    check("F truncated link -> notice + own progress", "不完整" in s["toast"] and s["view"] == "test" and s["local"]["n"] == 40, s)
    ctx.close()

    # H: restart does not wipe; starting new asks first
    ctx = mk(); mine = answers(300, 10); pg = fresh(ctx, local_obj(mine, "M", 50, done=True, page=19)); dialogs.clear()
    go(pg); pg.click("#restartBtn"); s = st(pg)
    check("H restart -> intro with result card, store intact", s["view"] == "intro" and s["card"] and s["local"]["done"], s)
    pg.select_option("#sex", "F"); pg.fill("#age", "22"); pg.click("#startBtn"); s = st(pg)
    check("H start new -> confirm then replaced", len(dialogs) == 1 and s["view"] == "test" and s["local"]["sex"] == "F" and s["local"]["n"] == 0, (dialogs, s))
    ctx.close()

    # G: two tabs -- a second tab opening, or adding answers, never pauses; a real conflict does
    LA = "q => JSON.parse(localStorage.getItem('%s')).answers[q]" % KEY
    ctx = mk(); pg = fresh(ctx, local_obj(answers(40, 11), "F", 26, page=2))
    go(pg); pgB = ctx.new_page(); pgB.goto(BASE, wait_until="networkidle"); pgB.wait_for_selector("#test:not(.hide)")
    s = st(pg); check("G opening a second tab does not pause the first", not s["stale"], s)
    pgB.wait_for_timeout(500)
    for q in range(41, 46): pgB.click('.qrow[data-qid="%d"] .opt[data-v="3"]' % q)
    s = st(pg); check("G additions merge silently into the first tab", not s["stale"] and s["local"]["n"] == 45 and pg.evaluate("document.querySelectorAll('#qlist .qrow.ok').length") == 15, s)
    pgB.click('.qrow[data-qid="41"] .opt[data-v="5"]')
    s = st(pg); check("G conflicting change pauses with two choices", s["stale"] and "用那边的" in pg.inner_text("#staleLoadBtn"), s)
    pg.click('.qrow[data-qid="42"] .opt[data-v="1"]'); pg.wait_for_timeout(200)
    check("G paused tab does not overwrite", pg.evaluate(LA, 42) == 3 and pg.evaluate(LA, 41) == 5)
    pg.click("#staleKeepBtn"); pg.wait_for_timeout(200)
    check("G keep this tab -> its answers saved", pg.evaluate(LA, 42) == 1 and pg.evaluate(LA, 41) == 3 and not st(pg)["stale"])
    ctx.close()
    b.close()
finally:
    srv.terminate()

ok = sum(1 for r in results if r[1])
for name, passed, detail in results:
    print(("PASS " if passed else "FAIL ") + name + ("" if passed else "\n     " + json.dumps(detail, ensure_ascii=False)[:600]))
print("\n%d/%d passed; page errors: %s" % (ok, len(results), errors[:5]))
